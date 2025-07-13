"""Tests for recorder service main entry point."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.recorder.__main__ import main, record_result


def test_record_result_success():
    """Test record_result function saves data successfully."""
    with patch(
        "app.recorder.utils.record_result"
    ) as mock_utils_record_result, patch.dict(
        "os.environ", {"OUTPUT_DIR": "/test/output", "ARCHIVE_DIR": "/test/archive"}
    ):

        from app.recorder.__main__ import record_result as main_record_result

        test_data = {"job_id": "test-123", "result": "success"}

        result = main_record_result(test_data)

        assert result == {"status": "completed", "error": None}


def test_record_result_with_default_dirs():
    """Test record_result uses default directories when env vars not set."""
    with patch(
        "app.recorder.utils.record_result"
    ) as mock_utils_record_result, patch.dict("os.environ", {}, clear=True):

        from app.recorder.__main__ import record_result as main_record_result

        test_data = {"job_id": "test-456", "data": "test"}

        result = main_record_result(test_data)

        assert result == {"status": "completed", "error": None}


def test_record_result_handles_exception():
    """Test record_result handles exceptions gracefully."""
    with patch("app.recorder.utils.record_result") as mock_utils_record_result, patch(
        "app.recorder.__main__.logger"
    ) as mock_logger:

        from app.recorder.__main__ import record_result as main_record_result

        # Mock the utils function to raise an exception
        mock_utils_record_result.side_effect = Exception("Save failed")

        test_data = {"job_id": "test-789"}

        result = main_record_result(test_data)

        assert result == {"status": "failed", "error": "Save failed"}
        mock_logger.exception.assert_called_once_with("Failed to save result")


def test_main_success():
    """Test main function runs successfully."""
    with patch("app.recorder.__main__.Redis") as mock_redis_class, patch(
        "app.recorder.__main__.Connection"
    ) as mock_connection, patch(
        "app.recorder.__main__.Worker"
    ) as mock_worker_class, patch.dict(
        "os.environ", {"REDIS_URL": "redis://localhost:6379/0"}
    ):

        # Mock Redis instance
        mock_redis_instance = MagicMock()
        mock_redis_class.from_url.return_value = mock_redis_instance

        # Mock worker instance
        mock_worker_instance = MagicMock()
        mock_worker_class.return_value = mock_worker_instance

        # Mock connection context manager
        mock_connection_instance = MagicMock()
        mock_connection.return_value = mock_connection_instance

        main()

        # Verify Redis connection
        mock_redis_class.from_url.assert_called_once_with("redis://localhost:6379/0")

        # Verify connection context manager
        mock_connection.assert_called_once_with(mock_redis_instance)

        # Verify worker creation
        mock_worker_class.assert_called_once_with(["recorder"])

        # Verify worker starts
        mock_worker_instance.work.assert_called_once()


def test_main_missing_redis_url():
    """Test main function raises error when REDIS_URL not set."""
    with patch.dict("os.environ", {}, clear=True):

        with pytest.raises(KeyError, match="REDIS_URL environment variable not set"):
            main()


def test_main_with_redis_url_from_env():
    """Test main function uses REDIS_URL from environment."""
    with patch("app.recorder.__main__.Redis") as mock_redis_class, patch(
        "app.recorder.__main__.Connection"
    ) as mock_connection, patch(
        "app.recorder.__main__.Worker"
    ) as mock_worker_class, patch.dict(
        "os.environ", {"REDIS_URL": "redis://custom:6379/5"}
    ):

        mock_redis_instance = MagicMock()
        mock_redis_class.from_url.return_value = mock_redis_instance

        mock_worker_instance = MagicMock()
        mock_worker_class.return_value = mock_worker_instance

        main()

        # Verify custom Redis URL is used
        mock_redis_class.from_url.assert_called_once_with("redis://custom:6379/5")


def test_main_worker_configuration():
    """Test worker is configured correctly."""
    with patch("app.recorder.__main__.Redis") as mock_redis_class, patch(
        "app.recorder.__main__.Connection"
    ) as mock_connection, patch(
        "app.recorder.__main__.Worker"
    ) as mock_worker_class, patch.dict(
        "os.environ", {"REDIS_URL": "redis://localhost:6379/0"}
    ):

        mock_redis_instance = MagicMock()
        mock_redis_class.from_url.return_value = mock_redis_instance

        mock_worker_instance = MagicMock()
        mock_worker_class.return_value = mock_worker_instance

        main()

        # Verify worker is created with correct queue
        mock_worker_class.assert_called_once_with(["recorder"])

        # Verify worker starts without scheduler (different from reconciler)
        mock_worker_instance.work.assert_called_once_with()
