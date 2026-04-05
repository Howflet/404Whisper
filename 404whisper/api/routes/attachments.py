"""
api/routes/attachments.py — Attachment endpoints.

  POST /api/attachments/upload   — encrypt & store a file; return 201 metadata
  GET  /api/attachments/{id}     — decrypt & stream the original file bytes

DATA_CONTRACT § Attachment — API Endpoints, Request/Response Schemas,
                              Error Contract.

Security notes:
  - encryption_key and hmac_key NEVER appear in any response.
  - File bytes are returned as a binary stream, not base64 JSON.
  - The route validates the conversation exists before touching the filesystem.
"""

from __future__ import annotations

import sqlite3
from importlib import import_module
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

_db_module    = import_module("404whisper.storage.db")
_queries      = import_module("404whisper.storage.queries")
_upload_mod   = import_module("404whisper.attachments.upload")
_download_mod = import_module("404whisper.attachments.download")
_ws           = import_module("404whisper.api.ws")  # WebSocket broadcast manager

get_db = _db_module.get_db
DbConn = Annotated[sqlite3.Connection, Depends(get_db)]

router = APIRouter()


# ── error helpers ──────────────────────────────────────────────────────────


def _bad_request(code: str, message: str) -> JSONResponse:
    """Return a 400 response in the standard error envelope."""
    return JSONResponse(
        status_code=400,
        content={"error": {"code": code, "message": message}},
    )


def _not_found(message: str = "Attachment not found.") -> JSONResponse:
    """Return a 404 response in the standard error envelope."""
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "NOT_FOUND", "message": message}},
    )


# ── endpoints ──────────────────────────────────────────────────────────────


@router.post("/attachments/upload", status_code=201)
async def upload_attachment(
    db: DbConn,
    file: Optional[UploadFile] = File(None),
    conversationId: Optional[str] = Form(None),
):
    """
    Upload and encrypt a file attachment.

    Multipart form fields:
        file           — The file to upload (required, ≤ 10 MiB).
        conversationId — Integer ID of the conversation (required).

    Returns 201 with attachment metadata on success.
    Metadata keys: id, fileName, fileSize, mimeType, uploadUrl, status, createdAt.
    encryptionKey and hmacKey are NEVER returned.

    Error codes:
        MISSING_FILE            → 400 if no file field is present.
        MISSING_CONVERSATION_ID → 400 if conversationId is absent.
        INVALID_CONVERSATION_ID → 400 if conversationId is not an integer.
        FILE_TOO_LARGE          → 400 if the file exceeds 10 MiB or is empty.
        NOT_FOUND               → 404 if the conversation does not exist.
    """
    # Validate required multipart fields.
    if file is None:
        return _bad_request("MISSING_FILE", "A file is required.")

    if conversationId is None:
        return _bad_request(
            "MISSING_CONVERSATION_ID",
            "conversationId form field is required.",
        )

    # Parse conversationId as an integer.
    try:
        conv_id = int(conversationId)
    except (ValueError, TypeError):
        return _bad_request(
            "INVALID_CONVERSATION_ID",
            "conversationId must be an integer.",
        )

    # Verify the conversation exists before reading file bytes.
    if _queries.get_conversation(db, conversation_id=conv_id) is None:
        return _not_found("Conversation not found.")

    # Read the entire file into memory (size is validated below).
    plaintext_bytes = await file.read()

    # Reject files that are empty or exceed the 10 MiB cap.
    if not _upload_mod.validate_file_size(len(plaintext_bytes)):
        return _bad_request(
            "FILE_TOO_LARGE",
            f"File must be between 1 byte and {_upload_mod.MAX_ATTACHMENT_BYTES} bytes.",
        )

    # Encrypt, cache to disk, and insert the DB row.
    metadata = _upload_mod.upload_attachment(
        db,
        plaintext_bytes=plaintext_bytes,
        file_name=file.filename or "attachment",
        mime_type=file.content_type or "application/octet-stream",
    )

    # Notify connected WebSocket clients that the upload completed.
    # Layer 6 (attachments) will emit intermediate progress events too;
    # for now we emit a single 100% event when the upload finishes.
    await _ws.manager.broadcast({
        "event": "attachment_progress",
        "payload": {
            "attachmentId":    metadata["id"],
            "status":          metadata["status"],   # "UPLOADED"
            "progressPercent": 100,                  # full progress once stored
        },
    })

    return metadata


@router.get("/attachments/{attachment_id}")
async def get_attachment(attachment_id: int, db: DbConn):
    """
    Download and decrypt an attachment, returning the original file bytes.

    Response headers set automatically:
        Content-Type:        Original MIME type of the file.
        Content-Disposition: attachment; filename="<original filename>"

    Returns 200 with binary content on success.

    Error codes:
        NOT_FOUND → 404 if no attachment with this ID exists, or if the
                    local cache file is missing (upload may not have completed).
    """
    try:
        plaintext, mime_type, file_name = _download_mod.download_attachment(
            db, attachment_id=attachment_id
        )
    except KeyError:
        return _not_found()
    except FileNotFoundError:
        return _not_found("Attachment file not found in local cache.")

    # Stream the decrypted bytes back to the client with appropriate headers.
    return StreamingResponse(
        iter([plaintext]),
        media_type=mime_type,
        headers={
            # RFC 5987 / RFC 6266: Content-Disposition tells the browser to
            # save the file rather than display it inline.
            "Content-Disposition": f'attachment; filename="{file_name}"',
        },
    )
