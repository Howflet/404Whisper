"""
messaging/delay.py — SLOW_BURN vibe delivery delay logic.

DATA_CONTRACT § Message — deliverAfter / SLOW_BURN vibe (OQ-6 resolved: 60 s).

Under the SLOW_BURN vibe, every message is hidden for 60 seconds after it is
sent.  The client checks deliver_after before displaying a message — if now is
still before deliver_after, the message stays hidden.

Public surface:
    SLOW_BURN_DELAY_SECONDS     → 60 (the fixed delay constant)
    compute_deliver_after(...)   → sent_at + delay_seconds
    is_held(deliver_after, now)  → True while the delay is active
"""

from __future__ import annotations

from datetime import datetime, timedelta


# ── constants ──────────────────────────────────────────────────────────────

# Fixed delivery delay for SLOW_BURN messages (OQ-6 resolved: 60 seconds).
# This constant is tested directly to prevent accidental drift.
SLOW_BURN_DELAY_SECONDS: int = 60


# ── helpers ────────────────────────────────────────────────────────────────


def compute_deliver_after(
    sent_at: datetime,
    delay_seconds: int = SLOW_BURN_DELAY_SECONDS,
) -> datetime:
    """
    Return the datetime at which a SLOW_BURN message becomes visible.

    The message is hidden until now >= deliver_after.

    Args:
        sent_at:       When the message was sent.
        delay_seconds: How long to hold the message (default 60 s).

    Returns:
        A timezone-aware datetime delay_seconds in the future from sent_at.

    Example:
        deliver_after = compute_deliver_after(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
        # → datetime(2026, 4, 4, 12, 1, 0, tzinfo=UTC)  (60 seconds later)
    """
    return sent_at + timedelta(seconds=delay_seconds)


def is_held(deliver_after: datetime, now: datetime) -> bool:
    """
    Return True while the SLOW_BURN delivery delay is still active.

    The message should NOT be shown to recipients until is_held() returns False.

    Args:
        deliver_after: The earliest time the message may be revealed.
        now:           The current UTC datetime.

    Returns:
        True  → message is still in the holding window (keep hidden).
        False → delay has passed (safe to display).

    Example:
        is_held(deliver_after=now + timedelta(seconds=30), now=now)  → True
        is_held(deliver_after=now - timedelta(seconds=1),  now=now)  → False
    """
    return now < deliver_after
