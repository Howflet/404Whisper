#!/usr/bin/env python3
"""
404Whisper Backend - FastAPI Application

This is the main entry point for the 404Whisper backend server.
"""

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Import API routes (when implemented)
from api.routes.identity import router as identity_router
from api.routes.groups import router as groups_router
from api.routes.conversations import router as conversations_router

app = FastAPI(
    title="404Whisper API",
    description="Session-based messaging application API",
    version="0.1.0"
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for production (when frontend is built)
# app.mount("/", StaticFiles(directory="../frontend/dist", html=True), name="static")

# Include API routers (when implemented)
app.include_router(identity_router, prefix="/api", tags=["identity"])
app.include_router(groups_router, prefix="/api", tags=["groups"])
app.include_router(conversations_router, prefix="/api", tags=["conversations"])

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Mock WebSocket - just keep connection alive
    try:
        while True:
            data = await websocket.receive_text()
            # Echo back for now
            await websocket.send_text(f"Echo: {data}")
    except Exception:
        pass

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8001,
        reload=False,
        log_level="info"
    )