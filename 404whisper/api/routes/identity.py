"""
api/routes/identity.py — Identity endpoints.

  POST /api/identity/new     — create a fresh Session identity
  POST /api/identity/import  — restore from mnemonic seed phrase
  GET  /api/identity         — return current identity (no private key/mnemonic)
  POST /api/identity/unlock  — verify passphrase against stored keystore
  PATCH /api/identity        — update display name or personal vibe

Identity row is persisted to the database so that each test gets a clean
slate via the in-memory DB override, rather than leaking state through a
module-level global.

The keystore file (encrypted private key on disk) is still written to
the filesystem — it is not stored in the DB.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from importlib import import_module

_identity_pkg = import_module("404whisper.identity")
_db_module    = import_module("404whisper.storage.db")
_queries      = import_module("404whisper.storage.queries")

create_identity      = _identity_pkg.create_identity
import_from_mnemonic = _identity_pkg.import_from_mnemonic
verify_passphrase    = _identity_pkg.verify_passphrase
MnemonicDecodeError  = _identity_pkg.MnemonicDecodeError

get_db = _db_module.get_db

# Reusable annotated dependency — declare once, use in every route signature.
DbConn = Annotated[sqlite3.Connection, Depends(get_db)]

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Keystore path — private key lives here, NOT in the DB
# ---------------------------------------------------------------------------

_DATA_DIR     = Path(__file__).parent.parent.parent / "data"
_DATA_DIR.mkdir(exist_ok=True)
KEYSTORE_PATH = _DATA_DIR / "keystore.json"

# ---------------------------------------------------------------------------
# Valid aesthetic vibes (the only ones allowed as personal vibes)
# ---------------------------------------------------------------------------

_AESTHETIC_VIBES = {"CAMPFIRE", "NEON", "LIBRARY", "VOID", "SUNRISE"}

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class NewIdentityRequest(BaseModel):
    """POST /api/identity/new"""
    passphrase: str
    displayName: Optional[str] = None

    @field_validator("passphrase")
    @classmethod
    def passphrase_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("passphrase must be at least 8 characters")
        return v

    @field_validator("displayName")
    @classmethod
    def display_name_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 64:
            raise ValueError("displayName must be 64 characters or fewer")
        return v


class ImportIdentityRequest(BaseModel):
    """POST /api/identity/import"""
    mnemonic: str
    passphrase: str

    @field_validator("passphrase")
    @classmethod
    def passphrase_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("passphrase must be at least 8 characters")
        return v


class UnlockRequest(BaseModel):
    """POST /api/identity/unlock"""
    passphrase: str


class PatchIdentityRequest(BaseModel):
    """PATCH /api/identity"""
    displayName: Optional[str] = None
    personalVibe: Optional[str] = None

    @field_validator("displayName")
    @classmethod
    def display_name_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 64:
            raise ValueError("displayName must be 64 characters or fewer")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validation_error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": "VALIDATION_ERROR", "message": message}},
    )


def _identity_to_response(row: dict) -> dict:
    """Convert a DB identity row to the camelCase API response shape."""
    return {
        "sessionId":    row["session_id"],
        "displayName":  row["display_name"],
        "personalVibe": row["personal_vibe"],
        "createdAt":    row["created_at"],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/identity/new", status_code=201)
async def create_new_identity(
    request: NewIdentityRequest,
    db: DbConn,
):
    """
    Generate a brand-new Session identity.

    Returns the mnemonic seed phrase ONCE — it is not stored anywhere.
    The caller must display it to the user immediately and never log it.
    Returns 409 if an identity already exists on this device.
    """
    # One identity per device.
    existing = db.execute("SELECT session_id FROM identities LIMIT 1").fetchone()
    if existing:
        return JSONResponse(
            status_code=409,
            content={"error": {
                "code": "IDENTITY_ALREADY_CREATED",
                "message": "An identity already exists on this device.",
            }},
        )

    result = create_identity(passphrase=request.passphrase, keystore_path=KEYSTORE_PATH)

    # Persist to DB — display_name and personal_vibe start as NULL.
    _queries.create_identity(
        db,
        session_id=result["session_id"],
        display_name=request.displayName,
    )

    # Mnemonic is returned here and ONLY here.
    return {
        "sessionId": result["session_id"],
        "mnemonic":  result["mnemonic"],
        "createdAt": result["created_at"],
    }


@router.post("/identity/import", status_code=201)
async def import_identity(
    request: ImportIdentityRequest,
    db: DbConn,
):
    """
    Restore a Session identity from a mnemonic seed phrase.

    Returns 409 if an identity already exists.
    Returns 422 if the mnemonic is invalid or has a bad checksum.
    """
    existing = db.execute("SELECT session_id FROM identities LIMIT 1").fetchone()
    if existing:
        return JSONResponse(
            status_code=409,
            content={"error": {
                "code": "IDENTITY_ALREADY_CREATED",
                "message": "An identity already exists on this device.",
            }},
        )

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

    _queries.create_identity(db, session_id=result["session_id"], display_name=None)

    # Mnemonic is NOT echoed back on import.
    return {
        "sessionId": result["session_id"],
        "createdAt": result["created_at"],
    }


@router.get("/identity")
async def get_identity(db: DbConn):
    """
    Return the current identity (no private key, no mnemonic — ever).
    Returns 404 if no identity has been created yet.
    """
    row = db.execute("SELECT * FROM identities LIMIT 1").fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": "No identity found."}},
        )
    return _identity_to_response(dict(row))


@router.post("/identity/unlock")
async def unlock_identity(request: UnlockRequest):
    """
    Verify passphrase against the on-disk keystore.
    Returns {"ok": true} on success, 400 on wrong passphrase.
    """
    if not verify_passphrase(request.passphrase, KEYSTORE_PATH):
        return _validation_error("Incorrect passphrase.", status=400)
    return {"ok": True}


@router.patch("/identity")
async def update_identity(
    request: PatchIdentityRequest,
    db: DbConn,
):
    """
    Update display name and/or personal vibe.

    Only aesthetic vibes (CAMPFIRE, NEON, LIBRARY, VOID, SUNRISE) are allowed
    as personal vibes — behavioral vibes are group-only.
    """
    row = db.execute("SELECT * FROM identities LIMIT 1").fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": "No identity found."}},
        )

    session_id = row["session_id"]
    updates: dict = {}

    if request.displayName is not None:
        updates["display_name"] = request.displayName

    if "personalVibe" in request.model_fields_set:
        vibe = request.personalVibe
        if vibe is not None and vibe not in _AESTHETIC_VIBES:
            return _validation_error(
                f"'{vibe}' cannot be used as a personal vibe. "
                "Only aesthetic vibes (CAMPFIRE, NEON, LIBRARY, VOID, SUNRISE) are allowed."
            )
        updates["personal_vibe"] = vibe

    if updates:
        _queries.update_identity(db, session_id=session_id, **updates)

    updated = db.execute("SELECT * FROM identities WHERE session_id = ?", (session_id,)).fetchone()
    return _identity_to_response(dict(updated))
