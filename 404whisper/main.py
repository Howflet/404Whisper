#!/usr/bin/env python3
"""
404Whisper — backend entry point.

HOW TO RUN (from the project root — /404Whisper/):
    python -m 404whisper.main

Or with live-reload (auto-restarts when you save a file):
    uvicorn 404whisper.main:app --reload --port 8001

Once running, open your browser to:
    http://127.0.0.1:8001/docs   ← interactive API explorer (Swagger UI)
    http://127.0.0.1:8001/redoc  ← alternative docs view

The frontend (Vite dev server on port 5173) connects to this server.
Nothing about the URLs or port changes — only the import paths were fixed
so the server starts correctly from the project root.
"""
from __future__ import annotations

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

# Absolute package imports — work from any working directory.
# Previously these were relative ("from api.routes…") which only worked
# when launched from inside the 404whisper/ subdirectory.
from importlib import import_module

_identity_routes      = import_module("404whisper.api.routes.identity")
_groups_routes        = import_module("404whisper.api.routes.groups")
_conversations_routes = import_module("404whisper.api.routes.conversations")

app = FastAPI(
    title="404Whisper API",
    description="Session-based end-to-end encrypted messaging",
    version="0.1.0",
    # /docs  → Swagger UI (try endpoints interactively in the browser)
    # /redoc → ReDoc (clean read-only docs)
)

# ── CORS: let the Vite dev server (port 5173) call this API ──────────────────
# This is unchanged — the frontend still connects to http://localhost:8001.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],   # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register route groups ────────────────────────────────────────────────────
# All endpoints are prefixed with /api, so URLs stay identical to before.
app.include_router(_identity_routes.router,      prefix="/api", tags=["identity"])
app.include_router(_groups_routes.router,        prefix="/api", tags=["groups"])
app.include_router(_conversations_routes.router, prefix="/api", tags=["conversations"])

# Mount static files for production (uncomment when frontend is built):
# app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")


# ── WebSocket placeholder ────────────────────────────────────────────────────
# Layer 4 (messaging / polling loop) will replace this with real events.
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Placeholder — echoes messages back until Layer 4 is implemented."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"echo: {data}")
    except Exception:
        pass


if __name__ == "__main__":
    # Entrypoint for: python -m 404whisper.main
    uvicorn.run(
        "404whisper.main:app",
        host="127.0.0.1",
        port=8001,
        reload=True,        # auto-restart on file save — great for development
        log_level="info",
    )
