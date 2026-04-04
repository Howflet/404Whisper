"""
Root conftest.py — shared constants, helpers, and fixtures for the entire
404Whisper test suite.

Import note
-----------
The application package is in a directory named '404whisper', which is not a
valid Python identifier (leading digit).  All imports from the app must use
``importlib.import_module('404whisper.<subpath>')``.  A helper ``pkg()`` is
provided here to keep test files concise.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so importlib can find '404whisper'.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def pkg(subpath: str = ""):
    """Import ``404whisper`` or a submodule.

    Usage::

        app = pkg("api.app").app
        schemas = pkg("api.schemas.identity")
    """
    module = "404whisper" + (f".{subpath}" if subpath else "")
    return importlib.import_module(module)


# ---------------------------------------------------------------------------
# Test-data constants — derived directly from the data contract.
# ---------------------------------------------------------------------------

#: A syntactically valid Session ID: 66 lowercase hex chars, '05' prefix.
VALID_SESSION_ID = "057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5b"
VALID_SESSION_ID_2 = "05" + "b" * 64
VALID_SESSION_ID_3 = "05" + "c" * 64

#: Invalid Session IDs mapped to a description of why they fail.
#  Source: DATA_CONTRACT § Global Validation Rules
INVALID_SESSION_IDS: dict[str, str] = {
    "wrong_prefix":       "06" + "a" * 64,
    "too_short":          "05" + "a" * 63,           # 65 chars total
    "too_long":           "05" + "a" * 65,           # 67 chars total
    "uppercase_hex":      "05" + "A" * 64,
    "non_hex_chars":      "05" + "z" * 64,
    "empty":              "",
    "whitespace_padded":  " " + "05" + "a" * 64,
}

VALID_PASSPHRASE = "hunter2hunter2"
WEAK_PASSPHRASE  = "short7"          # 6 chars — below the 8-char minimum
VALID_DISPLAY_NAME  = "Alice"
LONG_DISPLAY_NAME   = "A" * 65       # 65 chars — exceeds 64-char max
BLANK_DISPLAY_NAME  = ""
WHITESPACE_NAME     = "  Alice  "    # leading/trailing whitespace — invalid

#: Vibe classification lists — sourced from DATA_CONTRACT § Enums & Constants.
AESTHETIC_VIBES  = ["CAMPFIRE", "NEON", "LIBRARY", "VOID", "SUNRISE"]
BEHAVIORAL_VIBES = ["404", "CONFESSIONAL", "SLOW_BURN", "CHORUS", "SPOTLIGHT", "ECHO"]
WILDCARD_VIBES   = ["SCRAMBLE"]
ALL_VIBES        = AESTHETIC_VIBES + BEHAVIORAL_VIBES + WILDCARD_VIBES
GROUP_ONLY_VIBES = BEHAVIORAL_VIBES + WILDCARD_VIBES  # cannot be set as personal vibe

ATTACHMENT_STATUSES = ["PENDING", "UPLOADING", "UPLOADED", "DOWNLOADING", "DOWNLOADED", "FAILED"]
MESSAGE_TYPES       = ["TEXT", "ATTACHMENT", "GROUP_EVENT", "SYSTEM"]
GROUP_EVENT_TYPES   = ["MEMBER_JOINED", "MEMBER_LEFT", "VIBE_CHANGED", "GROUP_RENAMED"]
CONVERSATION_TYPES  = ["DM", "GROUP"]

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def valid_session_id() -> str:
    return VALID_SESSION_ID


@pytest.fixture()
def valid_session_id_2() -> str:
    return VALID_SESSION_ID_2


@pytest.fixture()
def valid_session_id_3() -> str:
    return VALID_SESSION_ID_3


@pytest.fixture()
def valid_passphrase() -> str:
    return VALID_PASSPHRASE


@pytest.fixture()
def valid_identity_payload() -> dict:
    return {"passphrase": VALID_PASSPHRASE, "displayName": VALID_DISPLAY_NAME}


@pytest.fixture()
def valid_contact_payload() -> dict:
    return {"sessionId": VALID_SESSION_ID_2, "displayName": "Bob"}


@pytest.fixture()
def valid_group_payload() -> dict:
    return {"name": "Night Owls", "memberSessionIds": [VALID_SESSION_ID_2]}


@pytest.fixture()
def valid_send_payload() -> dict:
    return {"conversationId": 1, "body": "Hello, world!"}
