"""
API Schemas - Vibes

Pydantic models for vibe-related API endpoints.
"""

from enum import Enum


class VibeId(str, Enum):
    """Vibe identifiers matching DATA_CONTRACT."""
    CAMPFIRE = "CAMPFIRE"
    NEON = "NEON"
    LIBRARY = "LIBRARY"
    VOID = "VOID"
    SUNRISE = "SUNRISE"
    ERROR_404 = "404"  # Can't start with digit
    CONFESSIONAL = "CONFESSIONAL"
    SLOW_BURN = "SLOW_BURN"
    CHORUS = "CHORUS"
    SPOTLIGHT = "SPOTLIGHT"
    ECHO = "ECHO"
    SCRAMBLE = "SCRAMBLE"