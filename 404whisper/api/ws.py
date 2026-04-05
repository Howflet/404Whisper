"""
api/ws.py — WebSocket connection manager and event broadcaster.

What this does
--------------
Keeps track of every client that is currently connected via WebSocket, and
provides a single ``broadcast()`` call that routes can use to push real-time
events to all of them.

How it works (plain-English):
  - When a client connects to ``/ws``, the WebSocket endpoint calls
    ``manager.connect(ws)`` to register it.
  - When the client disconnects, ``manager.disconnect(ws)`` removes it.
  - Any route that needs to push an event (e.g. a new message arrived)
    calls ``await manager.broadcast({"event": "...", "payload": {...}})``.
    Every connected client receives the event as a JSON string.

Why a module-level singleton?
  Routes are loaded via ``importlib.import_module``.  Because Python caches
  modules, every import of ``404whisper.api.ws`` returns the SAME object.
  That means ``manager`` is always the same instance regardless of which
  file imports it — exactly what we need for a shared broadcast registry.

Usage example (inside an async route):
    _ws = import_module("404whisper.api.ws")

    # After saving a message:
    await _ws.manager.broadcast({
        "event": "message_received",
        "payload": message_response,
    })

Layer notes:
  - Layer 4 (messaging/poll.py) will call broadcast() for incoming network messages.
  - Layer 6 (attachments) will call broadcast() for upload/download progress.
  - Layer 8 (API wiring) will wire remaining events (e.g. identity_locked).
"""
from __future__ import annotations

import json

from fastapi import WebSocket


class ConnectionManager:
    """
    Registry of active WebSocket clients.

    Thread/concurrency note:
      FastAPI runs all WebSocket handlers in a single async event loop, so
      we do NOT need a lock around ``_active``.  The list is only ever
      modified from coroutines scheduled on that loop.
    """

    def __init__(self) -> None:
        # Every WebSocket that is currently open and listening.
        self._active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        """
        Accept the WebSocket handshake and register the client.

        Called by the ``/ws`` endpoint handler as soon as a client connects.
        """
        await ws.accept()
        self._active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        """
        Remove a client from the registry.

        Safe to call even if the client was never registered (no-op).
        Called in the ``finally`` block of the ``/ws`` endpoint handler.
        """
        try:
            self._active.remove(ws)
        except ValueError:
            pass  # Already gone — harmless

    async def broadcast(self, event: dict) -> None:
        """
        Send a JSON event to every connected client.

        If a client has already disconnected (race condition), the send will
        raise — we catch it, silently remove the stale entry, and continue.

        Args:
            event: A dict with at minimum ``{"event": str, "payload": dict}``.
                   Serialised to JSON before sending.

        Example event shapes:
            {"event": "message_received",   "payload": {...}}
            {"event": "vibe_changed",        "payload": {...}}
            {"event": "attachment_progress", "payload": {...}}
            {"event": "identity_locked",     "payload": {}}
        """
        text = json.dumps(event)
        # Iterate over a snapshot so we can safely mutate _active inside the loop.
        for ws in list(self._active):
            try:
                await ws.send_text(text)
            except Exception:
                # Client disconnected mid-broadcast — clean up.
                self.disconnect(ws)


# ---------------------------------------------------------------------------
# Module-level singleton — imported by app.py and any route that needs to
# broadcast.  Because Python caches modules, this is the SAME object
# everywhere.
# ---------------------------------------------------------------------------
manager = ConnectionManager()
