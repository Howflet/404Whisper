"""
api/routes/groups.py — Group endpoints.

  POST   /api/groups                          — create group + auto-create conversation
  GET    /api/groups/{id}                     — group details + member list
  PATCH  /api/groups/{id}                     — rename or change vibe (with cooldown)
  POST   /api/groups/{id}/members             — add members
  DELETE /api/groups/{id}/members/{sessionId} — remove a member
  POST   /api/groups/{id}/leave               — leave the group

Vibe cooldown (data contract § OQ-1):
  - Any vibe change sets vibe_cooldown_until = now + 300 s (5 minutes).
  - A second change within that window returns 409 VIBE_COOLDOWN_ACTIVE.
  - Clearing the vibe (setting to null) bypasses the cooldown.

Session ID validation:
  - 66 lowercase hex chars, '05' prefix.
  - Applied to memberSessionIds on create and POST /members.
"""
from __future__ import annotations

import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from importlib import import_module

_db_module = import_module("404whisper.storage.db")
_queries   = import_module("404whisper.storage.queries")
_ws        = import_module("404whisper.api.ws")          # WebSocket broadcast manager
_vibes     = import_module("404whisper.api.schemas.vibes")  # vibe classification sets

get_db = _db_module.get_db
DbConn = Annotated[sqlite3.Connection, Depends(get_db)]

router = APIRouter()

UTC = timezone.utc

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SESSION_ID_RE = re.compile(r"^05[0-9a-f]{64}$")


def _is_valid_session_id(s: str) -> bool:
    return bool(_SESSION_ID_RE.match(s))


def _generate_group_session_id() -> str:
    """
    Generate a random 66-char hex Session ID for the new group.
    In production this would be a real X25519 keypair — here we generate
    a random placeholder until Layer 5 (groups crypto) is implemented.
    """
    return "05" + secrets.token_hex(32)


def _group_to_response(group_row: dict, member_count: int) -> dict:
    """Group summary shape (used for POST and PATCH responses)."""
    return {
        "id":               group_row["id"],
        "groupSessionId":   group_row["group_session_id"],
        "name":             group_row["name"],
        "memberCount":      member_count,
        "vibe":             group_row["vibe"],
        "vibeCooldownUntil": group_row["vibe_cooldown_until"],
        "createdAt":        group_row["created_at"],
    }


def _member_to_response(row: dict) -> dict:
    return {
        "sessionId": row["session_id"],
        "isAdmin":   bool(row["is_admin"]),
        "joinedAt":  row["joined_at"],
    }


def _fetch_group(db: sqlite3.Connection, group_id: int) -> dict | None:
    """Return a group row as a dict, or None if it doesn't exist."""
    row = db.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
    return dict(row) if row else None


def _group_exists(db: sqlite3.Connection, group_id: int) -> bool:
    """Return True if a group with this id exists."""
    return db.execute("SELECT id FROM groups WHERE id = ?", (group_id,)).fetchone() is not None


def _check_vibe_cooldown(group_row: dict) -> JSONResponse | None:
    """
    Return a 409 response if a vibe change is blocked by the cooldown window,
    or None if the change is allowed.
    """
    cooldown_until = group_row.get("vibe_cooldown_until")
    if not cooldown_until:
        return None
    try:
        if datetime.now(UTC) < datetime.fromisoformat(cooldown_until):
            return JSONResponse(
                status_code=409,
                content={"error": {
                    "code": "VIBE_COOLDOWN_ACTIVE",
                    "message": f"Vibe cannot be changed until {cooldown_until}.",
                }},
            )
    except ValueError:
        pass  # malformed timestamp — allow the change
    return None


def _not_found(message: str = "Group not found.") -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "NOT_FOUND", "message": message}},
    )


def _validation_error(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "VALIDATION_ERROR", "message": message}},
    )


