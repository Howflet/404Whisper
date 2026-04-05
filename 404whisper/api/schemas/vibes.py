"""
api/schemas/vibes.py — Vibe enum and personal-vibe validation.

DATA_CONTRACT § Enums & Constants — VibeId.

VibeId                 → all valid vibe identifiers (aesthetic + behavioral + wildcard).
AESTHETIC_VIBES        → set of aesthetic-only vibes (allowed as personal vibe).
validate_personal_vibe → raises ValueError for non-aesthetic or unknown vibes.
"""

from __future__ import annotations

from enum import Enum

# ── enum ───────────────────────────────────────────────────────────────────


class VibeId(str, Enum):
    """
    Every valid vibe identifier in 404Whisper.

    Aesthetic vibes (CAMPFIRE … SUNRISE):
        Change the visual style of a conversation.
        Can be used as a personal vibe or a group vibe.

    Behavioral vibes (404 … ECHO):
        Change HOW messages work inside a group.
        Group-only — cannot be set as a personal vibe.

    Wildcard (SCRAMBLE):
        Applies a random behavioral vibe each session.
        Treated as behavioral for permission purposes.

    Note: '404' can't be a valid Python identifier (starts with digit),
    so the enum member is named ERROR_404 but its .value is '404'.
    """

    # Aesthetic
    CAMPFIRE     = "CAMPFIRE"
    NEON         = "NEON"
    LIBRARY      = "LIBRARY"
    VOID         = "VOID"
    SUNRISE      = "SUNRISE"

    # Behavioral
    ERROR_404    = "404"          # member name can't start with a digit
    CONFESSIONAL = "CONFESSIONAL"
    SLOW_BURN    = "SLOW_BURN"
    CHORUS       = "CHORUS"
    SPOTLIGHT    = "SPOTLIGHT"
    ECHO         = "ECHO"

    # Wildcard
    SCRAMBLE     = "SCRAMBLE"


# ── vibe classification sets ───────────────────────────────────────────────

# Vibes allowed as a personal vibe (DATA_CONTRACT § OQ-12).
AESTHETIC_VIBES: frozenset[str] = frozenset({
    "CAMPFIRE", "NEON", "LIBRARY", "VOID", "SUNRISE",
})

# Vibes that are group-only (cannot be set as a personal vibe).
BEHAVIORAL_VIBES: frozenset[str] = frozenset({
    "404", "CONFESSIONAL", "SLOW_BURN", "CHORUS", "SPOTLIGHT", "ECHO",
})

WILDCARD_VIBES: frozenset[str] = frozenset({"SCRAMBLE"})

# Group-only = behavioral + wildcard.
GROUP_ONLY_VIBES: frozenset[str] = BEHAVIORAL_VIBES | WILDCARD_VIBES

# All valid vibe values (union of all three sets).
ALL_VIBES: frozenset[str] = AESTHETIC_VIBES | BEHAVIORAL_VIBES | WILDCARD_VIBES


# ── validator ──────────────────────────────────────────────────────────────


def validate_personal_vibe(vibe: str) -> str:
    """
    Validate that a vibe is allowed as a personal vibe.

    Only AESTHETIC vibes can be set as personal vibes.
    Behavioral and wildcard vibes are group-only.

    Args:
        vibe: The vibe string to validate.

    Returns:
        The vibe string unchanged if valid.

    Raises:
        ValueError: if the vibe is unknown or is a group-only vibe.

    Example:
        validate_personal_vibe("CAMPFIRE")   # → "CAMPFIRE"
        validate_personal_vibe("404")        # → raises ValueError
        validate_personal_vibe("INVALID")    # → raises ValueError
    """
    if vibe not in ALL_VIBES:
        raise ValueError(
            f"'{vibe}' is not a valid vibe. "
            f"Valid vibes: {sorted(ALL_VIBES)}"
        )
    if vibe not in AESTHETIC_VIBES:
        raise ValueError(
            f"'{vibe}' is a group-only vibe and cannot be used as a personal vibe. "
            f"Personal vibes must be one of: {sorted(AESTHETIC_VIBES)}"
        )
    return vibe