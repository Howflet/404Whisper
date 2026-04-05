"""
Unit tests — Layer 2: Crypto.

Covers every function in the crypto package:
  - x25519: DH shared secret, ephemeral keypair generation
  - ed25519: sign, verify, sign_and_prepend, verify_and_strip
  - symmetric: derive_key, encrypt/decrypt, encrypt_to_recipient / decrypt_from_sender
  - onion: build_onion_packet, peel_onion_layer (end-to-end round-trip)
  - __init__: encrypt_message / decrypt_message aliases

No network calls, no database, no filesystem — pure crypto.
"""
from __future__ import annotations

import os
import pytest

from tests.conftest import pkg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load(subpath: str):
    """Import a submodule of the crypto package."""
    return pkg(f"crypto.{subpath}")


# ---------------------------------------------------------------------------
# X25519 — Diffie-Hellman key exchange
# ---------------------------------------------------------------------------

class TestX25519:
    """crypto/x25519.py"""

    @pytest.fixture(autouse=True)
    def _mod(self):
        self.m = load("x25519")

    # ── Ephemeral keypair ────────────────────────────────────────────────────

    def test_generate_ephemeral_keypair_returns_two_32_byte_values(self):
        """Each keypair is two distinct 32-byte byte strings."""
        priv, pub = self.m.generate_ephemeral_keypair()
        assert isinstance(priv, bytes) and len(priv) == 32
        assert isinstance(pub,  bytes) and len(pub)  == 32

    def test_generate_ephemeral_keypair_is_random(self):
        """Two consecutive calls must produce different private keys."""
        priv_a, _ = self.m.generate_ephemeral_keypair()
        priv_b, _ = self.m.generate_ephemeral_keypair()
        assert priv_a != priv_b

    # ── Public key derivation ────────────────────────────────────────────────

    def test_public_key_from_private_is_32_bytes(self):
        priv = os.urandom(32)
        pub = self.m.public_key_from_private(priv)
        assert isinstance(pub, bytes) and len(pub) == 32

    def test_public_key_from_private_is_deterministic(self):
        """Same private key always yields the same public key."""
        priv = os.urandom(32)
        assert self.m.public_key_from_private(priv) == self.m.public_key_from_private(priv)

    def test_public_key_from_private_matches_keypair_output(self):
        """generate_ephemeral_keypair and public_key_from_private must agree."""
        priv, pub = self.m.generate_ephemeral_keypair()
        assert self.m.public_key_from_private(priv) == pub

    def test_public_key_from_private_rejects_wrong_size(self):
        with pytest.raises(ValueError):
            self.m.public_key_from_private(b"\x00" * 31)

    # ── DH shared secret ─────────────────────────────────────────────────────

    def test_compute_shared_secret_returns_32_bytes(self):
        priv, pub = self.m.generate_ephemeral_keypair()
        priv2, pub2 = self.m.generate_ephemeral_keypair()
        shared = self.m.compute_shared_secret(priv, pub2)
        assert isinstance(shared, bytes) and len(shared) == 32

    def test_dh_is_commutative(self):
        """
        Alice(alice_priv, bob_pub) == Bob(bob_priv, alice_pub).

        This is the fundamental property of Diffie-Hellman: both sides
        compute the same shared secret without ever transmitting it.
        """
        alice_priv, alice_pub = self.m.generate_ephemeral_keypair()
        bob_priv,   bob_pub   = self.m.generate_ephemeral_keypair()

        shared_alice = self.m.compute_shared_secret(alice_priv, bob_pub)
        shared_bob   = self.m.compute_shared_secret(bob_priv,   alice_pub)

        assert shared_alice == shared_bob

    def test_different_keypairs_produce_different_secrets(self):
        alice_priv, alice_pub = self.m.generate_ephemeral_keypair()
        bob_priv,   bob_pub   = self.m.generate_ephemeral_keypair()
        carol_priv, carol_pub = self.m.generate_ephemeral_keypair()

        shared_ab = self.m.compute_shared_secret(alice_priv, bob_pub)
        shared_ac = self.m.compute_shared_secret(alice_priv, carol_pub)

        assert shared_ab != shared_ac

    def test_compute_shared_secret_rejects_wrong_size(self):
        priv, pub = self.m.generate_ephemeral_keypair()
        with pytest.raises(ValueError):
            self.m.compute_shared_secret(priv, b"\x00" * 31)  # pub too short
        with pytest.raises(ValueError):
            self.m.compute_shared_secret(b"\x00" * 31, pub)   # priv too short


