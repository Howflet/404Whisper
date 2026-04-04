"""
Cross-layer consistency tests.

DATA_CONTRACT § Enums & Constants — verifies that the VibeId enum, the DB
CHECK constraint values, and the API schema all contain exactly the same set
of values.  Also verifies naming-convention compliance across layers.

These tests catch the class of bug where a developer adds a new vibe to the
Python enum but forgets to update the DB migration or the frontend TypeScript
types.
"""
from __future__ import annotations

import re
import sqlite3

import pytest

from tests.conftest import ALL_VIBES, ATTACHMENT_STATUSES, MESSAGE_TYPES, GROUP_EVENT_TYPES, pkg


# ---------------------------------------------------------------------------
# Expected canonical sets (source of truth = DATA_CONTRACT)
# ---------------------------------------------------------------------------
EXPECTED_VIBE_IDS = frozenset([
    "CAMPFIRE", "NEON", "LIBRARY", "VOID", "SUNRISE",
    "404", "CONFESSIONAL", "SLOW_BURN", "CHORUS", "SPOTLIGHT", "ECHO",
    "SCRAMBLE",
])

EXPECTED_ATTACHMENT_STATUSES = frozenset([
    "PENDING", "UPLOADING", "UPLOADED", "DOWNLOADING", "DOWNLOADED", "FAILED",
])

EXPECTED_MESSAGE_TYPES = frozenset(["TEXT", "ATTACHMENT", "GROUP_EVENT", "SYSTEM"])

EXPECTED_GROUP_EVENT_TYPES = frozenset([
    "MEMBER_JOINED", "MEMBER_LEFT", "VIBE_CHANGED", "GROUP_RENAMED",
])

EXPECTED_CONVERSATION_TYPES = frozenset(["DM", "GROUP"])


# ---------------------------------------------------------------------------
# API schema enum sync
# ---------------------------------------------------------------------------
@pytest.mark.consistency
class TestApiEnumSync:
    """Pydantic enums must match DATA_CONTRACT exactly — no more, no fewer values."""

    def test_vibe_id_enum_matches_contract(self):
        schemas = pkg("api.schemas.vibes")
        api_values = frozenset(v.value for v in schemas.VibeId)
        assert api_values == EXPECTED_VIBE_IDS, (
            f"VibeId mismatch.\nMissing: {EXPECTED_VIBE_IDS - api_values}\nExtra: {api_values - EXPECTED_VIBE_IDS}"
        )

    def test_attachment_status_enum_matches_contract(self):
        schemas = pkg("api.schemas.attachments")
        api_values = frozenset(v.value for v in schemas.AttachmentStatus)
        assert api_values == EXPECTED_ATTACHMENT_STATUSES

    def test_message_type_enum_matches_contract(self):
        schemas = pkg("api.schemas.messages")
        api_values = frozenset(v.value for v in schemas.MessageType)
        assert api_values == EXPECTED_MESSAGE_TYPES

    def test_group_event_type_enum_matches_contract(self):
        schemas = pkg("api.schemas.messages")
        api_values = frozenset(v.value for v in schemas.GroupEventType)
        assert api_values == EXPECTED_GROUP_EVENT_TYPES

    def test_conversation_type_enum_matches_contract(self):
        schemas = pkg("api.schemas.conversations")
        api_values = frozenset(v.value for v in schemas.ConversationType)
        assert api_values == EXPECTED_CONVERSATION_TYPES


# ---------------------------------------------------------------------------
# Database CHECK constraint sync
# ---------------------------------------------------------------------------
@pytest.mark.consistency
class TestDbEnumSync:
    """
    DB CHECK constraints are extracted from the schema definition and compared
    against the canonical enum sets.
    """

    @pytest.fixture()
    def schema_sql(self) -> str:
        """Returns the CREATE TABLE SQL for all tables."""
        storage = pkg("storage.db")
        return storage.SCHEMA_SQL  # The module must expose the schema as a string constant

    def _extract_check_values(self, schema_sql: str, column_name: str) -> frozenset[str]:
        """
        Parse CHECK(col IN ('A','B',...)) patterns from schema SQL.
        Returns the set of allowed values.
        """
        pattern = rf"CHECK\s*\(\s*{re.escape(column_name)}\s+IN\s*\(([^)]+)\)"
        match = re.search(pattern, schema_sql, re.IGNORECASE)
        if not match:
            return frozenset()
        raw = match.group(1)
        return frozenset(v.strip().strip("'\"") for v in raw.split(","))

    def test_db_vibe_enum_matches_contract(self, schema_sql):
        db_values = self._extract_check_values(schema_sql, "vibe")
        # NULL is allowed in DB but not an enum member; strip it before comparison
        db_values = db_values - {"NULL", "null", ""}
        if db_values:  # Only assert if CHECK constraint exists
            assert db_values == EXPECTED_VIBE_IDS

    def test_db_status_enum_matches_contract(self, schema_sql):
        db_values = self._extract_check_values(schema_sql, "status")
        db_values = db_values - {"NULL", "null", ""}
        if db_values:
            assert db_values == EXPECTED_ATTACHMENT_STATUSES

    def test_db_message_type_matches_contract(self, schema_sql):
        db_values = self._extract_check_values(schema_sql, "type")
        db_values = db_values - {"NULL", "null", ""}
        if db_values:
            assert db_values == EXPECTED_MESSAGE_TYPES

    def test_db_conversation_type_matches_contract(self, schema_sql):
        # conversations.type is a separate column to messages.type
        pattern = r"conversations.*?CHECK\s*\(\s*type\s+IN\s*\(([^)]+)\)"
        import re as _re
        match = _re.search(pattern, schema_sql, _re.IGNORECASE | _re.DOTALL)
        if match:
            raw = match.group(1)
            db_values = frozenset(v.strip().strip("'\"") for v in raw.split(","))
            assert db_values == EXPECTED_CONVERSATION_TYPES


# ---------------------------------------------------------------------------
# Naming-convention compliance
# ---------------------------------------------------------------------------
@pytest.mark.consistency
class TestNamingConventions:
    """
    DATA_CONTRACT § Naming Conventions:
      - API response fields must be camelCase
      - DB columns must be snake_case
    """

    CAMEL_CASE_RE  = re.compile(r"^[a-z][a-zA-Z0-9]*$")
    SNAKE_CASE_RE  = re.compile(r"^[a-z][a-z0-9_]*$")

    def test_identity_response_fields_are_camel_case(self):
        schemas = pkg("api.schemas.identity")
        resp = schemas.IdentityResponse(
            sessionId="05" + "a" * 64,
            displayName=None,
            personalVibe=None,
            createdAt="2026-04-04T12:00:00Z",
        )
        try:
            data = resp.model_dump(by_alias=True)
        except AttributeError:
            data = resp.dict(by_alias=True)
        for key in data:
            assert self.CAMEL_CASE_RE.match(key), (
                f"API response field '{key}' is not camelCase"
            )

    def test_db_column_names_are_snake_case(self):
        """
        Connect an in-memory DB, init the schema, and inspect PRAGMA table_info
        for every table to verify all column names are snake_case.
        """
        storage = pkg("storage.db")
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON")
        storage.init_schema(conn)

        tables = [
            row[0] for row in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        for table in tables:
            cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
            for col in cols:
                col_name = col[1]
                assert self.SNAKE_CASE_RE.match(col_name), (
                    f"DB column '{table}.{col_name}' is not snake_case"
                )

        conn.close()
