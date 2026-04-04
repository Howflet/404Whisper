"""
Integration tests — messages table.

DATA_CONTRACT § Message — Entity Definitions, Relationships, and Indexes.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import VALID_SESSION_ID, VALID_SESSION_ID_2, pkg

UTC = timezone.utc


def _seed_conversation(db) -> int:
    queries = pkg("storage.queries")
    pkg("storage.queries").create_contact(db, session_id=VALID_SESSION_ID_2, display_name="Bob", accepted=1)
    return queries.create_dm_conversation(db, contact_session_id=VALID_SESSION_ID_2)


def _seed_message(db, conv_id: int, **kwargs) -> int:
    queries = pkg("storage.queries")
    defaults = dict(
        sender_session_id=VALID_SESSION_ID,
        body="Hello",
        type="TEXT",
        sent_at=datetime.now(UTC).isoformat(),
    )
    defaults.update(kwargs)
    return queries.create_message(db, conversation_id=conv_id, **defaults)


@pytest.mark.integration
class TestMessagesTable:

    def test_insert_message_succeeds(self, db):
        conv_id = _seed_conversation(db)
        msg_id = _seed_message(db, conv_id)
        row = db.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
        assert row is not None
        assert row["body"] == "Hello"

    def test_message_type_defaults_to_text(self, db):
        conv_id = _seed_conversation(db)
        msg_id = _seed_message(db, conv_id, type="TEXT")
        row = db.execute("SELECT type FROM messages WHERE id = ?", (msg_id,)).fetchone()
        assert row["type"] == "TEXT"

    def test_invalid_message_type_raises(self, db):
        conv_id = _seed_conversation(db)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO messages
                   (conversation_id, sender_session_id, body, type, sent_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (conv_id, VALID_SESSION_ID, "Hi", "INVALID_TYPE", datetime.now(UTC).isoformat()),
            )

    def test_foreign_key_on_conversation_enforced(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO messages
                   (conversation_id, sender_session_id, body, type, sent_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (9999, VALID_SESSION_ID, "Hi", "TEXT", datetime.now(UTC).isoformat()),
            )

    def test_expires_at_nullable(self, db):
        conv_id = _seed_conversation(db)
        msg_id = _seed_message(db, conv_id, expires_at=None)
        row = db.execute("SELECT expires_at FROM messages WHERE id = ?", (msg_id,)).fetchone()
        assert row["expires_at"] is None

    def test_expires_at_stored_when_set(self, db):
        conv_id = _seed_conversation(db)
        expiry = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
        msg_id = _seed_message(db, conv_id, expires_at=expiry)
        row = db.execute("SELECT expires_at FROM messages WHERE id = ?", (msg_id,)).fetchone()
        assert row["expires_at"] == expiry

    def test_is_anonymous_defaults_to_false(self, db):
        conv_id = _seed_conversation(db)
        msg_id = _seed_message(db, conv_id)
        row = db.execute("SELECT is_anonymous FROM messages WHERE id = ?", (msg_id,)).fetchone()
        assert row["is_anonymous"] == 0

    def test_anonymous_message_has_null_sender(self, db):
        """CONFESSIONAL vibe: sender must not be stored when is_anonymous=True."""
        conv_id = _seed_conversation(db)
        msg_id = _seed_message(db, conv_id, sender_session_id=None, is_anonymous=1)
        row = db.execute(
            "SELECT sender_session_id, is_anonymous FROM messages WHERE id = ?", (msg_id,)
        ).fetchone()
        assert row["is_anonymous"] == 1
        assert row["sender_session_id"] is None

    def test_messages_ordered_by_sent_at(self, db):
        conv_id = _seed_conversation(db)
        base = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)
        for i in range(3):
            _seed_message(db, conv_id, sent_at=(base + timedelta(seconds=i)).isoformat())
        rows = db.execute(
            "SELECT sent_at FROM messages WHERE conversation_id = ? ORDER BY sent_at DESC",
            (conv_id,),
        ).fetchall()
        timestamps = [r["sent_at"] for r in rows]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_is_spotlight_pinned_defaults_to_false(self, db):
        conv_id = _seed_conversation(db)
        msg_id = _seed_message(db, conv_id)
        row = db.execute("SELECT is_spotlight_pinned FROM messages WHERE id = ?", (msg_id,)).fetchone()
        assert row["is_spotlight_pinned"] == 0


@pytest.mark.integration
class TestMessagePagination:
    """Verifies the cursor-based pagination query pattern for GET /conversations/{id}/messages."""

    def test_before_cursor_returns_older_messages(self, db):
        queries = pkg("storage.queries")
        conv_id = _seed_conversation(db)
        base = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)
        for i in range(5):
            _seed_message(db, conv_id, sent_at=(base + timedelta(minutes=i)).isoformat())

        pivot = (base + timedelta(minutes=3)).isoformat()
        page = queries.list_messages(db, conversation_id=conv_id, before=pivot, limit=50)
        assert all(m["sent_at"] < pivot for m in page)

    def test_limit_is_respected(self, db):
        queries = pkg("storage.queries")
        conv_id = _seed_conversation(db)
        base = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)
        for i in range(10):
            _seed_message(db, conv_id, sent_at=(base + timedelta(minutes=i)).isoformat())

        page = queries.list_messages(db, conversation_id=conv_id, limit=3)
        assert len(page) == 3
