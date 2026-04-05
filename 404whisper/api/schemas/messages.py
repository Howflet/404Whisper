"""
api/schemas/messages.py — Pydantic models for message endpoints.

DATA_CONTRACT § Message — Enums, Request/Response Schemas.

MessageType       → CHECK constraint values for messages.type
GroupEventType    → CHECK constraint values for messages.group_event_type
MessageSendRequest → POST /api/messages/send
MessageResponse   → all message endpoints
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# ── enums ──────────────────────────────────────────────────────────────────


class MessageType(str, Enum):
    """
    Valid values for the messages.type column.

    TEXT        — plain text message (most common).
    ATTACHMENT  — a message whose payload is a file (body may be null).
    GROUP_EVENT — system-generated event record (member joined, vibe changed, etc.).
    SYSTEM      — internal status messages not shown to users as chat bubbles.
    """

    TEXT        = "TEXT"
    ATTACHMENT  = "ATTACHMENT"
    GROUP_EVENT = "GROUP_EVENT"
    SYSTEM      = "SYSTEM"


class GroupEventType(str, Enum):
    """
    Valid values for messages.group_event_type.
    Only meaningful when messages.type = 'GROUP_EVENT'.
    """

    MEMBER_JOINED  = "MEMBER_JOINED"
    MEMBER_LEFT    = "MEMBER_LEFT"
    VIBE_CHANGED   = "VIBE_CHANGED"
    GROUP_RENAMED  = "GROUP_RENAMED"


# ── request schemas ────────────────────────────────────────────────────────


class MessageSendRequest(BaseModel):
    """
    POST /api/messages/send — send a new message.

    Either body or attachmentId must be provided (or both).

    Fields:
        conversationId: Primary key of the target conversation (required).
        body:           Text content — 1–2000 characters.
        attachmentId:   Foreign key to an uploaded attachment (Layer 6).
    """

    conversationId: int
    body: Optional[str] = None
    attachmentId: Optional[int] = None  # used in Layer 6 (attachments)

    @field_validator("body")
    @classmethod
    def body_valid(cls, v: Optional[str]) -> Optional[str]:
        """Body must be non-empty (if provided) and at most 2000 characters."""
        if v is not None:
            if not v:
                raise ValueError("body cannot be an empty string")
            if len(v) > 2000:
                raise ValueError("body must be 2000 characters or fewer")
        return v

    @model_validator(mode="after")
    def require_body_or_attachment(self) -> "MessageSendRequest":
        """At least one of body or attachmentId must be present."""
        if self.body is None and self.attachmentId is None:
            raise ValueError(
                "At least one of body or attachmentId must be provided"
            )
        return self


# ── response schemas ───────────────────────────────────────────────────────


class MessageResponse(BaseModel):
    """
    Response shape for all message endpoints.

    Vibe-specific fields:
      expiresAt       → set when the 404 vibe is active (message TTL = 24 h).
      deliverAfter    → set when SLOW_BURN vibe is active (delayed reveal).
      isAnonymous     → True when CONFESSIONAL vibe hid the sender.
      isSpotlightPinned → True when SPOTLIGHT vibe pinned this message.
      vibeMetadata    → extra vibe context (populated in Layer 4).
    """

    id: int
    conversationId: int
    senderSessionId: Optional[str] = None   # None for CONFESSIONAL anonymous messages
    body: Optional[str] = None
    type: str = "TEXT"                       # MessageType value
    sentAt: str
    receivedAt: Optional[str] = None
    expiresAt: Optional[str] = None          # 404 vibe TTL
    deliverAfter: Optional[str] = None       # SLOW_BURN delayed reveal
    isAnonymous: bool = False                # CONFESSIONAL vibe flag
    isSpotlightPinned: bool = False          # SPOTLIGHT vibe flag
    attachment: Optional[Any] = None         # AttachmentResponse (Layer 6)
    groupEventType: Optional[str] = None     # GROUP_EVENT messages only
    vibeMetadata: Optional[Any] = None       # extra vibe context (Layer 4)