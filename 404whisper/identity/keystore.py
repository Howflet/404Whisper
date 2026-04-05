"""
Layer 1 — Identity: Encrypted keystore.

What this file does (plain English):
    Your private key (the seed) is the most sensitive piece of data in the app.
    This file is responsible for SAVING it to disk in an encrypted form and
    LOADING it back again, using your passphrase as the "unlock code".

    Think of it like a safe:
      - store_seed()  → put the secret inside the safe and lock it with your passphrase.
      - load_seed()   → enter your passphrase to open the safe and retrieve the secret.

Two-stage security:
    1. Key Derivation (passphrase → encryption key):
         Argon2id  — deliberately slow and memory-hard so brute-forcing passwords
         is extremely expensive.  Even a GPU can only try a few guesses per second.
    2. Encryption (seed → ciphertext):
         AES-256-GCM — encrypts the 32-byte seed so it can be stored safely on disk.
         GCM mode also authenticates the ciphertext: if anyone tampers with the
         saved file, decryption will fail with an error rather than silently
         returning corrupt data.

File format (JSON):
    {
        "v"     : 1,           -- format version, for future upgrades
        "salt"  : "<hex>",     -- 16 random bytes fed into Argon2 (unique per save)
        "nonce" : "<hex>",     -- 12 random bytes fed into AES-GCM (unique per save)
        "ct"    : "<hex>"      -- the AES-GCM ciphertext + 16-byte auth tag
    }
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

# cryptography is the de-facto standard Python crypto library (wraps OpenSSL).
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Argon2id parameters (OWASP recommended minimum for interactive logins, 2024)
#
# time_cost   = 2   — number of hash iterations
# memory_cost = 65536 — memory used in KiB (64 MiB)
# parallelism = 1   — thread count
# length      = 32  — output key size in bytes (matches AES-256 key size)
# ---------------------------------------------------------------------------
_ARGON2_TIME    = 2
_ARGON2_MEMORY  = 65_536   # 64 MiB — makes brute-force expensive
_ARGON2_LANES   = 1
_KEY_LEN        = 32       # 256 bits → AES-256
_SALT_LEN       = 16       # 128 bits of salt
_NONCE_LEN      = 12       # 96 bits — standard for AES-GCM

# Bump this if the serialisation format ever changes, so old files can be
# detected and migrated rather than silently broken.
_FORMAT_VERSION = 1


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class KeystoreError(Exception):
    """Base class for all keystore failures."""


class WrongPassphraseError(KeystoreError):
    """
    Raised when decryption fails because the passphrase is incorrect.

    Note: AES-GCM authentication failure (wrong key) looks the same as data
    tampering.  We surface one unified error for both cases — no information
    leak about which one actually occurred.
    """


class KeystoreNotFoundError(KeystoreError):
    """Raised when store_seed() has never been called for this path."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def store_seed(seed: bytes, passphrase: str, path: Path) -> None:
    """
    Encrypt a 32-byte seed with ``passphrase`` and write it to ``path``.

    Each call uses fresh random salt and nonce, so the ciphertext on disk is
    different every time even for the same seed + passphrase pair.

    Args:
        seed      : Exactly 32 bytes — the identity seed to protect.
        passphrase: The user's passphrase string.  Must be at least 8 chars
                    (enforced by the API layer before this is called).
        path      : Filesystem path where the JSON keystore file will be written.
                    Parent directory must already exist.

    Raises:
        ValueError: If seed is not exactly 32 bytes.
    """
    if len(seed) != 32:
        raise ValueError(f"seed must be 32 bytes, got {len(seed)}")

    # ── Step 1: derive an AES-256 key from the passphrase ─────────────────
    salt = os.urandom(_SALT_LEN)   # fresh randomness every save
    aes_key = _derive_key(passphrase, salt)

    # ── Step 2: encrypt the seed with AES-256-GCM ─────────────────────────
    nonce = os.urandom(_NONCE_LEN)  # must be unique for every encryption
    aesgcm = AESGCM(aes_key)
    # encrypt() returns ciphertext + 16-byte authentication tag concatenated.
    ciphertext = aesgcm.encrypt(nonce, seed, associated_data=None)

    # ── Step 3: write to disk as JSON ────────────────────────────────────
    payload = {
        "v"    : _FORMAT_VERSION,
        "salt" : salt.hex(),
        "nonce": nonce.hex(),
        "ct"   : ciphertext.hex(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.debug("Keystore written to %s", path)


def load_seed(passphrase: str, path: Path) -> bytes:
    """
    Decrypt and return the 32-byte seed from a keystore file.

    Args:
        passphrase: The same passphrase used when ``store_seed()`` was called.
        path      : Path to the JSON keystore file.

    Returns:
        The original 32-byte seed.

    Raises:
        KeystoreNotFoundError : If the keystore file does not exist.
        WrongPassphraseError  : If the passphrase is wrong or the file is corrupt.
    """
    if not path.exists():
        raise KeystoreNotFoundError(f"No keystore at {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))

    salt       = bytes.fromhex(payload["salt"])
    nonce      = bytes.fromhex(payload["nonce"])
    ciphertext = bytes.fromhex(payload["ct"])

    # Re-derive the exact same AES key using the stored salt + the passphrase.
    aes_key = _derive_key(passphrase, salt)

    try:
        # decrypt() also verifies the auth tag — raises InvalidTag if wrong key
        # or tampered data.
        seed = AESGCM(aes_key).decrypt(nonce, ciphertext, associated_data=None)
    except Exception as exc:
        # Deliberately vague: don't reveal whether key derivation or
        # authentication failed — both map to "wrong passphrase."
        raise WrongPassphraseError("Incorrect passphrase or corrupted keystore.") from exc

    logger.debug("Keystore loaded from %s", path)
    return seed


def verify_passphrase(passphrase: str, path: Path) -> bool:
    """
    Return True if ``passphrase`` successfully decrypts the keystore.

    This is a convenience wrapper around :func:`load_seed` used by the
    ``POST /api/identity/unlock`` route.

    Args:
        passphrase: Passphrase to test.
        path      : Path to the keystore file.

    Returns:
        True if the passphrase is correct, False otherwise.
    """
    try:
        load_seed(passphrase, path)
        return True
    except (WrongPassphraseError, KeystoreNotFoundError):
        return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """
    Derive a 32-byte AES key from a passphrase using Argon2id.

    Argon2id is deliberately expensive so that an attacker who steals the
    keystore file cannot guess weak passphrases quickly.

    Args:
        passphrase: User's passphrase (UTF-8 encoded internally).
        salt      : 16 random bytes stored alongside the ciphertext.

    Returns:
        32-byte key suitable for AES-256.
    """
    kdf = Argon2id(
        salt=salt,
        length=_KEY_LEN,
        iterations=_ARGON2_TIME,
        lanes=_ARGON2_LANES,
        memory_cost=_ARGON2_MEMORY,
    )
    return kdf.derive(passphrase.encode("utf-8"))