def _invalid_session_id() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": {
            "code": "INVALID_SESSION_ID",
            "message": "Session ID must be 66 lowercase hex characters starting with '05'.",
        }},
    )


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CreateGroupRequest(BaseModel):
    """POST /api/groups"""
    name: str
    memberSessionIds: Optional[List[str]] = None

    @field_validator("name")
    @classmethod
    def name_valid(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name is required")
        if len(v) > 64:
            raise ValueError("name must be 64 characters or fewer")
        return v


class PatchGroupRequest(BaseModel):
    """PATCH /api/groups/{id}"""
    name: Optional[str] = None
    vibe: Optional[str] = None   # None means "clear the vibe"

    @field_validator("name")
    @classmethod
    def name_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and (not v.strip() or len(v) > 64):
            raise ValueError("name must be 1–64 characters")
        return v


class AddMembersRequest(BaseModel):
    """POST /api/groups/{id}/members"""
    sessionIds: List[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/groups", status_code=201)
async def create_group(request: CreateGroupRequest, db: DbConn):
    """
    Create a new group and auto-create a conversation linked to it.

    The creating user (looked up from the identities table) is added as an
    admin member automatically. Any additional memberSessionIds are added as
    regular members.

    Returns 400 if name is missing/too long or a memberSessionId is malformed.
    """
    # Validate all member Session IDs up front.
    for sid in (request.memberSessionIds or []):
        if not _is_valid_session_id(sid):
            return _invalid_session_id()

    # Look up the creator from the local identity.
    creator_row = db.execute("SELECT session_id FROM identities LIMIT 1").fetchone()
    creator_session_id = creator_row["session_id"] if creator_row else _generate_group_session_id()

    group_session_id = _generate_group_session_id()

    group_id = _queries.create_group(
        db,
        group_session_id=group_session_id,
        name=request.name,
        created_by_session_id=creator_session_id,
        vibe=None,
    )

    # Auto-create the conversation for this group.
    _queries.create_group_conversation(db, group_id=group_id)

    # Add creator as admin.
    _queries.add_group_member(db, group_id=group_id, session_id=creator_session_id, is_admin=True)

    # Add any extra members as regular members.
    for sid in (request.memberSessionIds or []):
        if sid != creator_session_id:
            _queries.add_group_member(db, group_id=group_id, session_id=sid, is_admin=False)

    member_count = db.execute(
        "SELECT COUNT(*) FROM group_members WHERE group_id = ?", (group_id,)
    ).fetchone()[0]

    group_row = _fetch_group(db, group_id)
    return _group_to_response(group_row, member_count)


@router.get("/groups/{group_id}")
async def get_group(group_id: int, db: DbConn):
    """
    Return group details including the full member list.

    Response includes:
        id, groupSessionId, name, memberCount, vibe, vibeCooldownUntil, createdAt,
        members: [{sessionId, isAdmin, joinedAt}]
    """
    group_row = _fetch_group(db, group_id)
    if group_row is None:
        return _not_found()

    members = _queries.list_group_members(db, group_id=group_id)

    response = _group_to_response(group_row, len(members))
    response["members"] = [_member_to_response(m) for m in members]
    return response


@router.patch("/groups/{group_id}")
async def update_group(group_id: int, request: PatchGroupRequest, db: DbConn):
    """
    Rename a group or change its vibe.

    Vibe cooldown rules (data contract § OQ-1):
      - Any vibe change (to a non-null value) sets a 5-minute cooldown.
      - A second change within the window returns 409 VIBE_COOLDOWN_ACTIVE.
      - Clearing the vibe (vibe=null) bypasses the cooldown check.

    Returns 404 if the group doesn't exist.
    Returns 409 if a vibe change is attempted within the cooldown window.
    """
    group_row = _fetch_group(db, group_id)
    if group_row is None:
        return _not_found()

    updates: dict = {}

    if request.name is not None:
        updates["name"] = request.name

    # Vibe field was explicitly provided (including null to clear).
    if "vibe" in request.model_fields_set:
        new_vibe = request.vibe

        if new_vibe is not None:
            blocked = _check_vibe_cooldown(group_row)
            if blocked:
                return blocked
            cooldown_ts = (datetime.now(UTC) + timedelta(seconds=300)).isoformat()
            updates["vibe"]                = new_vibe
            updates["vibe_changed_at"]     = datetime.now(UTC).isoformat()
            updates["vibe_cooldown_until"] = cooldown_ts
        else:
            updates["vibe"] = None   # clear — no cooldown check needed

    if updates:
        _queries.update_group(db, group_id=group_id, **updates)

    updated = _fetch_group(db, group_id)
    member_count = db.execute(
        "SELECT COUNT(*) FROM group_members WHERE group_id = ?", (group_id,)
    ).fetchone()[0]

    # Broadcast a vibe_changed event whenever the group vibe was actually set
    # (not cleared — clearing is a reset, not a content event).
    if "vibe" in updates and updates["vibe"] is not None:
        # Find the group's conversation so the frontend knows which chat updated.
        conv = _queries.get_conversation_by_group(db, group_id=group_id)
        conv_id = conv["id"] if conv else None

        # Find out who made the change (the local user's session ID).
        changer = db.execute("SELECT session_id FROM identities LIMIT 1").fetchone()
        changer_id = changer["session_id"] if changer else None

        new_vibe = updates["vibe"]
        await _ws.manager.broadcast({
            "event": "vibe_changed",
            "payload": {
                "conversationId":    conv_id,
                "newVibe":           new_vibe,
                "changedBySessionId": changer_id,
                # None until cooldown is actually set; None means no restriction.
                "cooldownUntil":     updates.get("vibe_cooldown_until"),
                # True when the vibe affects messaging behaviour (not just visual style).
                "isBehavioral":      new_vibe in _vibes.BEHAVIORAL_VIBES | _vibes.WILDCARD_VIBES,
            },
        })

    return _group_to_response(updated, member_count)


@router.post("/groups/{group_id}/members")
async def add_group_members(group_id: int, request: AddMembersRequest, db: DbConn):
    """
    Add one or more members to a group.

    Returns 400 for malformed Session IDs.
    Returns 404 if the group doesn't exist.
    Returns 409 if a member is already in the group.
    """
    if not _group_exists(db, group_id):
        return _not_found()

    for sid in request.sessionIds:
        if not _is_valid_session_id(sid):
            return _invalid_session_id()

    for sid in request.sessionIds:
        try:
            _queries.add_group_member(db, group_id=group_id, session_id=sid, is_admin=False)
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                return JSONResponse(
                    status_code=409,
                    content={"error": {
                        "code": "ALREADY_EXISTS",
                        "message": f"{sid} is already a member of this group.",
                    }},
                )
            raise

    return {"ok": True}


@router.delete("/groups/{group_id}/members/{session_id}", status_code=204)
async def remove_group_member(group_id: int, session_id: str, db: DbConn):
    """
    Remove a member from a group.

    Returns 204 on success, 404 if the group or member doesn't exist.
    """
    if not _group_exists(db, group_id):
        return _not_found()

    existing = db.execute(
        "SELECT id FROM group_members WHERE group_id = ? AND session_id = ?",
        (group_id, session_id),
    ).fetchone()
    if existing is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": "Member not found in this group."}},
        )

    _queries.remove_group_member(db, group_id=group_id, session_id=session_id)
    # 204 No Content


@router.post("/groups/{group_id}/leave")
async def leave_group(group_id: int, db: DbConn):
    """
    Leave a group.

    Looks up the local identity's session_id and removes it from the group.
    Returns 404 if the group doesn't exist.
    """
    if not _group_exists(db, group_id):
        return _not_found()

    creator_row = db.execute("SELECT session_id FROM identities LIMIT 1").fetchone()
    if creator_row:
        _queries.remove_group_member(
            db, group_id=group_id, session_id=creator_row["session_id"]
        )

    return {"ok": True}
