"""
Layer 2 — Crypto: Ed25519 digital signatures.

What this file does (plain English):
    A digital signature is the cryptographic equivalent of a handwritten
    signature — except it's mathematically impossible to forge.

    When Alice sends a message, she "signs" it with her private key.
    Anyone who has Alice's public key can verify that:
      1. The message truly came from Alice (authentication).
      2. The message was not altered in transit (integrity).

    Without signing, an attacker could intercept and modify messages —
    even encrypted ones — without either party knowing.  Signatures close
    this gap.

    Ed25519 is the signature scheme Session uses.  It is:
      - Fast — signing and verifying take microseconds.
      - Secure — based on the Edwards-curve25519 elliptic curve.
      - Deterministic — the same key + message always produces the same
        signature (no random nonce that could leak the key if misused).

How signatures fit into the Session protocol:
    Every outgoing message envelope is signed by the sender's Ed25519 key.
    The recipient verifies the signature before accepting the message.
    This prevents impersonation and message tampering.

Relationship to identity keys:
    The Ed25519 signing key lives in identity/keypair.py as
    ``Keypair.ed25519_private`` and ``Keypair.ed25519_public``.
    The functions here accept raw bytes (from the keypair), so this module
    doesn't depend on the identity layer — only PyNaCl.

Implementation:
    PyNaCl's ``nacl.signing.SigningKey`` / ``VerifyKey`` wrap libsodium's
    ``crypto_sign_ed25519`` family of functions.  The signature size is
    always 64 bytes; the message can be any length.
"""
from __future__ import annotations

import logging

# SigningKey  — holds the 32-byte Ed25519 seed (private key).
#               Call .sign(msg) to produce a signature.
# VerifyKey   — holds the 32-byte Ed25519 public key.
#               Call .verify(msg, signature) to check a signature.
from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError
from nacl.encoding import RawEncoder

logger = logging.getLogger(__name__)

# Ed25519 signature is always exactly 64 bytes.
SIGNATURE_SIZE: int = 64
# Ed25519 private key seed is always exactly 32 bytes.
KEY_SIZE: int = 32


# ---------------------------------------------------------------------------
# Sign
# ---------------------------------------------------------------------------


