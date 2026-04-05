"""
Layer 2 — Crypto: Symmetric authenticated encryption (XSalsa20-Poly1305).

What this file does (plain English):
    Once Alice and Bob have agreed on a shared secret via X25519 (see
    x25519.py), they need to actually encrypt and decrypt messages using
    that secret.  That's what this file handles.

    XSalsa20-Poly1305 is a combination cipher + MAC:
      - XSalsa20  is a stream cipher that scrambles the plaintext.
        Think of it like running the plaintext through a blender whose
        settings are determined by the key and a random nonce.
      - Poly1305  is a Message Authentication Code (MAC) — a short
        fingerprint that proves the ciphertext hasn't been tampered with.
        If even one bit is flipped, decryption fails loudly.

    Together they provide *authenticated encryption*: confidentiality
    (nobody can read it) + integrity (nobody can modify it undetected).

    This is the same construction used by NaCl's SecretBox, which is
    battle-tested and used by thousands of real-world apps.

Key derivation:
    The raw X25519 shared secret from x25519.py is NOT used directly as
    the symmetric key — it must first be "hardened" via a key derivation
    function (KDF) to remove any potential weak bits.  ``derive_key()``
    in this module handles that step using BLAKE2b.

Nonce handling:
    A "nonce" (number used once) is a random value mixed into every
    encryption call so that encrypting the same plaintext twice produces
    different ciphertext.  We generate a fresh 24-byte nonce for every
    encryption and prepend it to the ciphertext so the decryptor knows
    what to use.  Nonces are NOT secret — only the key is.

Session protocol note:
    Session message bodies are encrypted with a symmetric key derived from
    the X25519 DH exchange between sender and recipient.  Group messages
    use a shared group key distributed to members via 1-to-1 encrypted
    messages (Layer 5).
"""
from __future__ import annotations

import logging
import os

# SecretBox — authenticated symmetric encryption with a 32-byte secret key.
# Internally: XSalsa20 stream cipher + Poly1305 MAC.
from nacl.secret import SecretBox
from nacl.exceptions import CryptoError

# BLAKE2b is a fast, cryptographically secure hash function.
# We use it here as a KDF (Key Derivation Function) to turn raw DH output
# into a safe symmetric key.
from nacl.hash import blake2b as nacl_blake2b
from nacl.encoding import RawEncoder

logger = logging.getLogger(__name__)

# XSalsa20-Poly1305 key is always 32 bytes.
KEY_SIZE: int = SecretBox.KEY_SIZE        # 32
# XSalsa20 nonce is always 24 bytes.
NONCE_SIZE: int = SecretBox.NONCE_SIZE    # 24
# Poly1305 MAC tag appended to every ciphertext — 16 bytes overhead.
MAC_SIZE: int = 16


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def derive_key(
    shared_secret: bytes,
    context: bytes = b"404whisper-v1",
) -> bytes:
    """
    Derive a safe 32-byte symmetric encryption key from a raw X25519 shared secret.

    WHY NOT use the raw shared secret directly?
        The raw X25519 output, while 32 bytes, can theoretically be a
        degenerate all-zeros value for a maliciously crafted public key.
        Passing it through BLAKE2b eliminates this risk, mixes in a
        domain-separation context string, and produces uniform key material.

    HOW it works:
        BLAKE2b is a cryptographic hash function.  We hash the shared secret
        (optionally keyed by a context string) to produce the final key.
        The context "404whisper-v1" ensures that keys derived in this app
        are distinct from keys derived with the same DH secret in any other
        app — a technique called domain separation.

    Args:
        shared_secret: The 32-byte output of ``x25519.compute_shared_secret()``.
        context:       An optional byte string that "namespaces" the derived key.
                       Change this for different key purposes (e.g., group keys)
                       to ensure they are always distinct from message keys.

    Returns:
        A 32-byte symmetric key safe to pass to ``encrypt()`` / ``decrypt()``.

    Raises:
        ValueError: If ``shared_secret`` is not exactly 32 bytes.

    Example::

        from crypto.x25519 import compute_shared_secret
        raw = compute_shared_secret(my_priv, their_pub)
        key = derive_key(raw)
        # key is now safe to use for symmetric encryption
    """
    if len(shared_secret) != 32:
        raise ValueError(
            f"shared_secret must be 32 bytes, got {len(shared_secret)}"
        )

    # BLAKE2b produces a 64-byte digest by default.  We take the first 32
    # bytes as the symmetric key (the second 32 are safely discarded).
    #
    # Concatenating the context before hashing gives us domain separation:
    # same secret → different keys depending on context.
    digest = nacl_blake2b(shared_secret + context, encoder=RawEncoder)

    # digest is 64 bytes; we only need 32 for a SecretBox key.
    key = digest[:KEY_SIZE]
    logger.debug("derive_key: produced %d-byte symmetric key", len(key))
    return key


