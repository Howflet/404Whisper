"""
Contract tests — Group endpoints.

DATA_CONTRACT § Group — API Endpoints, Request/Response Schemas,
Error Contract, Vibe permission rules.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import (
    VALID_SESSION_ID,
    VALID_SESSION_ID_2,
    VALID_SESSION_ID_3,
    VALID_PASSPHRASE,
    AESTHETIC_VIBES,
    BEHAVIORAL_VIBES,
    LONG_DISPLAY_NAME,
)


async def _seed_identity(client):
    await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})


async def _seed_contact(client, session_id=VALID_SESSION_ID_2):
    await client.post("/api/contacts", json={"sessionId": session_id})


async def _seed_group(client, name="Night Owls", members=None) -> dict:
    payload = {"name": name}
    if members:
        payload["memberSessionIds"] = members
    resp = await client.post("/api/groups", json=payload)
    return resp


@pytest.mark.contract
class TestPostGroups:
    """POST /api/groups"""

    async def test_happy_path_returns_201(self, client: AsyncClient):
        await _seed_identity(client)
        resp = await _seed_group(client)
        assert resp.status_code == 201

    async def test_response_shape(self, client: AsyncClient):
        await _seed_identity(client)
        data = (await _seed_group(client)).json()
        for key in ("id", "groupSessionId", "name", "memberCount", "vibe", "vibeCooldownUntil", "createdAt"):
            assert key in data, f"Expected key '{key}' in POST /api/groups response"

    async def test_group_session_id_is_valid_session_id_format(self, client: AsyncClient):
        await _seed_identity(client)
        data = (await _seed_group(client)).json()
        gid = data["groupSessionId"]
        assert gid.startswith("05") and len(gid) == 66

    async def test_name_required(self, client: AsyncClient):
        await _seed_identity(client)
        resp = await client.post("/api/groups", json={})
        assert resp.status_code == 400

    async def test_name_too_long_returns_400(self, client: AsyncClient):
        await _seed_identity(client)
        resp = await client.post("/api/groups", json={"name": "G" * 65})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_invalid_member_session_id_returns_400(self, client: AsyncClient):
        await _seed_identity(client)
        resp = await client.post("/api/groups", json={
            "name": "Bad Group",
            "memberSessionIds": ["not-a-valid-id"],
        })
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_SESSION_ID"


@pytest.mark.contract
class TestGetGroup:
    """GET /api/groups/{id}"""

    async def test_returns_group_with_members(self, client: AsyncClient):
        await _seed_identity(client)
        group_id = (await _seed_group(client, members=[VALID_SESSION_ID_2])).json()["id"]
        data = (await client.get(f"/api/groups/{group_id}")).json()
        assert "members" in data
        assert isinstance(data["members"], list)

    async def test_nonexistent_group_returns_404(self, client: AsyncClient):
        await _seed_identity(client)
        resp = await client.get("/api/groups/9999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_member_shape(self, client: AsyncClient):
        await _seed_identity(client)
        group_id = (await _seed_group(client, members=[VALID_SESSION_ID_2])).json()["id"]
        data = (await client.get(f"/api/groups/{group_id}")).json()
        if data["members"]:
            member = data["members"][0]
            for key in ("sessionId", "isAdmin", "joinedAt"):
                assert key in member


@pytest.mark.contract
class TestPatchGroup:
    """PATCH /api/groups/{id}"""

    async def test_rename_group(self, client: AsyncClient):
        await _seed_identity(client)
        group_id = (await _seed_group(client, name="Old Name")).json()["id"]
        resp = await client.patch(f"/api/groups/{group_id}", json={"name": "New Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    async def test_set_aesthetic_vibe_succeeds(self, client: AsyncClient):
        await _seed_identity(client)
        group_id = (await _seed_group(client)).json()["id"]
        resp = await client.patch(f"/api/groups/{group_id}", json={"vibe": "CAMPFIRE"})
        assert resp.status_code == 200
        assert resp.json()["vibe"] == "CAMPFIRE"

    async def test_behavioral_vibe_change_sets_cooldown(self, client: AsyncClient):
        await _seed_identity(client)
        group_id = (await _seed_group(client)).json()["id"]
        resp = await client.patch(f"/api/groups/{group_id}", json={"vibe": "SLOW_BURN"})
        assert resp.status_code == 200
        assert resp.json()["vibeCooldownUntil"] is not None

    async def test_vibe_cooldown_blocks_second_change(self, client: AsyncClient):
        """DATA_CONTRACT: VIBE_COOLDOWN_ACTIVE (409) after a vibe change."""
        await _seed_identity(client)
        group_id = (await _seed_group(client)).json()["id"]
        await client.patch(f"/api/groups/{group_id}", json={"vibe": "CAMPFIRE"})
        resp = await client.patch(f"/api/groups/{group_id}", json={"vibe": "NEON"})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "VIBE_COOLDOWN_ACTIVE"

    async def test_nonexistent_group_returns_404(self, client: AsyncClient):
        await _seed_identity(client)
        resp = await client.patch("/api/groups/9999", json={"name": "X"})
        assert resp.status_code == 404

    async def test_clear_vibe_with_null(self, client: AsyncClient):
        await _seed_identity(client)
        group_id = (await _seed_group(client)).json()["id"]
        await client.patch(f"/api/groups/{group_id}", json={"vibe": "NEON"})
        resp = await client.patch(f"/api/groups/{group_id}", json={"vibe": None})
        assert resp.status_code == 200
        assert resp.json()["vibe"] is None


@pytest.mark.contract
class TestGroupMemberManagement:
    """POST /api/groups/{id}/members and DELETE /api/groups/{id}/members/{sessionId}"""

    async def test_add_member_returns_200(self, client: AsyncClient):
        await _seed_identity(client)
        group_id = (await _seed_group(client)).json()["id"]
        resp = await client.post(
            f"/api/groups/{group_id}/members",
            json={"sessionIds": [VALID_SESSION_ID_2]},
        )
        assert resp.status_code == 200

    async def test_add_duplicate_member_returns_409(self, client: AsyncClient):
        await _seed_identity(client)
        group_id = (await _seed_group(client, members=[VALID_SESSION_ID_2])).json()["id"]
        resp = await client.post(
            f"/api/groups/{group_id}/members",
            json={"sessionIds": [VALID_SESSION_ID_2]},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "ALREADY_EXISTS"

    async def test_add_member_invalid_session_id_returns_400(self, client: AsyncClient):
        await _seed_identity(client)
        group_id = (await _seed_group(client)).json()["id"]
        resp = await client.post(
            f"/api/groups/{group_id}/members",
            json={"sessionIds": ["bad-id"]},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_SESSION_ID"

    async def test_remove_member_returns_204(self, client: AsyncClient):
        await _seed_identity(client)
        group_id = (await _seed_group(client, members=[VALID_SESSION_ID_2])).json()["id"]
        resp = await client.delete(f"/api/groups/{group_id}/members/{VALID_SESSION_ID_2}")
        assert resp.status_code == 204

    async def test_remove_nonexistent_member_returns_404(self, client: AsyncClient):
        await _seed_identity(client)
        group_id = (await _seed_group(client)).json()["id"]
        resp = await client.delete(f"/api/groups/{group_id}/members/{VALID_SESSION_ID_2}")
        assert resp.status_code == 404


@pytest.mark.contract
class TestLeaveGroup:
    """POST /api/groups/{id}/leave"""

    async def test_leave_group_returns_200(self, client: AsyncClient):
        await _seed_identity(client)
        group_id = (await _seed_group(client)).json()["id"]
        resp = await client.post(f"/api/groups/{group_id}/leave")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    async def test_leave_nonexistent_group_returns_404(self, client: AsyncClient):
        await _seed_identity(client)
        resp = await client.post("/api/groups/9999/leave")
        assert resp.status_code == 404
