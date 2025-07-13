"""Tests for datasette scheduler module."""

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import pytest

from app.datasette.scheduler import (
    scheduled_export,
    cleanup_old_exports,
    get_interval_from_env,
)


class TestScheduledExport:
    """Tests for scheduled_export function."""

    @patch("app.datasette.scheduler.time.sleep")
    @patch("app.datasette.scheduler.export_to_sqlite")
    @patch("app.datasette.scheduler.os.makedirs")
    @patch("app.datasette.scheduler.datetime")
    def test_scheduled_export_basic_single_iteration(
        self, mock_datetime, mock_makedirs, mock_export, mock_sleep
    ):
        """Test basic scheduled export functionality for one iteration."""
        # Mock datetime to return consistent timestamp
        mock_now = MagicMock()
        mock_now.strftime.return_value = "20230101_120000"
        mock_datetime.now.return_value = mock_now

        # Mock sleep to break the infinite loop after first iteration
        mock_sleep.side_effect = KeyboardInterrupt("Break loop")

        output_dir = "/test/output"

        with pytest.raises(KeyboardInterrupt):
            scheduled_export(output_dir=output_dir, interval_seconds=60)

        # Verify directory creation
        mock_makedirs.assert_called_once_with(output_dir, exist_ok=True)

        # Verify export was called
        expected_path = "/test/output/pantry_pirate_radio_20230101_120000.sqlite"
        mock_export.assert_called_once_with(output_path=expected_path)

        # Verify sleep was called
        mock_sleep.assert_called_once_with(60)

    @patch("app.datasette.scheduler.time.sleep")
    @patch("app.datasette.scheduler.export_to_sqlite")
    @patch("app.datasette.scheduler.os.makedirs")
    @patch("app.datasette.scheduler.os.symlink")
    @patch("app.datasette.scheduler.os.remove")
    @patch("app.datasette.scheduler.os.path.exists")
    @patch("app.datasette.scheduler.os.path.islink")
    @patch("app.datasette.scheduler.datetime")
    def test_scheduled_export_with_symlink(
        self,
        mock_datetime,
        mock_islink,
        mock_exists,
        mock_remove,
        mock_symlink,
        mock_makedirs,
        mock_export,
        mock_sleep,
    ):
        """Test scheduled export with symlink creation."""
        mock_now = MagicMock()
        mock_now.strftime.return_value = "20230101_120000"
        mock_datetime.now.return_value = mock_now

        # Mock existing symlink
        mock_exists.return_value = True
        mock_islink.return_value = True

        mock_sleep.side_effect = KeyboardInterrupt("Break loop")

        with pytest.raises(KeyboardInterrupt):
            scheduled_export(
                output_dir="/test/output", interval_seconds=60, keep_latest_link=True
            )

        # Verify symlink operations
        mock_remove.assert_called_once_with("/test/output/latest.sqlite")
        mock_symlink.assert_called_once_with(
            "pantry_pirate_radio_20230101_120000.sqlite", "/test/output/latest.sqlite"
        )

    @patch("app.datasette.scheduler.time.sleep")
    @patch("app.datasette.scheduler.export_to_sqlite")
    @patch("app.datasette.scheduler.os.makedirs")
    @patch("app.datasette.scheduler.os.symlink")
    @patch("app.datasette.scheduler.os.remove")
    @patch("app.datasette.scheduler.os.path.exists")
    @patch("app.datasette.scheduler.os.path.islink")
    @patch("app.datasette.scheduler.cleanup_old_exports")
    @patch("app.datasette.scheduler.datetime")
    def test_scheduled_export_with_cleanup(
        self,
        mock_datetime,
        mock_cleanup,
        mock_islink,
        mock_exists,
        mock_remove,
        mock_symlink,
        mock_makedirs,
        mock_export,
        mock_sleep,
    ):
        """Test scheduled export with file cleanup."""
        mock_now = MagicMock()
        mock_now.strftime.return_value = "20230101_120000"
        mock_datetime.now.return_value = mock_now

        # Mock symlink behavior (default is keep_latest_link=True)
        mock_exists.return_value = True
        mock_islink.return_value = True

        mock_sleep.side_effect = KeyboardInterrupt("Break loop")

        with pytest.raises(KeyboardInterrupt):
            scheduled_export(
                output_dir="/test/output", interval_seconds=60, max_files=3
            )

        # Verify cleanup was called (default template has {timestamp})
        mock_cleanup.assert_called_once_with(
            "/test/output", 3, "pantry_pirate_radio_*.sqlite"
        )

    @patch("app.datasette.scheduler.time.sleep")
    @patch("app.datasette.scheduler.export_to_sqlite")
    @patch("app.datasette.scheduler.os.makedirs")
    @patch("app.datasette.scheduler.logger")
    @patch("app.datasette.scheduler.datetime")
    def test_scheduled_export_error_handling(
        self, mock_datetime, mock_logger, mock_makedirs, mock_export, mock_sleep
    ):
        """Test scheduled export error handling."""
        mock_now = MagicMock()
        mock_now.strftime.return_value = "20230101_120000"
        mock_datetime.now.return_value = mock_now

        # Mock export to raise an exception
        mock_export.side_effect = Exception("Export failed")
        mock_sleep.side_effect = KeyboardInterrupt("Break loop")

        with pytest.raises(KeyboardInterrupt):
            scheduled_export(output_dir="/test/output", interval_seconds=60)

        # Verify error was logged
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        assert "Error during scheduled export" in error_call

    @patch("app.datasette.scheduler.time.sleep")
    @patch("app.datasette.scheduler.export_to_sqlite")
    @patch("app.datasette.scheduler.os.makedirs")
    @patch("app.datasette.scheduler.datetime")
    def test_scheduled_export_custom_filename_template(
        self, mock_datetime, mock_makedirs, mock_export, mock_sleep
    ):
        """Test scheduled export with custom filename template."""
        mock_now = MagicMock()
        mock_now.strftime.return_value = "20230101_120000"
        mock_datetime.now.return_value = mock_now

        mock_sleep.side_effect = KeyboardInterrupt("Break loop")

        custom_template = "custom_export_{timestamp}.db"

        with pytest.raises(KeyboardInterrupt):
            scheduled_export(
                output_dir="/test/output", filename_template=custom_template
            )

        # Verify custom filename was used
        expected_path = "/test/output/custom_export_20230101_120000.db"
        mock_export.assert_called_once_with(output_path=expected_path)


