"""
Storage Layer

Public surface for the storage package.

  db       → schema definition + init_schema() (used by tests and Database)
  queries  → all CRUD functions (used by API routes and higher layers)
  Database → connection-managing class (used by main.py / API startup)
"""

from .db import init_schema, SCHEMA_SQL
from . import queries
from .database import Database

__all__ = ["Database", "init_schema", "SCHEMA_SQL", "queries"]
