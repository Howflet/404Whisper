"""
Integration-test fixtures — provides a clean, in-memory SQLite database for
every test function.

SQLCipher (sqlcipher3) is used in production; plain sqlite3 is used in tests
to avoid the encryption dependency in CI.  The schema is identical.
"""
from __future__ import annotations

import sqlite3
from typing import Generator

import pytest

from tests.conftest import pkg


@pytest.fixture()
def db() -> Generator[sqlite3.Connection, None, None]:
    """
    An in-memory SQLite connection initialised with the full 404Whisper schema.

    A fresh database is created for each test function and torn down
    immediately after — no state leaks between tests.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Run the same schema-init routine used in production.
    # This calls 404whisper.storage.db.init_schema(conn).
    storage = pkg("storage.db")
    storage.init_schema(conn)

    yield conn
    conn.close()
