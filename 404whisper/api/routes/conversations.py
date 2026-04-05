"""
api/routes/conversations.py — Conversation endpoints.

  GET  /api/conversations          — list all conversations
  GET  /api/conversations/{id}     — get one conversation
  POST /api/conversations          — create a DM conversation  (501 — needs messaging layer)
  DELETE /api/conversations/{id}   — delete a conversation     (501 — needs messaging layer)

Conversations are created automatically when a group is created (via groups.py)
or will be created by the messaging layer for incoming DMs.
Direct creation via POST is reserved for Layer 4 (messaging).
"""
from __future__ import annotations

import sqlite3
from typing import Annotated, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from importlib import import_module

_db_module = import_module("404whisper.storage.db")
_queries   = import_module("404whisper.storage.queries")

get_db = _db_module.get_db
DbConn = Annotated[sqlite3.Connection, Depends(get_db)]

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _conversation_to_response(row: dict) -> dict:
    """Convert a DB conversations row to the camelCase API response shape."""
    return {
        "id":                   row["id"],
        "type":                 row["type"],
        "contactSessionId":     row["contact_session_id"],
        "groupId":              row["group_id"],
        "lastMessageAt":        row["last_message_at"],
        "unreadCount":          row["unread_count"],
        "groupVibe":            row["group_vibe"],
        "personalVibeOverride": row["personal_vibe_override"],
        "vibeCooldownUntil":    row["vibe_cooldown_until"],
        "accepted":             bool(row["accepted"]),
        "createdAt":            row["created_at"],
        # updatedAt uses last_message_at when available, otherwise created_at
        "updatedAt":            row["last_message_at"] or row["created_at"],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/conversations")
async def list_conversations(db: DbConn, type: Optional[str] = None):  # noqa: A002
    """
    Return all conversations, most-recently-active first.

    Query params:
        type=DM     — only direct-message conversations
        type=GROUP  — only group conversations
        (omit)      — all conversations
    """
    rows = _queries.list_conversations(db)

    conversations = [_conversation_to_response(r) for r in rows]
    if type is not None:
        conversations = [c for c in conversations if c["type"] == type.upper()]

    return {"conversations": conversations}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: int, db: DbConn):
    """
    Return a single conversation by id.
    Returns 404 if it doesn't exist.
    """
    row = _queries.get_conversation(db, conversation_id=conversation_id)
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": "Conversation not found."}},
        )
    return _conversation_to_response(row)


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: int,
    db: DbConn,
    limit: int = 50,
    before: Optional[str] = None,
):
    """
    Return messages in a conversation, newest first, with cursor-based pagination.

    Query params:
        limit  — 1–100 messages per page (default 50). Out of range → 400.
        before — ISO-8601 cursor; returns only messages sent before this time.

    Response:
        messages   — list of message objects (oldest-to-newest within page)
        hasMore    — true if more pages exist before the oldest returned message
        nextBefore — sent_at of the oldest message on this page (use as next cursor)
    """
    if not (1 <= limit <= 100):
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "VALIDATION_ERROR",
                                "message": "limit must be between 1 and 100."}},
        )

    if _queries.get_conversation(db, conversation_id=conversation_id) is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": "Conversation not found."}},
        )

    # Fetch one extra row to detect whether more pages exist.
    rows = _queries.list_messages(db, conversation_id=conversation_id,
                                  before=before, limit=limit + 1)
    has_more   = len(rows) > limit
    page       = rows[:limit]
    next_before = page[-1]["sent_at"] if (has_more and page) else None

    return {
        "messages":   [_message_to_response(m) for m in page],
        "hasMore":    has_more,
        "nextBefore": next_before,
    }


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
        "attachment":       None,   # populated by Layer 6 (attachments)
        "groupEventType":   row.get("group_event_type"),
        "vibeMetadata":     None,   # populated by Layer 4 (messaging)
    }


@router.post("/conversations")
async def create_conversation():
    """Create a DM conversation. Implemented in Layer 4 (messaging)."""
    return JSONResponse(
        status_code=501,
        content={"error": {"code": "NOT_IMPLEMENTED", "message": "Implemented in Layer 4."}},
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: int):
    """Delete a conversation. Implemented in Layer 4 (messaging)."""
    return JSONResponse(
        status_code=501,
        content={"error": {"code": "NOT_IMPLEMENTED", "message": "Implemented in Layer 4."}},
    )
