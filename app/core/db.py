"""Database connection and session management."""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# Lazy database initialization - don't create engine at import time
engine = None
async_session_factory = None


def _initialize_database():
    """Initialize database engine and session factory."""
    global engine, async_session_factory

    if engine is not None:
        return  # Already initialized

    if os.getenv("TESTING") == "true":
        # Keep as None for testing - will be overridden in test fixtures
        return

    # Convert to postgresql+asyncpg:// for async support
    database_url = settings.DATABASE_URL
    if database_url.startswith("postgresql+psycopg2://"):
        database_url = database_url.replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://", 1
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(
        database_url,
        pool_size=settings.MAX_CONNECTIONS,
        max_overflow=0,
        echo=False,
    )

    # Create session factory
    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session.

    Yields:
        AsyncSession: Database session
    """
    # Initialize database on first use
    _initialize_database()

    if async_session_factory is None:
        raise RuntimeError("Database not initialized - cannot create session")

    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
