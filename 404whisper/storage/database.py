"""
storage/database.py — Connection-managing Database class.

Wraps sqlite3 (or sqlcipher3 in production) and delegates schema setup to
storage/db.py.  Higher layers (API routes, messaging, etc.) use this class
to get a database connection; they call functions from storage/queries.py
to read and write data.

Development vs. production:
  - Development: plain sqlite3, no passphrase encryption.
  - Production:  sqlcipher3 with Argon2-derived passphrase key.
    Swap the two commented lines in _get_connection() when ready.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

try:
    import sqlcipher3 as _sqlcipher3  # Available in production builds
except ImportError:
    _sqlcipher3 = None  # Falls back to plain sqlite3 in development / CI

from .db import init_schema


class Database:
    """
    Manages the on-disk SQLite database file.

    Lazy initialisation: the schema is created on the first call to
    _ensure_schema(), not at __init__ time.  This makes unit-testing easy —
    you can construct a Database object without touching the filesystem.

    Usage:
        db = Database(db_path="/data/whisper.db", passphrase="hunter2")
        conn = db._get_connection()
        identity_id = queries.create_identity(conn, session_id="05abc…")
    """

    def __init__(self, db_path: str, passphrase: str) -> None:
        self.db_path   = db_path
        self.passphrase = passphrase
        self._schema_initialized = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """
        Open and return a new database connection.

        row_factory is set to sqlite3.Row so callers get dict-like objects
        instead of plain tuples — column names are accessible by name.

        foreign_keys pragma enforces FK constraints and CASCADE DELETE.
        """
        if _sqlcipher3 is not None:
            # Production: encrypted DB using sqlcipher3.
            conn = _sqlcipher3.connect(self.db_path)
            conn.execute(f"PRAGMA key = '{self.passphrase}'")
        else:
            # Development / CI: plain sqlite3, no encryption.
            conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        """
        Run CREATE TABLE IF NOT EXISTS for all tables the first time we connect.

        Called automatically before any operation that needs the DB.
        Uses the canonical schema from storage/db.py so there is one source
        of truth shared between the production class and the test fixture.
        """
        if not self._schema_initialized:
            with self._get_connection() as conn:
                init_schema(conn)
            self._schema_initialized = True

    # ------------------------------------------------------------------
    # Context manager — lets callers use:  with db.connect() as conn: …
    # ------------------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        """
        Return an open connection with the schema guaranteed to exist.

        Typical usage in an API route:
            conn = db.connect()
            rows = queries.list_contacts(conn)
        """
        self._ensure_schema()
        return self._get_connection()