# ---------------------------------------------------------------------------
# Encrypt
# ---------------------------------------------------------------------------


def encrypt(plaintext: bytes, key: bytes) -> bytes:
    """
    Encrypt and authenticate arbitrary bytes using XSalsa20-Poly1305.

    Every call generates a fresh cryptographically random 24-byte nonce
    and prepends it to the ciphertext.  This means:
      - Encrypting the same plaintext twice gives DIFFERENT ciphertext
        (because the nonce differs), which prevents traffic analysis.
      - The nonce is NOT secret; it's needed for decryption.

    The MAC tag (Poly1305) is automatically appended inside the ciphertext
    so ``decrypt()`` can verify integrity before returning any bytes.

    Output format:
        ``[24-byte nonce][ciphertext + 16-byte MAC]``
        Total length = 24 + len(plaintext) + 16 bytes.

    Args:
        plaintext: Any bytes you want to encrypt (message body, file chunk, etc.)
        key:       A 32-byte symmetric key (from ``derive_key()``).

    Returns:
        Nonce + authenticated ciphertext as a single bytes object.

    Raises:
        ValueError: If ``key`` is not exactly 32 bytes.

    Example::

        ciphertext = encrypt(b"Hello Bob!", key)
        # ciphertext can be sent safely over an untrusted channel
    """
    if len(key) != KEY_SIZE:
        raise ValueError(f"key must be {KEY_SIZE} bytes, got {len(key)}")

    # Build the SecretBox with our key.  This is cheap (just stores the key).
    box = SecretBox(key)

    # Generate a fresh random nonce for this encryption.
    # NEVER reuse a nonce with the same key — that would break secrecy.
    nonce = os.urandom(NONCE_SIZE)

    # box.encrypt() returns a EncryptedMessage (bytes subclass) whose
    # layout is: nonce (24) + ciphertext + MAC (16).
    # RawEncoder means we get pure bytes back, not base64.
    encrypted = box.encrypt(plaintext, nonce=nonce, encoder=RawEncoder)

    logger.debug(
        "encrypt: %d plaintext bytes → %d ciphertext bytes",
        len(plaintext),
        len(encrypted),
    )
    return bytes(encrypted)


# ---------------------------------------------------------------------------
# Decrypt
# ---------------------------------------------------------------------------


