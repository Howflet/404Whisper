"""
Storage Layer - Encrypted SQLite Database

Provides encrypted storage for all application data.
"""

import sqlite3
# import sqlcipher3  # Commented out for development
from typing import Optional, List, Dict, Any
import os

# Schema SQL for testing
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS identities (
    id INTEGER PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    display_name TEXT,
    personal_vibe TEXT CHECK(personal_vibe IN ('CAMPFIRE','NEON','LIBRARY','VOID','SUNRISE','404','CONFESSIONAL','SLOW_BURN','CHORUS','SPOTLIGHT','ECHO','SCRAMBLE')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    display_name TEXT,
    accepted BOOLEAN DEFAULT FALSE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY,
    contact_session_id TEXT,
    group_id INTEGER,
    last_message_at TEXT,
    unread_count INTEGER DEFAULT 0,
    group_vibe TEXT CHECK(group_vibe IN ('CAMPFIRE','NEON','LIBRARY','VOID','SUNRISE','404','CONFESSIONAL','SLOW_BURN','CHORUS','SPOTLIGHT','ECHO','SCRAMBLE')),
    personal_vibe_override TEXT CHECK(personal_vibe_override IN ('CAMPFIRE','NEON','LIBRARY','VOID','SUNRISE','404','CONFESSIONAL','SLOW_BURN','CHORUS','SPOTLIGHT','ECHO','SCRAMBLE')),
    vibe_cooldown_until TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL,
    sender_session_id TEXT NOT NULL,
    body TEXT,
    attachment_id INTEGER,
    message_type TEXT CHECK(message_type IN ('TEXT','ATTACHMENT','GROUP_EVENT','SYSTEM')),
    group_event_type TEXT CHECK(group_event_type IN ('MEMBER_JOINED','MEMBER_LEFT','VIBE_CHANGED','GROUP_RENAMED')),
    sent_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations (id)
);

CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    group_vibe TEXT CHECK(group_vibe IN ('CAMPFIRE','NEON','LIBRARY','VOID','SUNRISE','404','CONFESSIONAL','SLOW_BURN','CHORUS','SPOTLIGHT','ECHO','SCRAMBLE')),
    vibe_cooldown_until TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS group_members (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    FOREIGN KEY (group_id) REFERENCES groups (id)
);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    encrypted_hash TEXT NOT NULL,
    upload_url TEXT,
    created_at TEXT NOT NULL
);
"""


def init_schema(conn):
    """Initialize schema on an existing connection (for testing)."""
    statements = [stmt.strip() for stmt in SCHEMA_SQL.split(';') if stmt.strip()]
    for stmt in statements:
        conn.execute(stmt)
    conn.commit()


class Database:
    def __init__(self, db_path: str, passphrase: str):
        self.db_path = db_path
        self.passphrase = passphrase
        # Initialize schema once on first use
        self._schema_initialized = False

    def _ensure_schema(self):
        """Initialize schema on first use (lazy initialization)."""
        if not self._schema_initialized:
            with self._get_connection() as conn:
                init_schema(conn)
            self._schema_initialized = True

    def _get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # conn.execute(f"PRAGMA key = '{self.passphrase}'")  # Commented out for development
        return conn

    # Identity operations
    def create_identity(self, session_id: str, display_name: Optional[str] = None) -> int:
        self._ensure_schema()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO identities (session_id, display_name, created_at) VALUES (?, ?, datetime('now'))",
                (session_id, display_name)
            )
            conn.commit()
            return cursor.lastrowid

    def get_identity(self, session_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_schema()
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM identities WHERE session_id = ?",
                (session_id,)
            ).fetchone()
            return dict(row) if row else None

    # Contact operations
    def add_contact(self, session_id: str, display_name: Optional[str] = None) -> int:
        self._ensure_schema()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO contacts (session_id, display_name, created_at) VALUES (?, ?, datetime('now'))",
                (session_id, display_name)
            )
            conn.commit()
            return cursor.lastrowid

    def get_contacts(self, accepted: Optional[bool] = None) -> List[Dict[str, Any]]:
        self._ensure_schema()
        with self._get_connection() as conn:
            if accepted is None:
                rows = conn.execute("SELECT * FROM contacts").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM contacts WHERE accepted = ?",
                    (accepted,)
                ).fetchall()
            return [dict(row) for row in rows]

    # Group operations
    def create_group(self, name: str, group_vibe: Optional[str] = None) -> int:
        self._ensure_schema()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO groups (name, group_vibe, created_at) VALUES (?, ?, datetime('now'))",
                (name, group_vibe)
            )
            conn.commit()
            return cursor.lastrowid

    def get_group(self, group_id: int) -> Optional[Dict[str, Any]]:
        self._ensure_schema()
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM groups WHERE id = ?",
                (group_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_groups(self) -> List[Dict[str, Any]]:
        self._ensure_schema()
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM groups ORDER BY created_at DESC").fetchall()
            return [dict(row) for row in rows]

    # Conversation operations
    def create_conversation(self, contact_session_id: Optional[str] = None, group_id: Optional[int] = None) -> int:
        self._ensure_schema()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO conversations (contact_session_id, group_id, created_at) VALUES (?, ?, datetime('now'))",
                (contact_session_id, group_id)
            )
            conn.commit()
            return cursor.lastrowid

    def get_conversations(self) -> List[Dict[str, Any]]:
        self._ensure_schema()
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM conversations ORDER BY last_message_at DESC").fetchall()
            return [dict(row) for row in rows]

    # Message operations
    def add_message(self, conversation_id: int, sender_session_id: str, body: str) -> int:
        self._ensure_schema()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO messages (conversation_id, sender_session_id, body, sent_at) VALUES (?, ?, ?, datetime('now'))",
                (conversation_id, sender_session_id, body)
            )
            conn.commit()
            return cursor.lastrowid

    def get_messages(self, conversation_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        self._ensure_schema()
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY sent_at DESC LIMIT ?",
                (conversation_id, limit)
            ).fetchall()
            return [dict(row) for row in rows]