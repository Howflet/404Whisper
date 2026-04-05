"""
api/routes/contacts.py — Contact endpoints.

  POST   /api/contacts                — add a contact (user-initiated → accepted=True)
  GET    /api/contacts                — list all contacts (optional ?accepted= filter)
  PATCH  /api/contacts/{sessionId}    — rename or accept a contact
  DELETE /api/contacts/{sessionId}    — hard-delete a contact

Data-contract notes:
  - Deleting a contact does NOT cascade to conversations (assumption A-7).
  - User-initiated contacts (created via POST here) are immediately accepted=True.
  - Incoming contacts from the network arrive via the messaging layer with accepted=False.
  - Session ID format: 66 lowercase hex chars, '05' prefix.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Annotated, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from importlib import import_module

_db_module = import_module("404whisper.storage.db")
_queries   = import_module("404whisper.storage.queries")

get_db = _db_module.get_db

# One line to declare the dependency — every route just adds `db: DbConn`.
DbConn = Annotated[sqlite3.Connection, Depends(get_db)]

router = APIRouter()

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

# A valid Session ID: exactly 66 lowercase hex chars, starting with "05".
_SESSION_ID_RE = re.compile(r"^05[0-9a-f]{64}$")


def _is_valid_session_id(s: str) -> bool:
    return bool(_SESSION_ID_RE.match(s))


def _invalid_session_id_response() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": {
            "code": "INVALID_SESSION_ID",
            "message": "Session ID must be 66 lowercase hex characters starting with '05'.",
        }},
    )


def _not_found_response(message: str = "Contact not found.") -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "NOT_FOUND", "message": message}},
    )


def _fetch_contact(db: sqlite3.Connection, session_id: str) -> dict | None:
    """Return a contact row as a dict, or None if it doesn't exist."""
    row = db.execute(
        "SELECT * FROM contacts WHERE session_id = ?", (session_id,)
    ).fetchone()
    return dict(row) if row else None


def _contact_to_response(row: dict) -> dict:
    """Convert a DB contacts row to the camelCase API response shape."""
    return {
        "sessionId":   row["session_id"],
        "displayName": row["display_name"],
        "accepted":    bool(row["accepted"]),
        "createdAt":   row["created_at"],
    }


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CreateContactRequest(BaseModel):
    """POST /api/contacts"""
    sessionId: str
    displayName: Optional[str] = None

    @field_validator("displayName")
    @classmethod
    def display_name_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 64:
            raise ValueError("displayName must be 64 characters or fewer")
        return v


class PatchContactRequest(BaseModel):
    """PATCH /api/contacts/{sessionId}"""
    displayName: Optional[str] = None
    accepted: Optional[bool] = None

    @field_validator("displayName")
    @classmethod
    def display_name_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 64:
            raise ValueError("displayName must be 64 characters or fewer")
        return v


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/contacts", status_code=201)
async def create_contact(request: CreateContactRequest, db: DbConn):
    """
    Add a new contact.

    Contacts created here (user-initiated) are immediately marked accepted=True.
    Contacts received from the network (incoming requests) arrive with accepted=False
    and are created by the messaging layer, not this endpoint.

    Returns 400 if the Session ID is malformed.
    Returns 409 if the contact already exists.
    """
    if not _is_valid_session_id(request.sessionId):
        return _invalid_session_id_response()

    try:
        _queries.create_contact(
            db,
            session_id=request.sessionId,
            display_name=request.displayName,
            accepted=1,   # user-initiated → immediately accepted
        )
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            return JSONResponse(
                status_code=409,
                content={"error": {
                    "code": "ALREADY_EXISTS",
                    "message": "A contact with this Session ID already exists.",
                }},
            )
        raise

    # Auto-create a DM conversation so the contact is immediately accessible.
    # (Mirrors how POST /api/groups auto-creates a group conversation.)
    _queries.create_dm_conversation(db, contact_session_id=request.sessionId)

    row = _fetch_contact(db, request.sessionId)
    return _contact_to_response(row)


@router.get("/contacts")
async def list_contacts(db: DbConn, accepted: Optional[str] = None):
    """
    Return all contacts.

    Query params:
        accepted=true   — only accepted contacts
        accepted=false  — only pending contacts
        (omit)          — all contacts
    """
    # Convert the string query param to bool/None for the query layer.
    accepted_filter: Optional[bool] = None
    if accepted is not None:
        accepted_filter = accepted.lower() == "true"

    rows = _queries.list_contacts(db, accepted=accepted_filter)
    return {"contacts": [_contact_to_response(r) for r in rows]}


@router.patch("/contacts/{session_id}")
async def update_contact(session_id: str, request: PatchContactRequest, db: DbConn):
    """
    Update a contact's display name and/or accepted status.

    Returns 404 if no contact with this Session ID exists.
    Returns 400 if displayName exceeds 64 characters.
    """
    if _fetch_contact(db, session_id) is None:
        return _not_found_response()

    updates: dict = {}
    if "displayName" in request.model_fields_set:
        updates["display_name"] = request.displayName
    if request.accepted is not None:
        updates["accepted"] = 1 if request.accepted else 0

    if updates:
        _queries.update_contact(db, session_id=session_id, **updates)

    return _contact_to_response(_fetch_contact(db, session_id))


@router.delete("/contacts/{session_id}", status_code=204)
async def delete_contact(session_id: str, db: DbConn):
    """
    Hard-delete a contact.

    Conversation history is preserved — this does NOT cascade to the
    conversations table (data contract assumption A-7).

    Returns 204 on success, 404 if the contact doesn't exist.
    """
    if _fetch_contact(db, session_id) is None:
        return _not_found_response()

    _queries.delete_contact(db, session_id=session_id)
    # 204 No Content — FastAPI returns an empty body automatically.
