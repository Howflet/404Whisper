"""
Integration tests — groups and group_members tables.

DATA_CONTRACT § Group — Entity Definitions and Relationships.
"""
from __future__ import annotations

import sqlite3

import pytest

from tests.conftest import VALID_SESSION_ID, VALID_SESSION_ID_2, VALID_SESSION_ID_3, pkg


def _seed_group(db, name="Night Owls", vibe=None) -> int:
    queries = pkg("storage.queries")
    return queries.create_group(
        db,
        group_session_id=VALID_SESSION_ID,
        name=name,
        created_by_session_id=VALID_SESSION_ID,
        vibe=vibe,
    )


@pytest.mark.integration
class TestGroupsTable:

    def test_insert_group_succeeds(self, db):
        group_id = _seed_group(db)
        row = db.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
        assert row is not None
        assert row["name"] == "Night Owls"

    def test_vibe_defaults_to_null(self, db):
        group_id = _seed_group(db)
        row = db.execute("SELECT vibe FROM groups WHERE id = ?", (group_id,)).fetchone()
        assert row["vibe"] is None

    def test_set_group_vibe(self, db):
        queries = pkg("storage.queries")
        group_id = _seed_group(db)
        queries.update_group(db, group_id=group_id, vibe="CAMPFIRE")
        row = db.execute("SELECT vibe FROM groups WHERE id = ?", (group_id,)).fetchone()
        assert row["vibe"] == "CAMPFIRE"

    def test_invalid_vibe_raises_integrity_error(self, db):
        group_id = _seed_group(db)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE groups SET vibe = 'NONEXISTENT' WHERE id = ?", (group_id,))

    def test_duplicate_group_session_id_raises(self, db):
        _seed_group(db)
        with pytest.raises(sqlite3.IntegrityError):
            _seed_group(db)

    def test_vibe_cooldown_until_stored(self, db):
        queries = pkg("storage.queries")
        group_id = _seed_group(db)
        queries.update_group(db, group_id=group_id, vibe_cooldown_until="2026-04-04T13:00:00Z")
        row = db.execute("SELECT vibe_cooldown_until FROM groups WHERE id = ?", (group_id,)).fetchone()
        assert row["vibe_cooldown_until"] == "2026-04-04T13:00:00Z"

    def test_update_group_name(self, db):
        queries = pkg("storage.queries")
        group_id = _seed_group(db, name="Old Name")
        queries.update_group(db, group_id=group_id, name="New Name")
        row = db.execute("SELECT name FROM groups WHERE id = ?", (group_id,)).fetchone()
        assert row["name"] == "New Name"


@pytest.mark.integration
class TestGroupMembersTable:

    def test_add_member_succeeds(self, db):
        queries = pkg("storage.queries")
        group_id = _seed_group(db)
        queries.add_group_member(db, group_id=group_id, session_id=VALID_SESSION_ID_2, is_admin=False)
        row = db.execute(
            "SELECT * FROM group_members WHERE group_id = ? AND session_id = ?",
            (group_id, VALID_SESSION_ID_2),
        ).fetchone()
        assert row is not None
        assert row["is_admin"] == 0

    def test_add_admin_member(self, db):
        queries = pkg("storage.queries")
        group_id = _seed_group(db)
        queries.add_group_member(db, group_id=group_id, session_id=VALID_SESSION_ID_2, is_admin=True)
        row = db.execute(
            "SELECT is_admin FROM group_members WHERE group_id = ? AND session_id = ?",
            (group_id, VALID_SESSION_ID_2),
        ).fetchone()
        assert row["is_admin"] == 1

    def test_duplicate_member_raises(self, db):
        queries = pkg("storage.queries")
        group_id = _seed_group(db)
        queries.add_group_member(db, group_id=group_id, session_id=VALID_SESSION_ID_2, is_admin=False)
        with pytest.raises(sqlite3.IntegrityError):
            queries.add_group_member(db, group_id=group_id, session_id=VALID_SESSION_ID_2, is_admin=False)

    def test_remove_member_succeeds(self, db):
        queries = pkg("storage.queries")
        group_id = _seed_group(db)
        queries.add_group_member(db, group_id=group_id, session_id=VALID_SESSION_ID_2, is_admin=False)
        queries.remove_group_member(db, group_id=group_id, session_id=VALID_SESSION_ID_2)
        row = db.execute(
            "SELECT * FROM group_members WHERE group_id = ? AND session_id = ?",
            (group_id, VALID_SESSION_ID_2),
        ).fetchone()
        assert row is None

    def test_list_members_returns_all(self, db):
        queries = pkg("storage.queries")
        group_id = _seed_group(db)
        queries.add_group_member(db, group_id=group_id, session_id=VALID_SESSION_ID_2, is_admin=False)
        queries.add_group_member(db, group_id=group_id, session_id=VALID_SESSION_ID_3, is_admin=False)
        members = queries.list_group_members(db, group_id=group_id)
        assert len(members) == 2

    def test_cascade_delete_on_group_delete(self, db):
        """Deleting a group must cascade-delete its members."""
        queries = pkg("storage.queries")
        group_id = _seed_group(db)
        queries.add_group_member(db, group_id=group_id, session_id=VALID_SESSION_ID_2, is_admin=False)
        db.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        members = db.execute(
            "SELECT * FROM group_members WHERE group_id = ?", (group_id,)
        ).fetchall()
        assert len(members) == 0

    def test_foreign_key_to_nonexistent_group_raises(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO group_members (group_id, session_id, is_admin) VALUES (?, ?, ?)",
                (9999, VALID_SESSION_ID_2, 0),
            )
