"""
api/routes/messages.py — Message send endpoint.

  POST /api/messages/send — store and (eventually) dispatch a message

Layer 4 note:
  Right now this only persists the message to the local DB.
  Actual network dispatch (onion routing to the Session swarm) will be
  added in Layer 4 (messaging/send.py).  The contract shape is identical
  whether the message is sent over the network or not.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from importlib import import_module

_db_module = import_module("404whisper.storage.db")
_queries   = import_module("404whisper.storage.queries")

get_db = _db_module.get_db
DbConn = Annotated[sqlite3.Connection, Depends(get_db)]

router = APIRouter()

UTC = timezone.utc

# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------


class SendMessageRequest(BaseModel):
    """POST /api/messages/send"""
    conversationId: int
    body: Optional[str] = None

    @field_validator("body")
    @classmethod
    def body_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 2000:
            raise ValueError("body must be 2000 characters or fewer")
        return v


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/messages/send", status_code=201)
async def send_message(request: SendMessageRequest, db: DbConn):
    """
    Store a new outgoing message in the local DB.

    Validates:
      - conversationId must reference an existing conversation → 404 otherwise
      - body is required (unless an attachment is present) → 400 if both absent
      - body must be ≤ 2000 characters → 400 if exceeded

    Returns the full message object on success (201).

    Layer 4 will add actual network dispatch here without changing the response shape.
    """
    # Verify the conversation exists.
    conv = _queries.get_conversation(db, conversation_id=request.conversationId)
    if conv is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND",
                                "message": "Conversation not found."}},
        )

    # Body is required unless an attachment is provided (attachment layer = Layer 6).
    if not request.body:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "VALIDATION_ERROR",
                                "message": "body is required when no attachment is present."}},
        )

    # Look up the sender's session ID from the local identity.
    identity_row = db.execute("SELECT session_id FROM identities LIMIT 1").fetchone()
    sender_session_id = identity_row["session_id"] if identity_row else None

    sent_at = datetime.now(UTC).isoformat()
    msg_id  = _queries.create_message(
        db,
        conversation_id=request.conversationId,
        sender_session_id=sender_session_id,
        body=request.body,
        type="TEXT",
        sent_at=sent_at,
    )

    # Update the conversation's last_message_at so it sorts correctly.
    _queries.update_conversation(db, conversation_id=request.conversationId,
                                  last_message_at=sent_at)

    row = dict(db.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone())
    return _message_to_response(row)


def _message_to_response(row: dict) -> dict:
    """Convert a DB messages row to the camelCase API response shape."""
    return {
        "id":               row["id"],
        "conversationId":   row["conversation_id"],
        "senderSessionId":  row["sender_session_id"],
        "body":             row["body"],
        "type":             row["type"],
        "sentAt":           row["sent_at"],
        "receivedAt":       row.get("received_at"),
        "expiresAt":        row.get("expires_at"),
        "deliverAfter":     row.get("deliver_after"),
        "isAnonymous":      bool(row.get("is_anonymous", 0)),
        "isSpotlightPinned": bool(row.get("is_spotlight_pinned", 0)),
        "attachment":       None,   # populated in Layer 6 (attachments)
        "groupEventType":   row.get("group_event_type"),
        "vibeMetadata":     None,   # populated in Layer 4 (messaging)
    }
