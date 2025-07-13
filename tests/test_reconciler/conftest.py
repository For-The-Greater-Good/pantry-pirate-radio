"""Shared fixtures for reconciler tests."""

from typing import Generator

import pytest
from prometheus_client import REGISTRY
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.reconciler.metrics import LOCATION_MATCHES, RECONCILER_JOBS, RECORD_VERSIONS
from tests.fixtures.types.config import get_test_settings

settings = get_test_settings()


@pytest.fixture(autouse=True)
def setup_database(db_session: Session) -> Generator[None, None, None]:
    """Clean test data between test runs."""
    # Clear test data from tables
    db_session.execute(text("TRUNCATE TABLE record_version CASCADE"))
    db_session.execute(text("TRUNCATE TABLE location CASCADE"))
    db_session.execute(text("TRUNCATE TABLE organization CASCADE"))
    db_session.commit()

    yield


@pytest.fixture(autouse=True)
def setup_metrics() -> Generator[None, None, None]:
    """Set up metrics for testing."""
    # Clear existing metrics
    for metric in [RECONCILER_JOBS, LOCATION_MATCHES, RECORD_VERSIONS]:
        try:
            REGISTRY.unregister(metric)
        except KeyError:
            pass

    # Register metrics
    for metric in [RECONCILER_JOBS, LOCATION_MATCHES, RECORD_VERSIONS]:
        REGISTRY.register(metric)

    yield

    # Clean up metrics
    for metric in [RECONCILER_JOBS, LOCATION_MATCHES, RECORD_VERSIONS]:
        try:
            REGISTRY.unregister(metric)
        except KeyError:
            pass


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Database session fixture."""
    # Create engine and session factory
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)

    # Create session
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
