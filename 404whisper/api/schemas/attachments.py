"""
api/schemas/attachments.py — Pydantic models for attachment endpoints.

DATA_CONTRACT § Attachment — Enums, Response Schemas.

AttachmentStatus  → valid status lifecycle values.
AttachmentResponse → GET /api/attachments/{id} response shape.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel

# ── enum ───────────────────────────────────────────────────────────────────


class AttachmentStatus(str, Enum):
    """
    Lifecycle stages for an attachment upload or download.

    Upload path:  PENDING → UPLOADING → UPLOADED (or FAILED)
    Download path: UPLOADED → DOWNLOADING → DOWNLOADED (or FAILED)

    Note: encryption_key and hmac_key are NEVER included in API responses —
    they are stored as BLOBs in the DB and only used by the attachments layer.
    """

    PENDING     = "PENDING"      # row created, upload not yet started
    UPLOADING   = "UPLOADING"    # bytes being sent to the Session file server
    UPLOADED    = "UPLOADED"     # successfully stored on file server
    DOWNLOADING = "DOWNLOADING"  # bytes being fetched from file server
    DOWNLOADED  = "DOWNLOADED"   # decrypted and cached locally
    FAILED      = "FAILED"       # any terminal error in the lifecycle


# ── response schemas ───────────────────────────────────────────────────────


class AttachmentResponse(BaseModel):
    """
    Response shape for attachment metadata (NOT the file bytes themselves).

    File bytes are returned as a binary stream from GET /api/attachments/{id}.
    This object is embedded inside MessageResponse.attachment.

    Keys:
        id:            Primary key of the attachment row.
        fileName:      Original file name (e.g. "photo.jpg").
        fileSize:      Size in bytes.
        mimeType:      MIME type string (e.g. "image/jpeg").
        uploadUrl:     Session file server URL (set after a successful upload).
        status:        Current lifecycle stage.
        createdAt:     ISO-8601 timestamp.
    """

    id: int
    fileName: str
    fileSize: int
    mimeType: str
    uploadUrl: Optional[str] = None  # None until the upload completes
    status: str                      # AttachmentStatus value
    createdAt: str