"""
Integration tests — extended query helpers.

Covers the 7 functions added to storage/queries.py to support the messaging
(Layer 4) and groups (Layer 5) build-out:

  get_group_by_session_id     — lookup group by its network address
  get_conversation_by_contact — find a DM conversation from a sender's ID
  get_conversation_by_group   — find a GROUP conversation from a group PK
  delete_group                — hard delete with cascade to members
  delete_message              — single-row message delete
  increment_conversation_unread — atomic counter bump (no read needed)
  purge_expired_messages      — batch delete of expired 404-vibe messages
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import VALID_SESSION_ID, VALID_SESSION_ID_2, VALID_SESSION_ID_3, pkg

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Shared seed helpers — keep each test self-contained and readable
# ---------------------------------------------------------------------------

def _make_contact(db, session_id=VALID_SESSION_ID_2, accepted=1):
    """Insert a contact row and return nothing — we just need it to exist."""
    pkg("storage.queries").create_contact(db, session_id=session_id, accepted=accepted)


def _make_group(db, session_id=VALID_SESSION_ID, name="Night Owls") -> int:
    """Insert a group row and return its integer PK."""
    return pkg("storage.queries").create_group(
        db,
        group_session_id=session_id,
        name=name,
        created_by_session_id=VALID_SESSION_ID,
    )


def _make_dm_conv(db, contact_session_id=VALID_SESSION_ID_2) -> int:
    """Create a DM conversation and return its integer PK."""
    _make_contact(db, session_id=contact_session_id)
    return pkg("storage.queries").create_dm_conversation(db, contact_session_id=contact_session_id)


def _make_group_conv(db) -> tuple[int, int]:
    """Create a group + companion conversation.  Returns (group_id, conv_id)."""
    q = pkg("storage.queries")
    gid = _make_group(db)
    cid = q.create_group_conversation(db, group_id=gid)
    return gid, cid


def _make_message(db, conv_id: int, sent_at: str = None, **kwargs) -> int:
    """Insert a message and return its PK.  Any kwarg overrides the defaults."""
    q = pkg("storage.queries")
    defaults: dict = {
        "sender_session_id": VALID_SESSION_ID,
        "body":              "hello",
        "type":              "TEXT",
        "sent_at":           sent_at or datetime.now(UTC).isoformat(),
    }
    defaults.update(kwargs)  # caller can override body, type, sent_at, etc.
    return q.create_message(db, conversation_id=conv_id, **defaults)


# ===========================================================================
# get_group_by_session_id
# ===========================================================================

@pytest.mark.integration
class TestGetGroupBySessionId:
    """
    Verify that groups can be looked up by their on-network 66-char hex ID.
    The network delivers messages using group_session_id, not the integer PK.
    """

    def test_returns_group_when_found(self, db):
        """Happy path — group was created locally, look it up by session_id."""
        q = pkg("storage.queries")
        _make_group(db, session_id=VALID_SESSION_ID)
        result = q.get_group_by_session_id(db, group_session_id=VALID_SESSION_ID)
        assert result is not None
        assert result["group_session_id"] == VALID_SESSION_ID

    def test_returns_none_when_not_found(self, db):
        """Unknown session IDs return None so callers can handle gracefully."""
        q = pkg("storage.queries")
        result = q.get_group_by_session_id(db, group_session_id=VALID_SESSION_ID_3)
        assert result is None

    def test_all_group_fields_present(self, db):
        """The returned dict must contain the full row (not a subset)."""
        q = pkg("storage.queries")
        _make_group(db, session_id=VALID_SESSION_ID)
        result = q.get_group_by_session_id(db, group_session_id=VALID_SESSION_ID)
        assert "name" in result
        assert "created_by_session_id" in result
        assert "created_at" in result


# ===========================================================================
# get_conversation_by_contact
# ===========================================================================

@pytest.mark.integration
class TestGetConversationByContact:
    """
    Verify DM conversation lookup by the contact's Session ID.
    The polling loop uses this to route incoming messages to the right row.
    """

    def test_returns_conversation_for_known_contact(self, db):
        q = pkg("storage.queries")
        conv_id = _make_dm_conv(db, contact_session_id=VALID_SESSION_ID_2)
        result = q.get_conversation_by_contact(db, contact_session_id=VALID_SESSION_ID_2)
        assert result is not None
        assert result["id"] == conv_id

    def test_returns_none_for_unknown_contact(self, db):
        q = pkg("storage.queries")
        # No conversation seeded for SESSION_ID_3.
        result = q.get_conversation_by_contact(db, contact_session_id=VALID_SESSION_ID_3)
        assert result is None

    def test_dm_type_is_set(self, db):
        """Returned conversation must have type = 'DM'."""
        q = pkg("storage.queries")
        _make_dm_conv(db)
        result = q.get_conversation_by_contact(db, contact_session_id=VALID_SESSION_ID_2)
        assert result["type"] == "DM"

    def test_does_not_return_group_conversation(self, db):
        """
        A GROUP conversation has group_id set, not contact_session_id.
        Looking up by a contact session ID must NOT return a group conv.
        """
        q = pkg("storage.queries")
        _, _ = _make_group_conv(db)
        # VALID_SESSION_ID is also used as the group_session_id — make sure
        # searching by it as a *contact* finds nothing.
        result = q.get_conversation_by_contact(db, contact_session_id=VALID_SESSION_ID)
        assert result is None


# ===========================================================================
# get_conversation_by_group
# ===========================================================================

@pytest.mark.integration
class TestGetConversationByGroup:
    """
    Verify GROUP conversation lookup by the group's integer PK.
    The groups layer needs this to write messages into the right conversation.
    """

    def test_returns_conversation_for_known_group(self, db):
        q = pkg("storage.queries")
        gid, cid = _make_group_conv(db)
        result = q.get_conversation_by_group(db, group_id=gid)
        assert result is not None
        assert result["id"] == cid

    def test_returns_none_for_unknown_group(self, db):
        q = pkg("storage.queries")
        result = q.get_conversation_by_group(db, group_id=9999)
        assert result is None

    def test_group_type_is_set(self, db):
        """Returned conversation must have type = 'GROUP'."""
        q = pkg("storage.queries")
        gid, _ = _make_group_conv(db)
        result = q.get_conversation_by_group(db, group_id=gid)
        assert result["type"] == "GROUP"

    def test_group_id_matches(self, db):
        """The group_id FK on the conversation must match the queried group."""
        q = pkg("storage.queries")
        gid, _ = _make_group_conv(db)
        result = q.get_conversation_by_group(db, group_id=gid)
        assert result["group_id"] == gid


# ===========================================================================
# delete_group
# ===========================================================================

@pytest.mark.integration
class TestDeleteGroup:
    """
    delete_group() removes the group row; ON DELETE CASCADE removes its members.
    The companion conversation is NOT deleted (history is preserved).
    """

    def test_group_is_gone_after_delete(self, db):
        q = pkg("storage.queries")
        gid = _make_group(db)
        q.delete_group(db, group_id=gid)
        result = db.execute("SELECT * FROM groups WHERE id = ?", (gid,)).fetchone()
        assert result is None

    def test_members_cascade_deleted(self, db):
        """group_members has ON DELETE CASCADE — members vanish with the group."""
        q = pkg("storage.queries")
        gid = _make_group(db)
        q.add_group_member(db, group_id=gid, session_id=VALID_SESSION_ID_2)
        q.add_group_member(db, group_id=gid, session_id=VALID_SESSION_ID_3)
        q.delete_group(db, group_id=gid)
        rows = db.execute(
            "SELECT * FROM group_members WHERE group_id = ?", (gid,)
        ).fetchall()
        assert len(rows) == 0

    def test_conversation_survives_group_deletion(self, db):
        """
        The companion GROUP conversation is NOT deleted — history is preserved.
        This mirrors the contact-deletion rule (data contract assumption A-7).
        """
        q = pkg("storage.queries")
        gid, cid = _make_group_conv(db)
        q.delete_group(db, group_id=gid)
        row = db.execute("SELECT * FROM conversations WHERE id = ?", (cid,)).fetchone()
        assert row is not None, "Group conversation must survive group deletion"

    def test_delete_nonexistent_group_is_noop(self, db):
        """Deleting a group that doesn't exist should not raise."""
        q = pkg("storage.queries")
        q.delete_group(db, group_id=9999)  # should not raise


