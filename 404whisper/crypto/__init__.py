"""
Layer 2 — Crypto: public API surface.

What this package does (plain English):
    This is the single entry point for all cryptographic operations in
    404Whisper.  Higher layers (messaging, groups, attachments) should
    import ONLY from this package, never directly from the sub-modules.

    The four primitives exposed here map directly to the four things the
    Session protocol needs to do with cryptography:

        1. encrypt_message()  — Encrypt a message from Alice to Bob.
                                  Uses X25519 DH + XSalsa20-Poly1305.
        2. decrypt_message()  — Decrypt a message received from Alice.
        3. sign()             — Sign bytes with an Ed25519 private key.
        4. verify()           — Check an Ed25519 signature.

    For onion routing, use ``build_onion_packet()`` and ``peel_onion_layer()``
    which are also re-exported here for convenience.

Sub-module breakdown:
    crypto/x25519.py    — X25519 Diffie-Hellman key exchange.
    crypto/ed25519.py   — Ed25519 sign + verify.
    crypto/symmetric.py — XSalsa20-Poly1305 symmetric encryption.
    crypto/onion.py     — 3-layer onion packet construction and peeling.

Usage example (Layer 4 — messaging)::

    # import via importlib: pkg("crypto") then call encrypt_message, decrypt_message, sign, verify

    # Alice encrypts and signs a message for Bob:
    ciphertext = encrypt_message(b"Hello Bob!", alice_priv, bob_pub)
    signature  = sign(ciphertext, alice_ed25519_priv)

    # Bob verifies the signature and decrypts:
    if verify(ciphertext, signature, alice_ed25519_pub):
        plaintext = decrypt_message(ciphertext, bob_priv, alice_pub)
        assert plaintext == b"Hello Bob!"
"""
from __future__ import annotations

# ── Re-exports from x25519 ────────────────────────────────────────────────────
from .x25519 import (
    generate_ephemeral_keypair,
    compute_shared_secret,
    public_key_from_private,
)

# ── Re-exports from ed25519 ───────────────────────────────────────────────────
from .ed25519 import (
    sign,
    verify,
    sign_and_prepend,
    verify_and_strip,
)

# ── Re-exports from symmetric ────────────────────────────────────────────────
from .symmetric import (
    derive_key,
    encrypt,
    decrypt,
    encrypt_to_recipient,
    decrypt_from_sender,
)

# ── Re-exports from onion ────────────────────────────────────────────────────
from .onion import (
    OnionHop,
    PeeledLayer,
    build_onion_packet,
    peel_onion_layer,
)

# ---------------------------------------------------------------------------
# Convenience aliases  — the names the messaging layer will call most often
# ---------------------------------------------------------------------------

# ``encrypt_message`` and ``decrypt_message`` are the main high-level calls.
# They wrap the full DH + symmetric flow via NaCl Box.
encrypt_message = encrypt_to_recipient
decrypt_message = decrypt_from_sender


__all__ = [
    # X25519 key exchange
    "generate_ephemeral_keypair",
    "compute_shared_secret",
    "public_key_from_private",
    # Key derivation
    "derive_key",
    # Ed25519 signatures
    "sign",
    "verify",
    "sign_and_prepend",
    "verify_and_strip",
    # Symmetric encryption
    "encrypt",
    "decrypt",
    # High-level message encryption
    "encrypt_message",
    "decrypt_message",
    # Onion routing
    "OnionHop",
    "PeeledLayer",
    "build_onion_packet",
    "peel_onion_layer",
]
