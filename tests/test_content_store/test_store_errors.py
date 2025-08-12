"""Tests for content store error handling to achieve 100% coverage."""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.content_store.store import ContentStore


def test_stats_handles_file_system_error():
    """Test that get_statistics() handles file system errors gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a content store instance
        store = ContentStore(Path(tmpdir))

        # Mock database query to return some content counts
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (2, 1, 1)  # total, processed, pending

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=None)

        with patch("sqlite3.connect", return_value=mock_conn):
            # Mock rglob to raise an exception when accessing files
            with patch.object(Path, "rglob") as mock_rglob:
                mock_rglob.side_effect = PermissionError("Access denied")

                # Call get_statistics - should handle the error
                result = store.get_statistics()

                # Verify it returns stats with store_size = 0
                assert result["total_content"] == 2
                assert result["processed_content"] == 1
                assert result["pending_content"] == 1
                assert (
                    result["store_size_bytes"] == 0
                )  # Failed to get size, defaulted to 0


def test_stats_handles_os_error():
    """Test that get_statistics() handles OS errors when calculating file sizes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ContentStore(Path(tmpdir))

        # Mock database query
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1, 1, 0)  # total, processed, pending

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=None)

        with patch("sqlite3.connect", return_value=mock_conn):
            # Mock rglob to return files but stat() fails
            mock_file = MagicMock()
            mock_file.stat.side_effect = OSError("File not found")

            with patch.object(Path, "rglob", return_value=[mock_file]):
                result = store.get_statistics()

                # Should handle the error and default to 0
                assert result["store_size_bytes"] == 0
                assert result["total_content"] == 1