# ---------------------------------------------------------------------------
# Ed25519 — digital signatures
# ---------------------------------------------------------------------------

class TestEd25519:
    """crypto/ed25519.py"""

    @pytest.fixture(autouse=True)
    def _mod(self):
        self.m = load("ed25519")

    @pytest.fixture()
    def keypair(self):
        """Fresh Ed25519 keypair for each test."""
        from nacl.signing import SigningKey
        sk = SigningKey.generate()
        return bytes(sk), bytes(sk.verify_key)

    # ── sign ─────────────────────────────────────────────────────────────────

    def test_sign_returns_64_bytes(self, keypair):
        sk, _ = keypair
        sig = self.m.sign(b"hello", sk)
        assert isinstance(sig, bytes) and len(sig) == 64

    def test_sign_is_deterministic(self, keypair):
        """Ed25519 is deterministic — same key + message → same signature."""
        sk, _ = keypair
        msg = b"determinism check"
        assert self.m.sign(msg, sk) == self.m.sign(msg, sk)

    def test_sign_rejects_wrong_key_size(self, keypair):
        with pytest.raises(ValueError):
            self.m.sign(b"msg", b"\x00" * 31)  # 31 bytes, not 32

    def test_sign_accepts_empty_message(self, keypair):
        sk, _ = keypair
        sig = self.m.sign(b"", sk)
        assert len(sig) == 64

    # ── verify ───────────────────────────────────────────────────────────────

    def test_verify_returns_true_for_valid_signature(self, keypair):
        sk, vk = keypair
        msg = b"authentic message"
        sig = self.m.sign(msg, sk)
        assert self.m.verify(msg, sig, vk) is True

    def test_verify_returns_false_for_tampered_message(self, keypair):
        sk, vk = keypair
        msg = b"real message"
        sig = self.m.sign(msg, sk)
        assert self.m.verify(b"TAMPERED", sig, vk) is False

    def test_verify_returns_false_for_wrong_key(self, keypair):
        """A signature from Alice cannot be verified with Bob's public key."""
        from nacl.signing import SigningKey
        alice_sk, _ = keypair
        _, bob_vk = bytes(SigningKey.generate()), bytes(SigningKey.generate().verify_key)
        msg = b"hello"
        sig = self.m.sign(msg, alice_sk)
        assert self.m.verify(msg, sig, bob_vk) is False

    def test_verify_returns_false_for_corrupted_signature(self, keypair):
        sk, vk = keypair
        msg = b"test"
        sig = self.m.sign(msg, sk)
        bad_sig = bytes([sig[0] ^ 0xFF]) + sig[1:]  # flip one bit
        assert self.m.verify(msg, bad_sig, vk) is False

    def test_verify_rejects_wrong_signature_size(self, keypair):
        _, vk = keypair
        with pytest.raises(ValueError):
            self.m.verify(b"msg", b"\x00" * 63, vk)  # 63 bytes, not 64

    # ── sign_and_prepend / verify_and_strip ───────────────────────────────────

    def test_sign_and_prepend_length(self, keypair):
        sk, _ = keypair
        msg = b"test message"
        blob = self.m.sign_and_prepend(msg, sk)
        assert len(blob) == 64 + len(msg)

    def test_verify_and_strip_round_trip(self, keypair):
        sk, vk = keypair
        msg = b"round trip!"
        blob = self.m.sign_and_prepend(msg, sk)
        recovered = self.m.verify_and_strip(blob, vk)
        assert recovered == msg

    def test_verify_and_strip_returns_none_for_tampered_blob(self, keypair):
        sk, vk = keypair
        blob = self.m.sign_and_prepend(b"real", sk)
        tampered = blob[:-1] + bytes([blob[-1] ^ 0xFF])
        assert self.m.verify_and_strip(tampered, vk) is None

    def test_verify_and_strip_returns_none_for_too_short_blob(self, keypair):
        _, vk = keypair
        assert self.m.verify_and_strip(b"\x00" * 10, vk) is None


# ---------------------------------------------------------------------------
# Symmetric — key derivation + authenticated encryption
# ---------------------------------------------------------------------------

