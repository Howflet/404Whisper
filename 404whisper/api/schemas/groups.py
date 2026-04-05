"""
api/schemas/groups.py — Pydantic models for group endpoints.

DATA_CONTRACT § Group — Request/Response Schemas.

GroupCreateRequest    → POST /api/groups
GroupPatchRequest     → PATCH /api/groups/{id}
AddMembersRequest     → POST /api/groups/{id}/members
GroupMemberResponse   → member list inside GroupResponse
GroupResponse         → all group endpoints
"""

from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── validation helper ──────────────────────────────────────────────────────

_SESSION_ID_RE = re.compile(r"^05[0-9a-f]{64}$")


def _validate_session_id(v: str) -> str:
    """Raise ValueError if v is not a valid Session ID."""
    if not _SESSION_ID_RE.match(v):
        raise ValueError(
            "Session ID must be exactly 66 lowercase hex characters starting with '05'"
        )
    return v


# ── request schemas ────────────────────────────────────────────────────────


class GroupCreateRequest(BaseModel):
    """
    POST /api/groups — create a new group.

    The local identity is automatically added as an admin member.
    Additional members can be specified in memberSessionIds.

    Fields:
        name:             Group display name (1–64 chars, required).
        memberSessionIds: Optional list of Session IDs to invite.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    member_session_ids: Optional[List[str]] = Field(None, alias="memberSessionIds")

    @field_validator("name")
    @classmethod
    def name_valid(cls, v: str) -> str:
        """Name must be 1–64 non-blank characters."""
        if not v or not v.strip():
            raise ValueError("name is required and cannot be blank")
        if len(v) > 64:
            raise ValueError("name must be 64 characters or fewer")
        return v

    @field_validator("member_session_ids", mode="before")
    @classmethod
    def member_ids_valid(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate each Session ID in the member list."""
        if v is not None:
            for sid in v:
                _validate_session_id(sid)
        return v


class GroupPatchRequest(BaseModel):
    """
    PATCH /api/groups/{id} — rename a group or change its vibe.

    Both fields are optional — send only what you want to change.
    Setting vibe to null clears the current vibe (no cooldown check on clear).
    """

    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = None
    vibe: Optional[str] = None  # None means "clear vibe" when explicitly sent

    @field_validator("name")
    @classmethod
    def name_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v.strip():
                raise ValueError("name cannot be blank")
            if len(v) > 64:
                raise ValueError("name must be 64 characters or fewer")
        return v


class AddMembersRequest(BaseModel):
    """POST /api/groups/{id}/members — add one or more members."""

    model_config = ConfigDict(populate_by_name=True)

    session_ids: List[str] = Field(alias="sessionIds")

    @field_validator("session_ids", mode="before")
    @classmethod
    def session_ids_valid(cls, v: List[str]) -> List[str]:
        for sid in v:
            _validate_session_id(sid)
        return v


# ── response schemas ───────────────────────────────────────────────────────


class GroupMemberResponse(BaseModel):
    """A single member entry inside a GroupResponse."""

    sessionId: str    # Member's Session ID
    isAdmin: bool     # True if the member has admin privileges
    joinedAt: str     # ISO-8601 timestamp of when they joined


class GroupResponse(BaseModel):
    """
    Response shape for all group endpoints.

    members is included in GET /api/groups/{id} responses.
    It may be omitted (empty list) in list/create responses to keep payloads small.
    """

    id: int                          # Internal primary key
    groupSessionId: str              # 66-char hex on-network Session ID for the group
    name: str                        # Human-readable group name
    vibe: Optional[str] = None       # Current active vibe, nullable
    vibeCooldownUntil: Optional[str] = None  # ISO-8601 timestamp; vibe can't change before this
    members: List[GroupMemberResponse] = []  # Full member list (GET endpoint only)
    createdAt: str                   # When the group was created
    updatedAt: str                   # When the group was last modified
