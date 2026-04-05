"""
storage/queries.py — All database CRUD operations for 404Whisper.

What is this file?
------------------
Think of this file as the "clerk" for our app's database. Every time the app
needs to read or write data — create a user, list messages, delete a contact —
it calls a function from this file. No SQL is written anywhere else.

How it works (plain-English version):
  1. The database stores everything in tables (like Excel sheets): identities,
     contacts, groups, messages, attachments, conversations.
  2. Every function below takes an open ``db`` connection as its first argument.
     Think of ``db`` as an open door to the database.
  3. Functions return plain Python dicts (or lists of dicts) so callers don't
     need to know anything about SQLite.

CRUD — what it means:
  Create → INSERT  (add a new row)
  Read   → SELECT  (fetch one or many rows)
  Update → UPDATE  (change columns on an existing row)
  Delete → DELETE  (remove a row)

──────────────────────────────────────────────────────────────────────────────
Function index  (group → function name → brief purpose)
──────────────────────────────────────────────────────────────────────────────
IDENTITIES (the local user — one row ever)
  create_identity          Insert a new identity (session_id + optional name).
  get_identity             Fetch identity by session_id → dict or None.
  update_identity          Change display_name or personal_vibe.

CONTACTS (remote users the local user knows about)
  create_contact           Add a new contact (accepted=0 by default = pending).
  get_contact              Fetch one contact by session_id → dict or None.
  update_contact           Rename a contact or mark them accepted.
  delete_contact           Hard-delete a contact (conversation history kept).
  list_contacts            List all contacts, optionally filtered by accepted.
  upsert_contact           Safe insert-or-update (used by the messaging layer).

CONVERSATIONS (a chat thread — either 1-to-1 DM or a GROUP)
  create_dm_conversation   Start a 1-to-1 chat with a contact.
  create_group_conversation Start a group chat thread.
  get_conversation         Fetch one conversation by id → dict or None.
  list_conversations       All conversations, most-recently-active first.
  update_conversation      Update vibe, unread count, last_message_at, etc.
  delete_conversation      Hard-delete a conversation + all its messages.
  get_conversation_by_contact Find a DM thread by the contact's session_id.
  get_conversation_by_group   Find a group thread by the group's integer PK.
  update_conversation_unread  Set unread count directly (e.g. mark all read).
  increment_conversation_unread Atomically add 1 to unread count (no race).

GROUPS (a chat room with its own network identity)
  create_group             Create a new group row.
  get_group                Fetch one group by integer id → dict or None.
  list_groups              All groups, newest first.
  update_group             Rename group or change/clear its vibe.
  delete_group             Hard-delete group + members; conversation survives.
  get_group_by_session_id  Find a group by its 66-char network hex address.

GROUP MEMBERS (who is in which group)
  add_group_member         Add a user to a group (optionally as admin).
  remove_group_member      Remove a user from a group (no-op if not there).
  list_group_members       All members of a group, oldest joiner first.

MESSAGES (a single message in a conversation)
  create_message           Insert a message with any vibe-specific fields.
  get_message              Fetch one message by id → dict or None.
  list_messages            Messages in a conversation, newest first + cursor.
  save_message             Atomic: insert message + bump conversation timestamp.
  pin_message              Set is_pinned=1 (404-vibe escape hatch).
  unpin_message            Clear is_pinned=0.
  delete_message           Hard-delete a single message.
  list_expired_messages    Fetch 404-vibe messages past their 24-h TTL.
  purge_expired_messages   Batch-delete all expired messages → returns count.

ATTACHMENTS (a file attached to a message)
  create_attachment        Insert attachment row before the message exists.
  get_attachment           Fetch one attachment by id → dict or None.
  update_attachment        Change status, upload_url, message_id, cache path.
  delete_attachment        Hard-delete an attachment row.
──────────────────────────────────────────────────────────────────────────────

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
    type: str = "TEXT",  # pylint: disable=redefined-builtin  # shadows builtin, matches data contract
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

    extra_cols = list(optional.keys())
    extra_vals = list(optional.values())

    # Build the full column list: required cols + optional cols + timestamp cols.
    # datetime('now') is a SQL expression, not a string — inject it directly, not as a bind param.
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


# ===========================================================================
# Extended single-row lookups
# ===========================================================================

def get_contact(db: sqlite3.Connection, *, session_id: str) -> Optional[dict]:
    """
    Fetch a single contact by session_id, or None if not found.

    Used by route handlers to check existence before updates/deletes.
    """
    row = db.execute(
        "SELECT * FROM contacts WHERE session_id = ?", (session_id,)
    ).fetchone()
    return _row_to_dict(row)


def get_message(db: sqlite3.Connection, *, message_id: int) -> Optional[dict]:
    """
    Fetch a single message by primary key, or None if not found.

    Used by the messaging layer to retrieve a message after inserting it,
    and by pin/unpin routes to confirm the message exists.
    """
    row = db.execute(
        "SELECT * FROM messages WHERE id = ?", (message_id,)
    ).fetchone()
    return _row_to_dict(row)


def get_attachment(db: sqlite3.Connection, *, attachment_id: int) -> Optional[dict]:
    """
    Fetch a single attachment row by primary key, or None if not found.

    Used by attachment routes to look up metadata before serving a download.
    Note: encryption_key and hmac_key are raw bytes — never include them
    in API responses.
    """
    row = db.execute(
        "SELECT * FROM attachments WHERE id = ?", (attachment_id,)
    ).fetchone()
    return _row_to_dict(row)


# ===========================================================================
# Upsert — for the messaging layer (network-received contacts)
# ===========================================================================

def upsert_contact(
    db: sqlite3.Connection,
    *,
    session_id: str,
    display_name: Optional[str] = None,
    accepted: int = 0,
) -> None:
    """
    Insert a contact row, or update it if session_id already exists.

    Used by the messaging layer when a message arrives from an unknown sender —
    the sender is automatically added as a pending contact (accepted=0).

    Unlike create_contact() which raises IntegrityError on duplicates,
    this function is safe to call multiple times for the same session_id:
      - On conflict: only updates display_name if the new value is non-NULL,
        preserving the existing name when None is passed.
      - accepted is NOT overwritten on conflict — a user who already accepted
        a contact keeps that status even if the network re-delivers the sender.

    Args:
        session_id:   66-char hex Session ID of the remote user.
        display_name: Optional display name from the sender's profile.
        accepted:     0 (pending) for network-originated contacts; 1 for local adds.
    """
    db.execute(
        """
        INSERT INTO contacts (session_id, display_name, accepted, created_at, updated_at)
        VALUES (?, ?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(session_id) DO UPDATE SET
            display_name = COALESCE(excluded.display_name, contacts.display_name),
            updated_at   = datetime('now')
        """,
        (session_id, display_name, accepted),
    )
    db.commit()


# ===========================================================================
# save_message — atomic message + conversation-stats update
# ===========================================================================

def save_message(
    db: sqlite3.Connection,
    *,
    conversation_id: int,
    sender_session_id: Optional[str] = None,
    body: Optional[str] = None,
    type: str = "TEXT",           # noqa: A002
    sent_at: str,
    **extra,
) -> int:
    """
    Insert a message row and bump the conversation's last_message_at in one call.

    This is the preferred write path for both outgoing and incoming messages.
    It keeps the conversation list sorted correctly without a separate update call.

    Equivalent to calling create_message() followed by update_conversation()
    but in a single logical operation.

    Returns:
        The integer primary key (id) of the new message row.

    See create_message() for the full list of accepted **extra keyword arguments.
    """
    # Insert the message first.
    msg_id = create_message(
        db,
        conversation_id=conversation_id,
        sender_session_id=sender_session_id,
        body=body,
        type=type,
        sent_at=sent_at,
        **extra,
    )
    # Bump the conversation's last_message_at so it floats to the top of the list.
    update_conversation(db, conversation_id=conversation_id, last_message_at=sent_at)
    return msg_id


# ===========================================================================
# update_conversation_unread — dedicated unread count setter
# ===========================================================================

def update_conversation_unread(
    db: sqlite3.Connection,
    *,
    conversation_id: int,
    unread_count: int,
) -> None:
    """
    Set the unread message count on a conversation directly.

    Prefer this over update_conversation() when only the unread count is
    changing — it's faster and more explicit.

    The polling loop calls this after marking all received messages as read:
        update_conversation_unread(db, conversation_id=conv_id, unread_count=0)

    Args:
        conversation_id: Primary key of the conversation to update.
        unread_count:    New unread count (use 0 to mark all as read).
    """
    db.execute(
        "UPDATE conversations SET unread_count = ? WHERE id = ?",
        (unread_count, conversation_id),
    )
    db.commit()


# ===========================================================================
# delete_conversation — hard delete conversation + its messages
# ===========================================================================

def delete_conversation(db: sqlite3.Connection, *, conversation_id: int) -> None:
    """
    Hard-delete a conversation and all of its messages.

    Messages are deleted first because the messages.conversation_id FK has
    no ON DELETE CASCADE — SQLite with PRAGMA foreign_keys = ON will raise
    an IntegrityError if we try to delete the conversation first.

    Data-contract note: attachments linked to deleted messages are NOT
    automatically removed from the file server — the caller is responsible
    for cleaning up remote uploads if needed.
    """
    # Remove messages in this conversation first (no FK cascade).
    db.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    # Then remove the conversation itself.
    db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    db.commit()


# ===========================================================================
# delete_attachment — remove a single attachment row
# ===========================================================================

def delete_attachment(db: sqlite3.Connection, *, attachment_id: int) -> None:
    """
    Hard-delete an attachment row.

    Callers are responsible for removing the encrypted file from the
    Session file server before calling this, if it was successfully uploaded.
    """
    db.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
    db.commit()


# ===========================================================================
# Lookup helpers — find rows by alternate keys (used by messaging / groups)
# ===========================================================================

def get_group_by_session_id(
    db: sqlite3.Connection,
    *,
    group_session_id: str,
) -> Optional[dict]:
    """
    Fetch a group by its on-network Session ID (the 66-char hex string).

    Why this exists:
        Incoming network messages reference the group by its Session ID, not by
        the integer primary key that the DB assigns.  This lookup bridges the gap.

    Args:
        group_session_id: The 66-char hex string stored in groups.group_session_id.

    Returns:
        Group dict, or None if no such group exists locally.

    Example:
        group = get_group_by_session_id(db, group_session_id="05abc…")
        if group is None:
            # We received a message for an unknown group — ignore or request sync.
            pass
    """
    row = db.execute(
        "SELECT * FROM groups WHERE group_session_id = ?", (group_session_id,)
    ).fetchone()
    return _row_to_dict(row)


def get_conversation_by_contact(
    db: sqlite3.Connection,
    *,
    contact_session_id: str,
) -> Optional[dict]:
    """
    Find the DM conversation linked to a specific contact's Session ID.

    Why this exists:
        When the polling loop receives an incoming DM, it knows the sender's
        Session ID but not the conversation's integer ID.  This lookup finds
        the right conversation so the message can be written to the correct row.

    Args:
        contact_session_id: The sender's Session ID (66-char hex).

    Returns:
        Conversation dict, or None if no DM conversation exists for this contact.

    Example:
        conv = get_conversation_by_contact(db, contact_session_id="05bbb…")
        if conv is None:
            conv_id = create_dm_conversation(db, contact_session_id="05bbb…")
        else:
            conv_id = conv["id"]
    """
    row = db.execute(
        "SELECT * FROM conversations WHERE type = 'DM' AND contact_session_id = ?",
        (contact_session_id,),
    ).fetchone()
    return _row_to_dict(row)


def get_conversation_by_group(
    db: sqlite3.Connection,
    *,
    group_id: int,
) -> Optional[dict]:
    """
    Find the GROUP conversation linked to a specific group's primary key.

    Why this exists:
        The groups layer creates a group row and a companion conversation row.
        To write messages or update unread counts, callers need the conversation's
        integer ID — this function retrieves it from the group's PK.

    Args:
        group_id: The integer primary key of the group (groups.id).

    Returns:
        Conversation dict, or None if no conversation exists for this group.

    Example:
        conv = get_conversation_by_group(db, group_id=42)
        if conv:
            save_message(db, conversation_id=conv["id"], ...)
    """
    row = db.execute(
        "SELECT * FROM conversations WHERE type = 'GROUP' AND group_id = ?",
        (group_id,),
    ).fetchone()
    return _row_to_dict(row)


# ===========================================================================
# Delete helpers — explicit removals for groups and individual messages
# ===========================================================================

def delete_group(db: sqlite3.Connection, *, group_id: int) -> None:
    """
    Hard-delete a group and all of its members.

    The group_members table has ON DELETE CASCADE, so members are removed
    automatically when the group row is deleted.  No manual cleanup needed.

    Data-contract note: the companion conversation row is NOT deleted — the
    conversation history is preserved even after the group is gone (same
    principle as contact deletion, assumption A-7).

    Args:
        group_id: The integer primary key of the group to delete.

    Example:
        # Admin disbands a group
        delete_group(db, group_id=42)
    """
    db.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    db.commit()


def delete_message(db: sqlite3.Connection, *, message_id: int) -> None:
    """
    Hard-delete a single message by primary key.

    Used by:
      - The 404-vibe TTL purge job (purge_expired_messages calls this per row,
        or the batch version deletes them all at once).
      - Any future moderation / admin-delete flow.

    Callers are responsible for checking is_pinned before calling — this
    function will delete pinned messages if called directly.

    Args:
        message_id: The integer primary key of the message to delete.

    Example:
        expired = list_expired_messages(db, now_iso=now.isoformat())
        for msg in expired:
            delete_message(db, message_id=msg["id"])
    """
    db.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    db.commit()


# ===========================================================================
# Atomic counter — increment unread count without a read-modify-write cycle
# ===========================================================================

def increment_conversation_unread(
    db: sqlite3.Connection,
    *,
    conversation_id: int,
) -> None:
    """
    Atomically increment the unread message counter on a conversation by 1.

    Why this is better than update_conversation_unread():
        The polling loop could receive many messages in a burst.  If two coroutines
        both read `unread_count = 3`, both compute `4`, and then both write `4`,
        one increment is lost.  This SQL form (`count + 1`) lets the DB engine
        apply the increment atomically — no race condition.

    Args:
        conversation_id: Primary key of the conversation to increment.

    Example:
        # Called once per inbound message in the polling loop
        increment_conversation_unread(db, conversation_id=conv["id"])
    """
    db.execute(
        "UPDATE conversations SET unread_count = unread_count + 1 WHERE id = ?",
        (conversation_id,),
    )
    db.commit()


# ===========================================================================
# list_expired_messages — 404 vibe TTL cleanup helper
# ===========================================================================

def list_expired_messages(
    db: sqlite3.Connection,
    *,
    now_iso: str,
) -> list[dict]:
    """
    Return all messages that have passed their TTL and are eligible for deletion.

    A message is purgeable when ALL of these are true:
      1. expires_at is set (i.e. the message was sent under the 404 vibe).
      2. expires_at <= now (the 24-hour countdown has finished).
      3. is_pinned = 0 (the message was NOT saved via the pin escape hatch).

    The messaging layer's background purge job calls this to find rows to delete.

    Args:
        now_iso: Current UTC time as an ISO-8601 string.
                 SQLite compares TEXT timestamps lexicographically,
                 so ISO-8601 format is required.

    Returns:
        List of message dicts ready for deletion.

    Example:
        from datetime import datetime, timezone
        expired = list_expired_messages(db, now_iso=datetime.now(timezone.utc).isoformat())
        for msg in expired:
            db.execute("DELETE FROM messages WHERE id = ?", (msg["id"],))
        db.commit()
    """
    rows = db.execute(
        """
        SELECT * FROM messages
        WHERE expires_at IS NOT NULL
          AND expires_at <= ?
          AND is_pinned  = 0
        ORDER BY expires_at ASC
        """,
        (now_iso,),
    ).fetchall()
    return _rows_to_list(rows)


# ===========================================================================
# purge_expired_messages — batch TTL purge in a single SQL statement
# ===========================================================================

def purge_expired_messages(
    db: sqlite3.Connection,
    *,
    now_iso: str,
) -> int:
    """
    Delete ALL expired, unpinned 404-vibe messages in one SQL statement.

    Why this exists alongside list_expired_messages():
        list_expired_messages() returns rows so the caller can inspect or log
        them before deletion.  purge_expired_messages() is the fast path used
        by the scheduled background job when logging is not needed.

    A message is deleted when ALL of the following are true:
      1. expires_at is set (the message was sent under the 404 vibe).
      2. expires_at <= now (the 24-hour countdown has finished).
      3. is_pinned = 0 (the admin has NOT used the escape hatch).

    Args:
        now_iso: Current UTC time as an ISO-8601 string.

    Returns:
        The number of rows deleted (0 if nothing was expired).

    Example:
        from datetime import datetime, timezone
        deleted = purge_expired_messages(
            db, now_iso=datetime.now(timezone.utc).isoformat()
        )
        print(f"Purged {deleted} expired message(s).")
    """
    cursor = db.execute(
        """
        DELETE FROM messages
        WHERE expires_at IS NOT NULL
          AND expires_at <= ?
          AND is_pinned  = 0
        """,
        (now_iso,),
    )
    db.commit()
    # rowcount tells us how many rows the DELETE actually removed.
    return cursor.rowcount
