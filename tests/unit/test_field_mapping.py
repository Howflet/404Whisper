"""
Unit tests — field mapping.

Verifies that Pydantic response models serialise internal snake_case field
names to the camelCase API field names defined in DATA_CONTRACT § Field
Mapping Table.

No database, no HTTP client.
"""
from __future__ import annotations

import pytest

from tests.conftest import VALID_SESSION_ID, pkg


def _to_dict(pydantic_obj) -> dict:
    """Return a response-mode dict (alias=True for camelCase export)."""
    try:
        # Pydantic v2
        return pydantic_obj.model_dump(by_alias=True)
    except AttributeError:
        # Pydantic v1
        return pydantic_obj.dict(by_alias=True)


class TestIdentityFieldMapping:
    """DATA_CONTRACT § Field Mapping Table — Identity fields."""

    @pytest.fixture(autouse=True)
    def _import(self):
        self.schemas = pkg("api.schemas.identity")

    def test_session_id_serialises_to_camel_case(self):
        resp = self.schemas.IdentityResponse(
            sessionId=VALID_SESSION_ID,
            displayName=None,
            personalVibe=None,
            createdAt="2026-04-04T12:00:00Z",
        )
        data = _to_dict(resp)
        assert "sessionId" in data
        assert "session_id" not in data

    def test_display_name_serialises_to_camel_case(self):
        resp = self.schemas.IdentityResponse(
            sessionId=VALID_SESSION_ID,
            displayName="Alice",
            personalVibe=None,
            createdAt="2026-04-04T12:00:00Z",
        )
        data = _to_dict(resp)
        assert "displayName" in data
        assert "display_name" not in data

    def test_personal_vibe_serialises_to_camel_case(self):
        resp = self.schemas.IdentityResponse(
            sessionId=VALID_SESSION_ID,
            displayName=None,
            personalVibe="CAMPFIRE",
            createdAt="2026-04-04T12:00:00Z",
        )
        data = _to_dict(resp)
        assert "personalVibe" in data
        assert "personal_vibe" not in data

    def test_created_at_serialises_to_camel_case(self):
        resp = self.schemas.IdentityResponse(
            sessionId=VALID_SESSION_ID,
            displayName=None,
            personalVibe=None,
            createdAt="2026-04-04T12:00:00Z",
        )
        data = _to_dict(resp)
        assert "createdAt" in data
        assert "created_at" not in data


class TestContactFieldMapping:
    """DATA_CONTRACT § Field Mapping Table — Contact fields."""

    @pytest.fixture(autouse=True)
    def _import(self):
        self.schemas = pkg("api.schemas.contacts")

    def test_contact_response_uses_camel_case(self):
        resp = self.schemas.ContactResponse(
            sessionId=VALID_SESSION_ID,
            displayName="Bob",
            accepted=True,
            createdAt="2026-04-04T12:00:00Z",
            updatedAt="2026-04-04T12:00:00Z",
        )
        data = _to_dict(resp)
        for snake_key in ("session_id", "display_name", "created_at", "updated_at"):
            assert snake_key not in data, f"snake_case key '{snake_key}' leaked into response"
        for camel_key in ("sessionId", "displayName", "createdAt", "updatedAt"):
            assert camel_key in data, f"camelCase key '{camel_key}' missing from response"


class TestMessageFieldMapping:
    """DATA_CONTRACT § Field Mapping Table — Message fields."""

    @pytest.fixture(autouse=True)
    def _import(self):
        self.schemas = pkg("api.schemas.messages")

    def test_message_response_uses_camel_case(self):
        resp = self.schemas.MessageResponse(
            id=1,
            conversationId=1,
            senderSessionId=VALID_SESSION_ID,
            body="hello",
            type="TEXT",
            sentAt="2026-04-04T12:00:00Z",
            receivedAt=None,
            expiresAt=None,
            deliverAfter=None,
            isAnonymous=False,
            isSpotlightPinned=False,
            attachment=None,
            groupEventType=None,
            vibeMetadata=None,
        )
        data = _to_dict(resp)
        expected_camel_keys = [
            "id", "conversationId", "senderSessionId", "body", "type",
            "sentAt", "receivedAt", "expiresAt", "deliverAfter",
            "isAnonymous", "isSpotlightPinned", "attachment",
            "groupEventType", "vibeMetadata",
        ]
        for key in expected_camel_keys:
            assert key in data, f"Expected camelCase key '{key}' in MessageResponse"

    def test_snake_case_keys_absent_from_message_response(self):
        resp = self.schemas.MessageResponse(
            id=1,
            conversationId=1,
            senderSessionId=VALID_SESSION_ID,
            body="hello",
            type="TEXT",
            sentAt="2026-04-04T12:00:00Z",
            receivedAt=None,
            expiresAt=None,
            deliverAfter=None,
            isAnonymous=False,
            isSpotlightPinned=False,
            attachment=None,
            groupEventType=None,
            vibeMetadata=None,
        )
        data = _to_dict(resp)
        snake_keys = [
            "sender_session_id", "sent_at", "received_at", "expires_at",
            "deliver_after", "is_anonymous", "is_spotlight_pinned",
            "group_event_type", "vibe_metadata",
        ]
        for key in snake_keys:
            assert key not in data, f"snake_case key '{key}' must not appear in API response"


class TestGroupFieldMapping:
    """DATA_CONTRACT § Field Mapping Table — Group fields."""

    @pytest.fixture(autouse=True)
    def _import(self):
        self.schemas = pkg("api.schemas.groups")

    def test_group_response_uses_camel_case(self):
        resp = self.schemas.GroupResponse(
            id=1,
            groupSessionId=VALID_SESSION_ID,
            name="Night Owls",
            vibe=None,
            vibeCooldownUntil=None,
            members=[],
            createdAt="2026-04-04T12:00:00Z",
            updatedAt="2026-04-04T12:00:00Z",
        )
        data = _to_dict(resp)
        assert "groupSessionId" in data
        assert "group_session_id" not in data
        assert "vibeCooldownUntil" in data
        assert "vibe_cooldown_until" not in data
