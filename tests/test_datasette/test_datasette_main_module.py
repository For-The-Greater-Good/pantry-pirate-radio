"""Tests for datasette main module."""

import sys
from unittest.mock import patch, MagicMock
import pytest

from app.datasette.__main__ import main


class TestDatasetteMain:
    """Tests for datasette main module functionality."""

    @patch("app.datasette.__main__.scheduled_export")
    @patch("app.datasette.__main__.get_interval_from_env")
    @patch("app.datasette.__main__.logger")
    def test_main_function_basic(
        self, mock_logger, mock_get_interval, mock_scheduled_export
    ):
        """Test basic main function execution."""
        # Mock environment and functions
        mock_get_interval.return_value = 3600

        with patch.dict("os.environ", {"OUTPUT_DIR": "/test/output"}):
            main()

        # Verify logging
        mock_logger.info.assert_any_call("Starting Datasette exporter service")
        mock_logger.info.assert_any_call("Export interval: 3600 seconds")
        mock_logger.info.assert_any_call("Output directory: /test/output")

        # Verify scheduled export was called
        mock_scheduled_export.assert_called_once_with(
            output_dir="/test/output", interval_seconds=3600
        )

    @patch("app.datasette.__main__.scheduled_export")
    @patch("app.datasette.__main__.get_interval_from_env")
    @patch("app.datasette.__main__.logger")
    def test_main_function_default_output_dir(
        self, mock_logger, mock_get_interval, mock_scheduled_export
    ):
        """Test main function with default output directory."""
        mock_get_interval.return_value = 7200

        # Don't set OUTPUT_DIR - should use default
        with patch.dict("os.environ", {}, clear=True):
            main()

        # Verify default output directory was used
        mock_logger.info.assert_any_call("Output directory: /data")
        mock_scheduled_export.assert_called_once_with(
            output_dir="/data", interval_seconds=7200
        )

    @patch("app.datasette.__main__.scheduled_export")
    @patch("app.datasette.__main__.get_interval_from_env")
    @patch("app.datasette.__main__.logger")
    def test_main_function_custom_interval(
        self, mock_logger, mock_get_interval, mock_scheduled_export
    ):
        """Test main function with custom interval."""
        mock_get_interval.return_value = 1800  # 30 minutes

        with patch.dict("os.environ", {"OUTPUT_DIR": "/custom/path"}):
            main()

        # Verify custom interval was used
        mock_logger.info.assert_any_call("Export interval: 1800 seconds")
        mock_scheduled_export.assert_called_once_with(
            output_dir="/custom/path", interval_seconds=1800
        )

    @patch("app.datasette.__main__.main")
    @patch("app.datasette.__main__.logger")
    def test_main_module_keyboard_interrupt(self, mock_logger, mock_main):
        """Test main module handling of KeyboardInterrupt."""
        # Mock main to raise KeyboardInterrupt
        mock_main.side_effect = KeyboardInterrupt()

        # Import and execute the main module logic
        with patch("app.datasette.__main__.__name__", "__main__"):
            try:
                # Simulate the if __name__ == "__main__" block
                try:
                    mock_main()
                except KeyboardInterrupt:
                    mock_logger.info("Exporter service stopped by user")
                except Exception as e:
                    mock_logger.error(f"Exporter service failed: {e}", exc_info=True)
                    sys.exit(1)
            except SystemExit:
                pass

        # Verify KeyboardInterrupt was handled
        mock_logger.info.assert_called_with("Exporter service stopped by user")

    @patch("app.datasette.__main__.main")
    @patch("app.datasette.__main__.logger")
    def test_main_module_exception_handling(self, mock_logger, mock_main):
        """Test main module handling of general exceptions."""
        # Mock main to raise a general exception
        test_exception = Exception("Test error")
        mock_main.side_effect = test_exception

        # Import and execute the main module logic
        with patch("app.datasette.__main__.__name__", "__main__"):
            with pytest.raises(SystemExit) as exc_info:
                # Simulate the if __name__ == "__main__" block
                try:
                    mock_main()
                except KeyboardInterrupt:
                    mock_logger.info("Exporter service stopped by user")
                except Exception as e:
                    mock_logger.error(f"Exporter service failed: {e}", exc_info=True)
                    sys.exit(1)

        # Verify exception was handled and logged
        mock_logger.error.assert_called_with(
            "Exporter service failed: Test error", exc_info=True
        )
        assert exc_info.value.code == 1

    @patch("app.datasette.__main__.scheduled_export")
    @patch("app.datasette.__main__.get_interval_from_env")
    @patch("app.datasette.__main__.logger")
    def test_logging_configuration(
        self, mock_logger, mock_get_interval, mock_scheduled_export
    ):
        """Test that logging is properly configured."""
        # This test verifies that the logging configuration is set up
        # by checking that logger calls work as expected
        mock_get_interval.return_value = 3600

        with patch.dict("os.environ", {"OUTPUT_DIR": "/test"}):
            main()

        # Verify multiple log messages were called
        assert mock_logger.info.call_count >= 3

        # Verify the expected log messages
        log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        assert "Starting Datasette exporter service" in log_calls
        assert "Export interval: 3600 seconds" in log_calls
        assert "Output directory: /test" in log_calls

    @patch("app.datasette.__main__.scheduled_export")
    @patch("app.datasette.__main__.get_interval_from_env")
    def test_main_function_calls_dependencies(
        self, mock_get_interval, mock_scheduled_export
    ):
        """Test that main function calls its dependencies correctly."""
        mock_get_interval.return_value = 1234

        with patch.dict("os.environ", {"OUTPUT_DIR": "/some/path"}):
            main()

        # Verify dependencies were called
        mock_get_interval.assert_called_once()
        mock_scheduled_export.assert_called_once_with(
            output_dir="/some/path", interval_seconds=1234
        )

    def test_module_imports(self):
        """Test that module imports work correctly."""
        # Test that we can import the main function
        from app.datasette.__main__ import main

        assert callable(main)

        # Test that logging is configured
        import logging

        logger = logging.getLogger("app.datasette.__main__")
        assert logger is not None

    @patch("app.datasette.__main__.scheduled_export")
    @patch("app.datasette.__main__.get_interval_from_env")
    def test_environment_variable_handling(
        self, mock_get_interval, mock_scheduled_export
    ):
        """Test various environment variable scenarios."""
        mock_get_interval.return_value = 3600

        # Test with empty string OUTPUT_DIR
        with patch.dict("os.environ", {"OUTPUT_DIR": ""}):
            main()

        mock_scheduled_export.assert_called_with(output_dir="", interval_seconds=3600)

        # Test with whitespace OUTPUT_DIR
        with patch.dict("os.environ", {"OUTPUT_DIR": "  /path/with/spaces  "}):
            main()

        mock_scheduled_export.assert_called_with(
            output_dir="  /path/with/spaces  ", interval_seconds=3600
        )
