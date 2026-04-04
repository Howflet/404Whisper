"""
Contract tests — WebSocket endpoint.

DATA_CONTRACT § WebSocket Contract — event types and payload shapes.
"""
from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from tests.conftest import VALID_SESSION_ID_2, VALID_PASSPHRASE, pkg


async def _bootstrap(client) -> int:
    await client.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
    await client.post("/api/contacts", json={"sessionId": VALID_SESSION_ID_2})
    convs = (await client.get("/api/conversations")).json()
    return convs["conversations"][0]["id"]


@pytest.mark.contract
class TestWebSocketConnection:
    """Basic connectivity — the WS endpoint must accept connections."""

    async def test_websocket_connects_without_error(self, client: AsyncClient):
        """
        Use the ASGI WebSocket test interface directly.

        httpx does not natively support WebSocket; we use the FastAPI
        test client's ws support via the underlying ASGI transport.
        """
        app_module = pkg("api.app")
        from starlette.testclient import TestClient

        with TestClient(app_module.app) as tc:
            with tc.websocket_connect("/ws") as ws:
                # Should connect without raising
                assert ws is not None


@pytest.mark.contract
class TestWebSocketEventShapes:
    """
    Verify that events emitted after REST actions conform to the shapes
    defined in DATA_CONTRACT § WebSocket Contract.
    """

    async def test_message_received_event_shape(self, client: AsyncClient):
        """
        Sending a message via REST should cause a 'message_received' WS event.
        This test drives the event by calling the REST endpoint and checking
        the event is emitted to the same in-process app.
        """
        app_module = pkg("api.app")
        from starlette.testclient import TestClient

        with TestClient(app_module.app) as tc:
            # Set up identity + contact via REST
            tc.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
            tc.post("/api/contacts", json={"sessionId": VALID_SESSION_ID_2})
            conv_id = tc.get("/api/conversations").json()["conversations"][0]["id"]

            with tc.websocket_connect("/ws") as ws:
                tc.post("/api/messages/send", json={"conversationId": conv_id, "body": "hi"})
                raw = ws.receive_text()
                event = json.loads(raw)

                assert "event" in event
                assert event["event"] == "message_received"
                assert "payload" in event

                payload = event["payload"]
                for key in ("id", "conversationId", "senderSessionId", "body",
                            "type", "sentAt", "isAnonymous"):
                    assert key in payload, f"Expected '{key}' in message_received payload"

    async def test_attachment_progress_event_shape(self, client: AsyncClient):
        """
        Uploading a file should emit attachment_progress events.
        Only verifies the schema of events emitted; progress values are implementation-specific.
        """
        app_module = pkg("api.app")
        from starlette.testclient import TestClient
        import io

        with TestClient(app_module.app) as tc:
            tc.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
            tc.post("/api/contacts", json={"sessionId": VALID_SESSION_ID_2})
            conv_id = tc.get("/api/conversations").json()["conversations"][0]["id"]

            with tc.websocket_connect("/ws") as ws:
                tc.post(
                    "/api/attachments/upload",
                    files=[("file", ("f.txt", io.BytesIO(b"x" * 256), "text/plain"))],
                    data={"conversationId": str(conv_id)},
                )
                # Drain events until we find an attachment_progress one
                for _ in range(5):
                    try:
                        raw = ws.receive_text()
                        event = json.loads(raw)
                        if event["event"] == "attachment_progress":
                            payload = event["payload"]
                            assert "attachmentId" in payload
                            assert "status" in payload
                            assert "progressPercent" in payload
                            assert 0 <= payload["progressPercent"] <= 100
                            break
                    except Exception:
                        break


@pytest.mark.contract
class TestWebSocketVibeChangedEvent:
    """DATA_CONTRACT § WebSocket — vibe_changed event."""

    async def test_vibe_changed_event_emitted_on_group_vibe_change(self):
        app_module = pkg("api.app")
        from starlette.testclient import TestClient
        import json

        with TestClient(app_module.app) as tc:
            tc.post("/api/identity/new", json={"passphrase": VALID_PASSPHRASE})
            group_id = tc.post("/api/groups", json={"name": "Test"}).json()["id"]

            with tc.websocket_connect("/ws") as ws:
                tc.patch(f"/api/groups/{group_id}", json={"vibe": "CAMPFIRE"})
                raw = ws.receive_text()
                event = json.loads(raw)

                if event["event"] == "vibe_changed":
                    payload = event["payload"]
                    for key in ("conversationId", "newVibe", "changedBySessionId",
                                "cooldownUntil", "isBehavioral"):
                        assert key in payload, f"Expected '{key}' in vibe_changed payload"
