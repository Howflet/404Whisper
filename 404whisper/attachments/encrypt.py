"""
attachments/encrypt.py — File encryption and decryption for attachments.

DATA_CONTRACT § Attachment — Encryption (AES-256-CBC + HMAC-SHA256).

This module implements the Session file server attachment encryption protocol:
  - AES-256-CBC for confidentiality  (symmetric block cipher, 256-bit key)
  - HMAC-SHA256 for integrity        (message authentication, 256-bit key)
  - PKCS7 padding to align plaintext to 16-byte (128-bit) AES blocks

Wire format of an encrypted blob (returned by encrypt(), consumed by decrypt()):
    ┌──────────────────────────────────────────────────┐
    │  IV (16 bytes)                                   │ ← random per-file IV
    │  Ciphertext (N bytes, PKCS7-padded, multiple 16) │ ← AES-256-CBC output
    │  HMAC (32 bytes)                                 │ ← SHA-256 over IV+ciphertext
    └──────────────────────────────────────────────────┘

Security model:
  - "Encrypt-then-MAC": the HMAC covers (IV + ciphertext), not plaintext.
    This prevents chosen-ciphertext attacks — the HMAC is verified before
    any decryption is attempted.
  - Keys are generated fresh per file (generate_keys()), stored in the DB
    as BLOB columns, and NEVER sent to the API client.
  - hmac.compare_digest() is used for constant-time comparison to avoid
    timing-based HMAC oracle attacks.

Public surface:
    KEY_BYTES           → 32  (AES-256 key size, also HMAC-SHA256 key size)
    generate_keys()     → (aes_key: bytes, hmac_key: bytes)
    encrypt(plaintext, aes_key, hmac_key) → encrypted_blob: bytes
    decrypt(blob, aes_key, hmac_key)      → plaintext: bytes
"""

from __future__ import annotations

import hmac
import os
from hashlib import sha256

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


# ── constants ──────────────────────────────────────────────────────────────

# AES block size is always 128 bits (16 bytes) regardless of key length.
_AES_BLOCK_BYTES: int = 16

# AES-256 requires a 32-byte key; HMAC-SHA256 also uses a 32-byte key.
KEY_BYTES: int = 32

# The IV is one AES block = 16 bytes.
_IV_BYTES: int = 16

# HMAC-SHA256 digest output is 32 bytes.
_HMAC_BYTES: int = 32


# ── key generation ─────────────────────────────────────────────────────────


def generate_keys() -> tuple[bytes, bytes]:
    """
    Generate a fresh random AES-256 key and HMAC-SHA256 key.

    Returns:
        (aes_key, hmac_key) — each is KEY_BYTES (32) random bytes from os.urandom.

    Call this once per attachment upload; store both keys in the DB as BLOBs.
    Never reuse keys across files.

    Example:
        aes_key, hmac_key = generate_keys()
        blob = encrypt(file_bytes, aes_key, hmac_key)
        # store aes_key + hmac_key in DB, store blob on disk
    """
    aes_key  = os.urandom(KEY_BYTES)
    hmac_key = os.urandom(KEY_BYTES)
    return aes_key, hmac_key


# ── encryption ─────────────────────────────────────────────────────────────


def encrypt(plaintext: bytes, aes_key: bytes, hmac_key: bytes) -> bytes:
    """
    Encrypt plaintext bytes using AES-256-CBC, then authenticate with HMAC-SHA256.

    Steps:
      1. Generate a random 16-byte IV.
      2. Apply PKCS7 padding to align plaintext to 16-byte blocks.
      3. Encrypt padded plaintext with AES-256-CBC.
      4. Compute HMAC-SHA256 over (IV + ciphertext) — encrypt-then-MAC.
      5. Return IV + ciphertext + HMAC as a single byte string.

    Args:
        plaintext: Raw file bytes to encrypt (any length, including zero).
        aes_key:   32-byte AES-256 key (from generate_keys()).
        hmac_key:  32-byte HMAC key (from generate_keys()).

    Returns:
        Encrypted blob: IV (16 B) + ciphertext (padded N B) + HMAC (32 B).

    Example:
        aes_key, hmac_key = generate_keys()
        blob = encrypt(b"hello world", aes_key, hmac_key)
        assert len(blob) == 16 + 16 + 32   # 11 bytes padded to 16 + overhead
    """
    # Step 1: fresh random IV for this encryption — never reuse an IV with the same key.
    iv = os.urandom(_IV_BYTES)

    # Step 2: PKCS7 padding ensures the plaintext length is a multiple of 16 bytes.
    padder = padding.PKCS7(_AES_BLOCK_BYTES * 8).padder()
    padded_plaintext = padder.update(plaintext) + padder.finalize()

    # Step 3: AES-256-CBC encryption.
    cipher    = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_plaintext) + encryptor.finalize()

    # Step 4: HMAC-SHA256 over (IV + ciphertext) for integrity verification.
    # Using stdlib hmac — no external dependency beyond 'cryptography' for AES.
    mac = hmac.new(hmac_key, iv + ciphertext, sha256).digest()

    # Step 5: concatenate everything into one blob for storage.
    return iv + ciphertext + mac


# ── decryption ─────────────────────────────────────────────────────────────


def decrypt(blob: bytes, aes_key: bytes, hmac_key: bytes) -> bytes:
    """
    Verify HMAC and decrypt a blob produced by encrypt().

    Steps:
      1. Split the blob into IV, ciphertext, and HMAC.
      2. Recompute the expected HMAC and compare (constant-time).
      3. If HMAC matches, decrypt the ciphertext with AES-256-CBC.
      4. Remove PKCS7 padding to recover the original plaintext.

    Args:
        blob:     Encrypted blob (IV + ciphertext + HMAC) from encrypt().
        aes_key:  32-byte AES-256 key originally used to encrypt.
        hmac_key: 32-byte HMAC key originally used to encrypt.

    Returns:
        Original plaintext bytes.

    Raises:
        ValueError: if the HMAC does not match — the data was tampered with
                    or the wrong keys were supplied.

    Example:
        plaintext = b"hello world"
        aes_key, hmac_key = generate_keys()
        blob      = encrypt(plaintext, aes_key, hmac_key)
        recovered = decrypt(blob, aes_key, hmac_key)
        assert recovered == plaintext
    """
    # Step 1: unpack the fixed-size IV and HMAC from the blob ends.
    # Layout: [IV (16)] [ciphertext (variable)] [HMAC (32)]
    iv         = blob[:_IV_BYTES]
    mac        = blob[-_HMAC_BYTES:]
    ciphertext = blob[_IV_BYTES:-_HMAC_BYTES]

    # Step 2: verify HMAC before touching the ciphertext.
    # compare_digest() runs in constant time — prevents timing oracle attacks.
    expected_mac = hmac.new(hmac_key, iv + ciphertext, sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError(
            "HMAC verification failed — attachment data may be tampered with "
            "or the wrong keys were supplied."
        )

    # Step 3: AES-256-CBC decryption.
    cipher    = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # Step 4: strip PKCS7 padding to recover original bytes.
    unpadder  = padding.PKCS7(_AES_BLOCK_BYTES * 8).unpadder()
    plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()

    return plaintext
