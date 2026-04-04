"""
Integration tests — contacts table.

DATA_CONTRACT § Contact — Entity Definitions.
"""
from __future__ import annotations

import sqlite3

import pytest

from tests.conftest import VALID_SESSION_ID, VALID_SESSION_ID_2, VALID_SESSION_ID_3, pkg


def _seed_contact(db, session_id=VALID_SESSION_ID_2, display_name="Bob", accepted=0):
    queries = pkg("storage.queries")
    return queries.create_contact(db, session_id=session_id, display_name=display_name, accepted=accepted)


@pytest.mark.integration
class TestContactsTable:

    def test_insert_contact_succeeds(self, db):
        _seed_contact(db)
        row = db.execute("SELECT * FROM contacts WHERE session_id = ?", (VALID_SESSION_ID_2,)).fetchone()
        assert row is not None

    def test_accepted_defaults_to_false(self, db):
        _seed_contact(db, accepted=0)
        row = db.execute("SELECT accepted FROM contacts WHERE session_id = ?", (VALID_SESSION_ID_2,)).fetchone()
        assert row["accepted"] == 0

    def test_accept_contact(self, db):
        queries = pkg("storage.queries")
        _seed_contact(db, accepted=0)
        queries.update_contact(db, session_id=VALID_SESSION_ID_2, accepted=True)
        row = db.execute("SELECT accepted FROM contacts WHERE session_id = ?", (VALID_SESSION_ID_2,)).fetchone()
        assert row["accepted"] == 1

    def test_update_display_name(self, db):
        queries = pkg("storage.queries")
        _seed_contact(db, display_name="Bob")
        queries.update_contact(db, session_id=VALID_SESSION_ID_2, display_name="Robert")
        row = db.execute("SELECT display_name FROM contacts WHERE session_id = ?", (VALID_SESSION_ID_2,)).fetchone()
        assert row["display_name"] == "Robert"

    def test_delete_contact(self, db):
        queries = pkg("storage.queries")
        _seed_contact(db)
        queries.delete_contact(db, session_id=VALID_SESSION_ID_2)
        row = db.execute("SELECT * FROM contacts WHERE session_id = ?", (VALID_SESSION_ID_2,)).fetchone()
        assert row is None

    def test_list_contacts_returns_all(self, db):
        queries = pkg("storage.queries")
        _seed_contact(db, session_id=VALID_SESSION_ID_2)
        _seed_contact(db, session_id=VALID_SESSION_ID_3)
        contacts = queries.list_contacts(db)
        assert len(contacts) == 2

    def test_list_contacts_filter_accepted(self, db):
        queries = pkg("storage.queries")
        _seed_contact(db, session_id=VALID_SESSION_ID_2, accepted=1)
        _seed_contact(db, session_id=VALID_SESSION_ID_3, accepted=0)
        accepted = queries.list_contacts(db, accepted=True)
        assert len(accepted) == 1
        assert accepted[0]["session_id"] == VALID_SESSION_ID_2

    def test_duplicate_session_id_raises(self, db):
        _seed_contact(db)
        with pytest.raises(sqlite3.IntegrityError):
            _seed_contact(db)

    def test_null_session_id_raises(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO contacts (session_id, accepted) VALUES (NULL, 0)")

    def test_created_at_populated(self, db):
        _seed_contact(db)
        row = db.execute("SELECT created_at FROM contacts WHERE session_id = ?", (VALID_SESSION_ID_2,)).fetchone()
        assert row["created_at"] is not None


@pytest.mark.integration
class TestContactsConversationRelationship:
    """contacts.session_id is referenced by conversations.contact_session_id."""

    def test_deleting_contact_does_not_cascade_delete_conversation(self, db):
        """
        DATA_CONTRACT assumption A-7: hard deletes, no soft delete.
        Deleting a contact should NOT cascade-delete conversation history.
        """
        queries = pkg("storage.queries")
        _seed_contact(db)
        conv_id = queries.create_dm_conversation(db, contact_session_id=VALID_SESSION_ID_2)
        queries.delete_contact(db, session_id=VALID_SESSION_ID_2)
        row = db.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        assert row is not None, "Conversation must survive contact deletion"
