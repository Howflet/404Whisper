"""
Unit tests — validation rules.

Every rule in DATA_CONTRACT § Global Validation Rules and per-entity
validation tables is exercised here.  No database, no HTTP.

The tests import the Pydantic schema classes from ``404whisper.api.schemas.*``
once they exist; until then the suite will fail with ImportError, which is the
expected TDD red state.
"""
from __future__ import annotations

import re
import pytest

from tests.conftest import (
    VALID_SESSION_ID,
    VALID_SESSION_ID_2,
    INVALID_SESSION_IDS,
    VALID_PASSPHRASE,
    WEAK_PASSPHRASE,
    VALID_DISPLAY_NAME,
    LONG_DISPLAY_NAME,
    BLANK_DISPLAY_NAME,
    WHITESPACE_NAME,
    AESTHETIC_VIBES,
    BEHAVIORAL_VIBES,
    WILDCARD_VIBES,
    ALL_VIBES,
    GROUP_ONLY_VIBES,
    pkg,
)

# ---------------------------------------------------------------------------
# Session ID regex — tested at the pure-regex level first so any layer that
# reuses the pattern can be validated without the full app stack.
# ---------------------------------------------------------------------------
SESSION_ID_RE = re.compile(r"^05[0-9a-f]{64}$")


class TestSessionIdRegex:
    """DATA_CONTRACT § Global Validation Rules — sessionId"""

    def test_valid_session_id_matches(self):
        assert SESSION_ID_RE.match(VALID_SESSION_ID)

    @pytest.mark.parametrize("label,value", INVALID_SESSION_IDS.items())
    def test_invalid_session_id_does_not_match(self, label, value):
        assert not SESSION_ID_RE.match(value), f"Expected '{label}' to fail regex"

    def test_session_id_is_exactly_66_chars(self):
        assert len(VALID_SESSION_ID) == 66

    def test_session_id_starts_with_05(self):
        assert VALID_SESSION_ID.startswith("05")

    def test_session_id_remaining_64_chars_are_lowercase_hex(self):
        tail = VALID_SESSION_ID[2:]
        assert len(tail) == 64
        assert all(c in "0123456789abcdef" for c in tail)


# ---------------------------------------------------------------------------
# Pydantic schema — IdentityCreateRequest
# ---------------------------------------------------------------------------
class TestIdentityCreateSchema:
    """DATA_CONTRACT § Identity — POST /api/identity/new request schema."""

    @pytest.fixture(autouse=True)
    def _import_schema(self):
        schemas = pkg("api.schemas.identity")
        self.Schema = schemas.IdentityCreateRequest

    def test_valid_payload_accepted(self):
        obj = self.Schema(passphrase=VALID_PASSPHRASE, displayName=VALID_DISPLAY_NAME)
        assert obj.passphrase == VALID_PASSPHRASE

    def test_display_name_is_optional(self):
        obj = self.Schema(passphrase=VALID_PASSPHRASE)
        assert obj.display_name is None

    def test_passphrase_below_minimum_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(passphrase=WEAK_PASSPHRASE)

    def test_display_name_above_maximum_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(passphrase=VALID_PASSPHRASE, displayName=LONG_DISPLAY_NAME)

    def test_display_name_blank_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(passphrase=VALID_PASSPHRASE, displayName=BLANK_DISPLAY_NAME)

    def test_display_name_whitespace_is_stripped_or_rejected(self):
        """Leading/trailing whitespace must not survive into storage."""
        from pydantic import ValidationError
        try:
            obj = self.Schema(passphrase=VALID_PASSPHRASE, displayName=WHITESPACE_NAME)
            # If accepted, strip_whitespace must have been applied
            assert obj.display_name == WHITESPACE_NAME.strip()
        except ValidationError:
            pass  # Also acceptable


# ---------------------------------------------------------------------------
# Pydantic schema — IdentityImportRequest
# ---------------------------------------------------------------------------
class TestIdentityImportSchema:
    """DATA_CONTRACT § Identity — POST /api/identity/import request schema."""

    @pytest.fixture(autouse=True)
    def _import_schema(self):
        schemas = pkg("api.schemas.identity")
        self.Schema = schemas.IdentityImportRequest

    def test_valid_payload_accepted(self):
        obj = self.Schema(mnemonic="word1 word2 word3", passphrase=VALID_PASSPHRASE)
        assert obj.mnemonic == "word1 word2 word3"

    def test_missing_mnemonic_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(passphrase=VALID_PASSPHRASE)

    def test_missing_passphrase_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(mnemonic="word1 word2")

    def test_weak_passphrase_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(mnemonic="word1 word2", passphrase=WEAK_PASSPHRASE)


# ---------------------------------------------------------------------------
# Pydantic schema — ContactCreateRequest
# ---------------------------------------------------------------------------
class TestContactCreateSchema:
    """DATA_CONTRACT § Contact — POST /api/contacts request schema."""

    @pytest.fixture(autouse=True)
    def _import_schema(self):
        schemas = pkg("api.schemas.contacts")
        self.Schema = schemas.ContactCreateRequest

    @pytest.mark.parametrize("label,bad_id", INVALID_SESSION_IDS.items())
    def test_invalid_session_id_raises(self, label, bad_id):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(sessionId=bad_id)

    def test_valid_session_id_accepted(self):
        obj = self.Schema(sessionId=VALID_SESSION_ID_2)
        assert obj.session_id == VALID_SESSION_ID_2

    def test_display_name_optional(self):
        obj = self.Schema(sessionId=VALID_SESSION_ID_2)
        assert obj.display_name is None

    def test_display_name_too_long_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(sessionId=VALID_SESSION_ID_2, displayName=LONG_DISPLAY_NAME)


