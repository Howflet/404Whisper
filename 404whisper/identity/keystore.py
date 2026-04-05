"""
Identity Layer - Keystore

Handles encrypted storage of private keys protected by passphrase.
"""

import os
import json
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from typing import Optional, Dict, Any

class Keystore:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def _derive_key(self, passphrase: str, salt: bytes) -> bytes:
        """Derive encryption key from passphrase using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        return kdf.derive(passphrase.encode())

    def _encrypt(self, data: bytes, key: bytes) -> Dict[str, Any]:
        """Encrypt data with AES-256-CBC."""
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()

        # Pad data to block size
        block_size = 16
        padding_length = block_size - (len(data) % block_size)
        padded_data = data + bytes([padding_length]) * padding_length

        encrypted = encryptor.update(padded_data) + encryptor.finalize()

        return {
            'iv': iv.hex(),
            'data': encrypted.hex()
        }

    def _decrypt(self, encrypted_data: Dict[str, Any], key: bytes) -> bytes:
        """Decrypt data with AES-256-CBC."""
        iv = bytes.fromhex(encrypted_data['iv'])
        encrypted = bytes.fromhex(encrypted_data['data'])

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()

        decrypted_padded = decryptor.update(encrypted) + decryptor.finalize()

        # Remove padding
        padding_length = decrypted_padded[-1]
        return decrypted_padded[:-padding_length]

    def store_key(self, private_key: bytes, passphrase: str) -> None:
        """Store encrypted private key."""
        salt = os.urandom(16)
        key = self._derive_key(passphrase, salt)
        encrypted = self._encrypt(private_key, key)

        keystore_data = {
            'salt': salt.hex(),
            'encrypted_key': encrypted
        }

        with open(self.file_path, 'w') as f:
            json.dump(keystore_data, f)

    def load_key(self, passphrase: str) -> Optional[bytes]:
        """Load and decrypt private key."""
        if not os.path.exists(self.file_path):
            return None

        with open(self.file_path, 'r') as f:
            keystore_data = json.load(f)

        salt = bytes.fromhex(keystore_data['salt'])
        key = self._derive_key(passphrase, salt)

        try:
            return self._decrypt(keystore_data['encrypted_key'], key)
        except Exception:
            return None  # Wrong passphrase