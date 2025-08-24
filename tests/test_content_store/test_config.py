"""Tests for content store configuration."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.content_store import ContentStore
from app.content_store.config import get_content_store


class TestContentStoreConfig:
    """Test cases for content store configuration."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        # Reset the singleton instance before each test
        import app.content_store.config as config

        config._content_store_instance = None
        config._content_store_initialized = False
        yield
        # Clean up after test
        config._content_store_instance = None
        config._content_store_initialized = False

    def test_should_return_none_when_not_configured(self):
        """Should return None when content store is not configured."""
        with patch.dict(os.environ, {}, clear=True):
            store = get_content_store()
            assert store is None

    def test_should_create_content_store_with_env_path(self):
        """Should create content store with path from environment variable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CONTENT_STORE_PATH": tmpdir}):
                store = get_content_store()
                assert store is not None
                assert isinstance(store, ContentStore)
                assert store.store_path == Path(tmpdir)

    def test_should_create_path_if_not_exists(self):
        """Should create store path if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_path = Path(tmpdir) / "content_store"
            assert not new_path.exists()

            with patch.dict(os.environ, {"CONTENT_STORE_PATH": str(new_path)}):
                store = get_content_store()
                assert store is not None
                assert new_path.exists()
                assert new_path.is_dir()

    def test_should_cache_singleton_instance(self):
        """Should return same instance on multiple calls."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CONTENT_STORE_PATH": tmpdir}):
                store1 = get_content_store()
                store2 = get_content_store()
                assert store1 is store2

    def test_should_handle_disable_flag(self):
        """Should return None when explicitly disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {"CONTENT_STORE_PATH": tmpdir, "CONTENT_STORE_ENABLED": "false"},
            ):
                store = get_content_store()
                assert store is None

    def test_should_be_enabled_by_default_when_path_set(self):
        """Should be enabled by default when path is set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CONTENT_STORE_PATH": tmpdir}):
                store = get_content_store()
                assert store is not None

    def test_should_handle_various_enabled_values(self):
        """Should handle various boolean representations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Test various false values
            for false_value in ["false", "False", "FALSE", "0", "no", "NO"]:
                with patch.dict(
                    os.environ,
                    {
                        "CONTENT_STORE_PATH": tmpdir,
                        "CONTENT_STORE_ENABLED": false_value,
                    },
                    clear=True,
                ):
                    # Reset singleton
                    import app.content_store.config as config

                    config._content_store_instance = None
                    config._content_store_initialized = False
                    store = get_content_store()
                    assert (
                        store is None
                    ), f"Expected None for CONTENT_STORE_ENABLED={false_value}"

            # Test various true values
            for true_value in ["true", "True", "TRUE", "1", "yes", "YES"]:
                with patch.dict(
                    os.environ,
                    {"CONTENT_STORE_PATH": tmpdir, "CONTENT_STORE_ENABLED": true_value},
                    clear=True,
                ):
                    # Reset singleton
                    import app.content_store.config as config

                    config._content_store_instance = None
                    config._content_store_initialized = False
                    store = get_content_store()
                    assert (
                        store is not None
                    ), f"Expected ContentStore for CONTENT_STORE_ENABLED={true_value}"

    def test_should_use_default_path_when_enabled_without_path(self):
        """Should use default path when enabled but no path specified."""
        with patch.dict(os.environ, {"CONTENT_STORE_ENABLED": "true"}, clear=True):
            # Reset singleton
            if hasattr(get_content_store, "_instance"):
                delattr(get_content_store, "_instance")
            store = get_content_store()
            assert store is not None
            # Default path should be relative to project root
            assert "content_store" in str(store.store_path)

    def test_should_not_use_production_path_in_tests(self):
        """Should not use production /data-repo path when running tests."""
        # When CONTENT_STORE_PATH is set to test path
        with patch.dict(
            os.environ, {"CONTENT_STORE_PATH": "/tmp/test_content_store"}  # noqa: S108
        ):  # Temporary test directory
            store = get_content_store()
            assert store is not None
            # Should use test path, not production path
            assert (
                str(store.store_path) == "/tmp/test_content_store"  # noqa: S108
            )  # Temporary test directory
            assert "/data-repo" not in str(store.store_path)
            assert "/tmp/test_content_store" in str(  # noqa: S108
                store.content_store_path
            )  # Temporary test directory
