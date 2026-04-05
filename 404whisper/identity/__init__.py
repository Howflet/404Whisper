"""
Layer 1 — Identity: public surface.

What this package does (plain English):
    This is the entry point for everything related to WHO YOU ARE inside
    404Whisper.  Your identity is defined by a single secret: a 32-byte seed.
    From that seed we can derive:
      - Your Session ID  (your public address — share this freely)
      - Your keypair     (private + public keys for encryption and signing)
      - A mnemonic       (13-25 human-readable backup words)

    This file wires together the three sub-modules:
        identity/keypair.py   — key derivation
        identity/mnemonic.py  — seed phrase encode / decode
        identity/keystore.py  — encrypted on-disk storage

Two main flows:
    1. New identity  → generate a random seed, encode to mnemonic, store encrypted.
    2. Import        → decode the mnemonic back to its seed, store encrypted.

Everything in this package is *synchronous*.  The async API routes in
404whisper/api/routes/identity.py call these functions via FastAPI's
``run_in_executor`` if they need to remain non-blocking.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

# Re-export the public symbols from sub-modules so callers can do:
#   from 404whisper.identity import derive_session_id, encode, decode
from .keypair  import derive_session_id, generate_keypair, public_key_from_session_id
from .mnemonic import encode, decode, MnemonicDecodeError
from .keystore import store_seed, load_seed, verify_passphrase, WrongPassphraseError

logger = logging.getLogger(__name__)

__all__ = [
    # keypair
    "derive_session_id",
    "generate_keypair",
    "public_key_from_session_id",
    # mnemonic
    "encode",
    "decode",
    "MnemonicDecodeError",
    # keystore
    "store_seed",
    "load_seed",
    "verify_passphrase",
    "WrongPassphraseError",
    # high-level flows
    "create_identity",
    "import_from_mnemonic",
]


# ---------------------------------------------------------------------------
# High-level identity flows
# ---------------------------------------------------------------------------


def create_identity(
    passphrase: str,
    keystore_path: Path | None = None,
) -> dict:
    """
    Generate a brand-new identity from scratch.

    Steps:
        1. Generate 32 random bytes as the seed (via os.urandom).
        2. Derive the Session ID (public address) from that seed.
        3. Encode the seed into a mnemonic phrase for human backup.
        4. Encrypt the seed with the passphrase and write to keystore_path.

    The mnemonic is returned ONCE and must be shown to the user immediately.
    It is NOT stored anywhere — if the user loses it and forgets their
    passphrase they cannot recover their identity.

    Args:
        passphrase    : User's passphrase (must be ≥ 8 chars — checked by caller).
        keystore_path : Where to write the encrypted keystore file.
                        If None, the keystore write is skipped (useful in tests).

    Returns:
        A dict with keys:
            ``session_id``  — 66-char hex string (the user's public address).
            ``mnemonic``    — 25-word backup phrase.  Show once, then discard.
            ``created_at``  — UTC ISO-8601 timestamp string.
    """
    # Step 1: 32 cryptographically random bytes → the root of the identity.
    seed = os.urandom(32)

    # Step 2: derive the public Session ID from the seed.
    session_id = derive_session_id(seed)

    # Step 3: convert the seed to a human-readable mnemonic backup.
    mnemonic = encode(seed)

    # Step 4: (optionally) save the seed encrypted to disk.
    if keystore_path is not None:
        store_seed(seed, passphrase, Path(keystore_path))

    created_at = datetime.now(timezone.utc).isoformat()
    logger.info("New identity created — session_id=%s", session_id)

    return {
        "session_id": session_id,
        "mnemonic"  : mnemonic,
        "created_at": created_at,
    }


def import_from_mnemonic(
    mnemonic: str,
    passphrase: str,
    keystore_path: Path | None = None,
) -> dict:
    """
    Restore an identity from an existing mnemonic seed phrase.

    This is used when a user switches devices or reinstalls the app and
    wants to recover their old identity.

    Steps:
        1. Decode the mnemonic back into its 32-byte seed.
        2. Derive the same Session ID from that seed (deterministic).
        3. Encrypt the seed with the new passphrase and write to keystore.

    Args:
        mnemonic      : 25-word Session seed phrase.
        passphrase    : New passphrase to protect the recovered identity.
        keystore_path : Where to write the encrypted keystore.
                        If None, the write is skipped (useful in tests).

    Returns:
        A dict with keys:
            ``session_id``  — the recovered public address.
            ``created_at``  — UTC ISO-8601 timestamp string.
        Note: ``mnemonic`` is NOT echoed back for security reasons.

    Raises:
        MnemonicDecodeError: If any word is invalid or the checksum fails.
    """
    # Step 1: decode the mnemonic → 32-byte seed.
    # This raises MnemonicDecodeError on any invalid word or checksum failure.
    seed = decode(mnemonic)

    # Step 2: re-derive the Session ID (always the same for a given seed).
    session_id = derive_session_id(seed)

    # Step 3: save the recovered seed under the new passphrase.
    if keystore_path is not None:
        store_seed(seed, passphrase, Path(keystore_path))

    created_at = datetime.now(timezone.utc).isoformat()
    logger.info("Identity imported — session_id=%s", session_id)

    return {
        "session_id": session_id,
        "created_at": created_at,
    }
