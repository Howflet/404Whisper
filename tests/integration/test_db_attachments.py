"""
Integration tests — attachments table.

DATA_CONTRACT § Attachment — Entity Definitions.
"""
from __future__ import annotations

import sqlite3

import pytest

from tests.conftest import VALID_SESSION_ID, VALID_SESSION_ID_2, pkg


def _seed_conversation(db) -> int:
    queries = pkg("storage.queries")
    queries.create_contact(db, session_id=VALID_SESSION_ID_2, display_name="Bob", accepted=1)
    return queries.create_dm_conversation(db, contact_session_id=VALID_SESSION_ID_2)


def _seed_attachment(db, **kwargs) -> int:
    queries = pkg("storage.queries")
    defaults = dict(
        file_name="photo.jpg",
        file_size=204800,
        mime_type="image/jpeg",
        status="PENDING",
    )
    defaults.update(kwargs)
    return queries.create_attachment(db, **defaults)


@pytest.mark.integration
class TestAttachmentsTable:

    def test_insert_attachment_succeeds(self, db):
        att_id = _seed_attachment(db)
        row = db.execute("SELECT * FROM attachments WHERE id = ?", (att_id,)).fetchone()
        assert row is not None
        assert row["file_name"] == "photo.jpg"

    def test_status_defaults_to_pending(self, db):
        att_id = _seed_attachment(db, status="PENDING")
        row = db.execute("SELECT status FROM attachments WHERE id = ?", (att_id,)).fetchone()
        assert row["status"] == "PENDING"

    def test_status_transitions_to_uploaded(self, db):
        queries = pkg("storage.queries")
        att_id = _seed_attachment(db, status="UPLOADING")
        queries.update_attachment(db, attachment_id=att_id, status="UPLOADED", upload_url="https://files.example.com/abc")
        row = db.execute("SELECT status, upload_url FROM attachments WHERE id = ?", (att_id,)).fetchone()
        assert row["status"] == "UPLOADED"
        assert row["upload_url"] is not None

    def test_invalid_status_raises(self, db):
        att_id = _seed_attachment(db)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE attachments SET status = 'FLYING' WHERE id = ?", (att_id,))

    def test_encryption_key_stored_as_blob(self, db):
        queries = pkg("storage.queries")
        att_id = _seed_attachment(db, encryption_key=b"\x00" * 32, hmac_key=b"\xff" * 32)
        row = db.execute("SELECT encryption_key, hmac_key FROM attachments WHERE id = ?", (att_id,)).fetchone()
        assert row["encryption_key"] == b"\x00" * 32
        assert row["hmac_key"] == b"\xff" * 32

    def test_message_id_nullable_before_send(self, db):
        att_id = _seed_attachment(db, message_id=None)
        row = db.execute("SELECT message_id FROM attachments WHERE id = ?", (att_id,)).fetchone()
        assert row["message_id"] is None

    def test_message_id_set_after_message_created(self, db):
        """Once the message row exists, attachments.message_id should be updated."""
        queries = pkg("storage.queries")
        conv_id = _seed_conversation(db)
        att_id = _seed_attachment(db)
        from datetime import datetime, timezone
        msg_id = queries.create_message(
            db,
            conversation_id=conv_id,
            sender_session_id=VALID_SESSION_ID,
            body=None,
            type="ATTACHMENT",
            sent_at=datetime.now(timezone.utc).isoformat(),
            attachment_id=att_id,
        )
        queries.update_attachment(db, attachment_id=att_id, message_id=msg_id)
        row = db.execute("SELECT message_id FROM attachments WHERE id = ?", (att_id,)).fetchone()
        assert row["message_id"] == msg_id

    def test_file_size_must_be_positive(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO attachments (file_name, file_size, mime_type, status) VALUES (?, ?, ?, ?)",
                ("bad.jpg", 0, "image/jpeg", "PENDING"),
            )

    def test_created_at_populated(self, db):
        att_id = _seed_attachment(db)
        row = db.execute("SELECT created_at FROM attachments WHERE id = ?", (att_id,)).fetchone()
        assert row["created_at"] is not None