# ===========================================================================
# delete_message
# ===========================================================================

@pytest.mark.integration
class TestDeleteMessage:
    """delete_message() removes a single message row by primary key."""

    def test_message_is_gone_after_delete(self, db):
        q = pkg("storage.queries")
        conv_id = _make_dm_conv(db)
        msg_id = _make_message(db, conv_id)
        q.delete_message(db, message_id=msg_id)
        row = db.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
        assert row is None

    def test_sibling_messages_untouched(self, db):
        """Deleting one message must not affect other messages in the conversation."""
        q = pkg("storage.queries")
        conv_id = _make_dm_conv(db)
        keep_id = _make_message(db, conv_id, body="keep me")
        del_id  = _make_message(db, conv_id, body="delete me")
        q.delete_message(db, message_id=del_id)
        remaining = db.execute(
            "SELECT * FROM messages WHERE conversation_id = ?", (conv_id,)
        ).fetchall()
        assert len(remaining) == 1
        assert remaining[0]["id"] == keep_id

    def test_delete_nonexistent_message_is_noop(self, db):
        """Deleting a message PK that doesn't exist should not raise."""
        q = pkg("storage.queries")
        q.delete_message(db, message_id=9999)  # should not raise


# ===========================================================================
# increment_conversation_unread
# ===========================================================================

