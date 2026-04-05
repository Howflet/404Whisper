"""
Identity Layer - Keypair Generation and Management

Handles X25519/Ed25519 keypair generation and Session ID derivation.
"""

import nacl.signing
import nacl.public
from typing import Tuple

def generate_keypair() -> Tuple[bytes, bytes]:
    """
    Generate a new X25519/Ed25519 keypair.

    Returns:
        Tuple of (private_key_bytes, public_key_bytes)
    """
    # Generate Ed25519 signing key
    signing_key = nacl.signing.SigningKey.generate()

    # Derive X25519 from Ed25519 for encryption
    private_key = signing_key.to_curve25519_private_key()
    public_key = private_key.public_key

    return private_key.encode(), public_key.encode()

def derive_session_id(public_key: bytes) -> str:
    """
    Derive Session ID from public key.

    Session ID is the hex-encoded public key with '05' prefix.
    """
    return '05' + public_key.hex()

def public_key_from_session_id(session_id: str) -> bytes:
    """
    Extract public key bytes from Session ID.
    """
    if not session_id.startswith('05') or len(session_id) != 66:
        raise ValueError("Invalid Session ID format")

    return bytes.fromhex(session_id[2:])