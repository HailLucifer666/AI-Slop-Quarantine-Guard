"""Async SQLAlchemy engine and session factory (real impl).

Uses SQLAlchemy 2.0 async with asyncio.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from typing import AsyncGenerator

from ..config import settings


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

# Create async session factory
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI: provide async session."""
    async with async_session() as session:
        yield session


async def init_db():
    """Initialize database (create tables) + lightweight column migrations."""
    from .models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent add of columns introduced after a table first shipped, so an
        # existing app.db keeps working without a migration tool (create_all won't
        # alter an existing table). ADD COLUMN is supported by SQLite and Postgres;
        # a duplicate raises, which we swallow.
        try:
            await conn.exec_driver_sql("ALTER TABLE scans ADD COLUMN progress TEXT")
        except Exception:
            pass  # column already exists


async def close_db():
    """Close engine."""
    await engine.dispose()
