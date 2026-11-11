"""Async SQLAlchemy engine and session factory (real impl).

Uses SQLAlchemy 2.0 async with asyncio.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from typing import AsyncGenerator

from ..config import settings

logger = logging.getLogger("db.session")


def _to_async_url(url: str) -> str:
    """Map a plain DB URL to its async driver (create_async_engine needs one).

    Users/Supabase paste sync-style URLs (``sqlite:///`` / ``postgresql://``); the
    async engine needs the aiosqlite/asyncpg driver. SQLite is the MVP path now;
    Postgres lands in Phase 5 (requires asyncpg).
    """
    if url.startswith("sqlite+") or url.startswith("postgresql+"):
        return url  # already names an async driver
    if url.startswith("sqlite:"):
        return url.replace("sqlite:", "sqlite+aiosqlite:", 1)
    if url.startswith("postgresql:"):
        return url.replace("postgresql:", "postgresql+asyncpg:", 1)
    return url


# Create async engine
engine = create_async_engine(
    _to_async_url(settings.database_url),
    echo=False,
    pool_pre_ping=True,
)

# Create async session factory (async_sessionmaker is the typed SA 2.0 factory
# for AsyncEngine; plain sessionmaker only accepts Engine/Connection).
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI: provide async session."""
    async with async_session() as session:
        yield session


# Columns added after their table first shipped. create_all() won't alter an existing
# table, so each is applied idempotently on startup: ADD COLUMN works on both SQLite
# and Postgres, and re-adding raises, which we swallow. Append-only — never reorder or
# remove an entry, since an older database may still need every earlier one.
_ADDED_COLUMNS = (
    ("scans", "progress", "TEXT"),
    ("scans", "heartbeat_at", "TIMESTAMP"),
    ("scans", "coverage_json", "TEXT"),
    ("scans", "groups_json", "TEXT"),
    ("scans", "resolved_sha", "VARCHAR"),
    ("scans", "content_hash", "VARCHAR"),
    ("scans", "file_count", "INTEGER"),
    ("scans", "ingested_at", "TIMESTAMP"),
    ("scans", "engine_versions_json", "TEXT"),
    ("scans", "suppressed_json", "TEXT"),
)


async def init_db():
    """Initialize database (create tables) + lightweight column migrations."""
    from .models import Base
    from .diagnostics import log_stray_databases
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table, column, coltype in _ADDED_COLUMNS:
            try:
                await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            except Exception:
                pass  # column already exists
        # State which database is live, in absolute terms. When the API and worker
        # disagree about this path the dashboard silently serves another file's rows,
        # so it must be greppable in the logs of both processes.
        scans = (await conn.exec_driver_sql("SELECT COUNT(*) FROM scans")).scalar()
        logger.info(
            "database resolved: %s (dialect=%s, scans=%s rows)",
            engine.url.database, engine.dialect.name, scans,
        )
    log_stray_databases()


async def close_db():
    """Close engine."""
    await engine.dispose()
