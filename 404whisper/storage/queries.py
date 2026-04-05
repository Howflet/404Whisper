"""
storage/queries.py — All database CRUD operations.

Every function here takes an open sqlite3.Connection as its first argument.
This design keeps the functions stateless and easy to test: the test fixture
just passes an in-memory connection, and production code passes the real file.

Naming conventions (match data contract § Naming Conventions):
  - Python parameter names: snake_case   (session_id, display_name)
  - Database column names:  snake_case   (session_id, display_name)
  - Vibe / enum values:     SCREAMING_SNAKE_CASE (CAMPFIRE, 404, etc.)

Error handling philosophy:
  - Let sqlite3.IntegrityError bubble up to callers.
    UNIQUE violations, CHECK constraint failures, and FK errors are all
    IntegrityErrors — the API layer translates them into HTTP 409/400 responses.
  - Do NOT catch and swallow database exceptions here.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convert a sqlite3.Row to a plain dict, or return None if no row."""
    return dict(row) if row is not None else None


def _rows_to_list(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """Convert a list of sqlite3.Row objects to a list of plain dicts."""
    return [dict(r) for r in rows]


def _build_update(table: str, pk_col: str, allowed: set[str], fields: dict) -> tuple[str, list]:
    """
    Build a parameterised UPDATE statement from a dict of fields to change.

    Only columns that appear in `allowed` are written — this prevents SQL
    injection from unexpected keyword arguments.

    Returns:
        (sql_string, [values..., pk_value])

    Raises:
        ValueError: if `fields` contains no recognised column names.

    Example:
        sql, params = _build_update(
            "contacts", "session_id",
            {"display_name", "accepted"},
            {"display_name": "Bob", "accepted": 1},
        )
        # sql   → "UPDATE contacts SET display_name = ?, updated_at = datetime('now') WHERE session_id = ?"
        # params → ["Bob", 1, <pk_value>]   ← pk_value added by caller
    """
    # Filter to only the allowed columns the caller actually provided.
    to_set = {k: v for k, v in fields.items() if k in allowed}
    if not to_set:
        raise ValueError(
            f"No recognised columns to update on '{table}'. "
            f"Allowed: {allowed}. Got: {set(fields)}"
        )
    # Build "col = ?" fragments.
    set_clauses = [f"{col} = ?" for col in to_set]
    values      = list(to_set.values())

    # Always refresh updated_at when we touch a row that has the column.
    _tables_with_updated_at = {"identities", "contacts", "groups", "attachments"}
    if table in _tables_with_updated_at:
        set_clauses.append("updated_at = datetime('now')")

    sql = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {pk_col} = ?"
    return sql, values


# ===========================================================================
# Identities
# ===========================================================================

def create_identity(
    db: sqlite3.Connection,
    *,
    session_id: str,
    display_name: Optional[str] = None,
) -> int:
    """
    Insert a new identity row for the local user.

    There can only be one identity per Session ID (UNIQUE constraint).
    Both created_at and updated_at are set to the current UTC time.

    Returns:
        The integer primary key (id) of the newly created row.

    Raises:
        sqlite3.IntegrityError: if session_id already exists.
    """
    cursor = db.execute(
        """
        INSERT INTO identities (session_id, display_name, created_at, updated_at)
        VALUES (?, ?, datetime('now'), datetime('now'))
        """,
        (session_id, display_name),
    )
    db.commit()
    return cursor.lastrowid


def get_identity(db: sqlite3.Connection, *, session_id: str) -> Optional[dict]:
    """
    Fetch the identity row for a given session_id, or None if not found.
    """
    row = db.execute(
        "SELECT * FROM identities WHERE session_id = ?", (session_id,)
    ).fetchone()
    return _row_to_dict(row)


def update_identity(
    db: sqlite3.Connection,
    *,
    session_id: str,
    **fields,
) -> None:
    """
    Update one or more columns on an identity row.

    Supported keyword arguments:
        display_name (str | None) — the user's chosen display name
        personal_vibe (str | None) — must be an AESTHETIC vibe or None

    The DB CHECK constraint on personal_vibe will raise IntegrityError if an
    invalid value (e.g. a behavioral vibe or a typo) is passed.

    Example:
        update_identity(db, session_id="05abc…", display_name="Alice")
        update_identity(db, session_id="05abc…", personal_vibe="CAMPFIRE")
    """
    _ALLOWED = {"display_name", "personal_vibe"}
    sql, values = _build_update("identities", "session_id", _ALLOWED, fields)
    db.execute(sql, [*values, session_id])
    db.commit()


# ===========================================================================
# Contacts
# ===========================================================================

def create_contact(
    db: sqlite3.Connection,
    *,
    session_id: str,
    display_name: Optional[str] = None,
    accepted: int = 0,
) -> int:
    """
    Add a new contact.

    accepted=0 → pending request (default)
    accepted=1 → already accepted / trusted contact

    Returns:
        The integer primary key (id) of the new row.

    Raises:
        sqlite3.IntegrityError: if session_id already exists.
    """
    cursor = db.execute(
        """
        INSERT INTO contacts (session_id, display_name, accepted, created_at, updated_at)
        VALUES (?, ?, ?, datetime('now'), datetime('now'))
        """,
        (session_id, display_name, accepted),
    )
    db.commit()
    return cursor.lastrowid


def update_contact(
    db: sqlite3.Connection,
    *,
    session_id: str,
    **fields,
) -> None:
    """
    Update a contact row.

    Supported keyword arguments:
        display_name (str | None) — override the contact's display name
        accepted (int)            — 0 = pending, 1 = accepted

    Example:
        update_contact(db, session_id="05bbb…", accepted=1)
        update_contact(db, session_id="05bbb…", display_name="Robert")
    """
    _ALLOWED = {"display_name", "accepted"}
    sql, values = _build_update("contacts", "session_id", _ALLOWED, fields)
    db.execute(sql, [*values, session_id])
    db.commit()


def delete_contact(db: sqlite3.Connection, *, session_id: str) -> None:
    """
    Hard-delete a contact by session_id.

    Data-contract note: deleting a contact does NOT cascade to conversations —
    the conversation history is preserved (assumption A-7).
    """
    db.execute("DELETE FROM contacts WHERE session_id = ?", (session_id,))
    db.commit()


def list_contacts(
    db: sqlite3.Connection,
    *,
    accepted: Optional[bool] = None,
) -> list[dict]:
    """
    Return all contacts, optionally filtered by acceptance status.

    Args:
        accepted: If None, return all contacts.
                  If True,  return only accepted contacts.
                  If False, return only pending contacts.

    Returns:
        List of contact dicts ordered by created_at DESC.
    """
    if accepted is None:
        rows = db.execute(
            "SELECT * FROM contacts ORDER BY created_at DESC"
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM contacts WHERE accepted = ? ORDER BY created_at DESC",
            (1 if accepted else 0,),
        ).fetchall()
    return _rows_to_list(rows)


# ===========================================================================
# Conversations
# ===========================================================================

def create_dm_conversation(
    db: sqlite3.Connection,
    *,
    contact_session_id: str,
) -> int:
    """
    Create a 1-to-1 (DM) conversation with a contact.

    The conversation type is always 'DM'; group_id is always NULL.
    accepted defaults to 0 (not yet accepted — it's a pending request).

    Returns:
        The integer primary key (id) of the new conversation.
    """
    cursor = db.execute(
        """
        INSERT INTO conversations (type, contact_session_id, created_at)
        VALUES ('DM', ?, datetime('now'))
        """,
        (contact_session_id,),
    )
    db.commit()
    return cursor.lastrowid


def create_group_conversation(
    db: sqlite3.Connection,
    *,
    group_id: int,
) -> int:
    """
    Create a GROUP conversation linked to an existing group row.

    Returns:
        The integer primary key (id) of the new conversation.
    """
    cursor = db.execute(
        """
        INSERT INTO conversations (type, group_id, created_at)
        VALUES ('GROUP', ?, datetime('now'))
        """,
        (group_id,),
    )
    db.commit()
    return cursor.lastrowid


def get_conversation(db: sqlite3.Connection, *, conversation_id: int) -> Optional[dict]:
    """Fetch a single conversation by id, or None if not found."""
    row = db.execute(
        "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
    ).fetchone()
    return _row_to_dict(row)


def list_conversations(db: sqlite3.Connection) -> list[dict]:
    """
    Return all conversations ordered by most-recently-active first.

    Conversations with no messages yet (last_message_at IS NULL) sort last.
    """
    rows = db.execute(
        "SELECT * FROM conversations ORDER BY last_message_at DESC NULLS LAST"
    ).fetchall()
    return _rows_to_list(rows)


def update_conversation(
    db: sqlite3.Connection,
    *,
    conversation_id: int,
    **fields,
) -> None:
    """
    Update a conversation row.

    Supported keyword arguments:
        last_message_at        (str)       — ISO-8601 timestamp of the last message
        unread_count           (int)       — number of unread messages
        group_vibe             (str|None)  — current group vibe
        personal_vibe_override (str|None)  — user's local vibe override
        vibe_changed_at        (str|None)  — when vibe was last changed
        vibe_cooldown_until    (str|None)  — earliest time vibe can change again
        accepted               (int)       — 0 = pending, 1 = accepted
    """
    _ALLOWED = {
        "last_message_at", "unread_count",
        "group_vibe", "personal_vibe_override",
        "vibe_changed_at", "vibe_cooldown_until",
        "accepted",
    }
    sql, values = _build_update("conversations", "id", _ALLOWED, fields)
    db.execute(sql, [*values, conversation_id])
    db.commit()


# ===========================================================================
# Groups
# ===========================================================================

def create_group(
    db: sqlite3.Connection,
    *,
    group_session_id: str,
    name: str,
    created_by_session_id: str,
    vibe: Optional[str] = None,
) -> int:
    """
    Create a new group.

    Args:
        group_session_id:      66-char hex Session ID generated for the group.
        name:                  Human-readable group name (1–64 chars).
        created_by_session_id: Session ID of the user creating the group.
        vibe:                  Optional initial vibe (any vibe value).

    Returns:
        The integer primary key (id) of the new group row.

    Raises:
        sqlite3.IntegrityError: if group_session_id already exists.
    """
    cursor = db.execute(
        """
        INSERT INTO groups
            (group_session_id, name, created_by_session_id, vibe, created_at, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (group_session_id, name, created_by_session_id, vibe),
    )
    db.commit()
    return cursor.lastrowid


def get_group(db: sqlite3.Connection, *, group_id: int) -> Optional[dict]:
    """Fetch a single group by primary key, or None if not found."""
    row = db.execute(
        "SELECT * FROM groups WHERE id = ?", (group_id,)
    ).fetchone()
    return _row_to_dict(row)


def list_groups(db: sqlite3.Connection) -> list[dict]:
    """Return all groups ordered by most recently created first."""
    rows = db.execute(
        "SELECT * FROM groups ORDER BY created_at DESC"
    ).fetchall()
    return _rows_to_list(rows)


def update_group(
    db: sqlite3.Connection,
    *,
    group_id: int,
    **fields,
) -> None:
    """
    Update a group row.

    Supported keyword arguments:
        name                (str)      — new group name
        vibe                (str|None) — new vibe (any valid vibe or None to clear)
        vibe_changed_at     (str|None) — ISO-8601 timestamp of the vibe change
        vibe_cooldown_until (str|None) — ISO-8601 timestamp until next vibe change

    The DB CHECK constraint on `vibe` will raise IntegrityError for unknown values.
    """
    _ALLOWED = {"name", "vibe", "vibe_changed_at", "vibe_cooldown_until"}
    sql, values = _build_update("groups", "id", _ALLOWED, fields)
    db.execute(sql, [*values, group_id])
    db.commit()


# ===========================================================================
# Group members
# ===========================================================================

def add_group_member(
    db: sqlite3.Connection,
    *,
    group_id: int,
    session_id: str,
    is_admin: bool = False,
) -> int:
    """
    Add a member to a group.

    Args:
        group_id:   Primary key of the target group.
        session_id: Session ID of the user to add.
        is_admin:   True if the user is an admin; False for regular member.

    Returns:
        The integer primary key (id) of the new group_members row.

    Raises:
        sqlite3.IntegrityError: if (group_id, session_id) already exists
                                or if group_id references a nonexistent group.
    """
    cursor = db.execute(
        """
        INSERT INTO group_members (group_id, session_id, is_admin, joined_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        (group_id, session_id, 1 if is_admin else 0),
    )
    db.commit()
    return cursor.lastrowid


def remove_group_member(
    db: sqlite3.Connection,
    *,
    group_id: int,
    session_id: str,
) -> None:
    """Remove a member from a group.  No-op if the member doesn't exist."""
    db.execute(
        "DELETE FROM group_members WHERE group_id = ? AND session_id = ?",
        (group_id, session_id),
    )
    db.commit()


def list_group_members(
    db: sqlite3.Connection,
    *,
    group_id: int,
) -> list[dict]:
    """
    Return all members of a group.

    Returns:
        List of dicts with keys: id, group_id, session_id, is_admin, joined_at.
        Ordered by joined_at ASC (earliest joiner first).
    """
    rows = db.execute(
        "SELECT * FROM group_members WHERE group_id = ? ORDER BY joined_at ASC",
        (group_id,),
    ).fetchall()
    return _rows_to_list(rows)


# ===========================================================================
# Messages
# ===========================================================================

# Columns accepted as optional keyword arguments in create_message.
# This whitelist prevents unexpected column names from being passed through.
_MESSAGE_OPTIONAL_COLS = {
    "received_at",
    "expires_at",
    "deliver_after",
    "is_anonymous",
    "is_spotlight_pinned",
    "is_pinned",
    "chorus_group_id",
    "attachment_id",
    "group_event_type",
    "active_vibe_at_send",
}


def create_message(
    db: sqlite3.Connection,
    *,
    conversation_id: int,
    sender_session_id: Optional[str] = None,
    body: Optional[str] = None,
    type: str = "TEXT",           # noqa: A002 — shadows builtin, matches data contract
    sent_at: str,
    **extra,
) -> int:
    """
    Insert a new message into a conversation.

    Required args:
        conversation_id:   FK to conversations.id (must exist).
        sent_at:           ISO-8601 timestamp string.
        type:              One of TEXT | ATTACHMENT | GROUP_EVENT | SYSTEM.

    Optional args (passed as **extra, whitelisted):
        sender_session_id  — None for CONFESSIONAL anonymous messages.
        body               — None for ATTACHMENT or GROUP_EVENT messages.
        received_at        — when the message was received from the network.
        expires_at         — 404 vibe: auto-delete time (sent_at + 24 h).
        deliver_after      — SLOW_BURN vibe: reveal time (sent_at + 60 s).
        is_anonymous       — 1 for CONFESSIONAL hidden-sender messages.
        is_spotlight_pinned — 1 when pinned by SPOTLIGHT vibe.
        is_pinned          — 1 when pinned as 404 escape hatch.
        chorus_group_id    — UUID grouping CHORUS-vibe messages.
        attachment_id      — FK to attachments.id.
        group_event_type   — MEMBER_JOINED | MEMBER_LEFT | VIBE_CHANGED | GROUP_RENAMED.
        active_vibe_at_send — snapshot of the group's vibe at send time.

    Returns:
        The integer primary key (id) of the new message row.

    Raises:
        sqlite3.IntegrityError: for unknown type values or missing conversation.
    """
    # Pull optional columns that were actually provided.
    optional = {k: v for k, v in extra.items() if k in _MESSAGE_OPTIONAL_COLS}

    # Build dynamic column list.
    base_cols    = ["conversation_id", "sender_session_id", "body", "type", "sent_at"]
    base_vals    = [conversation_id, sender_session_id, body, type, sent_at]
    extra_cols   = list(optional.keys())
    extra_vals   = list(optional.values())

    all_cols = base_cols + extra_cols
    placeholders = ", ".join("?" * len(all_cols))
    col_list     = ", ".join(all_cols)

    cursor = db.execute(
        f"INSERT INTO messages ({col_list}) VALUES ({placeholders})",
        base_vals + extra_vals,
    )
    db.commit()
    return cursor.lastrowid


def list_messages(
    db: sqlite3.Connection,
    *,
    conversation_id: int,
    before: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """
    Return messages in a conversation, newest first, with cursor-based pagination.

    Args:
        conversation_id: Which conversation to query.
        before:          ISO-8601 timestamp cursor — only return messages
                         with sent_at STRICTLY BEFORE this value.
                         Pass None (default) to start from the very latest.
        limit:           Maximum number of rows to return (default 50, max 100).

    Returns:
        List of message dicts ordered by sent_at DESC (newest first).

    Usage example (fetching the next page):
        # First page — no cursor
        page1 = list_messages(db, conversation_id=1, limit=20)
        # Next page — use sent_at of the oldest message from page1
        page2 = list_messages(db, conversation_id=1,
                               before=page1[-1]["sent_at"], limit=20)
    """
    if before is None:
        rows = db.execute(
            """
            SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY sent_at DESC
            LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT * FROM messages
            WHERE conversation_id = ? AND sent_at < ?
            ORDER BY sent_at DESC
            LIMIT ?
            """,
            (conversation_id, before, limit),
        ).fetchall()
    return _rows_to_list(rows)


def pin_message(db: sqlite3.Connection, *, message_id: int) -> None:
    """Set is_pinned = 1 on a message (404-vibe escape hatch)."""
    db.execute("UPDATE messages SET is_pinned = 1 WHERE id = ?", (message_id,))
    db.commit()


def unpin_message(db: sqlite3.Connection, *, message_id: int) -> None:
    """Clear is_pinned = 0 on a message."""
    db.execute("UPDATE messages SET is_pinned = 0 WHERE id = ?", (message_id,))
    db.commit()


# ===========================================================================
# Attachments
# ===========================================================================

# Columns accepted as optional keyword arguments in create_attachment.
_ATTACHMENT_OPTIONAL_COLS = {
    "message_id",
    "upload_url",
    "encryption_key",
    "hmac_key",
    "local_cache_path",
}


def create_attachment(
    db: sqlite3.Connection,
    *,
    file_name: str,
    file_size: int,
    mime_type: str,
    status: str = "PENDING",
    **extra,
) -> int:
    """
    Insert a new attachment row.

    The row is created before the message exists (during upload), so
    message_id is optional and defaults to NULL.

    Required args:
        file_name: Original filename (e.g. "photo.jpg").
        file_size: Size in bytes — must be > 0.
        mime_type: MIME type string (e.g. "image/jpeg").

    Optional args (passed as **extra, whitelisted):
        message_id      — NULL until the message row is created.
        upload_url      — Session file server URL (set after upload).
        encryption_key  — Raw bytes (BLOB) for AES-256-CBC decryption.
        hmac_key        — Raw bytes (BLOB) for HMAC-SHA-256 verification.
        local_cache_path — Path to the cached decrypted file on disk.

    Returns:
        The integer primary key (id) of the new attachment row.

    Raises:
        sqlite3.IntegrityError: if file_size ≤ 0 or status is invalid.
    """
    optional = {k: v for k, v in extra.items() if k in _ATTACHMENT_OPTIONAL_COLS}

    base_cols = ["file_name", "file_size", "mime_type", "status", "created_at", "updated_at"]
    base_vals = [file_name, file_size, mime_type, status, "datetime('now')", "datetime('now')"]
    extra_cols = list(optional.keys())
    extra_vals = list(optional.values())

    # Use datetime('now') as a SQL expression, not a string — build it properly.
    all_cols = ["file_name", "file_size", "mime_type", "status"] + extra_cols + ["created_at", "updated_at"]
    placeholders = ", ".join(["?"] * (4 + len(extra_cols))) + ", datetime('now'), datetime('now')"
    col_list = ", ".join(all_cols)

    cursor = db.execute(
        f"INSERT INTO attachments ({col_list}) VALUES ({placeholders})",
        [file_name, file_size, mime_type, status] + extra_vals,
    )
    db.commit()
    return cursor.lastrowid


def update_attachment(
    db: sqlite3.Connection,
    *,
    attachment_id: int,
    **fields,
) -> None:
    """
    Update an attachment row.

    Supported keyword arguments:
        status           — PENDING | UPLOADING | UPLOADED | DOWNLOADING | DOWNLOADED | FAILED
        upload_url       — URL returned by the Session file server after upload.
        message_id       — Link to the message row once it has been created.
        local_cache_path — Path to the cached file on disk (set after download).

    The DB CHECK constraint on `status` will raise IntegrityError for unknown values.
    """
    _ALLOWED = {"status", "upload_url", "message_id", "local_cache_path"}
    sql, values = _build_update("attachments", "id", _ALLOWED, fields)
    db.execute(sql, [*values, attachment_id])
    db.commit()
