"""
Unit tests — business logic.

Tests the rules described in CONTEXT.md and DATA_CONTRACT that live in the
application layer (not in the DB schema and not in HTTP routing).

No database, no HTTP client.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import (
    VALID_SESSION_ID,
    VALID_SESSION_ID_2,
    AESTHETIC_VIBES,
    BEHAVIORAL_VIBES,
    WILDCARD_VIBES,
    GROUP_ONLY_VIBES,
    pkg,
)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Identity business rules
# ---------------------------------------------------------------------------
class TestIdentityBusinessRules:
    """DATA_CONTRACT § Identity — business rules."""

    @pytest.fixture(autouse=True)
    def _import(self):
        self.mod = pkg("identity.keypair")

    def test_derived_session_id_starts_with_05(self):
        """Session ID must be X25519 public key hex-prefixed with '05'."""
        session_id = self.mod.derive_session_id(b"\xab" * 32)
        assert session_id.startswith("05")

    def test_derived_session_id_is_66_chars(self):
        session_id = self.mod.derive_session_id(b"\xab" * 32)
        assert len(session_id) == 66

    def test_derived_session_id_is_lowercase_hex(self):
        session_id = self.mod.derive_session_id(b"\xab" * 32)
        assert re.fullmatch(r"[0-9a-f]+", session_id[2:])

    def test_different_seeds_produce_different_session_ids(self):
        id_a = self.mod.derive_session_id(b"\xaa" * 32)
        id_b = self.mod.derive_session_id(b"\xbb" * 32)
        assert id_a != id_b

    def test_same_seed_always_produces_same_session_id(self):
        seed = b"\x01" * 32
        assert self.mod.derive_session_id(seed) == self.mod.derive_session_id(seed)


# ---------------------------------------------------------------------------
# Mnemonic business rules
# ---------------------------------------------------------------------------
class TestMnemonicBusinessRules:
    """DATA_CONTRACT § Identity — mnemonic/seed phrase encode/decode."""

    @pytest.fixture(autouse=True)
    def _import(self):
        self.mod = pkg("identity.mnemonic")

    def test_encode_returns_string_of_words(self):
        seed = b"\x00" * 32
        mnemonic = self.mod.encode(seed)
        assert isinstance(mnemonic, str)
        assert len(mnemonic.split()) > 0

    def test_decode_inverts_encode(self):
        seed = bytes(range(32))
        mnemonic = self.mod.encode(seed)
        recovered = self.mod.decode(mnemonic)
        assert recovered == seed

    def test_decode_invalid_word_raises(self):
        """Words not in Session's custom word list must raise."""
        from importlib import import_module
        exc_mod = import_module("404whisper.identity.mnemonic")
        with pytest.raises(Exception):   # MnemonicDecodeError or ValueError
            self.mod.decode("notaword notaword notaword")

    def test_mnemonic_uses_session_word_list_not_bip39(self):
        """BIP39 first word 'abandon' must NOT appear in valid Session mnemonics."""
        seed = b"\x00" * 32
        mnemonic = self.mod.encode(seed)
        # A Session mnemonic derived from all-zeros should not contain 'abandon'
        # (which is the first word in the BIP39 list)
        assert "abandon" not in mnemonic.split()


# ---------------------------------------------------------------------------
# Vibe business rules
# ---------------------------------------------------------------------------
class TestVibeBusinessRules:
    """DATA_CONTRACT § Vibe Mode — classification and permission rules."""

    @pytest.fixture(autouse=True)
    def _import(self):
        self.mod = pkg("api.services.vibes")

    @pytest.mark.parametrize("vibe", AESTHETIC_VIBES)
    def test_aesthetic_vibes_are_not_behavioral(self, vibe):
        assert not self.mod.is_behavioral(vibe)

    @pytest.mark.parametrize("vibe", BEHAVIORAL_VIBES)
    def test_behavioral_vibes_are_behavioral(self, vibe):
        assert self.mod.is_behavioral(vibe)

    @pytest.mark.parametrize("vibe", WILDCARD_VIBES)
    def test_wildcard_vibes_are_behavioral(self, vibe):
        """Wildcards are treated as behavioral for permission purposes."""
        assert self.mod.is_behavioral(vibe)

    @pytest.mark.parametrize("vibe", AESTHETIC_VIBES)
    def test_aesthetic_vibes_allowed_as_personal(self, vibe):
        assert self.mod.is_allowed_personal_vibe(vibe)

    @pytest.mark.parametrize("vibe", GROUP_ONLY_VIBES)
    def test_behavioral_vibes_not_allowed_as_personal(self, vibe):
        assert not self.mod.is_allowed_personal_vibe(vibe)

    def test_vibe_change_requires_admin_for_behavioral(self):
        """Non-admin attempting a behavioral vibe change should be rejected."""
        assert self.mod.requires_admin(vibe="404") is True

    def test_vibe_change_does_not_require_admin_for_aesthetic(self):
        assert self.mod.requires_admin(vibe="CAMPFIRE") is False


