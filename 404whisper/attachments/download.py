"""
attachments/download.py — Attachment retrieval and decryption.

DATA_CONTRACT § Attachment — Download flow (UPLOADED → DOWNLOADING → DOWNLOADED).

Retrieves a locally cached encrypted blob, verifies its integrity via
HMAC-SHA256, and decrypts it back to the original plaintext bytes.

Layer note:
  In production (once Layer 3 — network — is available), the download flow
  would fetch the encrypted bytes from the Session file server URL stored in
  `upload_url`, then cache the result locally.  For now, `local_cache_path`
  is the only source — Layer 6 uses it as the canonical store.
  Upgrading to the real network only requires changing this file.

Public surface:
    download_attachment(db, attachment_id) → (plaintext_bytes, mime_type, file_name)
"""

from __future__ import annotations

import sqlite3
from importlib import import_module
from pathlib import Path

from .encrypt import decrypt

_queries = import_module("404whisper.storage.queries")


def download_attachment(
    db: sqlite3.Connection,
    *,
    attachment_id: int,
) -> tuple[bytes, str, str]:
    """
    Retrieve, verify, and decrypt an attachment from the local cache.

    Full download pipeline:
      1. Fetch the attachment row from the DB (keys + cache path).
      2. Read the encrypted blob from the local cache file.
      3. Verify HMAC-SHA256 to detect any tampering.
      4. Decrypt using the stored AES-256 key.
      5. Return the original plaintext bytes together with MIME type and filename.

    Args:
        db:            Open sqlite3 connection (from the FastAPI dependency).
        attachment_id: Primary key of the attachment row to retrieve.

    Returns:
        A 3-tuple: (plaintext_bytes, mime_type, file_name).
          - plaintext_bytes: The original file bytes before encryption.
          - mime_type:       The MIME type stored at upload time (e.g. "image/jpeg").
          - file_name:       The original filename (e.g. "photo.jpg").

    Raises:
        KeyError:         if no attachment row exists for attachment_id.
        FileNotFoundError: if the encrypted cache file is missing on disk
                           (not yet uploaded, or cache was manually cleared).
        ValueError:       if the HMAC does not match (data was tampered with
                          or the wrong keys were supplied — see encrypt.py).

    Example:
        plaintext, mime, name = download_attachment(db, attachment_id=7)
        return StreamingResponse(iter([plaintext]), media_type=mime,
                                 headers={"Content-Disposition": f'attachment; filename="{name}"'})
    """
    # Step 1: fetch the full attachment row (includes keys and cache path).
    row = _queries.get_attachment(db, attachment_id=attachment_id)
    if row is None:
        raise KeyError(f"No attachment found with id={attachment_id}.")

    # Step 2: locate and read the encrypted blob from disk.
    cache_path = row.get("local_cache_path")
    if not cache_path or not Path(cache_path).exists():
        raise FileNotFoundError(
            f"Encrypted cache file not found for attachment {attachment_id}. "
            "The file may not have been uploaded yet, or the cache was cleared."
        )
    encrypted_blob = Path(cache_path).read_bytes()

    # Step 3+4: verify HMAC then decrypt.
    # sqlite3 returns BLOB columns as bytes — convert memoryview defensively.
    aes_key  = bytes(row["encryption_key"])
    hmac_key = bytes(row["hmac_key"])
    plaintext = decrypt(encrypted_blob, aes_key, hmac_key)

    # Step 5: return the plaintext along with the metadata the route needs
    # to set Content-Type and Content-Disposition headers.
    return plaintext, row["mime_type"], row["file_name"]