def decrypt(ciphertext: bytes, key: bytes) -> bytes:
    """
    Decrypt and verify a ciphertext produced by ``encrypt()``.

    The first 24 bytes of ``ciphertext`` are the nonce (extracted
    automatically).  The remaining bytes are the XSalsa20 ciphertext
    and Poly1305 MAC.  If the MAC check fails — meaning the ciphertext was
    modified in any way — this function raises ``CryptoError`` before
    returning a single byte of plaintext.

    This property (refusing to return data that fails the MAC) is called
    *authenticated decryption* and is critical for security.  Unauthenticated
    decryption can be exploited via padding oracles and similar attacks.

    Args:
        ciphertext: The bytes returned by ``encrypt()`` —
                    nonce (24) + ciphertext + MAC (16).
        key:        The same 32-byte symmetric key used to encrypt.

    Returns:
        The original plaintext bytes, identical to what was passed to ``encrypt()``.

    Raises:
        ValueError:   If ``key`` is not exactly 32 bytes.
        CryptoError:  If MAC verification fails (ciphertext was tampered with,
                      or the wrong key was used).  This is a security signal —
                      log and discard the message; never silently ignore it.

    Example::

        plaintext = decrypt(ciphertext, key)
        assert plaintext == b"Hello Bob!"
    """
    if len(key) != KEY_SIZE:
        raise ValueError(f"key must be {KEY_SIZE} bytes, got {len(key)}")

    box = SecretBox(key)

    # decrypt() reads the nonce from the first NONCE_SIZE bytes automatically,
    # verifies the MAC, and returns plaintext.  Raises CryptoError on failure.
    try:
        plaintext = box.decrypt(ciphertext, encoder=RawEncoder)
    except CryptoError as exc:
        logger.error(
            "decrypt: MAC verification FAILED — ciphertext may have been tampered with"
        )
        raise  # Re-raise so callers can decide how to handle this

    logger.debug(
        "decrypt: %d ciphertext bytes → %d plaintext bytes",
        len(ciphertext),
        len(plaintext),
    )
    return bytes(plaintext)


# ---------------------------------------------------------------------------
# Convenience: Box (encrypt-to-recipient without manual DH)
# ---------------------------------------------------------------------------


def encrypt_to_recipient(
    plaintext: bytes,
    sender_private_key: bytes,
    recipient_public_key: bytes,
) -> bytes:
    """
    Encrypt a message from a sender to a specific recipient using DH + symmetric encryption.

    This bundles the X25519 DH + ``derive_key()`` + ``encrypt()`` into one
    call.  Internally it uses PyNaCl's ``Box`` which implements the NaCl
    ``crypto_box`` primitive — the same combination (X25519 + HSalsa20 + XSalsa20 + Poly1305)
    used throughout the Session protocol.

    Args:
        plaintext:            The bytes to encrypt.
        sender_private_key:   Sender's 32-byte X25519 private key.
        recipient_public_key: Recipient's 32-byte X25519 public key.

    Returns:
        Nonce (24) + authenticated ciphertext bytes.

    Example::

        ciphertext = encrypt_to_recipient(b"Hi Bob", alice_priv, bob_pub)
        plaintext  = decrypt_from_sender(ciphertext, bob_priv, alice_pub)
        assert plaintext == b"Hi Bob"
    """
    # Import here to avoid circular imports between crypto submodules.
    from nacl.public import PrivateKey, PublicKey, Box

    sender_sk = PrivateKey(sender_private_key)
    recipient_pk = PublicKey(recipient_public_key)
    box = Box(sender_sk, recipient_pk)

    nonce = os.urandom(NONCE_SIZE)
    encrypted = box.encrypt(plaintext, nonce=nonce, encoder=RawEncoder)
    logger.debug(
        "encrypt_to_recipient: %d → %d bytes",
        len(plaintext),
        len(encrypted),
    )
    return bytes(encrypted)


def decrypt_from_sender(
    ciphertext: bytes,
    recipient_private_key: bytes,
    sender_public_key: bytes,
) -> bytes:
    """
    Decrypt a message produced by ``encrypt_to_recipient()``.

    The roles are simply reversed: the recipient uses their own private key
    + the sender's public key to reconstruct the same shared secret.

    Args:
        ciphertext:           Bytes from ``encrypt_to_recipient()``.
        recipient_private_key: Recipient's 32-byte X25519 private key.
        sender_public_key:    Sender's 32-byte X25519 public key.

    Returns:
        The original plaintext bytes.

    Raises:
        CryptoError: If MAC verification fails.
    """
    from nacl.public import PrivateKey, PublicKey, Box

    recipient_sk = PrivateKey(recipient_private_key)
    sender_pk = PublicKey(sender_public_key)
    box = Box(recipient_sk, sender_pk)

    try:
        plaintext = box.decrypt(ciphertext, encoder=RawEncoder)
    except CryptoError:
        logger.error("decrypt_from_sender: MAC verification FAILED")
        raise

    logger.debug(
        "decrypt_from_sender: %d → %d bytes",
        len(ciphertext),
        len(plaintext),
    )
    return bytes(plaintext)
