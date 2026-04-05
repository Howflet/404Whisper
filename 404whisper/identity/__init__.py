"""
Identity & Authentication Layer

Provides high-level functions for identity management.
"""

from .keypair import generate_keypair, derive_session_id, public_key_from_session_id
from .mnemonic import encode_mnemonic, decode_mnemonic
from .keystore import Keystore

def create_identity(passphrase: str, keystore_path: str) -> str:
    """
    Create a new identity with keystore.

    Returns the Session ID.
    """
    private_key, public_key = generate_keypair()
    session_id = derive_session_id(public_key)

    keystore = Keystore(keystore_path)
    keystore.store_key(private_key, passphrase)

    return session_id

def load_identity(passphrase: str, keystore_path: str) -> Optional[str]:
    """
    Load identity from keystore.

    Returns Session ID if successful, None if wrong passphrase or no keystore.
    """
    keystore = Keystore(keystore_path)
    private_key = keystore.load_key(passphrase)

    if private_key is None:
        return None

    # Reconstruct public key from private key
    import nacl.public
    private_key_obj = nacl.public.PrivateKey(private_key)
    public_key = private_key_obj.public_key.encode()

    return derive_session_id(public_key)

def import_from_mnemonic(mnemonic: str, passphrase: str, keystore_path: str) -> str:
    """
    Import identity from mnemonic phrase.

    Returns the Session ID.
    """
    private_key = decode_mnemonic(mnemonic)
    session_id = create_identity(passphrase, keystore_path)
    return session_id