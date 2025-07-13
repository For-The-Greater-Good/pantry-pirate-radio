"""Tests for Datasette exporter main entry point."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from app.datasette.__main__ import main


def test_main_success():
    """Test main function runs successfully."""
    with patch(
        "app.datasette.__main__.get_interval_from_env"
    ) as mock_get_interval, patch(
        "app.datasette.__main__.scheduled_export"
    ) as mock_scheduled_export, patch.dict(
        "os.environ", {"OUTPUT_DIR": "/test/output"}
    ):

        mock_get_interval.return_value = 3600

        main()

        mock_get_interval.assert_called_once()
        mock_scheduled_export.assert_called_once_with(
            output_dir="/test/output", interval_seconds=3600
        )


def test_main_default_output_dir():
    """Test main function uses default output directory."""
    with patch(
        "app.datasette.__main__.get_interval_from_env"
    ) as mock_get_interval, patch(
        "app.datasette.__main__.scheduled_export"
    ) as mock_scheduled_export, patch.dict(
        "os.environ", {}, clear=True
    ):

        mock_get_interval.return_value = 1800

        main()

        mock_scheduled_export.assert_called_once_with(
            output_dir="/data", interval_seconds=1800
        )


def test_main_keyboard_interrupt():
    """Test main function handles KeyboardInterrupt."""
    with patch("app.datasette.__main__.scheduled_export") as mock_scheduled_export:
        # Make scheduled_export raise KeyboardInterrupt
        mock_scheduled_export.side_effect = KeyboardInterrupt()

        # The main() function should raise KeyboardInterrupt
        with pytest.raises(KeyboardInterrupt):
            main()


def test_main_exception_handling():
    """Test main function handles general exceptions."""
    with patch("app.datasette.__main__.scheduled_export") as mock_scheduled_export:
        # Make scheduled_export raise an exception
        mock_scheduled_export.side_effect = Exception("Test error")

        # Call main() which should propagate the exception
        with pytest.raises(Exception) as exc_info:
            main()

        # Verify the exception message
        assert str(exc_info.value) == "Test error"


def test_main_logging_configuration():
    """Test main function logs startup information."""
    with patch(
        "app.datasette.__main__.get_interval_from_env"
    ) as mock_get_interval, patch(
        "app.datasette.__main__.scheduled_export"
    ) as mock_scheduled_export, patch(
        "app.datasette.__main__.logger"
    ) as mock_logger, patch.dict(
        "os.environ", {"OUTPUT_DIR": "/custom/path"}
    ):

        mock_get_interval.return_value = 7200

        main()

        # Check that logging calls were made
        mock_logger.info.assert_any_call("Starting Datasette exporter service")
        mock_logger.info.assert_any_call("Export interval: 7200 seconds")
        mock_logger.info.assert_any_call("Output directory: /custom/path")
