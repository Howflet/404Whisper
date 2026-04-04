"""
Integration tests — identities table.

DATA_CONTRACT § Identity — Entity Definitions.
"""
from __future__ import annotations

import sqlite3

import pytest

from tests.conftest import VALID_SESSION_ID, VALID_DISPLAY_NAME, pkg


@pytest.mark.integration
class TestIdentityTable:

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_insert_identity_succeeds(self, db: sqlite3.Connection):
        queries = pkg("storage.queries")
        queries.create_identity(
            db,
            session_id=VALID_SESSION_ID,
            display_name=VALID_DISPLAY_NAME,
        )
        row = db.execute("SELECT * FROM identities WHERE session_id = ?", (VALID_SESSION_ID,)).fetchone()
        assert row is not None
        assert row["session_id"] == VALID_SESSION_ID
        assert row["display_name"] == VALID_DISPLAY_NAME

    def test_created_at_is_populated_automatically(self, db: sqlite3.Connection):
        queries = pkg("storage.queries")
        queries.create_identity(db, session_id=VALID_SESSION_ID, display_name=None)
        row = db.execute("SELECT created_at FROM identities WHERE session_id = ?", (VALID_SESSION_ID,)).fetchone()
        assert row["created_at"] is not None

    def test_updated_at_is_populated_on_create(self, db: sqlite3.Connection):
        queries = pkg("storage.queries")
        queries.create_identity(db, session_id=VALID_SESSION_ID, display_name=None)
        row = db.execute("SELECT updated_at FROM identities WHERE session_id = ?", (VALID_SESSION_ID,)).fetchone()
        assert row["updated_at"] is not None

    def test_display_name_nullable(self, db: sqlite3.Connection):
        queries = pkg("storage.queries")
        queries.create_identity(db, session_id=VALID_SESSION_ID, display_name=None)
        row = db.execute("SELECT display_name FROM identities WHERE session_id = ?", (VALID_SESSION_ID,)).fetchone()
        assert row["display_name"] is None

    def test_update_display_name(self, db: sqlite3.Connection):
        queries = pkg("storage.queries")
        queries.create_identity(db, session_id=VALID_SESSION_ID, display_name="Alice")
        queries.update_identity(db, session_id=VALID_SESSION_ID, display_name="Alicia")
        row = db.execute("SELECT display_name FROM identities WHERE session_id = ?", (VALID_SESSION_ID,)).fetchone()
        assert row["display_name"] == "Alicia"

    def test_update_personal_vibe(self, db: sqlite3.Connection):
        queries = pkg("storage.queries")
        queries.create_identity(db, session_id=VALID_SESSION_ID, display_name=None)
        queries.update_identity(db, session_id=VALID_SESSION_ID, personal_vibe="CAMPFIRE")
        row = db.execute("SELECT personal_vibe FROM identities WHERE session_id = ?", (VALID_SESSION_ID,)).fetchone()
        assert row["personal_vibe"] == "CAMPFIRE"

    # ------------------------------------------------------------------
    # Constraint violations
    # ------------------------------------------------------------------

    def test_duplicate_session_id_raises_integrity_error(self, db: sqlite3.Connection):
        queries = pkg("storage.queries")
        queries.create_identity(db, session_id=VALID_SESSION_ID, display_name=None)
        with pytest.raises(sqlite3.IntegrityError):
            queries.create_identity(db, session_id=VALID_SESSION_ID, display_name=None)

    def test_null_session_id_raises_integrity_error(self, db: sqlite3.Connection):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO identities (session_id) VALUES (NULL)")

    def test_invalid_personal_vibe_raises_integrity_error(self, db: sqlite3.Connection):
        """DB-level CHECK constraint must reject unknown vibe values."""
        queries = pkg("storage.queries")
        queries.create_identity(db, session_id=VALID_SESSION_ID, display_name=None)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "UPDATE identities SET personal_vibe = 'INVALID_VIBE' WHERE session_id = ?",
                (VALID_SESSION_ID,),
            )
