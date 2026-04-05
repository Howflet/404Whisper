"""
api/schemas/contacts.py — Pydantic models for contact endpoints.

DATA_CONTRACT § Contact — Request/Response Schemas.

ContactCreateRequest   → POST /api/contacts
ContactPatchRequest    → PATCH /api/contacts/{sessionId}
ContactResponse        → all contact endpoints
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── validation helper ──────────────────────────────────────────────────────

# A valid Session ID: exactly 66 lowercase hex characters, starting with "05".
_SESSION_ID_RE = re.compile(r"^05[0-9a-f]{64}$")


# ── request schemas ────────────────────────────────────────────────────────


class ContactCreateRequest(BaseModel):
    """
    POST /api/contacts — add a new contact.

    User-initiated contacts are immediately accepted=True.
    Contacts received from the network (incoming DM) arrive via the messaging
    layer with accepted=False.

    Fields:
        sessionId:   66-char hex Session ID of the remote user (required).
        displayName: Optional nickname (1–64 chars).
    """

    # Accept both camelCase aliases (JSON bodies) and snake_case (internal use).
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    display_name: Optional[str] = Field(None, alias="displayName")

    @field_validator("session_id")
    @classmethod
    def session_id_valid(cls, v: str) -> str:
        """Session ID must be 66 lowercase hex chars starting with '05'."""
        if not _SESSION_ID_RE.match(v):
            raise ValueError(
                "sessionId must be exactly 66 lowercase hex characters starting with '05'"
            )
        return v

    @field_validator("display_name")
    @classmethod
    def display_name_valid(cls, v: Optional[str]) -> Optional[str]:
        """Display name must be 1–64 chars if provided."""
        if v is not None and len(v) > 64:
            raise ValueError("displayName must be 64 characters or fewer")
        return v


class ContactPatchRequest(BaseModel):
    """
    PATCH /api/contacts/{sessionId} — update display name or acceptance status.

    Both fields are optional — send only what you want to change.
    Setting displayName to null clears the stored name.
    """

    model_config = ConfigDict(populate_by_name=True)

    display_name: Optional[str] = Field(None, alias="displayName")
    accepted: Optional[bool] = None

    @field_validator("display_name")
    @classmethod
    def display_name_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 64:
            raise ValueError("displayName must be 64 characters or fewer")
        return v


# ── response schemas ───────────────────────────────────────────────────────


class ContactResponse(BaseModel):
    """
    Response shape for all contact endpoints.

    Keys are camelCase per the data contract.
    accepted is a boolean (True = confirmed contact, False = pending request).
    """

    sessionId: str            # Remote user's Session ID
    displayName: Optional[str] = None  # User-assigned nickname
    accepted: bool            # True once the contact has been accepted
    createdAt: str            # When the contact row was created
    updatedAt: str            # When the contact row was last modified
