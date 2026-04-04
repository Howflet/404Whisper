"""
Contract tests — Attachment endpoints.

DATA_CONTRACT § Attachment — API Endpoints, Request/Response Schemas,
Error Contract.
"""
from __future__ import annotations

import io

import pytest
from httpx import AsyncClient

from tests.conftest import VALID_SESSION_ID_2, VALID_PASSPHRASE


async def _bootstrap(client) -> int:
    await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
    await client.post("/api/contacts", json={"sessionId": VALID_SESSION_ID_2})
    convs = (await client.get("/api/conversations")).json()
    return convs["conversations"][0]["id"]


def _make_file(size_bytes: int = 1024, filename: str = "test.txt") -> tuple:
    content = b"A" * size_bytes
    return ("file", (filename, io.BytesIO(content), "text/plain"))


@pytest.mark.contract
class TestPostAttachmentsUpload:
    """POST /api/attachments/upload"""

    async def test_happy_path_returns_201(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        resp = await client.post(
            "/api/attachments/upload",
            files=[_make_file()],
            data={"conversationId": str(conv_id)},
        )
        assert resp.status_code == 201

    async def test_response_shape(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        data = (await client.post(
            "/api/attachments/upload",
            files=[_make_file(filename="photo.jpg")],
            data={"conversationId": str(conv_id)},
        )).json()
        for key in ("id", "fileName", "fileSize", "mimeType", "status", "createdAt"):
            assert key in data, f"Expected key '{key}' in attachment upload response"

    async def test_status_is_uploaded_on_success(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        data = (await client.post(
            "/api/attachments/upload",
            files=[_make_file()],
            data={"conversationId": str(conv_id)},
        )).json()
        assert data["status"] == "UPLOADED"

    async def test_encryption_key_not_in_response(self, client: AsyncClient):
        """Encryption key must never leave the backend."""
        conv_id = await _bootstrap(client)
        data = (await client.post(
            "/api/attachments/upload",
            files=[_make_file()],
            data={"conversationId": str(conv_id)},
        )).json()
        assert "encryptionKey" not in data
        assert "encryption_key" not in data
        assert "hmacKey" not in data

    async def test_missing_file_returns_400(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        resp = await client.post(
            "/api/attachments/upload",
            data={"conversationId": str(conv_id)},
        )
        assert resp.status_code == 400

    async def test_missing_conversation_id_returns_400(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        resp = await client.post(
            "/api/attachments/upload",
            files=[_make_file()],
        )
        assert resp.status_code == 400

    async def test_unknown_conversation_id_returns_404(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        resp = await client.post(
            "/api/attachments/upload",
            files=[_make_file()],
            data={"conversationId": "9999"},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.contract
class TestGetAttachment:
    """GET /api/attachments/{id}"""

    async def test_download_returns_binary_content(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        upload = (await client.post(
            "/api/attachments/upload",
            files=[_make_file(size_bytes=512, filename="hello.txt")],
            data={"conversationId": str(conv_id)},
        )).json()
        att_id = upload["id"]
        resp = await client.get(f"/api/attachments/{att_id}")
        assert resp.status_code == 200
        assert len(resp.content) == 512

    async def test_download_sets_correct_content_type(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        upload = (await client.post(
            "/api/attachments/upload",
            files=[("file", ("doc.txt", io.BytesIO(b"hello"), "text/plain"))],
            data={"conversationId": str(conv_id)},
        )).json()
        resp = await client.get(f"/api/attachments/{upload['id']}")
        assert "text/plain" in resp.headers.get("content-type", "")

    async def test_download_sets_content_disposition(self, client: AsyncClient):
        conv_id = await _bootstrap(client)
        upload = (await client.post(
            "/api/attachments/upload",
            files=[_make_file(filename="report.txt")],
            data={"conversationId": str(conv_id)},
        )).json()
        resp = await client.get(f"/api/attachments/{upload['id']}")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "report.txt" in resp.headers.get("content-disposition", "")

    async def test_nonexistent_attachment_returns_404(self, client: AsyncClient):
        await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
        resp = await client.get("/api/attachments/9999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"