@pytest.mark.integration
class TestIncrementConversationUnread:
    """
    increment_conversation_unread() bumps unread_count atomically.
    The SQL form (count + 1) avoids read-modify-write races in the polling loop.
    """

    def test_starts_at_zero(self, db):
        """New conversations have unread_count = 0 by default."""
        conv_id = _make_dm_conv(db)
        row = db.execute(
            "SELECT unread_count FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        assert row["unread_count"] == 0

    def test_single_increment(self, db):
        q = pkg("storage.queries")
        conv_id = _make_dm_conv(db)
        q.increment_conversation_unread(db, conversation_id=conv_id)
        row = db.execute(
            "SELECT unread_count FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        assert row["unread_count"] == 1

    def test_multiple_increments_accumulate(self, db):
        """Each call adds exactly 1 — three calls should leave count = 3."""
        q = pkg("storage.queries")
        conv_id = _make_dm_conv(db)
        for _ in range(3):
            q.increment_conversation_unread(db, conversation_id=conv_id)
        row = db.execute(
            "SELECT unread_count FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        assert row["unread_count"] == 3

    def test_reset_after_read(self, db):
        """
        After incrementing, the polling loop can reset to 0 via
        update_conversation_unread.  Verify the round-trip is clean.
        """
        q = pkg("storage.queries")
        conv_id = _make_dm_conv(db)
        for _ in range(5):
            q.increment_conversation_unread(db, conversation_id=conv_id)
        q.update_conversation_unread(db, conversation_id=conv_id, unread_count=0)
        row = db.execute(
            "SELECT unread_count FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        assert row["unread_count"] == 0


# ===========================================================================
# purge_expired_messages
# ===========================================================================

@pytest.mark.integration
class TestPurgeExpiredMessages:
    """
    purge_expired_messages() is the fast-path batch delete for the 404-vibe
    TTL background job.  It deletes all expired, unpinned messages in one SQL
    statement and returns the count of rows removed.
    """

    def _far_past(self, hours_ago: int = 48) -> str:
        """Return an ISO-8601 timestamp that is well past the 24-hour TTL."""
        return (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat()

    def _future(self, hours: int = 1) -> str:
        """Return an ISO-8601 timestamp that has NOT expired yet."""
        return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()

    def test_returns_zero_when_nothing_expired(self, db):
        q = pkg("storage.queries")
        conv_id = _make_dm_conv(db)
        # Message with a future expiry — should NOT be deleted.
        _make_message(db, conv_id, expires_at=self._future())
        deleted = q.purge_expired_messages(db, now_iso=datetime.now(UTC).isoformat())
        assert deleted == 0

    def test_deletes_expired_unpinned_messages(self, db):
        q = pkg("storage.queries")
        conv_id = _make_dm_conv(db)
        # Two expired messages.
        _make_message(db, conv_id, expires_at=self._far_past())
        _make_message(db, conv_id, expires_at=self._far_past())
        deleted = q.purge_expired_messages(db, now_iso=datetime.now(UTC).isoformat())
        assert deleted == 2
        remaining = db.execute(
            "SELECT * FROM messages WHERE conversation_id = ?", (conv_id,)
        ).fetchall()
        assert len(remaining) == 0

    def test_pinned_messages_survive_purge(self, db):
        """
        Pinned messages are the admin escape hatch for the 404 vibe.
        They must NOT be deleted even when their TTL has expired.
        """
        q = pkg("storage.queries")
        conv_id = _make_dm_conv(db)
        # Expired but pinned — must survive.
        _make_message(db, conv_id, expires_at=self._far_past(), is_pinned=1)
        deleted = q.purge_expired_messages(db, now_iso=datetime.now(UTC).isoformat())
        assert deleted == 0
        row = db.execute("SELECT * FROM messages WHERE is_pinned = 1").fetchone()
        assert row is not None

    def test_messages_without_expires_at_never_purged(self, db):
        """
        Messages sent outside the 404 vibe have expires_at = NULL.
        They must never be touched by the purge job, regardless of age.
        """
        q = pkg("storage.queries")
        conv_id = _make_dm_conv(db)
        # Regular text message — no TTL.
        _make_message(db, conv_id, expires_at=None)
        deleted = q.purge_expired_messages(db, now_iso=datetime.now(UTC).isoformat())
        assert deleted == 0

    def test_mixed_batch_only_deletes_eligible_rows(self, db):
        """
        Four messages:
          A — expired, not pinned   → deleted
          B — expired, pinned       → kept
          C — not yet expired       → kept
          D — no expiry (non-404)   → kept
        Only message A should be removed.
        """
        q = pkg("storage.queries")
        conv_id = _make_dm_conv(db)
        id_a = _make_message(db, conv_id, expires_at=self._far_past(), is_pinned=0)
        id_b = _make_message(db, conv_id, expires_at=self._far_past(), is_pinned=1)
        id_c = _make_message(db, conv_id, expires_at=self._future())
        id_d = _make_message(db, conv_id, expires_at=None)

        deleted = q.purge_expired_messages(db, now_iso=datetime.now(UTC).isoformat())
        assert deleted == 1

        remaining_ids = {
            row["id"]
            for row in db.execute("SELECT id FROM messages").fetchall()
        }
        assert id_a not in remaining_ids
        assert {id_b, id_c, id_d} == remaining_ids
