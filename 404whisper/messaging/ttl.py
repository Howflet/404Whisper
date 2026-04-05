"""
messaging/ttl.py — 404 vibe message TTL (Time-To-Live) logic.

DATA_CONTRACT § Message — expiresAt / 404 vibe (OQ-2 resolved: forward-only).

The 404 vibe makes messages self-destruct 24 hours after they were sent.
A background purge job reads expired messages and deletes them from the DB.
Pinned messages (is_pinned=True) are exempt from purging as an escape hatch.

Public surface:
    compute_expires_at(sent_at)          → sent_at + 24 h
    is_expired(expires_at, now)          → True when the TTL has passed
    is_purgeable(expires_at, is_pinned, now) → True when safe to delete
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


# ── constants ──────────────────────────────────────────────────────────────

# How long a 404-vibe message lives before it is eligible for deletion.
# OQ-2 resolved: 24 hours, counted forward from sent_at only.
MESSAGE_TTL_HOURS: int = 24


# ── helpers ────────────────────────────────────────────────────────────────


def compute_expires_at(sent_at: datetime) -> datetime:
    """
    Return the datetime at which a 404-vibe message will expire.

    The TTL is always 24 hours after the message was sent (OQ-2).
    The clock is forward-only — editing or re-reading a message does NOT
    reset or extend the countdown.

    Args:
        sent_at: When the message was sent (timezone-aware datetime).

    Returns:
        A timezone-aware datetime 24 hours in the future from sent_at.

    Example:
        expires = compute_expires_at(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
        # expires == datetime(2026, 4, 5, 12, 0, 0, tzinfo=UTC)
    """
    return sent_at + timedelta(hours=MESSAGE_TTL_HOURS)


def is_expired(expires_at: datetime, now: datetime) -> bool:
    """
    Return True if the message TTL has passed.

    Args:
        expires_at: The computed expiry datetime (from compute_expires_at).
        now:        The current UTC datetime.

    Example:
        is_expired(expires_at=datetime(2026, 4, 4, ...), now=datetime(2026, 4, 5, ...))
        # → True  (the expiry time is in the past)
    """
    return now >= expires_at


def is_purgeable(
    expires_at: Optional[datetime],
    is_pinned: bool,
    now: datetime,
) -> bool:
    """
    Return True when a message is safe to delete by the background purge job.

    A message is purgeable when ALL of the following are true:
      1. expires_at is set — the message was sent under the 404 vibe.
      2. The TTL has passed — now >= expires_at.
      3. is_pinned is False — the admin has not used the escape hatch (OQ-4).

    If expires_at is None the message was never in the 404 vibe and must
    never be automatically deleted, regardless of is_pinned.

    Args:
        expires_at: Expiry datetime, or None if no TTL was set.
        is_pinned:  True when an admin pinned the message to prevent expiry.
        now:        Current UTC datetime.

    Example:
        # Expired, not pinned → delete it
        is_purgeable(expires_at=past_time, is_pinned=False, now=now) → True

        # Expired, but pinned → keep it
        is_purgeable(expires_at=past_time, is_pinned=True, now=now)  → False

        # No TTL at all → never purge
        is_purgeable(expires_at=None, is_pinned=False, now=now)      → False
    """
    if expires_at is None:
        return False       # no TTL → never auto-purge
    if is_pinned:
        return False       # escape hatch engaged — do not delete
    return is_expired(expires_at, now)