# ---------------------------------------------------------------------------
# Cooldown business rules
# ---------------------------------------------------------------------------
class TestVibeCooldown:
    """DATA_CONTRACT § Vibe Mode — cooldown: 5 minutes (OQ-1 resolved)."""

    @pytest.fixture(autouse=True)
    def _import(self):
        self.mod = pkg("api.services.vibes")

    def test_cooldown_active_when_within_window(self):
        now = datetime.now(UTC)
        cooldown_until = now + timedelta(minutes=5)
        assert self.mod.is_cooldown_active(cooldown_until=cooldown_until, now=now)

    def test_cooldown_inactive_when_expired(self):
        now = datetime.now(UTC)
        cooldown_until = now - timedelta(seconds=1)
        assert not self.mod.is_cooldown_active(cooldown_until=cooldown_until, now=now)

    def test_cooldown_inactive_when_none(self):
        assert not self.mod.is_cooldown_active(cooldown_until=None, now=datetime.now(UTC))

    def test_cooldown_duration_is_exactly_5_minutes(self):
        """OQ-1 resolved: cooldown = 5 minutes (300 s). The constant must not drift."""
        now = datetime.now(UTC)
        cooldown_until = self.mod.compute_cooldown_until(now=now)
        delta = cooldown_until - now
        assert delta.total_seconds() == 300


# ---------------------------------------------------------------------------
# Message TTL (404 vibe) business rules
# ---------------------------------------------------------------------------
class TestMessageTTLLogic:
    """DATA_CONTRACT § Message — expiresAt / 404 vibe (OQ-2 resolved: forward-only; OQ-3: countdown continues)."""

    @pytest.fixture(autouse=True)
    def _import(self):
        self.mod = pkg("messaging.ttl")

    def test_compute_expires_at_is_24h_after_sent_at(self):
        sent_at = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)
        expires_at = self.mod.compute_expires_at(sent_at)
        assert expires_at == sent_at + timedelta(hours=24)

    def test_message_is_expired_after_24h(self):
        sent_at = datetime.now(UTC) - timedelta(hours=25)
        expires_at = self.mod.compute_expires_at(sent_at)
        assert self.mod.is_expired(expires_at, now=datetime.now(UTC))

    def test_message_is_not_expired_within_24h(self):
        sent_at = datetime.now(UTC) - timedelta(hours=1)
        expires_at = self.mod.compute_expires_at(sent_at)
        assert not self.mod.is_expired(expires_at, now=datetime.now(UTC))


# ---------------------------------------------------------------------------
# Slow Burn delivery delay
# ---------------------------------------------------------------------------
class TestSlowBurnDelay:
    """DATA_CONTRACT § Message — deliverAfter / SLOW_BURN vibe (OQ-6 resolved: fixed 60 s)."""

    @pytest.fixture(autouse=True)
    def _import(self):
        self.mod = pkg("messaging.delay")

    def test_compute_deliver_after_defaults_to_60s(self):
        sent_at = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)
        deliver_after = self.mod.compute_deliver_after(sent_at, delay_seconds=60)
        assert deliver_after == sent_at + timedelta(seconds=60)

    def test_message_held_when_before_deliver_after(self):
        now = datetime.now(UTC)
        deliver_after = now + timedelta(seconds=30)
        assert self.mod.is_held(deliver_after, now=now)

    def test_message_released_when_past_deliver_after(self):
        now = datetime.now(UTC)
        deliver_after = now - timedelta(seconds=1)
        assert not self.mod.is_held(deliver_after, now=now)

    def test_delay_constant_is_60_seconds(self):
        """OQ-6 resolved: SLOW_BURN_DELAY_SECONDS must equal 60. Guards against accidental changes."""
        assert self.mod.SLOW_BURN_DELAY_SECONDS == 60


