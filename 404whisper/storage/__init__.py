"""
404whisper.storage — Layer 7: Data Storage & Management
========================================================

What lives here
---------------
This package is the *only* place in the app that talks to the database.
Everything above it (API routes, messaging, groups, attachments) asks this
package for data — they never write raw SQL themselves.

Three modules, one job each:

  db.py        The schema: defines all 7 tables with CREATE TABLE statements.
               Also provides ``get_db()`` (the FastAPI dependency that hands
               each HTTP request its own open DB connection) and
               ``init_schema()`` (called on startup and in tests).

  database.py  The ``Database`` class: opens the on-disk SQLite file, runs
               the schema on first use.  Supports the encrypted sqlcipher3
               backend in production and plain sqlite3 in development / CI.

  queries.py   Every CRUD function the app uses: insert contacts, list
               messages, purge expired 404-vibe messages, etc.  Each function
               takes an open connection as its first argument so the callers
               decide which database they're talking to (real file or
               in-memory test DB).

Quick-start for other layers
----------------------------
::

    from importlib import import_module
    _q  = import_module("404whisper.storage.queries")
    _db = import_module("404whisper.storage.db")

    # In a FastAPI route:
    @router.get("/contacts")
    async def get_contacts(db = Depends(_db.get_db)):
        return _q.list_contacts(db)

    # In tests (in-memory DB):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    _db.init_schema(conn)
    contacts = _q.list_contacts(conn)

Public exports
--------------
  Database      Connection-managing class (used by main.py and get_db).
  init_schema   Run all CREATE TABLE statements on any open connection.
  SCHEMA_SQL    The raw SQL string (useful for introspection / migration tools).
  queries       Module of all CRUD functions — import and call directly.
"""

from .db import init_schema, SCHEMA_SQL
from . import queries
from .database import Database

__all__ = ["Database", "init_schema", "SCHEMA_SQL", "queries"]
