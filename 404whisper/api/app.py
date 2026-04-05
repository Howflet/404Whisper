"""
api/app.py — FastAPI application factory.

This module owns the single `app` instance that:
  - The contract-test fixture imports via pkg("api.app").app
  - main.py runs via uvicorn

All route groups are registered here. Each route file uses Depends(get_db)
for database access, which lets tests swap in an in-memory connection via
app.dependency_overrides without touching production code.
"""

from __future__ import annotations

from importlib import import_module

from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Connection manager lives in its own module so routes can import it too
# without creating a circular dependency on app.py.
_ws_module = import_module("404whisper.api.ws")
ws_manager = _ws_module.manager  # re-exported for convenience

# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="404Whisper API",
    description="Session-based end-to-end encrypted messaging",
    version="0.1.0",
)

# Allow the Vite dev server (port 5173) to call this API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Validation error handler
# FastAPI's default is 422 Unprocessable Entity for request body errors.
# The data contract requires 400 with our standard error envelope instead.
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    message = first.get("msg", "Invalid request.")
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "VALIDATION_ERROR", "message": message}},
    )


# ---------------------------------------------------------------------------
# Route registration
# Use importlib so the numeric package name "404whisper" is handled correctly.
# ---------------------------------------------------------------------------

_identity      = import_module("404whisper.api.routes.identity")
_groups        = import_module("404whisper.api.routes.groups")
_conversations = import_module("404whisper.api.routes.conversations")
_contacts      = import_module("404whisper.api.routes.contacts")
_messages      = import_module("404whisper.api.routes.messages")
_attachments   = import_module("404whisper.api.routes.attachments")

app.include_router(_identity.router,      prefix="/api", tags=["identity"])
app.include_router(_groups.router,        prefix="/api", tags=["groups"])
app.include_router(_conversations.router, prefix="/api", tags=["conversations"])
app.include_router(_contacts.router,      prefix="/api", tags=["contacts"])
app.include_router(_messages.router,      prefix="/api", tags=["messages"])
app.include_router(_attachments.router,   prefix="/api", tags=["attachments"])

# ---------------------------------------------------------------------------
# WebSocket endpoint
#
# Clients connect here to receive real-time push events from the server:
#   message_received   — a new message arrived (Layer 4)
#   vibe_changed       — a group or conversation vibe was updated
#   attachment_progress — upload/download progress (Layer 6)
#   identity_locked    — idle timeout expired (Layer 8)
#
# The ConnectionManager (api/ws.py) tracks all open connections.
# Routes call ``ws_manager.broadcast(event)`` to push to every client.
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Register the client, listen for pings, broadcast server events.

    Client → server: any text is echoed back (heartbeat / dev tool).
    Server → client: JSON events via ws_manager.broadcast().
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; echo anything the client sends.
            data = await websocket.receive_text()
            await websocket.send_text(f"echo: {data}")
    except Exception:
        # Raised when the client disconnects or the connection drops.
        pass
    finally:
        ws_manager.disconnect(websocket)
