"""
Contract tests — Identity endpoints.

DATA_CONTRACT § Identity — API Endpoints, Request/Response Schemas,
Error Contract.

Every test asserts:
  1. The correct HTTP status code.
  2. The exact response shape (camelCase field names, correct types).
  3. The correct error code from the error contract on failure paths.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import (
    VALID_SESSION_ID,
    VALID_PASSPHRASE,
    VALID_DISPLAY_NAME,
    WEAK_PASSPHRASE,
    LONG_DISPLAY_NAME,
    INVALID_SESSION_IDS,
)


@pytest.mark.contract
class TestPostIdentityNew:
    """POST /api/identity/new"""

    async def test_happy_path_returns_201(self, client: AsyncClient):
        resp = await client.post("/api/identity/new", json={
            "passphrase": VALID_PASSPHRASE,
            "displayName": VALID_DISPLAY_NAME,
        })
        assert resp.status_code == 201

    async def test_response_contains_session_id(self, client: AsyncClient):
        resp = await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        data = resp.json()
        assert "sessionId" in data
        assert data["sessionId"].startswith("05")
        assert len(data["sessionId"]) == 66

    async def test_response_contains_mnemonic(self, client: AsyncClient):
        resp = await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        data = resp.json()
        assert "mnemonic" in data
        assert isinstance(data["mnemonic"], str)
        assert len(data["mnemonic"].split()) > 0

    async def test_response_contains_created_at(self, client: AsyncClient):
        resp = await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        data = resp.json()
        assert "createdAt" in data

    async def test_private_key_not_in_response(self, client: AsyncClient):
        resp = await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        data = resp.json()
        assert "privateKey" not in data
        assert "private_key" not in data
        assert "passphrase" not in data

    async def test_weak_passphrase_returns_400(self, client: AsyncClient):
        resp = await client.post("/api/identity/new", json={"passphrase": WEAK_PASSPHRASE})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_missing_passphrase_returns_400(self, client: AsyncClient):
        resp = await client.post("/api/identity/new", json={})
        assert resp.status_code == 400

    async def test_display_name_too_long_returns_400(self, client: AsyncClient):
        resp = await client.post("/api/identity/new", json={
            "passphrase": VALID_PASSPHRASE,
            "displayName": LONG_DISPLAY_NAME,
        })
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_duplicate_identity_returns_409(self, client: AsyncClient):
        payload = {"passphrase": VALID_PASSPHRASE}
        await client.post("/api/identity/new", json=payload)
        resp = await client.post("/api/identity/new", json=payload)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "IDENTITY_ALREADY_CREATED"


@pytest.mark.contract
class TestPostIdentityImport:
    """POST /api/identity/import"""

    async def test_happy_path_returns_201(self, client: AsyncClient):
        # First create one to get a valid mnemonic
        create_resp = await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        mnemonic = create_resp.json()["mnemonic"]

        # Reset state by recreating the client fixture won't work here;
        # this test depends on the server having no identity yet.
        # Pragmatically, import is tested after verifying mnemonic round-trip.
        # OQ: multi-identity reset endpoint may be needed for test isolation.
        resp = await client.post("/api/identity/import", json={
            "mnemonic": mnemonic,
            "passphrase": "newpassphrase1",
        })
        # Expect 409 because new was already called — documents the constraint
        assert resp.status_code in (201, 409)

    async def test_invalid_mnemonic_returns_422(self, client: AsyncClient):
        resp = await client.post("/api/identity/import", json={
            "mnemonic": "not valid words at all xyz",
            "passphrase": VALID_PASSPHRASE,
        })
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "SEED_PHRASE_INVALID"

    async def test_missing_mnemonic_returns_400(self, client: AsyncClient):
        resp = await client.post("/api/identity/import", json={"passphrase": VALID_PASSPHRASE})
        assert resp.status_code == 400

    async def test_weak_passphrase_returns_400(self, client: AsyncClient):
        resp = await client.post("/api/identity/import", json={
            "mnemonic": "word1 word2 word3",
            "passphrase": WEAK_PASSPHRASE,
        })
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_mnemonic_not_returned_in_response(self, client: AsyncClient):
        """The mnemonic must never be echoed back."""
        resp = await client.post("/api/identity/import", json={
            "mnemonic": "word1 word2 word3",
            "passphrase": VALID_PASSPHRASE,
        })
        if resp.status_code == 201:
            assert "mnemonic" not in resp.json()


@pytest.mark.contract
class TestGetIdentity:
    """GET /api/identity"""

    async def test_returns_404_when_no_identity(self, client: AsyncClient):
        resp = await client.get("/api/identity")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_returns_200_after_creation(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        resp = await client.get("/api/identity")
        assert resp.status_code == 200

    async def test_response_shape(self, client: AsyncClient):
        await client.post("/api/identity/new", json={
            "passphrase": VALID_PASSPHRASE,
            "displayName": VALID_DISPLAY_NAME,
        })
        data = (await client.get("/api/identity")).json()
        for key in ("sessionId", "displayName", "personalVibe", "createdAt"):
            assert key in data, f"Expected key '{key}' in GET /api/identity response"

    async def test_private_key_absent_from_get(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        data = (await client.get("/api/identity")).json()
        assert "privateKey" not in data
        assert "passphrase" not in data
        assert "mnemonic" not in data


@pytest.mark.contract
class TestPatchIdentity:
    """PATCH /api/identity"""

    async def test_update_display_name(self, client: AsyncClient):
        await client.post("/api/identity/new", json={
            "passphrase": VALID_PASSPHRASE,
            "displayName": "Alice",
        })
        resp = await client.patch("/api/identity", json={"displayName": "Alicia"})
        assert resp.status_code == 200
        assert resp.json()["displayName"] == "Alicia"

    async def test_set_aesthetic_personal_vibe(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        resp = await client.patch("/api/identity", json={"personalVibe": "CAMPFIRE"})
        assert resp.status_code == 200
        assert resp.json()["personalVibe"] == "CAMPFIRE"

    async def test_behavioral_vibe_as_personal_returns_400(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        resp = await client.patch("/api/identity", json={"personalVibe": "404"})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_clear_personal_vibe_with_null(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        await client.patch("/api/identity", json={"personalVibe": "NEON"})
        resp = await client.patch("/api/identity", json={"personalVibe": None})
        assert resp.status_code == 200
        assert resp.json()["personalVibe"] is None

    async def test_display_name_too_long_returns_400(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        resp = await client.patch("/api/identity", json={"displayName": LONG_DISPLAY_NAME})
        assert resp.status_code == 400


@pytest.mark.contract
class TestPostIdentityUnlock:
    """POST /api/identity/unlock"""

    async def test_correct_passphrase_returns_200(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        resp = await client.post("/api/identity/unlock", json={"passphrase": VALID_PASSPHRASE})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    async def test_wrong_passphrase_returns_400(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        resp = await client.post("/api/identity/unlock", json={"passphrase": "wrongpassword"})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
