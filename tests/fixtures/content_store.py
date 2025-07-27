"""Content store fixtures for tests."""

import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from app.content_store import ContentStore
from app.content_store.config import reset_content_store


@pytest.fixture
def temp_content_store(monkeypatch) -> Generator[ContentStore, None, None]:
    """Provide a temporary content store for tests."""
    # Reset singleton before test
    reset_content_store()

    # Create temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set environment variables
        monkeypatch.setenv("CONTENT_STORE_PATH", tmpdir)
        monkeypatch.setenv("CONTENT_STORE_ENABLED", "true")

        # Get content store instance
        from app.content_store.config import get_content_store

        store = get_content_store()

        yield store

        # Clean up
        reset_content_store()


@pytest.fixture
def no_content_store(monkeypatch) -> Generator[None, None, None]:
    """Disable content store for tests."""
    # Reset singleton before test
    reset_content_store()

    # Disable content store
    monkeypatch.setenv("CONTENT_STORE_ENABLED", "false")

    yield

    # Clean up
    reset_content_store()


@pytest.fixture(autouse=True)
def auto_reset_content_store():
    """Automatically reset content store singleton between tests."""
    reset_content_store()
    yield
    reset_content_store()