def sign(message: bytes, signing_key_bytes: bytes) -> bytes:
    """
    Sign a message with an Ed25519 private key.

    Produces a 64-byte signature that proves the message was authored by
    the holder of ``signing_key_bytes`` and has not been modified.

    Think of this like sealing an envelope with a wax stamp — anyone can
    see the stamp, but only you have the seal that made it.

    Args:
        message:          The raw bytes to sign.  Can be any length, including
                          an empty byte string.
        signing_key_bytes: The 32-byte Ed25519 signing seed (the "private" half
                           of the Ed25519 keypair).  Keep this secret.

    Returns:
        64 bytes — the detached Ed25519 signature over ``message``.
        "Detached" means the signature is separate from the message, not
        prepended to it.  The caller decides how to transmit both.

    Raises:
        ValueError: If ``signing_key_bytes`` is not exactly 32 bytes.

    Example::

        sig = sign(b"Hello, Session!", signing_key_bytes=keypair.ed25519_private)
        assert len(sig) == 64
    """
    if len(signing_key_bytes) != KEY_SIZE:
        raise ValueError(
            f"Ed25519 signing key must be {KEY_SIZE} bytes, got {len(signing_key_bytes)}"
        )

    # Construct the SigningKey from raw seed bytes.
    sk = SigningKey(signing_key_bytes)

    # sign() returns a SignedMessage whose first 64 bytes are the signature.
    # Using RawEncoder to get pure bytes back (no base64 overhead).
    signed = sk.sign(message, encoder=RawEncoder)

    # signed is nonce(64) + message — we only want the detached signature
    # (the first 64 bytes), not the full signed message blob.
    signature = bytes(signed.signature)

    logger.debug(
        "Ed25519 signed %d bytes → %d-byte signature",
        len(message),
        len(signature),
    )
    return signature


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def verify(
    message: bytes,
    signature: bytes,
    verify_key_bytes: bytes,
) -> bool:
    """
    Verify an Ed25519 signature.

    Returns True if the signature is valid (the message was signed by the
    private key that corresponds to ``verify_key_bytes`` and has not been
    changed since signing).  Returns False for any invalid signature — it
    NEVER raises an exception for bad signatures, making it safe to call
    inside conditional checks without try/except boilerplate.

    Think of this like checking a wax seal: you compare it against the
    owner's known stamp impression and either it matches or it doesn't.

    Args:
        message:         The original message bytes (exactly as they were
                         when ``sign()`` was called).
        signature:       The 64-byte detached signature returned by ``sign()``.
        verify_key_bytes: The 32-byte Ed25519 public key of the signer.

    Returns:
        True  — signature is valid; the message is authentic and unmodified.
        False — signature is invalid; the message was forged or tampered with.

    Raises:
        ValueError: If ``verify_key_bytes`` is not exactly 32 bytes, or if
                    ``signature`` is not exactly 64 bytes (these are programmer
                    errors, not authentication failures).

    Example::

        ok = verify(b"Hello, Session!", signature=sig, verify_key_bytes=keypair.ed25519_public)
        assert ok is True

        tampered = b"Hello, HACKER!"
        assert verify(tampered, signature=sig, verify_key_bytes=keypair.ed25519_public) is False
    """
    if len(verify_key_bytes) != KEY_SIZE:
        raise ValueError(
            f"Ed25519 verify key must be {KEY_SIZE} bytes, got {len(verify_key_bytes)}"
        )
    if len(signature) != SIGNATURE_SIZE:
        raise ValueError(
            f"Ed25519 signature must be {SIGNATURE_SIZE} bytes, got {len(signature)}"
        )

    vk = VerifyKey(verify_key_bytes)

    try:
        # verify() raises BadSignatureError on failure; returns the message on success.
        vk.verify(message, signature, encoder=RawEncoder)
        logger.debug("Ed25519 signature VALID for %d-byte message", len(message))
        return True
    except BadSignatureError:
        # This is an expected outcome (tampered or forged message), not a crash.
        logger.warning(
            "Ed25519 signature INVALID for %d-byte message — possible tampering",
            len(message),
        )
        return False


# ---------------------------------------------------------------------------
# Convenience: sign-then-prepend and verify-then-strip
# ---------------------------------------------------------------------------


def sign_and_prepend(message: bytes, signing_key_bytes: bytes) -> bytes:
    """
    Sign a message and return the 64-byte signature prepended to the message.

    This is a convenience wrapper for the common pattern of transmitting
    the signature alongside the message as a single blob.

    Format: ``[64-byte signature][message bytes]``

    Args:
        message:          The bytes to sign.
        signing_key_bytes: 32-byte Ed25519 signing seed.

    Returns:
        64 + len(message) bytes.

    Example::

        blob = sign_and_prepend(b"hi", signing_key_bytes)
        assert len(blob) == 64 + 2
    """
    sig = sign(message, signing_key_bytes)
    return sig + message


def verify_and_strip(
    signed_blob: bytes,
    verify_key_bytes: bytes,
) -> bytes | None:
    """
    Verify a signature-prepended blob and return the inner message.

    This is the inverse of ``sign_and_prepend()``.  It extracts the
    64-byte signature from the front of the blob, verifies it, and
    returns the remaining message bytes on success.

    Args:
        signed_blob:      64+ bytes: the detached signature followed by
                          the original message (as returned by
                          ``sign_and_prepend()``).
        verify_key_bytes: 32-byte Ed25519 public key of the expected signer.

    Returns:
        The original message bytes if the signature is valid.
        None if the signature is invalid or the blob is too short.

    Example::

        msg = verify_and_strip(blob, verify_key_bytes)
        assert msg == b"hi"
    """
    if len(signed_blob) < SIGNATURE_SIZE:
        logger.warning(
            "verify_and_strip: blob too short (%d bytes, need ≥ %d)",
            len(signed_blob),
            SIGNATURE_SIZE,
        )
        return None

    signature = signed_blob[:SIGNATURE_SIZE]
    message   = signed_blob[SIGNATURE_SIZE:]

    if verify(message, signature, verify_key_bytes):
        return message
    return None
