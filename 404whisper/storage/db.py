"""
storage/db.py — Database schema definition and startup helpers.

What this file does
-------------------
This file is the *single source of truth* for the database structure.
It defines all 7 tables (as SQL) and provides two helper functions:

  - ``init_schema(conn)`` — run all CREATE TABLE statements on any connection.
    Used both by production startup and by tests to spin up a fresh DB.

  - ``get_db()`` — a FastAPI "dependency": called once per HTTP request to hand
    the route handler an open, schema-initialized connection.  After the request
    finishes the connection is closed automatically.

Table overview (think of each as a spreadsheet tab):
┌──────────────────┬─────────────────────────────────────────────────────────┐
│ Table            │ What it stores                                          │
├──────────────────┼─────────────────────────────────────────────────────────┤
│ identities       │ The local user (one row per app install).               │
│ contacts         │ Remote users the local user knows about.                │
│ groups           │ Group chats (each has its own network Session ID).      │
│ group_members    │ Who is in which group + their admin status.             │
│ conversations    │ A chat thread — either DM (1-to-1) or GROUP.           │
│ messages         │ Individual messages inside a conversation.              │
│ attachments      │ Files attached to messages (encrypted, on file server). │
└──────────────────┴─────────────────────────────────────────────────────────┘

Why a separate module?
  Keeping schema SQL here makes it easy to run the exact same CREATE TABLE
  statements in both tests (plain sqlite3) and production (sqlcipher3),
  with zero duplication.
"""

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# All valid vibe values from the data contract.
# AESTHETIC vibes may be used as personal vibes (one person's mood).
# BEHAVIORAL and WILDCARD vibes are group-only (they change how messages work).
_AESTHETIC  = "'CAMPFIRE','NEON','LIBRARY','VOID','SUNRISE'"
_BEHAVIORAL = "'404','CONFESSIONAL','SLOW_BURN','CHORUS','SPOTLIGHT','ECHO'"
_WILDCARD   = "'SCRAMBLE'"
_ALL_VIBES  = f"{_AESTHETIC},{_BEHAVIORAL},{_WILDCARD}"

