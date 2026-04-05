"""
api/serializers/messages.py — Message response serialisation.

DATA_CONTRACT § Message — Field Mapping Table, CONFESSIONAL Vibe Rules.

Public surface:
    serialise_message(raw)  → camelCase API response dict from a DB row dict

Key rule implemented here (data contract § OQ-12):
    When is_anonymous=True (CONFESSIONAL vibe), sender_session_id is masked
    to None in the response even if it exists in the DB.  The DB stores the
    real session_id for moderation purposes; the API never reveals it.
"""

from __future__ import annotations

from typing import Any


def serialise_message(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a raw messages DB row to the camelCase API response shape.

    Applies CONFESSIONAL vibe masking: if is_anonymous is truthy, the
    senderSessionId is replaced with None regardless of what the DB holds.

    Args:
        raw: A dict from sqlite3.Row (or any dict with snake_case message keys).
             Expected keys: id, conversation_id, sender_session_id, body, type,
             sent_at, received_at, expires_at, deliver_after, is_anonymous,
             is_spotlight_pinned, attachment_id, group_event_type, active_vibe_at_send.
             Missing keys are treated as None.

    Returns:
        A camelCase dict ready to be returned as a JSON API response.

    Example:
        row = {"sender_session_id": "05abc…", "is_anonymous": True, ...}
        resp = serialise_message(row)
        resp["senderSessionId"]  # → None  (masked by CONFESSIONAL vibe)
    """
    is_anon = bool(raw.get("is_anonymous", False))

    return {
        "id":               raw.get("id"),
        "conversationId":   raw.get("conversation_id"),
        # CONFESSIONAL masking: hide sender when is_anonymous is set.
        "senderSessionId":  None if is_anon else raw.get("sender_session_id"),
        "body":             raw.get("body"),
        "type":             raw.get("type", "TEXT"),
        "sentAt":           raw.get("sent_at"),
        "receivedAt":       raw.get("received_at"),
        "expiresAt":        raw.get("expires_at"),           # 404 vibe TTL
        "deliverAfter":     raw.get("deliver_after"),        # SLOW_BURN delay
        "isAnonymous":      is_anon,
        "isSpotlightPinned": bool(raw.get("is_spotlight_pinned", False)),
        "attachment":       None,    # populated by Layer 6 (attachments)
        "groupEventType":   raw.get("group_event_type"),
        "vibeMetadata":     None,    # populated by Layer 4 (messaging)
    }
