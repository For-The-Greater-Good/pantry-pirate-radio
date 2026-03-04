"""Tests for content store configuration."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.content_store import ContentStore, FileContentStoreBackend
from app.content_store.config import _create_backend, get_content_store


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


class TestContentStoreBackendFactory:
    """Test cases for backend factory configuration."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        import app.content_store.config as config

        config._content_store_instance = None
        config._content_store_initialized = False
        yield
        config._content_store_instance = None
        config._content_store_initialized = False

    def test_create_backend_defaults_to_file(self, tmp_path):
        """_create_backend should default to file backend."""
        backend = _create_backend(tmp_path, "file")
        assert isinstance(backend, FileContentStoreBackend)

    def test_create_backend_file_initializes_directories(self, tmp_path):
        """File backend should create directory structure."""
        backend = _create_backend(tmp_path, "file")

        assert (tmp_path / "content_store").exists()
        assert (tmp_path / "content_store" / "content").exists()
        assert (tmp_path / "content_store" / "results").exists()
        assert (tmp_path / "content_store" / "index.db").exists()

    def test_create_backend_s3_requires_bucket(self, tmp_path):
        """S3 backend should raise ValueError if CONTENT_STORE_S3_BUCKET missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                _create_backend(tmp_path, "s3")

            assert "CONTENT_STORE_S3_BUCKET is required" in str(exc_info.value)

    def test_create_backend_s3_requires_table(self, tmp_path):
        """S3 backend should raise ValueError if CONTENT_STORE_DYNAMODB_TABLE missing."""
        with patch.dict(
            os.environ, {"CONTENT_STORE_S3_BUCKET": "test-bucket"}, clear=True
        ):
            with pytest.raises(ValueError) as exc_info:
                _create_backend(tmp_path, "s3")

            assert "CONTENT_STORE_DYNAMODB_TABLE is required" in str(exc_info.value)

    def test_create_backend_s3_creates_backend_with_env_vars(self, tmp_path):
        """S3 backend should be created when all env vars present."""
        from unittest.mock import MagicMock

        from app.content_store.backend_s3 import S3ContentStoreBackend

        with patch.dict(
            os.environ,
            {
                "CONTENT_STORE_S3_BUCKET": "my-bucket",
                "CONTENT_STORE_DYNAMODB_TABLE": "my-table",
                "AWS_DEFAULT_REGION": "us-west-2",
            },
            clear=True,
        ):
            # Mock the S3 and DynamoDB clients to avoid actual AWS calls
            with patch.object(S3ContentStoreBackend, "_get_s3_client") as mock_s3:
                with patch.object(
                    S3ContentStoreBackend, "_get_dynamodb_client"
                ) as mock_dynamodb:
                    mock_s3.return_value = MagicMock()
                    mock_dynamodb.return_value = MagicMock()

                    backend = _create_backend(tmp_path, "s3")

                    assert isinstance(backend, S3ContentStoreBackend)
                    assert backend.s3_bucket == "my-bucket"
                    assert backend.dynamodb_table == "my-table"
                    assert backend.region_name == "us-west-2"

    def test_create_backend_unknown_type_raises(self, tmp_path):
        """Unknown backend type should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            _create_backend(tmp_path, "unknown")

        assert "Unknown CONTENT_STORE_BACKEND" in str(exc_info.value)

    def test_get_content_store_uses_file_backend_by_default(self):
        """get_content_store should use file backend by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CONTENT_STORE_PATH": tmpdir}, clear=True):
                store = get_content_store()
                assert store is not None
                assert isinstance(store.backend, FileContentStoreBackend)

    def test_get_content_store_respects_backend_env_var(self):
        """get_content_store should respect CONTENT_STORE_BACKEND env var."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {"CONTENT_STORE_PATH": tmpdir, "CONTENT_STORE_BACKEND": "file"},
                clear=True,
            ):
                store = get_content_store()
                assert store is not None
                assert isinstance(store.backend, FileContentStoreBackend)

    def test_get_content_store_s3_backend_requires_env_vars(self):
        """get_content_store with s3 backend should raise if env vars missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {"CONTENT_STORE_PATH": tmpdir, "CONTENT_STORE_BACKEND": "s3"},
                clear=True,
            ):
                with pytest.raises(ValueError) as exc_info:
                    get_content_store()
                assert "CONTENT_STORE_S3_BUCKET is required" in str(exc_info.value)

    def test_get_content_store_s3_backend_with_env_vars(self):
        """get_content_store with s3 backend should work with proper env vars."""
        from unittest.mock import MagicMock

        from app.content_store.backend_s3 import S3ContentStoreBackend

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CONTENT_STORE_PATH": tmpdir,
                    "CONTENT_STORE_BACKEND": "s3",
                    "CONTENT_STORE_S3_BUCKET": "test-bucket",
                    "CONTENT_STORE_DYNAMODB_TABLE": "test-table",
                },
                clear=True,
            ):
                # Mock AWS clients
                with patch.object(S3ContentStoreBackend, "_get_s3_client") as mock_s3:
                    with patch.object(
                        S3ContentStoreBackend, "_get_dynamodb_client"
                    ) as mock_dynamodb:
                        mock_s3.return_value = MagicMock()
                        mock_dynamodb.return_value = MagicMock()

                        store = get_content_store()
                        assert store is not None
                        assert isinstance(store.backend, S3ContentStoreBackend)
