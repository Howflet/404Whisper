"""
Contract-test fixtures — provides an httpx AsyncClient wired to the FastAPI
app, with a fresh in-memory database for every test function.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.conftest import pkg


@pytest_asyncio.fixture()
async def client() -> AsyncClient:
    """
    An httpx AsyncClient pointed at the FastAPI app.

    The app is started with a fresh in-memory DB (injected via the app's
    dependency-override mechanism) so no test state leaks.
    """
    app_module = pkg("api.app")
    app = app_module.app

    # Override the DB dependency with an in-memory connection for isolation.
    db_module = pkg("storage.db")
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    db_module.init_schema(conn)

    async def _override_db():
        yield conn

    app.dependency_overrides[db_module.get_db] = _override_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
    conn.close()
