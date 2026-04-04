"""
Contract tests — Message and Conversation endpoints.

DATA_CONTRACT § Message / Conversation — API Endpoints, Response Schemas,
Error Contract.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import VALID_SESSION_ID, VALID_SESSION_ID_2, VALID_PASSPHRASE


async def _bootstrap(client) -> int:
    """Create an identity, a contact, and a DM conversation. Returns conversation ID."""
    await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
    await client.post("/api/contacts", json={"sessionId": VALID_SESSION_ID_2})
    convs = (await client.get("/api/conversations")).json()
    return convs["conversations"][0]["id"]


@pytest.mark.contract
class TestGetConversations:
    """GET /api/conversations"""

    async def test_empty_returns_200(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        resp = await client.get("/api/conversations")
        assert resp.status_code == 200
        assert "conversations" in resp.json()

    async def test_dm_conversation_appears_after_contact_add(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        await client.post("/api/contacts", json={"sessionId": VALID_SESSION_ID_2})
        data = (await client.get("/api/conversations")).json()
        assert len(data["conversations"]) >= 1

    async def test_conversation_shape(self, client: AsyncClient):
        await _bootstrap(client)
        conv = (await client.get("/api/conversations")).json()["conversations"][0]
        for key in ("id", "type", "unreadCount", "groupVibe", "personalVibeOverride",
                    "vibeCooldownUntil", "accepted", "createdAt", "updatedAt"):
            assert key in conv, f"Expected key '{key}' in conversation object"

    async def test_filter_by_type_dm(self, client: AsyncClient):
        await _bootstrap(client)
        data = (await client.get("/api/conversations", params={"type": "DM"})).json()
        assert all(c["type"] == "DM" for c in data["conversations"])

    async def test_filter_by_type_group(self, client: AsyncClient):
        await _bootstrap(client)
        data = (await client.get("/api/conversations", params={"type": "GROUP"})).json()
        assert all(c["type"] == "GROUP" for c in data["conversations"])


@pytest.mark.contract
class TestGetConversationMessages:
    """GET /api/conversations/{id}/messages"""

    async def test_empty_conversation_returns_empty_list(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        data = (await client.get(f"/api/conversations/{conv_id}/messages")).json()
        assert data["messages"] == []
        assert data["hasMore"] is False

    async def test_nonexistent_conversation_returns_404(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        resp = await client.get("/api/conversations/9999/messages")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_pagination_response_shape(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        data = (await client.get(f"/api/conversations/{conv_id}/messages")).json()
        assert "messages" in data
        assert "hasMore" in data
        assert "nextBefore" in data

    async def test_limit_param_too_large_returns_400(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        resp = await client.get(f"/api/conversations/{conv_id}/messages", params={"limit": 101})
        assert resp.status_code == 400

    async def test_limit_param_zero_returns_400(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        resp = await client.get(f"/api/conversations/{conv_id}/messages", params={"limit": 0})
        assert resp.status_code == 400


@pytest.mark.contract
class TestPostMessagesSend:
    """POST /api/messages/send"""

    async def test_happy_path_returns_201(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        resp = await client.post("/api/messages/send", json={
            "conversationId": conv_id,
            "body": "Hello, world!",
        })
        assert resp.status_code == 201

    async def test_response_is_message_object(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        data = (await client.post("/api/messages/send", json={
            "conversationId": conv_id,
            "body": "Hello!",
        })).json()
        for key in ("id", "conversationId", "senderSessionId", "body", "type",
                    "sentAt", "receivedAt", "expiresAt", "deliverAfter",
                    "isAnonymous", "isSpotlightPinned", "attachment",
                    "groupEventType", "vibeMetadata"):
            assert key in data, f"Expected key '{key}' in MessageObject"

    async def test_message_type_is_text(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        data = (await client.post("/api/messages/send", json={
            "conversationId": conv_id,
            "body": "Hi",
        })).json()
        assert data["type"] == "TEXT"

    async def test_missing_conversation_id_returns_400(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        resp = await client.post("/api/messages/send", json={"body": "Hi"})
        assert resp.status_code == 400

    async def test_unknown_conversation_id_returns_404(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        resp = await client.post("/api/messages/send", json={"conversationId": 9999, "body": "Hi"})
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_empty_body_without_attachment_returns_400(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        resp = await client.post("/api/messages/send", json={"conversationId": conv_id})
        assert resp.status_code == 400

    async def test_body_too_long_returns_400(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        resp = await client.post("/api/messages/send", json={
            "conversationId": conv_id,
            "body": "x" * 2001,
        })
        assert resp.status_code == 400

    async def test_is_anonymous_false_by_default(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        data = (await client.post("/api/messages/send", json={
            "conversationId": conv_id,
            "body": "visible message",
        })).json()
        assert data["isAnonymous"] is False
        assert data["senderSessionId"] is not None

    async def test_sent_message_appears_in_conversation(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        await client.post("/api/messages/send", json={"conversationId": conv_id, "body": "Hello"})
        msgs = (await client.get(f"/api/conversations/{conv_id}/messages")).json()
        assert len(msgs["messages"]) == 1
        assert msgs["messages"][0]["body"] == "Hello"
