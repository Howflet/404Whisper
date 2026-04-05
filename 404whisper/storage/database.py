"""
storage/database.py — Database connection manager.

What this file does
-------------------
Manages opening and closing the SQLite database file on disk.

Think of it as the "key to the building":
  - In development (no sqlcipher3 installed): opens the plain .db file.
  - In production (sqlcipher3 installed): opens the *encrypted* .db file using
    a passphrase derived from the user's unlock passphrase (Argon2).

The ``Database`` class is used by ``storage/db.py``'s ``get_db()`` function,
which is called automatically by FastAPI before each HTTP request.

You will almost never need to import this class directly — use ``get_db()``
(from ``storage.db``) instead, which handles open/close for you.

Development vs. production:
  - Development: plain sqlite3, no passphrase encryption.
  - Production:  sqlcipher3 with Argon2-derived passphrase key.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

try:
    import sqlcipher3 as _sqlcipher3  # Available in production builds
except ImportError:
    _sqlcipher3 = None  # Falls back to plain sqlite3 in development / CI

# Re-export both so that any module importing from storage.database
# gets everything it needs — no need to also import from storage.db.
# The cross-layer tests (test_cross_layer.py) access SCHEMA_SQL and
# init_schema directly via pkg("storage.database").
from .db import init_schema, SCHEMA_SQL


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
            # check_same_thread=False allows FastAPI's async machinery (which may
            # hand off work to a thread pool) to reuse the same connection.
            conn = _sqlcipher3.connect(self.db_path, check_same_thread=False)
            conn.execute(f"PRAGMA key = '{self.passphrase}'")
        else:
            # Development / CI: plain sqlite3, no encryption.
            # check_same_thread=False is required when Starlette's TestClient runs
            # the ASGI app in a background thread (common in contract/WS tests).
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
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
