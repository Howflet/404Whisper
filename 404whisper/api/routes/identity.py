"""
Layer 8 — API: Identity endpoints.

Routes wired to Layer 1 (identity package) that are now implemented:
  POST /api/identity/new     — generate a fresh identity, return mnemonic once
  POST /api/identity/import  — restore identity from a mnemonic seed phrase
  GET  /api/identity         — return current identity (no private key / mnemonic)
  POST /api/identity/unlock  — verify passphrase against stored keystore
  PATCH /api/identity        — update display name or personal vibe

State note:
    Identity state is kept in module-level variables for now (no DB yet).
    Layer 7 (storage) will replace this with proper DB persistence.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

# Layer 1 imports — all names come from the package we just built.
from importlib import import_module

_identity = import_module("404whisper.identity")
create_identity      = _identity.create_identity
import_from_mnemonic = _identity.import_from_mnemonic
verify_passphrase    = _identity.verify_passphrase

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Keystore path — stored next to the package, in a data/ directory.
# ---------------------------------------------------------------------------
_DATA_DIR    = Path(__file__).parent.parent.parent / "data"
_DATA_DIR.mkdir(exist_ok=True)
KEYSTORE_PATH = _DATA_DIR / "keystore.json"

# ---------------------------------------------------------------------------
# In-memory state (replaced by DB in Layer 7)
# ---------------------------------------------------------------------------
_identity_state: dict | None = None   # set on create or import
_is_locked: bool = True               # True until unlock is called

# ---------------------------------------------------------------------------
# Request / Response schemas (Pydantic validates every incoming JSON body)
# ---------------------------------------------------------------------------


class NewIdentityRequest(BaseModel):
    """Body for POST /api/identity/new"""
    passphrase: str
    displayName: Optional[str] = None

    @field_validator("passphrase")
    @classmethod
    def passphrase_min_length(cls, v: str) -> str:
        # Data contract: passphrase must be at least 8 characters.
        if len(v) < 8:
            raise ValueError("passphrase must be at least 8 characters")
        return v

    @field_validator("displayName")
    @classmethod
    def display_name_max_length(cls, v: Optional[str]) -> Optional[str]:
        # Data contract: display name max 64 characters.
        if v is not None and len(v) > 64:
            raise ValueError("displayName must be 64 characters or fewer")
        return v


class ImportIdentityRequest(BaseModel):
    """Body for POST /api/identity/import"""
    mnemonic: str
    passphrase: str

    @field_validator("passphrase")
    @classmethod
    def passphrase_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("passphrase must be at least 8 characters")
        return v


class UnlockRequest(BaseModel):
    """Body for POST /api/identity/unlock"""
    passphrase: str


class PatchIdentityRequest(BaseModel):
    """Body for PATCH /api/identity"""
    displayName: Optional[str] = None
    personalVibe: Optional[str] = None   # Use sentinel to distinguish "not sent" vs null

    @field_validator("displayName")
    @classmethod
    def display_name_max_length(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 64:
            raise ValueError("displayName must be 64 characters or fewer")
        return v


# Valid aesthetic vibes only — behavioral vibes cannot be personal vibes.
_AESTHETIC_VIBES = {"CAMPFIRE", "NEON", "LIBRARY", "VOID", "SUNRISE"}

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _validation_error(message: str, status: int = 400) -> JSONResponse:
    """Return a standard validation error response."""
    return JSONResponse(
        status_code=status,
        content={"error": {"code": "VALIDATION_ERROR", "message": message}},
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/identity/new", status_code=201)
async def create_new_identity(request: NewIdentityRequest):
    """
    Generate a brand-new Session identity.

    Returns the mnemonic seed phrase ONCE — it is not stored.
    The caller must display it to the user immediately.

    Returns 409 if an identity already exists on this instance.
    """
    global _identity_state, _is_locked

    # Only one identity per instance (data contract).
    if _identity_state is not None:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "IDENTITY_ALREADY_CREATED",
                               "message": "An identity already exists on this device."}},
        )

    result = create_identity(passphrase=request.passphrase, keystore_path=KEYSTORE_PATH)

    _identity_state = {
        "sessionId"   : result["session_id"],
        "displayName" : request.displayName,
        "personalVibe": None,
        "createdAt"   : result["created_at"],
    }
    _is_locked = False   # freshly created — treat as unlocked

    # Mnemonic is returned here and ONLY here.
    return {
        "sessionId" : result["session_id"],
        "mnemonic"  : result["mnemonic"],
        "createdAt" : result["created_at"],
    }


@router.post("/identity/import", status_code=201)
async def import_identity(request: ImportIdentityRequest):
    """
    Restore a Session identity from a mnemonic seed phrase.

    Returns 409 if an identity already exists.
    Returns 422 if the mnemonic is invalid or has a bad checksum.
    """
    global _identity_state, _is_locked

    if _identity_state is not None:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "IDENTITY_ALREADY_CREATED",
                               "message": "An identity already exists on this device."}},
        )

    MnemonicDecodeError = _identity.MnemonicDecodeError
    try:
        result = import_from_mnemonic(
            mnemonic=request.mnemonic,
            passphrase=request.passphrase,
            keystore_path=KEYSTORE_PATH,
        )
    except MnemonicDecodeError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "SEED_PHRASE_INVALID", "message": str(exc)}},
        )

    _identity_state = {
        "sessionId"   : result["session_id"],
        "displayName" : None,
        "personalVibe": None,
        "createdAt"   : result["created_at"],
    }
    _is_locked = False

    # Mnemonic is NOT echoed back on import (data contract).
    return {
        "sessionId": result["session_id"],
        "createdAt": result["created_at"],
    }


@router.get("/identity")
async def get_identity():
    """
    Return the current identity (no private key, no mnemonic — ever).

    Returns 404 if no identity has been created yet.
    """
    if _identity_state is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": "No identity found."}},
        )
    return _identity_state


@router.post("/identity/unlock")
async def unlock_identity(request: UnlockRequest):
    """
    Verify passphrase and mark the session as unlocked.

    Returns {"ok": true} on success.
    Returns 400 on wrong passphrase.
    """
    global _is_locked

    if not verify_passphrase(request.passphrase, KEYSTORE_PATH):
        return _validation_error("Incorrect passphrase.", status=400)

    _is_locked = False
    return {"ok": True}


@router.patch("/identity")
async def update_identity(request: PatchIdentityRequest):
    """
    Update display name and / or personal vibe.

    Only aesthetic vibes are allowed as personal vibes (data contract).
    Behavioral vibes (404, CONFESSIONAL, etc.) are group-only.
    """
    global _identity_state

    if _identity_state is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": "No identity found."}},
        )

    # Apply display name update.
    if request.displayName is not None:
        _identity_state = {**_identity_state, "displayName": request.displayName}

    # Apply personal vibe update (None clears it; omitted field is ignored).
    if "personalVibe" in request.model_fields_set:
        vibe = request.personalVibe
        if vibe is not None and vibe not in _AESTHETIC_VIBES:
            return _validation_error(
                f"'{vibe}' cannot be used as a personal vibe. "
                "Only aesthetic vibes (CAMPFIRE, NEON, LIBRARY, VOID, SUNRISE) are allowed."
            )
        _identity_state = {**_identity_state, "personalVibe": vibe}

    return _identity_state
