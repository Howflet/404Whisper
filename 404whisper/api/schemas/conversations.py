"""
API Schemas - Conversations

Pydantic models for conversation-related API endpoints.
"""

from enum import Enum


class ConversationType(str, Enum):
    """Conversation type values matching DATA_CONTRACT."""
    DM = "DM"
    GROUP = "GROUP"