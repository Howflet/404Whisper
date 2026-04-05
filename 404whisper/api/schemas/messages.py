"""
API Schemas - Messages

Pydantic models for message-related API endpoints.
"""

from enum import Enum


class MessageType(str, Enum):
    """Message type values matching DATA_CONTRACT."""
    TEXT = "TEXT"
    ATTACHMENT = "ATTACHMENT"
    GROUP_EVENT = "GROUP_EVENT"
    SYSTEM = "SYSTEM"


class GroupEventType(str, Enum):
    """Group event type values matching DATA_CONTRACT."""
    MEMBER_JOINED = "MEMBER_JOINED"
    MEMBER_LEFT = "MEMBER_LEFT"
    VIBE_CHANGED = "VIBE_CHANGED"
    GROUP_RENAMED = "GROUP_RENAMED"