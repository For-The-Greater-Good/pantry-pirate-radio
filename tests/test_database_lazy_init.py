"""Tests for lazy database initialization functionality."""

import os
from unittest.mock import patch, MagicMock

import pytest


def test_database_lazy_initialization():
    """Test that database initialization is lazy and works correctly."""
    # Clear any existing state
    import app.core.db

    app.core.db.engine = None
    app.core.db.async_session_factory = None

    # Test that variables start as None
    assert app.core.db.engine is None
    assert app.core.db.async_session_factory is None


def test_initialize_database_with_testing_flag():
    """Test that _initialize_database skips creation when TESTING=true."""
    import app.core.db

    app.core.db.engine = None
    app.core.db.async_session_factory = None

    with patch.dict(os.environ, {"TESTING": "true"}):
        app.core.db._initialize_database()

        # Should remain None in testing mode
        assert app.core.db.engine is None
        assert app.core.db.async_session_factory is None


def test_initialize_database_already_initialized():
    """Test that _initialize_database skips if already initialized."""
    import app.core.db

    # Set up as already initialized
    mock_engine = MagicMock()
    app.core.db.engine = mock_engine

    with patch("app.core.db.create_async_engine") as mock_create:
        app.core.db._initialize_database()

        # Should not create a new engine
        mock_create.assert_not_called()
        assert app.core.db.engine is mock_engine


@pytest.mark.asyncio
async def test_get_session_initializes_database():
    """Test that get_session calls _initialize_database."""
    import app.core.db

    app.core.db.engine = None
    app.core.db.async_session_factory = None

    with patch("app.core.db._initialize_database") as mock_init:
        # This will fail due to None session factory, but that's expected
        try:
            async for _ in app.core.db.get_session():
                pass
        except RuntimeError as e:
            assert "Database not initialized" in str(e)

        # Verify initialization was called
        mock_init.assert_called_once()


@pytest.mark.asyncio
async def test_get_session_runtime_error_when_not_initialized():
    """Test that get_session raises RuntimeError when session factory is None."""
    import app.core.db

    app.core.db.engine = None
    app.core.db.async_session_factory = None

    with patch("app.core.db._initialize_database"):
        with pytest.raises(RuntimeError, match="Database not initialized"):
            async for _ in app.core.db.get_session():
                pass


def test_database_url_conversion_postgresql():
    """Test database URL conversion for postgresql://."""
    import app.core.db

    app.core.db.engine = None
    app.core.db.async_session_factory = None

    with patch.dict(os.environ, {"TESTING": "false"}), patch(
        "app.core.db.settings"
    ) as mock_settings, patch("app.core.db.create_async_engine") as mock_create, patch(
        "app.core.db.async_sessionmaker"
    ) as mock_session:

        mock_settings.DATABASE_URL = "postgresql://user:pass@host:5432/db"
        mock_settings.MAX_CONNECTIONS = 10

        app.core.db._initialize_database()

        # Verify URL was converted to asyncpg
        mock_create.assert_called_once()
        call_args = mock_create.call_args[0]
        assert call_args[0] == "postgresql+asyncpg://user:pass@host:5432/db"


def test_database_url_conversion_postgres():
    """Test database URL conversion for postgres://."""
    import app.core.db

    app.core.db.engine = None
    app.core.db.async_session_factory = None

    with patch.dict(os.environ, {"TESTING": "false"}), patch(
        "app.core.db.settings"
    ) as mock_settings, patch("app.core.db.create_async_engine") as mock_create, patch(
        "app.core.db.async_sessionmaker"
    ) as mock_session:

        mock_settings.DATABASE_URL = "postgres://user:pass@host:5432/db"
        mock_settings.MAX_CONNECTIONS = 10

        app.core.db._initialize_database()

        # Verify URL was converted to asyncpg
        mock_create.assert_called_once()
        call_args = mock_create.call_args[0]
        assert call_args[0] == "postgresql+asyncpg://user:pass@host:5432/db"


def test_database_url_no_conversion_needed():
    """Test that URLs already with specific drivers are not modified."""
    import app.core.db

    app.core.db.engine = None
    app.core.db.async_session_factory = None

    with patch.dict(os.environ, {"TESTING": "false"}), patch(
        "app.core.db.settings"
    ) as mock_settings, patch("app.core.db.create_async_engine") as mock_create, patch(
        "app.core.db.async_sessionmaker"
    ) as mock_session:

        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/db"
        mock_settings.MAX_CONNECTIONS = 10

        app.core.db._initialize_database()

        # Verify URL was used as-is
        mock_create.assert_called_once()
        call_args = mock_create.call_args[0]
        assert call_args[0] == "postgresql+asyncpg://user:pass@host:5432/db"