class TestSymmetric:
    """crypto/symmetric.py"""

    @pytest.fixture(autouse=True)
    def _mod(self):
        self.m = load("symmetric")

    # ── derive_key ───────────────────────────────────────────────────────────

    def test_derive_key_returns_32_bytes(self):
        key = self.m.derive_key(os.urandom(32))
        assert isinstance(key, bytes) and len(key) == 32

    def test_derive_key_is_deterministic(self):
        secret = os.urandom(32)
        assert self.m.derive_key(secret) == self.m.derive_key(secret)

    def test_derive_key_different_contexts_produce_different_keys(self):
        """Domain separation: same secret + different context → different key."""
        secret = os.urandom(32)
        key_a = self.m.derive_key(secret, context=b"context-a")
        key_b = self.m.derive_key(secret, context=b"context-b")
        assert key_a != key_b

    def test_derive_key_rejects_wrong_secret_size(self):
        with pytest.raises(ValueError):
            self.m.derive_key(b"\x00" * 16)  # too short

    # ── encrypt / decrypt ────────────────────────────────────────────────────

    def test_encrypt_then_decrypt_round_trip(self):
        key = os.urandom(32)
        plaintext = b"Super secret message"
        ciphertext = self.m.encrypt(plaintext, key)
        assert self.m.decrypt(ciphertext, key) == plaintext

    def test_encrypt_output_is_longer_than_plaintext(self):
        """Ciphertext must include nonce (24) + MAC (16) overhead."""
        key = os.urandom(32)
        plaintext = b"hello"
        ciphertext = self.m.encrypt(plaintext, key)
        assert len(ciphertext) == len(plaintext) + 24 + 16

    def test_encrypt_is_random(self):
        """Same key + plaintext → different ciphertext due to random nonce."""
        key = os.urandom(32)
        ct1 = self.m.encrypt(b"same text", key)
        ct2 = self.m.encrypt(b"same text", key)
        assert ct1 != ct2

    def test_decrypt_fails_on_tampered_ciphertext(self):
        """MAC check must reject any modification to the ciphertext."""
        from nacl.exceptions import CryptoError
        key = os.urandom(32)
        ct = self.m.encrypt(b"secret", key)
        # Flip the last byte of the ciphertext (inside the MAC region).
        bad_ct = ct[:-1] + bytes([ct[-1] ^ 0xFF])
        with pytest.raises(CryptoError):
            self.m.decrypt(bad_ct, key)

    def test_decrypt_fails_with_wrong_key(self):
        """Decrypting with the wrong key must fail (MAC mismatch)."""
        from nacl.exceptions import CryptoError
        key1 = os.urandom(32)
        key2 = os.urandom(32)
        ct = self.m.encrypt(b"private", key1)
        with pytest.raises(CryptoError):
            self.m.decrypt(ct, key2)

    def test_encrypt_rejects_wrong_key_size(self):
        with pytest.raises(ValueError):
            self.m.encrypt(b"msg", b"\x00" * 16)  # 16 bytes, need 32

    def test_decrypt_rejects_wrong_key_size(self):
        from nacl.exceptions import CryptoError
        key = os.urandom(32)
        ct = self.m.encrypt(b"msg", key)
        with pytest.raises(ValueError):
            self.m.decrypt(ct, b"\x00" * 16)

    def test_encrypt_and_decrypt_empty_plaintext(self):
        """Empty plaintext is a valid edge case."""
        key = os.urandom(32)
        ct = self.m.encrypt(b"", key)
        assert self.m.decrypt(ct, key) == b""

    # ── encrypt_to_recipient / decrypt_from_sender ───────────────────────────

    def test_encrypt_to_recipient_round_trip(self):
        """
        Alice encrypts for Bob; Bob decrypts.
        This is the primary message-level flow.
        """
        gen = load("x25519").generate_ephemeral_keypair
        alice_priv, alice_pub = gen()
        bob_priv,   bob_pub   = gen()

        plaintext  = b"Hey Bob, this is a secret"
        ciphertext = self.m.encrypt_to_recipient(plaintext, alice_priv, bob_pub)
        recovered  = self.m.decrypt_from_sender(ciphertext, bob_priv, alice_pub)
        assert recovered == plaintext

    def test_wrong_recipient_cannot_decrypt(self):
        """Carol cannot decrypt a message intended for Bob."""
        from nacl.exceptions import CryptoError
        gen = load("x25519").generate_ephemeral_keypair
        alice_priv, alice_pub = gen()
        bob_priv,   bob_pub   = gen()
        carol_priv, carol_pub = gen()

        ct = self.m.encrypt_to_recipient(b"for Bob only", alice_priv, bob_pub)
        with pytest.raises(CryptoError):
            self.m.decrypt_from_sender(ct, carol_priv, alice_pub)


