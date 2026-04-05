"""
messaging/chorus.py — CHORUS vibe message-grouping logic.

DATA_CONTRACT § Message — chorusGroupId / CHORUS vibe (OQ-5 resolved: 30-second window).

Under the CHORUS vibe, messages sent within the same 30-second window are
grouped together and revealed simultaneously.  Each group is identified by a
UUID stored in messages.chorus_group_id.

How it works:
  1. The first message in a window generates a new UUID group ID.
  2. Each subsequent message checks whether it falls within 30 seconds of
     when that window started.  If yes, it gets the same group ID.
  3. If the window has expired, a new group ID (and window) is started.

Public surface:
    CHORUS_WINDOW_SECONDS      → 30 (the fixed window constant)
    assign_chorus_group_id(...)→ returns a UUID string for the message's group

Implementation note on db_state:
    assign_chorus_group_id() takes the previous group ID as `db_state`.
    A module-level dict maps each group ID → when that window started.
    In production the DB holds the timing info; in unit tests the in-process
    dict suffices because all calls happen in the same Python session.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional


# ── constants ──────────────────────────────────────────────────────────────

# How long a single CHORUS grouping window stays open (OQ-5 resolved: 30 s).
# This constant is tested directly to prevent accidental drift.
CHORUS_WINDOW_SECONDS: int = 30


# ── module-level window cache ──────────────────────────────────────────────

# Maps chorus_group_id → the datetime when that window was opened.
# Used in unit tests and local (single-process) scenarios.
# The production polling loop should derive this from the DB instead:
#   SELECT MIN(sent_at) FROM messages WHERE chorus_group_id = ?
_window_starts: dict[str, datetime] = {}


# ── public function ────────────────────────────────────────────────────────


def assign_chorus_group_id(
    sent_at: datetime,
    conversation_id: int,
    db_state: Optional[str],
) -> str:
    """
    Return the CHORUS group ID that this message belongs to.

    A CHORUS group ID is a UUID string.  All messages within the same
    30-second window share the same group ID and are revealed together.

    Args:
        sent_at:         When the message was sent (timezone-aware datetime).
        conversation_id: Which conversation the message belongs to.
                         Reserved for future use when the window cache is
                         persisted per-conversation in the DB.
        db_state:        The chorus_group_id of the most recent message in this
                         conversation, or None if there are no prior messages.
                         Pass None to always start a new group.

    Returns:
        A UUID string.  Pass this as `db_state` in the next call to continue
        checking the same window.

    Example:
        # First message starts a new window
        gid = assign_chorus_group_id(sent_at=base, conversation_id=1, db_state=None)

        # Second message 15 s later — same window, same group ID
        gid2 = assign_chorus_group_id(sent_at=base+15s, conversation_id=1, db_state=gid)
        assert gid == gid2

        # Third message 35 s after the first — window expired, new group ID
        gid3 = assign_chorus_group_id(sent_at=base+35s, conversation_id=1, db_state=gid)
        assert gid != gid3
    """
    # If there is a prior group and we know when its window started, check the gap.
    if db_state is not None and db_state in _window_starts:
        window_start = _window_starts[db_state]
        elapsed_seconds = (sent_at - window_start).total_seconds()
        if elapsed_seconds < CHORUS_WINDOW_SECONDS:
            # Still within the window — this message joins the existing group.
            return db_state

    # Start a fresh chorus window.
    new_group_id = str(uuid.uuid4())
    _window_starts[new_group_id] = sent_at
    return new_group_id
