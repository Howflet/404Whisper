"""
Identity API Routes

Handles user identity creation, import, and management.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import os
import sys
sys.path.append(os.path.dirname(__file__) + '/../..')
from identity import create_identity, load_identity, import_from_mnemonic
from identity.keystore import Keystore
from identity.mnemonic import encode_mnemonic

router = APIRouter()

# Keystore path
KEYSTORE_PATH = os.path.join(os.path.dirname(__file__), '../../data/keystore.json')
os.makedirs(os.path.dirname(KEYSTORE_PATH), exist_ok=True)

class IdentityResponse(BaseModel):
    sessionId: str
    displayName: Optional[str] = None
    personalVibe: Optional[str] = None
    createdAt: str

class NewIdentityRequest(BaseModel):
    displayName: Optional[str] = None
    passphrase: str

class NewIdentityResponse(BaseModel):
    sessionId: str
    mnemonic: str

class ImportIdentityRequest(BaseModel):
    mnemonic: str
    displayName: Optional[str] = None
    passphrase: str

class UnlockRequest(BaseModel):
    passphrase: str

# Global state (in production, use proper session management)
current_identity = None
is_locked = True

@router.get("/identity")
async def get_identity() -> IdentityResponse:
    """Get current user identity"""
    if current_identity is None:
        return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND", "message": "No identity found"}})
    if is_locked:
        return JSONResponse(status_code=423, content={"error": {"code": "IDENTITY_LOCKED", "message": "Keystore is locked; client must POST /api/identity/unlock first"}})
    return current_identity

@router.post("/identity/new")
async def create_new_identity_endpoint(request: NewIdentityRequest) -> NewIdentityResponse:
    """Create a new identity"""
    global current_identity, is_locked

    # Generate new identity
    session_id = create_identity(request.passphrase, KEYSTORE_PATH)

    # Generate mnemonic
    keystore = Keystore(KEYSTORE_PATH)
    private_key = keystore.load_key(request.passphrase)
    mnemonic = encode_mnemonic(private_key)

    current_identity = IdentityResponse(
        sessionId=session_id,
        displayName=request.displayName,
        personalVibe=None,
        createdAt="2026-04-04T00:00:00Z"
    )
    is_locked = True  # Keystore starts locked

    return NewIdentityResponse(sessionId=session_id, mnemonic=mnemonic)

@router.post("/identity/import")
async def import_identity_endpoint(request: ImportIdentityRequest) -> IdentityResponse:
    """Import identity from mnemonic"""
    global current_identity, is_locked

    session_id = import_from_mnemonic(request.mnemonic, request.passphrase, KEYSTORE_PATH)

    current_identity = IdentityResponse(
        sessionId=session_id,
        displayName=request.displayName,
        personalVibe=None,
        createdAt="2026-04-04T00:00:00Z"
    )
    is_locked = True

    return current_identity

@router.post("/identity/unlock")
async def unlock_identity_endpoint(request: UnlockRequest):
    """Unlock keystore with passphrase"""
    global is_locked

    session_id = load_identity(request.passphrase, KEYSTORE_PATH)
    if session_id is None:
        return JSONResponse(status_code=401, content={"error": {"code": "INVALID_PASSPHRASE", "message": "Invalid passphrase"}})

    is_locked = False
    return {"ok": True}

@router.patch("/identity")
async def update_identity_endpoint(data: dict):
    """Update identity settings"""
    # TODO: Implement
    return JSONResponse(status_code=501, content={"error": {"code": "NOT_IMPLEMENTED", "message": "Not implemented"}})