# ---------------------------------------------------------------------------
# Onion routing — packet construction and peeling
# ---------------------------------------------------------------------------

class TestOnion:
    """crypto/onion.py — full 3-hop round-trip."""

    @pytest.fixture(autouse=True)
    def _mod(self):
        self.m = load("onion")

    @pytest.fixture()
    def three_hop_nodes(self):
        """
        Create three simulated service nodes, each with their own X25519 keypair.
        The public keys go into the OnionHop objects; the private keys are used
        to simulate what each node does when it receives and peels the packet.
        """
        gen = load("x25519").generate_ephemeral_keypair

        guard_priv, guard_pub  = gen()
        relay_priv, relay_pub  = gen()
        exit_priv,  exit_pub   = gen()

        guard_hop = self.m.OnionHop(public_key=guard_pub, host="10.0.0.1", port=8080)
        relay_hop = self.m.OnionHop(public_key=relay_pub, host="10.0.0.2", port=8080)
        exit_hop  = self.m.OnionHop(public_key=exit_pub,  host="10.0.0.3", port=8080)

        return (
            (guard_priv, guard_hop),
            (relay_priv, relay_hop),
            (exit_priv,  exit_hop),
        )

    # ── build_onion_packet ───────────────────────────────────────────────────

    def test_build_onion_packet_returns_bytes(self, three_hop_nodes):
        _, hops = zip(*three_hop_nodes)  # unzip to get just the OnionHop objects
        (_, guard_hop), (_, relay_hop), (_, exit_hop) = three_hop_nodes
        packet = self.m.build_onion_packet(
            payload=b"store message",
            hops=[guard_hop, relay_hop, exit_hop],
        )
        assert isinstance(packet, bytes) and len(packet) > 0

    def test_build_onion_packet_requires_exactly_3_hops(self, three_hop_nodes):
        (_, guard_hop), _, _ = three_hop_nodes
        with pytest.raises(ValueError):
            self.m.build_onion_packet(b"payload", hops=[guard_hop])  # only 1 hop

    def test_build_onion_packet_is_random(self, three_hop_nodes):
        """Two builds of the same payload produce different packets (random nonces)."""
        (_, guard_hop), (_, relay_hop), (_, exit_hop) = three_hop_nodes
        hops = [guard_hop, relay_hop, exit_hop]
        pkt1 = self.m.build_onion_packet(b"same payload", hops)
        pkt2 = self.m.build_onion_packet(b"same payload", hops)
        assert pkt1 != pkt2

    # ── peel_onion_layer ─────────────────────────────────────────────────────

    def test_peel_guard_layer_returns_routing_layer(self, three_hop_nodes):
        """
        Guard peels → routing layer with next_hop pointing to relay.
        """
        (guard_priv, guard_hop), (_, relay_hop), (_, exit_hop) = three_hop_nodes
        packet = self.m.build_onion_packet(
            payload=b"test payload",
            hops=[guard_hop, relay_hop, exit_hop],
        )
        layer = self.m.peel_onion_layer(packet, guard_priv)

        assert layer.next_hop is not None
        assert layer.next_hop["host"] == relay_hop.host
        assert layer.next_hop["port"] == relay_hop.port
        assert isinstance(layer.inner_packet, bytes) and len(layer.inner_packet) > 0

    def test_peel_relay_layer_returns_routing_layer(self, three_hop_nodes):
        """
        Relay peels → routing layer with next_hop pointing to exit.
        """
        (guard_priv, guard_hop), (relay_priv, relay_hop), (_, exit_hop) = three_hop_nodes
        packet = self.m.build_onion_packet(
            payload=b"test payload",
            hops=[guard_hop, relay_hop, exit_hop],
        )
        guard_layer = self.m.peel_onion_layer(packet, guard_priv)
        relay_layer = self.m.peel_onion_layer(guard_layer.inner_packet, relay_priv)

        assert relay_layer.next_hop is not None
        assert relay_layer.next_hop["host"] == exit_hop.host
        assert relay_layer.next_hop["port"] == exit_hop.port

    def test_full_3_hop_round_trip(self, three_hop_nodes):
        """
        Complete end-to-end test:
            build → guard peels → relay peels → exit peels → original payload.

        This is the integration test for the whole onion flow.
        """
        (guard_priv, guard_hop), (relay_priv, relay_hop), (exit_priv, exit_hop) = three_hop_nodes
        original_payload = b"Hello, anonymous world!"

        # Build the onion packet (done by the sender before dispatching).
        outer_packet = self.m.build_onion_packet(
            payload=original_payload,
            hops=[guard_hop, relay_hop, exit_hop],
        )

        # Guard node receives the outer packet, peels its layer.
        guard_result = self.m.peel_onion_layer(outer_packet, guard_priv)
        assert guard_result.next_hop["host"] == relay_hop.host  # guard knows relay
        assert guard_result.next_hop is not None

        # Relay node receives what the guard forwarded, peels its layer.
        relay_result = self.m.peel_onion_layer(guard_result.inner_packet, relay_priv)
        assert relay_result.next_hop["host"] == exit_hop.host   # relay knows exit
        assert relay_result.next_hop is not None

        # Exit node receives what the relay forwarded, peels the final layer.
        exit_result = self.m.peel_onion_layer(relay_result.inner_packet, exit_priv)
        assert exit_result.next_hop is None                      # exit: no more hops
        assert exit_result.inner_packet == original_payload      # payload intact!

    def test_peel_with_wrong_key_raises_crypto_error(self, three_hop_nodes):
        """
        A hop that tries to decrypt a layer with the wrong private key gets
        a CryptoError — the MAC rejects the tampered decryption.
        """
        from nacl.exceptions import CryptoError

        (guard_priv, guard_hop), (_, relay_hop), (_, exit_hop) = three_hop_nodes
        wrong_priv, _ = load("x25519").generate_ephemeral_keypair()

        packet = self.m.build_onion_packet(b"secret", [guard_hop, relay_hop, exit_hop])

        with pytest.raises(CryptoError):
            self.m.peel_onion_layer(packet, wrong_priv)

    def test_peel_rejects_too_short_packet(self, three_hop_nodes):
        (guard_priv, *_), *_ = three_hop_nodes
        with pytest.raises(ValueError):
            self.m.peel_onion_layer(b"\x00" * 10, guard_priv)

    def test_onion_payload_is_not_visible_in_outer_packet(self, three_hop_nodes):
        """
        The original payload must NOT appear as a substring in the outer packet.
        This sanity-checks that encryption is actually happening.
        """
        (_, guard_hop), (_, relay_hop), (_, exit_hop) = three_hop_nodes
        payload = b"SUPER SECRET PAYLOAD DO NOT REVEAL"
        packet = self.m.build_onion_packet(payload, [guard_hop, relay_hop, exit_hop])
        assert payload not in packet


