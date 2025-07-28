"""Database test fixtures."""

from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from .types.config import Settings, get_test_settings

settings: Settings = get_test_settings()


@pytest_asyncio.fixture(scope="function")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Get database engine for testing.

    Yields:
        AsyncEngine for test database
    """
    # Safety check: ensure we're using test database
    db_url = settings.DATABASE_URL.lower()
    if "test" not in db_url:
        raise ValueError(
            f"Database URL '{settings.DATABASE_URL}' doesn't appear to be a test database! "
            "Test database URL should contain 'test' to prevent data loss."
        )

    # Convert sync database URL to async for testing
    async_url = settings.DATABASE_URL.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    ).replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(
        async_url,
        echo=settings.DB_ECHO,
        pool_pre_ping=True,
        future=True,
    )

    try:
        # Verify database connection
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

        # Return engine
        yield engine

    finally:
        # Close engine
        await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session_factory(
    db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Get session factory for testing.

    Args:
        db_engine: Database engine

    Returns:
        Session factory for creating test sessions
    """
    return async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture(scope="function")
async def db_session(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Get database session for testing.

    Args:
        db_session_factory: Session factory

    Yields:
        Database session that rolls back after test
    """
    async with db_session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()


@pytest.fixture(scope="function")
def db_session_sync() -> Generator[Session, None, None]:
    """Get synchronous database session for testing.

    Yields:
        Synchronous database session
    """
    # Safety check: ensure we're using test database
    db_url = settings.DATABASE_URL.lower()
    if "test" not in db_url:
        raise ValueError(
            f"Database URL '{settings.DATABASE_URL}' doesn't appear to be a test database! "
            "Test database URL should contain 'test' to prevent data loss."
        )

    # Ensure sync database URL uses psycopg2
    sync_url = settings.DATABASE_URL
    if "postgresql+asyncpg://" in sync_url:
        sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    elif "postgresql://" in sync_url and "postgresql+psycopg2://" not in sync_url:
        sync_url = sync_url.replace("postgresql://", "postgresql+psycopg2://")

    engine = create_engine(
        sync_url,
        echo=settings.DB_ECHO,
        pool_pre_ping=True,
        future=True,
    )

    try:
        # Create session factory
        session_factory = sessionmaker(
            engine,
            expire_on_commit=False,
        )

        # Create session
        with session_factory() as session:
            try:
                yield session
            finally:
                session.rollback()
                session.close()

    finally:
        # Close engine
        engine.dispose()
