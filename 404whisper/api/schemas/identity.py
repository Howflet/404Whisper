"""
API Schemas - Identity

Pydantic models for identity-related API endpoints.
"""

from pydantic import BaseModel
from typing import Optional


class IdentityResponse(BaseModel):
    """Identity response model."""
    sessionId: str
    displayName: Optional[str] = None
    personalVibe: Optional[str] = None
    createdAt: str