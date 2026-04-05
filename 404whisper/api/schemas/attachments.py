"""
API Schemas - Attachments

Pydantic models for attachment-related API endpoints.
"""

from enum import Enum


class AttachmentStatus(str, Enum):
    """Attachment status values matching DATA_CONTRACT."""
    PENDING = "PENDING"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"
    FAILED = "FAILED"