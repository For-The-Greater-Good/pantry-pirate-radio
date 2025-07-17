"""Database connection and session management."""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# Create async engine
# Convert postgres:// to postgresql+asyncpg:// for async support
database_url = settings.DATABASE_URL

# Skip database engine creation during testing to avoid connection issues
if os.getenv("TESTING") == "true":
    # Use a mock engine for testing - will be overridden in test fixtures
    engine = None
    async_session_factory = None
else:
    if database_url.startswith("postgresql://"):
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
    if async_session_factory is None:
        raise RuntimeError("Database not initialized - cannot create session")

    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
