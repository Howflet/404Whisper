"""
attachments/upload.py — Attachment validation, encryption, and local storage.

DATA_CONTRACT § Attachment — Size Limits (OQ-7 resolved: 10 MiB),
                              Status lifecycle (PENDING → UPLOADING → UPLOADED).

This module owns the full upload pipeline:
  1. Validate the file size (must be 1 byte – 10 MiB).
  2. Generate fresh per-file AES-256 + HMAC-SHA256 keys.
  3. Encrypt the raw bytes (via attachments/encrypt.py).
  4. Write the encrypted blob to the local attachment cache on disk.
  5. Create an attachment row in the DB with status=UPLOADED.
  6. Return a safe metadata dict (keys are NEVER included).

Layer note:
  In production (once Layer 3 — network — is available), step 4 would POST
  the encrypted bytes to the real Session file server and store the returned
  URL in `upload_url`.  For now, local disk storage is the source of truth
  and `upload_url` is left NULL.  Swapping this out only affects this file.

Public surface:
    MAX_ATTACHMENT_BYTES    → 10,485,760  (the hard upload limit)
    validate_file_size(n)   → True if 0 < n <= MAX_ATTACHMENT_BYTES
    upload_attachment(...)  → metadata dict safe for API responses
"""

from __future__ import annotations

import sqlite3
import uuid
from importlib import import_module
from pathlib import Path

from .encrypt import encrypt, generate_keys

_queries = import_module("404whisper.storage.queries")


# ── constants ──────────────────────────────────────────────────────────────

# Maximum allowed attachment size in bytes (OQ-7 resolved: 10 MiB).
# This constant is tested directly so any accidental change is caught.
# 10 MiB = 10 × 1024 × 1024 = 10,485,760 bytes.
MAX_ATTACHMENT_BYTES: int = 10 * 1024 * 1024   # 10_485_760

# Directory where encrypted blobs are written between upload and network delivery.
# Relative to the project root — matches the convention used by storage/db.py.
# Created automatically on first upload if it doesn't exist.
_CACHE_DIR: Path = Path("404whisper/data/attachments")


# ── validation ─────────────────────────────────────────────────────────────


def validate_file_size(size_bytes: int) -> bool:
    """
    Return True if size_bytes is within the allowed attachment size range.

    Rules (data contract § Attachment):
      - Must be positive (zero-byte files are rejected — DB CHECK enforces this too).
      - Must not exceed MAX_ATTACHMENT_BYTES (10 MiB).

    Args:
        size_bytes: File size in bytes as reported by the multipart upload.

    Returns:
        True  → size is valid; proceed with upload.
        False → size is out of range; route handler returns HTTP 400.

    Example:
        validate_file_size(1024)          → True   (1 KiB — fine)
        validate_file_size(10_485_760)    → True   (exactly 10 MiB — allowed)
        validate_file_size(10_485_761)    → False  (1 byte over the limit)
        validate_file_size(0)             → False  (empty file)
        validate_file_size(-1)            → False  (negative — invalid)
    """
    return 0 < size_bytes <= MAX_ATTACHMENT_BYTES


# ── internal helper ────────────────────────────────────────────────────────


def _attachment_to_api(row: dict) -> dict:
    """
    Convert a DB attachment row to the camelCase API response shape.

    Critically, encryption_key and hmac_key are NEVER included.
    They are stored as BLOBs and must remain server-side only.

    Args:
        row: Dict from queries.get_attachment() — column names in snake_case.

    Returns:
        Dict with camelCase keys safe to return as a JSON API response.
    """
    return {
        "id":        row["id"],
        "fileName":  row["file_name"],
        "fileSize":  row["file_size"],
        "mimeType":  row["mime_type"],
        "uploadUrl": row["upload_url"],  # NULL until Session file server is live
        "status":    row["status"],
        "createdAt": row["created_at"],
    }


# ── public function ────────────────────────────────────────────────────────


def upload_attachment(
    db: sqlite3.Connection,
    *,
    plaintext_bytes: bytes,
    file_name: str,
    mime_type: str,
) -> dict:
    """
    Encrypt and store a file attachment, then create its DB row.

    Full upload pipeline:
      1. Validate file size — raises ValueError if out of range.
      2. Generate a fresh AES-256 key + HMAC-SHA256 key pair.
      3. Encrypt the plaintext bytes into an IV+ciphertext+HMAC blob.
      4. Write the encrypted blob to disk (404whisper/data/attachments/<uuid>.enc).
      5. Insert an attachment row in the DB:
           status=UPLOADED, encryption_key=<bytes>, hmac_key=<bytes>,
           local_cache_path=<absolute path to the .enc file>.
      6. Fetch the full row so DB-generated fields (created_at) are included.
      7. Return a metadata dict with NO keys — safe for JSON serialisation.

    Args:
        db:              Open sqlite3 connection (from the FastAPI dependency).
        plaintext_bytes: Raw file bytes from the multipart upload.
        file_name:       Original filename (e.g. "photo.jpg").
        mime_type:       MIME type string (e.g. "image/jpeg").

    Note:
        conversation_id is validated by the route before calling this function.
        The messaging layer (Layer 4) will link attachments to messages directly
        via queries.update_attachment(db, attachment_id=..., message_id=...).

    Returns:
        Dict: id, fileName, fileSize, mimeType, uploadUrl, status, createdAt.
        Never contains encryptionKey or hmacKey.

    Raises:
        ValueError: if the file is empty or exceeds MAX_ATTACHMENT_BYTES.

    Example:
        metadata = upload_attachment(
            db,
            plaintext_bytes=file_bytes,
            file_name="invoice.pdf",
            mime_type="application/pdf",
            conversation_id=42,
        )
        # → {"id": 1, "fileName": "invoice.pdf", "fileSize": 2048,
        #    "mimeType": "application/pdf", "uploadUrl": null,
        #    "status": "UPLOADED", "createdAt": "2026-04-05T..."}
    """
    file_size = len(plaintext_bytes)

    # Guard: validate size before doing any work.
    if not validate_file_size(file_size):
        raise ValueError(
            f"File size {file_size} bytes is out of the allowed range "
            f"(1 byte – {MAX_ATTACHMENT_BYTES} bytes)."
        )

    # Step 2: fresh random keys — one pair per file, never reused.
    aes_key, hmac_key = generate_keys()

    # Step 3: encrypt the raw bytes into the wire-format blob.
    encrypted_blob = encrypt(plaintext_bytes, aes_key, hmac_key)

    # Step 4: persist the encrypted blob to the local attachment cache.
    # The directory is created lazily on the very first upload.
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _CACHE_DIR / f"{uuid.uuid4()}.enc"
    cache_path.write_bytes(encrypted_blob)

    # Step 5: insert the DB row.
    # sqlite3 stores Python bytes as a BLOB column automatically.
    att_id = _queries.create_attachment(
        db,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type,
        status="UPLOADED",
        encryption_key=aes_key,
        hmac_key=hmac_key,
        local_cache_path=str(cache_path),
    )

    # Steps 6–7: fetch the row (gets created_at from DB) and convert to API shape.
    row = _queries.get_attachment(db, attachment_id=att_id)
    return _attachment_to_api(row)
