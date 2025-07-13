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
    # Use psycopg2 for both async and sync since we're using RQ
    engine = create_async_engine(
        settings.DATABASE_URL,
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
    # Use psycopg2 for both async and sync since we're using RQ
    engine = create_engine(
        settings.DATABASE_URL,
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
