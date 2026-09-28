"""SQLite connections with foreign-key enforcement and versioned initialization."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import aiosqlite

from codex_account_manager.core.paths import paths
from codex_account_manager.storage.migrations import migrate


async def initialize_database() -> int:
    """Ensure the database exists and is migrated to the latest schema."""
    return await migrate()


@asynccontextmanager
async def connect() -> AsyncIterator[aiosqlite.Connection]:
    """Open a connection with sane pragmas applied."""
    async with aiosqlite.connect(paths.db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.execute("PRAGMA busy_timeout=5000;")
        yield db
