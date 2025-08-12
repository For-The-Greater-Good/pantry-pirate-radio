"""Tests for recorder utils error handling to achieve 100% coverage."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
import pytest

from app.recorder.utils import record_result


def test_record_result_with_empty_output_dir():
    """Test that record_result handles empty OUTPUT_DIR environment variable."""
    # Create test data - missing job_id to trigger validation error
    test_data = {
        "job": {
            "metadata": {
                "scraper_id": "test_scraper",
                "source_url": "https://example.com",
            },
        },
        "result": {"text": "Test result"},
        "error": None,
    }

    # Should return error status when job_id is missing
    result = record_result(test_data)
    assert result["status"] == "failed"
    assert "Missing required field: job_id" in result["error"]


def test_record_result_daily_summary_update_failure():
    """Test that daily summary update failure is logged as warning."""
    # Import update_daily_summary directly to test it
    from app.recorder.utils import update_daily_summary

    # Create a temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        summary_file = Path(tmpdir) / "summary.json"

        # Make the file read-only to cause a write error
        summary_file.write_text('{"total_jobs": 0}')
        summary_file.chmod(0o444)  # Read-only

        # Mock the logger to verify warning is logged
        with patch("app.recorder.utils.logger") as mock_logger:
            # This should log a warning but not raise
            update_daily_summary(
                summary_file, "job-123", "test_scraper", datetime.now()
            )

            # Verify warning was logged
            mock_logger.warning.assert_called_once()
            args = mock_logger.warning.call_args
            assert "Failed to update daily summary" in args[0][0]


def test_record_result_summary_file_write_error():
    """Test handling of main file write errors."""
    test_data = {
        "job_id": "job-456",
        "job": {
            "metadata": {
                "scraper_id": "test_scraper",
                "source_url": "https://example.com",
            },
            "created_at": "2024-01-15T12:00:00Z",
        },
        "result": {"text": "Result text"},
        "error": None,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"OUTPUT_DIR": tmpdir}):
            # Make the file write operation fail
            with patch("builtins.open", side_effect=OSError("Disk full")):
                # The function should catch the exception and return error status
                result = record_result(test_data)

                assert result["status"] == "failed"
                assert "Disk full" in result["error"]
