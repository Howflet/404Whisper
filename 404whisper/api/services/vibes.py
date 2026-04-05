"""
api/services/vibes.py — Vibe business rules.

DATA_CONTRACT § Vibe Mode — Classification, Permissions, Cooldown.

This module is the single source of truth for vibe logic.
No database access, no HTTP — pure Python so it's trivially testable.

Public surface:
    is_behavioral(vibe)             → True for behavioral/wildcard vibes
    is_allowed_personal_vibe(vibe)  → True only for aesthetic vibes
    requires_admin(vibe)            → True when only admins can set this vibe
    is_cooldown_active(...)         → True when the vibe-change window is open
    compute_cooldown_until(now)     → now + COOLDOWN_SECONDS
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional


# ── constants ──────────────────────────────────────────────────────────────

# How long (in seconds) a group must wait between vibe changes (OQ-1 resolved).
COOLDOWN_SECONDS: int = 300  # 5 minutes

# Vibe classification sets — mirrors api/schemas/vibes.py but kept here so
# service logic has no dependency on the Pydantic schema layer.
_AESTHETIC_VIBES: frozenset[str] = frozenset({
    "CAMPFIRE", "NEON", "LIBRARY", "VOID", "SUNRISE",
})
_BEHAVIORAL_VIBES: frozenset[str] = frozenset({
    "404", "CONFESSIONAL", "SLOW_BURN", "CHORUS", "SPOTLIGHT", "ECHO",
})
_WILDCARD_VIBES: frozenset[str] = frozenset({"SCRAMBLE"})

# Behavioral and wildcard vibes are both "group-only" — they can't be personal vibes.
_GROUP_ONLY_VIBES: frozenset[str] = _BEHAVIORAL_VIBES | _WILDCARD_VIBES


# ── classification ─────────────────────────────────────────────────────────


def is_behavioral(vibe: str) -> bool:
    """
    Return True if this vibe changes how messages BEHAVE (not just look).

    Behavioral vibes (e.g. 404, SLOW_BURN) and the wildcard SCRAMBLE are
    both considered "behavioral" for permission and classification purposes.

    Aesthetic vibes (CAMPFIRE, NEON, …) return False.

    Example:
        is_behavioral("404")       → True
        is_behavioral("SCRAMBLE")  → True   # wildcard is treated as behavioral
        is_behavioral("CAMPFIRE")  → False
    """
    return vibe in _GROUP_ONLY_VIBES


def is_allowed_personal_vibe(vibe: str) -> bool:
    """
    Return True if this vibe can be set as a user's personal vibe.

    Only aesthetic vibes are allowed as personal vibes.
    Behavioral and wildcard vibes are group-only.

    Example:
        is_allowed_personal_vibe("CAMPFIRE")     → True
        is_allowed_personal_vibe("404")          → False
        is_allowed_personal_vibe("DOES_NOT_EXIST") → False
    """
    return vibe in _AESTHETIC_VIBES


def requires_admin(vibe: str) -> bool:
    """
    Return True when only a group admin is allowed to set this vibe.

    Behavioral vibe changes require admin privileges because they alter
    the behaviour of the group for ALL members.
    Aesthetic vibes (just cosmetic) do not require admin.

    Example:
        requires_admin("404")      → True
        requires_admin("CAMPFIRE") → False
    """
    return is_behavioral(vibe)


# ── cooldown helpers ───────────────────────────────────────────────────────


def is_cooldown_active(
    cooldown_until: Optional[datetime],
    now: datetime,
) -> bool:
    """
    Return True if a vibe change is currently blocked by the cooldown window.

    The cooldown window opens when a vibe is set and closes 5 minutes later.
    If cooldown_until is None there is no active cooldown.

    Args:
        cooldown_until: The datetime after which the next vibe change is allowed.
                        None means no cooldown is in effect.
        now:            The current UTC datetime.

    Example:
        is_cooldown_active(cooldown_until=None, now=datetime.now(UTC))     → False
        is_cooldown_active(cooldown_until=now + timedelta(minutes=3), now) → True
        is_cooldown_active(cooldown_until=now - timedelta(seconds=1), now) → False
    """
    if cooldown_until is None:
        return False
    return now < cooldown_until


def compute_cooldown_until(now: datetime) -> datetime:
    """
    Return the datetime when the cooldown will expire (now + 5 minutes).

    This should be stored in vibe_cooldown_until whenever a non-null vibe
    is set on a group or conversation.

    Args:
        now: Current UTC datetime (pass datetime.now(timezone.utc)).

    Returns:
        A timezone-aware datetime exactly COOLDOWN_SECONDS (300 s) in the future.

    Example:
        ts = compute_cooldown_until(now=datetime.now(timezone.utc))
        # Store ts.isoformat() in the DB, compare with datetime.fromisoformat()
    """
    return now + timedelta(seconds=COOLDOWN_SECONDS)