# ---------------------------------------------------------------------------
# Pydantic schema — GroupCreateRequest
# ---------------------------------------------------------------------------
class TestGroupCreateSchema:
    """DATA_CONTRACT § Group — POST /api/groups request schema."""

    @pytest.fixture(autouse=True)
    def _import_schema(self):
        schemas = pkg("api.schemas.groups")
        self.Schema = schemas.GroupCreateRequest

    def test_valid_group_accepted(self):
        obj = self.Schema(name="Night Owls")
        assert obj.name == "Night Owls"

    def test_name_required(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema()

    def test_name_blank_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(name="")

    def test_name_too_long_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(name="G" * 65)

    def test_member_session_ids_optional(self):
        obj = self.Schema(name="Quiet Room")
        assert obj.member_session_ids == [] or obj.member_session_ids is None

    def test_invalid_member_session_id_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(name="Bad Group", memberSessionIds=["not-a-valid-id"])


# ---------------------------------------------------------------------------
# Pydantic schema — MessageSendRequest
# ---------------------------------------------------------------------------
class TestMessageSendSchema:
    """DATA_CONTRACT § Message — POST /api/messages/send request schema."""

    @pytest.fixture(autouse=True)
    def _import_schema(self):
        schemas = pkg("api.schemas.messages")
        self.Schema = schemas.MessageSendRequest

    def test_valid_text_message_accepted(self):
        obj = self.Schema(conversationId=1, body="Hello!")
        assert obj.body == "Hello!"

    def test_missing_conversation_id_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(body="Hello!")

    def test_body_and_attachment_both_absent_raises(self):
        """At least one of body or attachmentId must be present."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(conversationId=1)

    def test_body_exceeds_max_length_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(conversationId=1, body="x" * 2001)

    def test_body_empty_string_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(conversationId=1, body="")


# ---------------------------------------------------------------------------
# Pagination parameters
# ---------------------------------------------------------------------------
class TestPaginationSchema:
    """DATA_CONTRACT § Conversation — GET /api/conversations/{id}/messages query params."""

    @pytest.fixture(autouse=True)
    def _import_schema(self):
        schemas = pkg("api.schemas.conversations")
        self.Schema = schemas.MessageListParams

    def test_defaults_are_applied(self):
        obj = self.Schema()
        assert obj.limit == 50

    def test_limit_at_maximum_boundary(self):
        obj = self.Schema(limit=100)
        assert obj.limit == 100

    def test_limit_above_maximum_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(limit=101)

    def test_limit_at_minimum_boundary(self):
        obj = self.Schema(limit=1)
        assert obj.limit == 1

    def test_limit_below_minimum_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.Schema(limit=0)


# ---------------------------------------------------------------------------
# Vibe validation
# ---------------------------------------------------------------------------
class TestVibeValidation:
    """DATA_CONTRACT § Enums & Constants — VibeId and vibe permission rules."""

    @pytest.fixture(autouse=True)
    def _import_schema(self):
        schemas = pkg("api.schemas.vibes")
        self.VibeId = schemas.VibeId
        self.PersonalVibeValidator = schemas.validate_personal_vibe

    @pytest.mark.parametrize("vibe", AESTHETIC_VIBES)
    def test_aesthetic_vibe_valid_as_personal(self, vibe):
        # Should not raise
        self.PersonalVibeValidator(vibe)

    @pytest.mark.parametrize("vibe", GROUP_ONLY_VIBES)
    def test_behavioral_vibe_rejected_as_personal(self, vibe):
        from pydantic import ValidationError
        with pytest.raises((ValidationError, ValueError)):
            self.PersonalVibeValidator(vibe)

    def test_unknown_vibe_id_raises(self):
        from pydantic import ValidationError
        with pytest.raises((ValidationError, ValueError)):
            self.PersonalVibeValidator("DOES_NOT_EXIST")

    @pytest.mark.parametrize("vibe", ALL_VIBES)
    def test_all_vibes_valid_at_group_level(self, vibe):
        """Every VibeId should be accepted in the VibeId enum."""
        assert self.VibeId(vibe) is not None


# ---------------------------------------------------------------------------
# Attachment size limit (OQ-7 resolved: 10 MiB)
# ---------------------------------------------------------------------------
class TestAttachmentSizeLimit:
    """DATA_CONTRACT § Attachment — MAX_ATTACHMENT_BYTES = 10,485,760."""

    @pytest.fixture(autouse=True)
    def _import(self):
        self.mod = pkg("attachments.upload")

    def test_size_limit_constant_is_10_mib(self):
        """OQ-7 resolved: must be exactly 10 * 1024 * 1024 bytes."""
        assert self.mod.MAX_ATTACHMENT_BYTES == 10_485_760

    def test_file_at_limit_is_accepted(self):
        assert self.mod.validate_file_size(10_485_760) is True

    def test_file_above_limit_is_rejected(self):
        assert self.mod.validate_file_size(10_485_761) is False

    def test_zero_byte_file_is_rejected(self):
        assert self.mod.validate_file_size(0) is False

    def test_negative_size_is_rejected(self):
        assert self.mod.validate_file_size(-1) is False
