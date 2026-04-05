"""
attachments/ — File attachment layer (Layer 6).

Handles encrypting, uploading, downloading, and decrypting file attachments.
Files are encrypted with AES-256-CBC + HMAC-SHA256 before being stored.
In production, encrypted blobs are posted to the Session file server; for
now they are cached locally under 404whisper/data/attachments/.

Sub-modules:
  encrypt.py   → generate_keys(), encrypt(), decrypt()
  upload.py    → validate_file_size(), upload_attachment()
  download.py  → download_attachment()

Public surface (re-exported here for convenience):
  upload_attachment(db, *, plaintext_bytes, file_name, mime_type)
      → metadata dict safe for API responses (no keys).

  download_attachment(db, *, attachment_id)
      → (plaintext_bytes, mime_type, file_name)
"""

from .download import download_attachment
from .upload import upload_attachment

__all__ = ["upload_attachment", "download_attachment"]
