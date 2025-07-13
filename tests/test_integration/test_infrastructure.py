"""Test infrastructure integration."""

from typing import Any, cast

import pytest
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_database_connection(db_session_sync: Session) -> None:
    """Test database connection and PostGIS."""
    result = db_session_sync.execute(text("SELECT version()"))
    version = result.scalar_one()
    assert version is not None
    assert "postgresql" in version.lower()

    result = db_session_sync.execute(text("SELECT postgis_full_version()"))
    version = result.scalar_one()
    assert version is not None
    assert "postgis" in version.lower()


@pytest.mark.integration
def test_redis_connection(redis_client: "Redis[Any]") -> None:
    """Test Redis connection."""
    # Set test value
    redis_client.set("test_key", b"test_value")

    # Get value back
    value = redis_client.get("test_key")
    assert value is not None
    assert value == b"test_value"


@pytest.mark.integration
def test_redis_clean_between_tests(redis_client: "Redis[Any]") -> None:
    """Test Redis is cleaned between tests."""
    # Previous test key should be gone
    value = redis_client.get("test_key")
    assert value is None

    # Current test should have clean Redis
    keys = cast(list[bytes], redis_client.keys("*"))
    assert len(keys) == 0