SCHEMA_SQL = f"""
-- ── identities ────────────────────────────────────────────────────────────
-- One row per app install.  Stores the local user's Session ID + display name.
-- The private key is NEVER stored in the DB — it lives in the encrypted keystore file.
-- personal_vibe is restricted to AESTHETIC vibes only (data contract § OQ-12).
CREATE TABLE IF NOT EXISTS identities (
    id           INTEGER PRIMARY KEY,
    session_id   TEXT    UNIQUE NOT NULL,
    display_name TEXT,
    personal_vibe TEXT   CHECK(personal_vibe IN ({_AESTHETIC})),
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

-- ── contacts ──────────────────────────────────────────────────────────────
-- Remote Session IDs the user knows about.
-- accepted=0 means a pending contact request; accepted=1 means confirmed.
-- Hard delete (no soft delete) — deleting a contact preserves the conversation history (A-7).
CREATE TABLE IF NOT EXISTS contacts (
    id           INTEGER PRIMARY KEY,
    session_id   TEXT    UNIQUE NOT NULL,
    display_name TEXT,
    accepted     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

-- ── groups ────────────────────────────────────────────────────────────────
-- A group chat.  group_session_id is the group's on-network identity (66-char hex).
-- vibe may be any vibe (aesthetic or behavioral/wildcard — all allowed for groups).
-- vibe changes are rate-limited by vibe_cooldown_until (5-minute window, OQ-1).
CREATE TABLE IF NOT EXISTS groups (
    id                   INTEGER PRIMARY KEY,
    group_session_id     TEXT    UNIQUE NOT NULL,
    name                 TEXT    NOT NULL,
    created_by_session_id TEXT   NOT NULL,
    vibe                 TEXT    CHECK(vibe IN ({_ALL_VIBES})),
    vibe_changed_at      TEXT,
    vibe_cooldown_until  TEXT,
    created_at           TEXT    NOT NULL,
    updated_at           TEXT    NOT NULL
);

-- ── group_members ─────────────────────────────────────────────────────────
-- Membership table — who is in which group, and whether they are an admin.
-- ON DELETE CASCADE ensures members are removed when the group is deleted.
-- UNIQUE(group_id, session_id) prevents duplicate membership rows.
CREATE TABLE IF NOT EXISTS group_members (
    id         INTEGER PRIMARY KEY,
    group_id   INTEGER NOT NULL,
    session_id TEXT    NOT NULL,
    is_admin   INTEGER NOT NULL DEFAULT 0,
    joined_at  TEXT    NOT NULL,
    UNIQUE(group_id, session_id),
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
);

-- ── messages ──────────────────────────────────────────────────────────────
-- A single message in a conversation.  sender_session_id is NULL when the
-- CONFESSIONAL vibe is active and the sender chose to stay anonymous (OQ-12).
-- Vibe-specific columns:
--   expires_at         → 404 vibe: message self-destructs 24 h after sent_at
--   deliver_after      → SLOW_BURN vibe: message hidden for 60 s after sent_at
--   is_anonymous       → CONFESSIONAL vibe: 1 when sender identity is hidden
--   is_spotlight_pinned → SPOTLIGHT vibe: 1 when pinned by spotlight
--   is_pinned          → 404 escape hatch: admin can pin to prevent expiry
--   chorus_group_id    → CHORUS vibe: UUID grouping messages in 30-s windows
--   active_vibe_at_send → snapshot of the group vibe at the moment of sending
--
-- NOTE: This table is declared before the conv table in the script.
-- SQLite allows FK forward-references at DDL time — the FK is only enforced
-- at DML time (INSERT/UPDATE/DELETE) when both tables exist.
CREATE TABLE IF NOT EXISTS messages (
    id                  INTEGER PRIMARY KEY,
    conversation_id     INTEGER NOT NULL,
    sender_session_id   TEXT,
    body                TEXT,
    type                TEXT    NOT NULL DEFAULT 'TEXT'
                                CHECK(type IN ('TEXT','ATTACHMENT','GROUP_EVENT','SYSTEM')),
    sent_at             TEXT    NOT NULL,
    received_at         TEXT,
    expires_at          TEXT,
    deliver_after       TEXT,
    is_anonymous        INTEGER NOT NULL DEFAULT 0,
    is_spotlight_pinned INTEGER NOT NULL DEFAULT 0,
    is_pinned           INTEGER NOT NULL DEFAULT 0,
    chorus_group_id     TEXT,
    attachment_id       INTEGER,
    group_event_type    TEXT    CHECK(group_event_type IN
                                     ('MEMBER_JOINED','MEMBER_LEFT','VIBE_CHANGED','GROUP_RENAMED')),
    active_vibe_at_send TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

-- ── conversations ─────────────────────────────────────────────────────────
-- A conversation is either a DM (1-to-1) or a GROUP chat.
-- The CHECK constraint enforces that exactly one of contact_session_id / group_id
-- is set, matching the conversation type.
-- accepted=0 means the remote party hasn't accepted yet (incoming request).
CREATE TABLE IF NOT EXISTS conversations (
    id                       INTEGER PRIMARY KEY,
    type                     TEXT    NOT NULL DEFAULT 'DM'
                                     CHECK(type IN ('DM', 'GROUP')),
    contact_session_id       TEXT,
    group_id                 INTEGER,
    last_message_at          TEXT,
    unread_count             INTEGER NOT NULL DEFAULT 0,
    group_vibe               TEXT    CHECK(group_vibe IN ({_ALL_VIBES})),
    personal_vibe_override   TEXT    CHECK(personal_vibe_override IN ({_ALL_VIBES})),
    vibe_changed_at          TEXT,
    vibe_cooldown_until      TEXT,
    accepted                 INTEGER NOT NULL DEFAULT 0,
    created_at               TEXT    NOT NULL,
    -- Exactly one side must be populated depending on type.
    CHECK (
        (type = 'DM'    AND contact_session_id IS NOT NULL AND group_id IS NULL) OR
        (type = 'GROUP' AND group_id IS NOT NULL            AND contact_session_id IS NULL)
    )
);

-- ── attachments ───────────────────────────────────────────────────────────
-- A file attached to a message.  Uploaded to the Session file server.
-- Keys are BLOB so they are stored as raw bytes, never as hex strings.
-- message_id is NULL during upload (the message row doesn't exist yet).
-- file_size CHECK(> 0) enforces the data contract's "no empty files" rule.
CREATE TABLE IF NOT EXISTS attachments (
    id               INTEGER PRIMARY KEY,
    message_id       INTEGER,
    file_name        TEXT    NOT NULL,
    file_size        INTEGER NOT NULL CHECK(file_size > 0),
    mime_type        TEXT    NOT NULL,
    upload_url       TEXT,
    encryption_key   BLOB,
    hmac_key         BLOB,
    local_cache_path TEXT,
    status           TEXT    NOT NULL
                     CHECK(status IN ('PENDING','UPLOADING','UPLOADED',
                                      'DOWNLOADING','DOWNLOADED','FAILED')),
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_db():
    """
    FastAPI dependency — yields an open DB connection for one request.

    In production, reads the DB path and passphrase from environment variables.
    In tests, this function is overridden via app.dependency_overrides so that
    every test gets an isolated in-memory connection (no state leaks).

    Usage in a route:
        from fastapi import Depends
        from importlib import import_module
        _db = import_module("404whisper.storage.db")

        @router.get("/foo")
        async def foo(db = Depends(_db.get_db)):
            return queries.list_contacts(db)
    """
    import os
    from .database import Database

    db_path   = os.environ.get("WHISPER_DB_PATH", "404whisper/data/whisper.db")
    # Passphrase is only used in production when sqlcipher3 is installed.
    # In development (plain sqlite3), this value is ignored entirely.
    passphrase = os.environ.get("WHISPER_DB_PASSPHRASE", "")

    instance = Database(db_path, passphrase)
    conn = instance.connect()
    try:
        yield conn
    finally:
        conn.close()


def init_schema(conn) -> None:
    """
    Run all CREATE TABLE statements on an existing connection.

    Called once when the app starts (or by the test fixture for each test).
    Safe to call multiple times — all statements use IF NOT EXISTS.

    Uses executescript() instead of manual semicolon-splitting so that
    semicolons inside SQL comments (e.g. "-- a; b") are not treated as
    statement boundaries.

    Args:
        conn: An open sqlite3 (or sqlcipher3) connection.
    """
    conn.executescript(SCHEMA_SQL)
