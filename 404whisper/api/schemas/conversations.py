"""
api/schemas/conversations.py — Pydantic models for conversation endpoints.

DATA_CONTRACT § Conversation — Enums, Query Parameters, Response Schemas.

ConversationType  → CHECK constraint values for conversations.type
MessageListParams → GET /api/conversations/{id}/messages query params
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# ── enums ──────────────────────────────────────────────────────────────────


class ConversationType(str, Enum):
    """
    Valid values for the conversations.type column.

    DM    — a 1-to-1 direct message conversation between two users.
    GROUP — a group chat with one or more members.
    """

    DM    = "DM"
    GROUP = "GROUP"


# ── query parameter schemas ────────────────────────────────────────────────


class MessageListParams(BaseModel):
    """
    Query parameters for GET /api/conversations/{id}/messages.

    Supports cursor-based pagination so the client loads messages in pages
    without missing items that arrive while the user scrolls.

    Fields:
        limit:  Maximum messages per page. Must be 1–100 (default 50).
        before: ISO-8601 cursor — only return messages sent BEFORE this time.
                Omit to start from the most recent message.
    """

    limit: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Maximum messages to return. 1–100 inclusive.",
    )
    before: Optional[str] = Field(
        default=None,
        description=(
            "ISO-8601 timestamp cursor. Only messages with sentAt < before are returned. "
            "Pass the sentAt of the last message on the previous page to paginate backwards."
        ),
    )