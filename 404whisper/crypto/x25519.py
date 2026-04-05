"""
Layer 2 — Crypto: X25519 Diffie-Hellman key exchange.

What this file does (plain English):
    Imagine you and a friend each hold one half of a secret handshake.
    You can perform that handshake in public — anyone can watch — but only the
    two of you end up knowing the shared secret that comes out of it.
    That's Diffie-Hellman (DH) key exchange.

    X25519 is a modern, fast, and secure variant of DH built on the
    Curve25519 elliptic curve.  It is the algorithm Session uses to
    establish a shared secret between any two participants before they
    exchange encrypted messages.

Why we need this:
    Before Alice can send Bob an encrypted message, Alice and Bob need to
    agree on a secret key they both know but that nobody else can derive.
    X25519 lets them do this using only each other's *public* keys.

    Alice computes: shared = X25519(alice_private, bob_public)
    Bob   computes: shared = X25519(bob_private,   alice_public)
    Both results are identical — that is the magic of elliptic-curve DH.

The resulting shared secret is fed into the symmetric-encryption layer
(crypto/symmetric.py) to actually encrypt and decrypt message bytes.

Implementation detail:
    We use PyNaCl's low-level bindings (nacl.bindings.crypto_scalarmult)
    which call libsodium's X25519 implementation directly.  libsodium is a
    battle-tested cryptographic library used in production by thousands of
    applications worldwide.
"""
from __future__ import annotations

import os
import logging

# nacl.bindings exposes the raw libsodium C functions.
# crypto_scalarmult is the raw X25519 scalar multiplication (DH operation).
# crypto_scalarmult_base is the same but uses the standard base point,
# which is how you derive a public key from a private key.
from nacl.bindings import crypto_scalarmult, crypto_scalarmult_base
from nacl.public import PrivateKey

logger = logging.getLogger(__name__)

# X25519 keys and shared secrets are always exactly 32 bytes.
KEY_SIZE: int = 32


# ---------------------------------------------------------------------------
# Keypair generation
# ---------------------------------------------------------------------------


def generate_ephemeral_keypair() -> tuple[bytes, bytes]:
    """
    Generate a fresh, one-time-use X25519 keypair.

    "Ephemeral" means throw-away: each message or onion layer gets its own
    fresh keypair.  This provides forward secrecy — if an attacker records
    encrypted traffic today and later compromises your identity key, they
    still cannot decrypt past messages because the per-message ephemeral
    keys are long gone.

    How it works:
        1. Generate 32 cryptographically random bytes as the private key.
        2. Multiply the fixed curve base-point by the private key scalar
           to produce the matching public key (this is an EC point, but
           PyNaCl gives it back to us as 32 bytes).

    Returns:
        (private_key_bytes, public_key_bytes) — each exactly 32 bytes.

    Example::

        priv, pub = generate_ephemeral_keypair()
        assert len(priv) == 32
        assert len(pub)  == 32
    """
    # os.urandom(32) gives us 32 cryptographically secure random bytes.
    # This is the private key — keep it secret; discard after use.
    private_key_bytes = os.urandom(KEY_SIZE)

    # Multiply the Curve25519 base point by our private scalar to get the
    # public key — the point that corresponds to our private key.
    public_key_bytes = crypto_scalarmult_base(private_key_bytes)

    logger.debug("Generated ephemeral X25519 keypair")
    return private_key_bytes, public_key_bytes


def public_key_from_private(private_key_bytes: bytes) -> bytes:
    """
    Derive the X25519 public key that corresponds to a private key.

    This is used to verify or reconstruct the public key from a stored
    private key (e.g., from the identity keystore).

    Args:
        private_key_bytes: A 32-byte X25519 private key.

    Returns:
        The corresponding 32-byte X25519 public key.

    Raises:
        ValueError: If private_key_bytes is not exactly 32 bytes.

    Example::

        pub = public_key_from_private(os.urandom(32))
        assert len(pub) == 32
    """
    if len(private_key_bytes) != KEY_SIZE:
        raise ValueError(
            f"X25519 private key must be {KEY_SIZE} bytes, got {len(private_key_bytes)}"
        )
    return crypto_scalarmult_base(private_key_bytes)


# ---------------------------------------------------------------------------
# The DH exchange itself
# ---------------------------------------------------------------------------


def compute_shared_secret(
    my_private_key: bytes,
    their_public_key: bytes,
) -> bytes:
    """
    Perform an X25519 Diffie-Hellman exchange to produce a 32-byte shared secret.

    This is the core of the key-agreement protocol.  Both parties call this
    function with their own private key and the other party's public key.
    The output is the same 32-byte value on both sides — without either party
    ever having transmitted it.

    Why this is secure:
        Knowing only the two public keys, an eavesdropper cannot reproduce
        the shared secret (this would require solving the elliptic-curve
        discrete-log problem, which is computationally infeasible).

    IMPORTANT — you MUST hash / derive a proper key from this raw output
    before using it for encryption.  The raw X25519 output has a small chance
    of being a degenerate "all-zeros" value for certain malicious public keys.
    Use ``derive_key_from_secret()`` in crypto/symmetric.py to convert this
    into a safe symmetric key.  The higher-level ``encrypt_message()`` in
    crypto/__init__.py handles this automatically.

    Args:
        my_private_key:  Your 32-byte X25519 private key.
        their_public_key: The other party's 32-byte X25519 public key.

    Returns:
        A 32-byte shared secret.  This is the same value both sides compute.

    Raises:
        ValueError: If either key is not exactly 32 bytes.
        nacl.exceptions.CryptoError: If libsodium rejects the keys.

    Example::

        # Alice side
        alice_priv, alice_pub = generate_ephemeral_keypair()
        # Bob side
        bob_priv, bob_pub = generate_ephemeral_keypair()

        # Both compute the same shared secret:
        shared_a = compute_shared_secret(alice_priv, bob_pub)
        shared_b = compute_shared_secret(bob_priv, alice_pub)
        assert shared_a == shared_b
    """
    if len(my_private_key) != KEY_SIZE:
        raise ValueError(
            f"Private key must be {KEY_SIZE} bytes, got {len(my_private_key)}"
        )
    if len(their_public_key) != KEY_SIZE:
        raise ValueError(
            f"Public key must be {KEY_SIZE} bytes, got {len(their_public_key)}"
        )

    # crypto_scalarmult(n, p) computes n·p on Curve25519.
    # n = our private key (scalar), p = their public key (curve point).
    # The result is the shared point, encoded as 32 bytes.
    shared = crypto_scalarmult(my_private_key, their_public_key)

    logger.debug("X25519 DH exchange completed — shared secret computed")
    return shared