# ---------------------------------------------------------------------------
# 404 vibe — pin escape hatch (OQ-4 resolved)
# ---------------------------------------------------------------------------
class TestPinEscapeHatch:
    """DATA_CONTRACT § Message — isPinned / 404 vibe escape hatch."""

    @pytest.fixture(autouse=True)
    def _import(self):
        self.mod = pkg("messaging.ttl")

    def test_pinned_message_not_expired_even_past_expires_at(self):
        """The purge job must skip messages where is_pinned=True."""
        expires_at = datetime.now(UTC) - timedelta(hours=1)   # already past
        assert not self.mod.is_purgeable(expires_at=expires_at, is_pinned=True, now=datetime.now(UTC))

    def test_unpinned_expired_message_is_purgeable(self):
        expires_at = datetime.now(UTC) - timedelta(hours=1)
        assert self.mod.is_purgeable(expires_at=expires_at, is_pinned=False, now=datetime.now(UTC))

    def test_unpinned_unexpired_message_is_not_purgeable(self):
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        assert not self.mod.is_purgeable(expires_at=expires_at, is_pinned=False, now=datetime.now(UTC))

    def test_no_expires_at_never_purgeable(self):
        """Messages not in 404 vibe have no TTL and must never be purged."""
        assert not self.mod.is_purgeable(expires_at=None, is_pinned=False, now=datetime.now(UTC))


# ---------------------------------------------------------------------------
# Chorus grouping (OQ-5 resolved: 30-second window)
# ---------------------------------------------------------------------------
class TestChorusGrouping:
    """DATA_CONTRACT § Message — chorusGroupId / CHORUS vibe (30-second window)."""

    @pytest.fixture(autouse=True)
    def _import(self):
        self.mod = pkg("messaging.chorus")

    def test_grouping_window_constant_is_30_seconds(self):
        """OQ-5 resolved: CHORUS_WINDOW_SECONDS must equal 30."""
        assert self.mod.CHORUS_WINDOW_SECONDS == 30

    def test_messages_within_window_share_group_id(self):
        base = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)
        id_a = self.mod.assign_chorus_group_id(sent_at=base, conversation_id=1, db_state=None)
        id_b = self.mod.assign_chorus_group_id(
            sent_at=base + timedelta(seconds=29), conversation_id=1, db_state=id_a
        )
        assert id_a == id_b

    def test_messages_outside_window_get_new_group_id(self):
        base = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)
        id_a = self.mod.assign_chorus_group_id(sent_at=base, conversation_id=1, db_state=None)
        id_b = self.mod.assign_chorus_group_id(
            sent_at=base + timedelta(seconds=31), conversation_id=1, db_state=id_a
        )
        assert id_a != id_b

    def test_chorus_group_id_is_uuid_format(self):
        import re
        group_id = self.mod.assign_chorus_group_id(
            sent_at=datetime.now(UTC), conversation_id=1, db_state=None
        )
        uuid_re = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        assert uuid_re.match(group_id), f"chorus_group_id '{group_id}' is not a valid UUID"


# ---------------------------------------------------------------------------
# Confessional anonymisation
# ---------------------------------------------------------------------------
class TestConfessionalAnonymisation:
    """DATA_CONTRACT § Message — isAnonymous / CONFESSIONAL vibe."""

    @pytest.fixture(autouse=True)
    def _import(self):
        self.mod = pkg("api.serializers.messages")

    def test_sender_session_id_is_none_when_anonymous(self):
        raw = {"sender_session_id": VALID_SESSION_ID, "is_anonymous": True}
        serialised = self.mod.serialise_message(raw)
        assert serialised["senderSessionId"] is None

    def test_sender_session_id_present_when_not_anonymous(self):
        raw = {"sender_session_id": VALID_SESSION_ID, "is_anonymous": False}
        serialised = self.mod.serialise_message(raw)
        assert serialised["senderSessionId"] == VALID_SESSION_ID
