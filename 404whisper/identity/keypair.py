"""
Layer 1 — Identity: Keypair derivation.

What this file does (plain English):
    Your Session identity is a pair of cryptographic keys generated from a
    single random 32-byte "seed" (think of it like a master password stored
    as raw bytes).  Give the same seed in → always get the same keys out.

    The *public* key becomes your Session ID and is freely shared.
    The *private* key (the seed itself) never leaves this machine.

Two key types are derived from one seed:
    X25519  — used for encrypting messages TO someone (key agreement).
    Ed25519 — used for signing messages FROM you (proving authenticity).

Session ID format (per Session protocol spec):
    "05" + hex(x25519_public_key)   →  66 lowercase hex chars total
    Example: 057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5b

    The "05" prefix tells the network: "this is an X25519 key."
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

# PyNaCl wraps libsodium — the industry-standard cryptography library.
# PrivateKey handles X25519 (encryption), SigningKey handles Ed25519 (signing).
from nacl.public import PrivateKey
from nacl.signing import SigningKey

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data container — bundles every key derived from a single seed.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Keypair:
    """
    A complete Session keypair derived from one 32-byte seed.

    frozen=True means the object is immutable after creation — no accidental
    overwriting of key material.

    Attributes:
        seed           : The original secret 32-byte seed.  Protect this.
        x25519_private : 32-byte X25519 private key (for DH key exchange).
        x25519_public  : 32-byte X25519 public key (safe to share).
        ed25519_private: 32-byte Ed25519 signing seed (keep secret).
        ed25519_public : 32-byte Ed25519 verify key (safe to share).
        session_id     : "05" + hex(x25519_public) — your network address.
    """

    seed: bytes
    x25519_private: bytes
    x25519_public: bytes
    ed25519_private: bytes
    ed25519_public: bytes
    session_id: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def derive_session_id(seed: bytes) -> str:
    """
    Derive a Session ID from a 32-byte seed.

    This is what the unit tests call.  It takes raw secret bytes and returns
    the 66-char public address other users will send messages to.

    How it works step-by-step:
        1. Use the seed as an X25519 private key (PyNaCl does this directly).
        2. Ask PyNaCl for the matching public key (32 bytes).
        3. Hex-encode those 32 bytes → 64 hex chars.
        4. Prepend "05" → 66-char Session ID.

    Args:
        seed: Exactly 32 bytes of entropy.  Use ``os.urandom(32)`` for new
              identities; use a stored seed to restore an existing identity.

    Returns:
        66-character lowercase hex string starting with "05".
        Deterministic — same seed always produces the same Session ID.

    Raises:
        ValueError: If ``seed`` is not exactly 32 bytes.

    Example::

        >>> session_id = derive_session_id(os.urandom(32))
        >>> assert session_id.startswith("05")
        >>> assert len(session_id) == 66
    """
    if len(seed) != 32:
        raise ValueError(f"seed must be exactly 32 bytes, got {len(seed)}")

    # PrivateKey(seed) builds an X25519 key pair deterministically from the seed.
    # .public_key is the paired public key — safe to share with anyone.
    priv = PrivateKey(seed)
    pub_bytes = bytes(priv.public_key)  # 32 bytes

    # Prepend the Session protocol X25519 key-type prefix.
    return "05" + pub_bytes.hex()  # "05" + 64 hex chars = 66 total


def generate_keypair(seed: bytes) -> Keypair:
    """
    Derive a full Session keypair (X25519 + Ed25519) from a 32-byte seed.

    Both key types share the same seed, so a single secret backup (the seed
    or its mnemonic representation) is enough to restore the entire identity.

    Args:
        seed: Exactly 32 bytes of random data.

    Returns:
        A frozen :class:`Keypair` containing all derived key material and the
        Session ID string.

    Raises:
        ValueError: If ``seed`` is not exactly 32 bytes.
    """
    if len(seed) != 32:
        raise ValueError(f"seed must be exactly 32 bytes, got {len(seed)}")

    # ── X25519: encryption keys ───────────────────────────────────────────
    # PyNaCl derives the X25519 public key automatically from the private key.
    x25519_priv = PrivateKey(seed)
    x25519_pub  = bytes(x25519_priv.public_key)

    # ── Ed25519: signing keys ─────────────────────────────────────────────
    # SigningKey accepts a 32-byte seed and expands it internally into the
    # full 64-byte key material.  We store only the compact 32-byte form.
    ed25519_priv = SigningKey(seed)
    ed25519_pub  = bytes(ed25519_priv.verify_key)

    session_id = "05" + x25519_pub.hex()
    logger.debug("Keypair generated — session_id=%s", session_id)

    return Keypair(
        seed=seed,
        x25519_private=bytes(x25519_priv),
        x25519_public=x25519_pub,
        ed25519_private=bytes(ed25519_priv),
        ed25519_public=ed25519_pub,
        session_id=session_id,
    )


def public_key_from_session_id(session_id: str) -> bytes:
    """
    Extract the raw 32-byte X25519 public key from a Session ID string.

    This is the inverse of the "05" + hex() formatting in derive_session_id.

    Args:
        session_id: A valid 66-character Session ID (e.g. "05ab…").

    Returns:
        32-byte X25519 public key.

    Raises:
        ValueError: If the Session ID is malformed.
    """
    if not session_id.startswith("05") or len(session_id) != 66:
        raise ValueError(
            f"Invalid Session ID — must be 66 hex chars starting with '05', "
            f"got: {session_id!r}"
        )
    return bytes.fromhex(session_id[2:])
