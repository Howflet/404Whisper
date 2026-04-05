"""
api/schemas/identity.py — Pydantic models for identity endpoints.

DATA_CONTRACT § Identity — Request/Response Schemas.

Input models (requests) use camelCase aliases so the JSON body matches
the contract, while exposing snake_case attributes internally.
Response models use camelCase field names directly for clean serialisation.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── helpers ────────────────────────────────────────────────────────────────

_SESSION_ID_RE = re.compile(r"^05[0-9a-f]{64}$")


# ── request schemas ────────────────────────────────────────────────────────


class IdentityCreateRequest(BaseModel):
    """
    POST /api/identity/new — create a new identity from scratch.

    Generates a fresh X25519 keypair and encrypts the seed with the passphrase.
    The mnemonic is returned ONCE in the response and never stored.

    Fields:
        passphrase:  Encrypts the local keystore. Min 8 characters.
        displayName: Optional screen name (1–64 chars, no leading/trailing whitespace).
    """

    # Allow initialisation with either camelCase alias OR snake_case name.
    model_config = ConfigDict(populate_by_name=True)

    passphrase: str
    display_name: Optional[str] = Field(None, alias="displayName")

    @field_validator("passphrase")
    @classmethod
    def passphrase_min_length(cls, v: str) -> str:
        """Passphrase must be at least 8 characters long."""
        if len(v) < 8:
            raise ValueError("passphrase must be at least 8 characters")
        return v

    @field_validator("display_name", mode="before")
    @classmethod
    def display_name_valid(cls, v: Optional[str]) -> Optional[str]:
        """Strip whitespace then validate length. Blank/whitespace-only names are rejected."""
        if v is not None:
            v = v.strip()          # remove leading/trailing whitespace first
            if not v:
                raise ValueError("displayName cannot be blank or whitespace-only")
            if len(v) > 64:
                raise ValueError("displayName must be 64 characters or fewer")
        return v


class IdentityImportRequest(BaseModel):
    """
    POST /api/identity/import — restore an identity from a seed phrase.

    Decodes the 25-word Session mnemonic back to the 32-byte seed,
    re-derives the keypair, and encrypts it into the keystore.

    Fields:
        mnemonic:   25-word Session seed phrase (space-separated).
        passphrase: Encrypts the restored keystore. Min 8 characters.
    """

    model_config = ConfigDict(populate_by_name=True)

    mnemonic: str
    passphrase: str

    @field_validator("passphrase")
    @classmethod
    def passphrase_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("passphrase must be at least 8 characters")
        return v


# ── response schemas ───────────────────────────────────────────────────────


class IdentityResponse(BaseModel):
    """
    Response shape for GET /api/identity and PATCH /api/identity.

    Only public information is returned — the private key and seed phrase
    are NEVER included in any API response.
    """

    sessionId: str        # 66-char hex, '05' prefix — the user's on-network address
    displayName: Optional[str] = None   # human-readable name, nullable
    personalVibe: Optional[str] = None  # aesthetic vibe (CAMPFIRE, NEON, …), nullable
    createdAt: str        # ISO-8601 UTC timestamp