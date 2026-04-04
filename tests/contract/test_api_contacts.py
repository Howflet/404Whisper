"""
Contract tests — Contact endpoints.

DATA_CONTRACT § Contact — API Endpoints, Request/Response Schemas, Error Contract.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import (
    VALID_SESSION_ID,
    VALID_SESSION_ID_2,
    VALID_SESSION_ID_3,
    VALID_PASSPHRASE,
    INVALID_SESSION_IDS,
    LONG_DISPLAY_NAME,
)


async def _seed_identity(client):
    await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})


async def _seed_contact(client, session_id=VALID_SESSION_ID_2, display_name="Bob"):
    return await client.post("/api/contacts", json={"sessionId": session_id, "displayName": display_name})


@pytest.mark.contract
class TestPostContacts:
    """POST /api/contacts"""

    async def test_happy_path_returns_201(self, client: AsyncClient):
        await _seed_identity(client)
        resp = await _seed_contact(client)
        assert resp.status_code == 201

    async def test_response_shape(self, client: AsyncClient):
        await _seed_identity(client)
        data = (await _seed_contact(client)).json()
        for key in ("sessionId", "displayName", "accepted", "createdAt"):
            assert key in data

    async def test_user_initiated_contact_is_accepted(self, client: AsyncClient):
        await _seed_identity(client)
        data = (await _seed_contact(client)).json()
        assert data["accepted"] is True

    @pytest.mark.parametrize("label,bad_id", list(INVALID_SESSION_IDS.items())[:4])
    async def test_invalid_session_id_returns_400(self, client: AsyncClient, label, bad_id):
        await _seed_identity(client)
        resp = await client.post("/api/contacts", json={"sessionId": bad_id})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_SESSION_ID"

    async def test_duplicate_contact_returns_409(self, client: AsyncClient):
        await _seed_identity(client)
        await _seed_contact(client)
        resp = await _seed_contact(client)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "ALREADY_EXISTS"

    async def test_display_name_too_long_returns_400(self, client: AsyncClient):
        await _seed_identity(client)
        resp = await client.post("/api/contacts", json={
            "sessionId": VALID_SESSION_ID_2,
            "displayName": LONG_DISPLAY_NAME,
        })
        assert resp.status_code == 400

    async def test_display_name_optional(self, client: AsyncClient):
        await _seed_identity(client)
        resp = await client.post("/api/contacts", json={"sessionId": VALID_SESSION_ID_2})
        assert resp.status_code == 201
        assert resp.json()["displayName"] is None


@pytest.mark.contract
class TestGetContacts:
    """GET /api/contacts"""

    async def test_empty_list_returns_200(self, client: AsyncClient):
        await _seed_identity(client)
        resp = await client.get("/api/contacts")
        assert resp.status_code == 200
        assert resp.json()["contacts"] == []

    async def test_returns_created_contacts(self, client: AsyncClient):
        await _seed_identity(client)
        await _seed_contact(client, VALID_SESSION_ID_2)
        await _seed_contact(client, VALID_SESSION_ID_3, "Carol")
        data = (await client.get("/api/contacts")).json()
        assert len(data["contacts"]) == 2

    async def test_filter_by_accepted_true(self, client: AsyncClient):
        await _seed_identity(client)
        await _seed_contact(client, VALID_SESSION_ID_2)   # accepted=True (user-initiated)
        data = (await client.get("/api/contacts", params={"accepted": "true"})).json()
        assert all(c["accepted"] is True for c in data["contacts"])

    async def test_filter_by_accepted_false(self, client: AsyncClient):
        await _seed_identity(client)
        await _seed_contact(client, VALID_SESSION_ID_2)   # accepted=True
        data = (await client.get("/api/contacts", params={"accepted": "false"})).json()
        # All user-initiated contacts are accepted; pending list should be empty
        assert all(c["accepted"] is False for c in data["contacts"])


@pytest.mark.contract
class TestPatchContact:
    """PATCH /api/contacts/{sessionId}"""

    async def test_rename_contact(self, client: AsyncClient):
        await _seed_identity(client)
        await _seed_contact(client, display_name="Bob")
        resp = await client.patch(f"/api/contacts/{VALID_SESSION_ID_2}", json={"displayName": "Robert"})
        assert resp.status_code == 200
        assert resp.json()["displayName"] == "Robert"

    async def test_accept_contact(self, client: AsyncClient):
        await _seed_identity(client)
        await _seed_contact(client)
        resp = await client.patch(f"/api/contacts/{VALID_SESSION_ID_2}", json={"accepted": True})
        assert resp.status_code == 200
        assert resp.json()["accepted"] is True

    async def test_nonexistent_contact_returns_404(self, client: AsyncClient):
        await _seed_identity(client)
        resp = await client.patch(f"/api/contacts/{VALID_SESSION_ID_2}", json={"displayName": "X"})
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_display_name_too_long_returns_400(self, client: AsyncClient):
        await _seed_identity(client)
        await _seed_contact(client)
        resp = await client.patch(f"/api/contacts/{VALID_SESSION_ID_2}", json={"displayName": LONG_DISPLAY_NAME})
        assert resp.status_code == 400

    async def test_clear_display_name_with_null(self, client: AsyncClient):
        await _seed_identity(client)
        await _seed_contact(client, display_name="Bob")
        resp = await client.patch(f"/api/contacts/{VALID_SESSION_ID_2}", json={"displayName": None})
        assert resp.status_code == 200
        assert resp.json()["displayName"] is None


@pytest.mark.contract
class TestDeleteContact:
    """DELETE /api/contacts/{sessionId}"""

    async def test_delete_existing_contact_returns_204(self, client: AsyncClient):
        await _seed_identity(client)
        await _seed_contact(client)
        resp = await client.delete(f"/api/contacts/{VALID_SESSION_ID_2}")
        assert resp.status_code == 204

    async def test_delete_nonexistent_contact_returns_404(self, client: AsyncClient):
        await _seed_identity(client)
        resp = await client.delete(f"/api/contacts/{VALID_SESSION_ID_2}")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_contact_absent_after_delete(self, client: AsyncClient):
        await _seed_identity(client)
        await _seed_contact(client)
        await client.delete(f"/api/contacts/{VALID_SESSION_ID_2}")
        data = (await client.get("/api/contacts")).json()
        assert len(data["contacts"]) == 0