# ---------------------------------------------------------------------------
# crypto/__init__.py — public API aliases
# ---------------------------------------------------------------------------

class TestCryptoPublicAPI:
    """Tests for the top-level crypto package aliases."""

    @pytest.fixture(autouse=True)
    def _mod(self):
        self.m = pkg("crypto")

    def test_encrypt_message_decrypt_message_round_trip(self):
        """
        encrypt_message / decrypt_message are the primary calls for Layer 4.
        This test mirrors what the messaging layer will do for every outgoing
        and incoming message.
        """
        gen = load("x25519").generate_ephemeral_keypair
        alice_priv, alice_pub = gen()
        bob_priv,   bob_pub   = gen()

        body = b"This is a Session message body"
        ciphertext = self.m.encrypt_message(body, alice_priv, bob_pub)
        recovered  = self.m.decrypt_message(ciphertext, bob_priv, alice_pub)
        assert recovered == body

    def test_sign_verify_round_trip(self):
        """sign + verify must work together through the public API."""
        from nacl.signing import SigningKey
        sk_obj = SigningKey.generate()
        sk = bytes(sk_obj)
        vk = bytes(sk_obj.verify_key)

        msg = b"Authenticated Session message"
        sig = self.m.sign(msg, sk)
        assert self.m.verify(msg, sig, vk) is True

    def test_all_symbols_exported(self):
        """Every function documented in __all__ must exist on the module."""
        expected = [
            "generate_ephemeral_keypair", "compute_shared_secret", "public_key_from_private",
            "derive_key", "sign", "verify", "sign_and_prepend", "verify_and_strip",
            "encrypt", "decrypt", "encrypt_message", "decrypt_message",
            "OnionHop", "PeeledLayer", "build_onion_packet", "peel_onion_layer",
        ]
        for name in expected:
            assert hasattr(self.m, name), f"crypto.__init__ is missing '{name}'"