class TestCleanupOldExports:
    """Tests for cleanup_old_exports function."""

    def test_cleanup_old_exports_with_temp_files(self):
        """Test cleanup with real temporary files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            test_files = []
            for i in range(5):
                file_path = Path(temp_dir) / f"pantry_pirate_radio_{i:02d}.sqlite"
                file_path.write_text(f"test content {i}")
                test_files.append(file_path)
                # Add small delay to ensure different modification times
                time.sleep(0.01)

            # Keep only 2 files
            cleanup_old_exports(temp_dir, keep_count=2)

            # Check remaining files
            remaining_files = list(Path(temp_dir).glob("pantry_pirate_radio_*.sqlite"))
            assert len(remaining_files) == 2

            # The most recent files should remain (04 and 03)
            remaining_names = [f.name for f in remaining_files]
            assert "pantry_pirate_radio_04.sqlite" in remaining_names
            assert "pantry_pirate_radio_03.sqlite" in remaining_names

    @patch("glob.glob")
    @patch("app.datasette.scheduler.os.path.getmtime")
    @patch("app.datasette.scheduler.os.remove")
    @patch("app.datasette.scheduler.logger")
    def test_cleanup_old_exports_remove_error(
        self, mock_logger, mock_remove, mock_getmtime, mock_glob
    ):
        """Test cleanup handling remove errors."""
        # Mock files
        mock_files = ["/test/file1.sqlite", "/test/file2.sqlite", "/test/file3.sqlite"]
        mock_glob.return_value = mock_files

        # Mock modification times (newest first after sort)
        mock_getmtime.side_effect = [
            1000,
            2000,
            3000,
        ]  # Will be sorted as [3000, 2000, 1000]

        # Mock remove to fail on one file
        mock_remove.side_effect = [None, PermissionError("Permission denied")]

        cleanup_old_exports("/test", keep_count=1)

        # Verify remove was called for files to be deleted (keep newest, remove 2 oldest)
        assert mock_remove.call_count == 2

        # Verify error was logged
        mock_logger.error.assert_called_once()
        error_message = mock_logger.error.call_args[0][0]
        assert "Error removing old file" in error_message

    @patch("glob.glob")
    def test_cleanup_old_exports_no_files(self, mock_glob):
        """Test cleanup when no files match pattern."""
        mock_glob.return_value = []

        # Should not raise any errors
        cleanup_old_exports("/test", keep_count=5)

        mock_glob.assert_called_once_with("/test/pantry_pirate_radio_*.sqlite")

    @patch("glob.glob")
    @patch("app.datasette.scheduler.os.path.getmtime")
    def test_cleanup_old_exports_fewer_files_than_keep_count(
        self, mock_getmtime, mock_glob
    ):
        """Test cleanup when fewer files exist than keep_count."""
        mock_files = ["/test/file1.sqlite", "/test/file2.sqlite"]
        mock_glob.return_value = mock_files
        mock_getmtime.side_effect = [1000, 2000]

        with patch("app.datasette.scheduler.os.remove") as mock_remove:
            cleanup_old_exports("/test", keep_count=5)

            # No files should be removed
            mock_remove.assert_not_called()


class TestGetIntervalFromEnv:
    """Tests for get_interval_from_env function."""

    def test_get_interval_from_env_default(self):
        """Test getting interval with no environment variable."""
        with patch.dict(os.environ, {}, clear=True):
            interval = get_interval_from_env()
            assert interval == 3600

    def test_get_interval_from_env_custom_value(self):
        """Test getting interval with custom environment variable."""
        with patch.dict(os.environ, {"EXPORT_INTERVAL": "7200"}):
            interval = get_interval_from_env()
            assert interval == 7200

    @patch("app.datasette.scheduler.logger")
    def test_get_interval_from_env_invalid_value(self, mock_logger):
        """Test getting interval with invalid environment variable."""
        with patch.dict(os.environ, {"EXPORT_INTERVAL": "invalid"}):
            interval = get_interval_from_env()
            assert interval == 3600  # Should return default

            # Verify warning was logged
            mock_logger.warning.assert_called_once_with(
                "Invalid EXPORT_INTERVAL, using default of 3600 seconds"
            )

    def test_get_interval_from_env_zero_value(self):
        """Test getting interval with zero value."""
        with patch.dict(os.environ, {"EXPORT_INTERVAL": "0"}):
            interval = get_interval_from_env()
            assert interval == 0

    def test_get_interval_from_env_negative_value(self):
        """Test getting interval with negative value."""
        with patch.dict(os.environ, {"EXPORT_INTERVAL": "-1"}):
            interval = get_interval_from_env()
            assert interval == -1
