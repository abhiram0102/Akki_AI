"""Test-session setup.

`backend.database` builds a SQLAlchemy engine at import time, so a missing
`DATABASE_URL` makes EVERY backend test error during collection — not fail, but
error before a single test body runs, with an opaque "Could not parse
SQLAlchemy URL" that gives no hint the environment is at fault. There was no
conftest, so a clean shell could not run the suite at all.

Setting a default here fixes that for good. It must happen at conftest import
time, before pytest imports any test module that pulls in `backend.database`.

The URL is never connected to. Tests that need real data mock their graph and
database access; this only has to be well-formed enough for the engine to be
constructed. A real `DATABASE_URL` already in the environment always wins, so
this changes nothing for anyone running against a live database.
"""
import os

# `setdefault`, not assignment: never override a real configured database.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://akki:changeme@localhost:5433/akki_ai_test",
)
