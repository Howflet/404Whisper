#!/usr/bin/env python3
"""
404Whisper — backend entry point.

HOW TO RUN (from the project root):
    python -m 404whisper.main

Or with live-reload:
    uvicorn 404whisper.main:app --reload --port 8001

Once running:
    http://127.0.0.1:8001/docs   ← Swagger UI
    http://127.0.0.1:8001/redoc  ← ReDoc
"""
from __future__ import annotations

import uvicorn

# The app is defined in api/app.py so the contract-test fixture can import it
# independently without pulling in uvicorn.
from importlib import import_module

_api = import_module("404whisper.api.app")
app  = _api.app

if __name__ == "__main__":
    uvicorn.run(
        "404whisper.main:app",
        host="127.0.0.1",
        port=8001,
        reload=True,
        log_level="info",
    )
