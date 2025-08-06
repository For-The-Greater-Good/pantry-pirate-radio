"""Tests for app/content_store/__main__.py module."""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from io import StringIO

import pytest

from app.content_store.__main__ import main
from app.content_store.monitor import ContentStoreMonitor
from app.content_store.store import ContentStore


class TestContentStoreMain:
    """Test the main function and CLI interface."""

    @pytest.fixture
    def mock_content_store(self):
        """Create a mock content store."""
        return Mock(spec=ContentStore)

    @pytest.fixture
    def mock_monitor(self):
        """Create a mock content store monitor."""
        monitor = Mock(spec=ContentStoreMonitor)
        monitor.get_recent_activity.return_value = {
            "submissions_24h": 150,
            "processed_24h": 145,
        }
        monitor.find_duplicates.return_value = {}
        monitor.get_storage_efficiency.return_value = {
            "total_submissions": 1000,
            "unique_content": 850,
            "duplicates_avoided": 150,
            "deduplication_rate": 0.15,
            "space_saved_percentage": 12.5,
        }
        monitor.get_statistics.return_value = {
            "total_content": 850,
            "processed_content": 800,
            "pending_content": 50,
            "processing_rate": 0.94,
            "store_size_mb": 256.75,
        }
        monitor.get_processing_timeline.return_value = [
            {"date": "2024-01-01", "total": 100, "processed": 95, "pending": 5},
            {"date": "2024-01-02", "total": 120, "processed": 115, "pending": 5},
        ]
        return monitor

    @patch("app.content_store.__main__.get_content_store")
    def test_main_no_content_store_configured(self, mock_get_store, capsys):
        """Test main when no content store is configured."""
        mock_get_store.return_value = None

        with patch("sys.argv", ["__main__.py", "status"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Error: Content store not configured" in captured.err
        assert "Set CONTENT_STORE_PATH environment variable" in captured.err

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_status_basic(
        self,
        mock_get_store,
        mock_monitor_class,
        mock_content_store,
        mock_monitor,
        capsys,
    ):
        """Test status command basic functionality."""
        mock_get_store.return_value = mock_content_store
        mock_monitor_class.return_value = mock_monitor

        with patch("sys.argv", ["__main__.py", "status"]):
            main()

        mock_monitor_class.assert_called_once_with(mock_content_store)
        mock_monitor.print_summary.assert_called_once()
        mock_monitor.get_recent_activity.assert_not_called()

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_status_detailed(
        self,
        mock_get_store,
        mock_monitor_class,
        mock_content_store,
        mock_monitor,
        capsys,
    ):
        """Test status command with detailed flag."""
        mock_get_store.return_value = mock_content_store
        mock_monitor_class.return_value = mock_monitor

        with patch("sys.argv", ["__main__.py", "status", "--detailed"]):
            main()

        mock_monitor.print_summary.assert_called_once()
        mock_monitor.get_recent_activity.assert_called_once()

        captured = capsys.readouterr()
        assert "=== Recent Activity (24h) ===" in captured.out
        assert "Submissions: 150" in captured.out
        assert "Processed: 145" in captured.out

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_report_default_output(
        self,
        mock_get_store,
        mock_monitor_class,
        mock_content_store,
        mock_monitor,
        capsys,
    ):
        """Test report command with default output."""
        mock_get_store.return_value = mock_content_store
        mock_monitor_class.return_value = mock_monitor

        with patch("sys.argv", ["__main__.py", "report"]):
            main()

        mock_monitor.export_report.assert_called_once()
        # Check that it was called with a Path object
        call_args = mock_monitor.export_report.call_args[0][0]
        assert isinstance(call_args, Path)
        assert call_args.name == "content_store_report.json"

        mock_monitor.print_summary.assert_called_once()

        captured = capsys.readouterr()
        assert "Report saved to:" in captured.out

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_report_custom_output(
        self,
        mock_get_store,
        mock_monitor_class,
        mock_content_store,
        mock_monitor,
        capsys,
    ):
        """Test report command with custom output file."""
        mock_get_store.return_value = mock_content_store
        mock_monitor_class.return_value = mock_monitor

        with patch(
            "sys.argv", ["__main__.py", "report", "--output", "custom_report.json"]
        ):
            main()

        mock_monitor.export_report.assert_called_once()
        call_args = mock_monitor.export_report.call_args[0][0]
        assert isinstance(call_args, Path)
        assert call_args.name == "custom_report.json"

        captured = capsys.readouterr()
        assert "custom_report.json" in captured.out

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_report_short_flag(
        self, mock_get_store, mock_monitor_class, mock_content_store, mock_monitor
    ):
        """Test report command with short output flag."""
        mock_get_store.return_value = mock_content_store
        mock_monitor_class.return_value = mock_monitor

        with patch("sys.argv", ["__main__.py", "report", "-o", "short_report.json"]):
            main()

        call_args = mock_monitor.export_report.call_args[0][0]
        assert call_args.name == "short_report.json"

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_duplicates_none_found(
        self,
        mock_get_store,
        mock_monitor_class,
        mock_content_store,
        mock_monitor,
        capsys,
    ):
        """Test duplicates command when no duplicates found."""
        mock_get_store.return_value = mock_content_store
        mock_monitor_class.return_value = mock_monitor
        mock_monitor.find_duplicates.return_value = {}

        with patch("sys.argv", ["__main__.py", "duplicates"]):
            main()

        mock_monitor.find_duplicates.assert_called_once()

        captured = capsys.readouterr()
        assert "No duplicate content found" in captured.out

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_duplicates_found(
        self,
        mock_get_store,
        mock_monitor_class,
        mock_content_store,
        mock_monitor,
        capsys,
    ):
        """Test duplicates command when duplicates are found."""
        mock_get_store.return_value = mock_content_store
        mock_monitor_class.return_value = mock_monitor

        mock_duplicates = {
            "hash123456789abcdef": {
                "count": 3,
                "sources": ["scraper1", "scraper2"],
                "first_seen": "2024-01-01T12:00:00Z",
            },
            "hash987654321fedcba": {
                "count": 2,
                "sources": ["scraper3"],
                "first_seen": "2024-01-02T10:30:00Z",
            },
        }
        mock_monitor.find_duplicates.return_value = mock_duplicates

        with patch("sys.argv", ["__main__.py", "duplicates"]):
            main()

        captured = capsys.readouterr()
        assert "=== Duplicate Content (2 found) ===" in captured.out
        assert "Hash: hash123456789abc..." in captured.out
        assert "Count: 3" in captured.out
        assert "Sources: scraper1, scraper2" in captured.out
        assert "First seen: 2024-01-01T12:00:00Z" in captured.out

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_duplicates_with_limit(
        self,
        mock_get_store,
        mock_monitor_class,
        mock_content_store,
        mock_monitor,
        capsys,
    ):
        """Test duplicates command with custom limit."""
        mock_get_store.return_value = mock_content_store
        mock_monitor_class.return_value = mock_monitor

        # Create more duplicates than the limit
        mock_duplicates = {
            f"hash{i}": {
                "count": 10 - i,
                "sources": [f"scraper{i}"],
                "first_seen": f"2024-01-0{i}",
            }
            for i in range(1, 6)  # 5 duplicates
        }
        mock_monitor.find_duplicates.return_value = mock_duplicates

        with patch("sys.argv", ["__main__.py", "duplicates", "--limit", "2"]):
            main()

        captured = capsys.readouterr()
        # Should show the top 2 by count (hash1 with count 9, hash2 with count 8)
        assert captured.out.count("Hash: hash") == 2
        assert "Count: 9" in captured.out
        assert "Count: 8" in captured.out

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_efficiency(
        self,
        mock_get_store,
        mock_monitor_class,
        mock_content_store,
        mock_monitor,
        capsys,
    ):
        """Test efficiency command."""
        mock_get_store.return_value = mock_content_store
        mock_monitor_class.return_value = mock_monitor

        with patch("sys.argv", ["__main__.py", "efficiency"]):
            main()

        mock_monitor.get_storage_efficiency.assert_called_once()

        captured = capsys.readouterr()
        assert "=== Storage Efficiency ===" in captured.out
        assert "Total Submissions: 1,000" in captured.out
        assert "Unique Content: 850" in captured.out
        assert "Duplicates Avoided: 150" in captured.out
        assert "Deduplication Rate: 15.0%" in captured.out
        assert "Space Saved: 12.5%" in captured.out

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_stats_default_days(
        self,
        mock_get_store,
        mock_monitor_class,
        mock_content_store,
        mock_monitor,
        capsys,
    ):
        """Test stats command with default days."""
        mock_get_store.return_value = mock_content_store
        mock_monitor_class.return_value = mock_monitor

        with patch("sys.argv", ["__main__.py", "stats"]):
            main()

        mock_monitor.get_statistics.assert_called_once()
        mock_monitor.get_processing_timeline.assert_called_once_with(days=7)

        captured = capsys.readouterr()
        assert "=== Detailed Statistics ===" in captured.out
        assert "Total Content: 850" in captured.out
        assert "Processed: 800" in captured.out
        assert "Pending: 50" in captured.out
        assert "Processing Rate: 94.0%" in captured.out
        assert "Store Size: 256.75 MB" in captured.out

        assert "=== Processing Timeline (Last 7 days) ===" in captured.out
        assert "2024-01-01: 100 total, 95 processed, 5 pending" in captured.out
        assert "2024-01-02: 120 total, 115 processed, 5 pending" in captured.out

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_stats_custom_days(
        self,
        mock_get_store,
        mock_monitor_class,
        mock_content_store,
        mock_monitor,
        capsys,
    ):
        """Test stats command with custom days."""
        mock_get_store.return_value = mock_content_store
        mock_monitor_class.return_value = mock_monitor

        with patch("sys.argv", ["__main__.py", "stats", "--days", "14"]):
            main()

        mock_monitor.get_processing_timeline.assert_called_once_with(days=14)

        captured = capsys.readouterr()
        assert "=== Processing Timeline (Last 14 days) ===" in captured.out

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_dashboard_default_settings(
        self,
        mock_get_store,
        mock_monitor_class,
        mock_content_store,
        mock_monitor,
        capsys,
    ):
        """Test dashboard command with default settings."""
        mock_get_store.return_value = mock_content_store
        mock_monitor_class.return_value = mock_monitor

        # Mock the Flask app
        mock_app = Mock()

        with patch("sys.argv", ["__main__.py", "dashboard"]):
            with patch("app.content_store.dashboard.app", mock_app):
                main()

        mock_app.run.assert_called_once_with(host="127.0.0.1", port=5050, debug=False)

        captured = capsys.readouterr()
        assert (
            "Starting Content Store Dashboard on http://127.0.0.1:5050" in captured.out
        )
        assert "Access the dashboard at http://localhost:5050" in captured.out

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_dashboard_custom_host_port(
        self,
        mock_get_store,
        mock_monitor_class,
        mock_content_store,
        mock_monitor,
        capsys,
    ):
        """Test dashboard command with custom host and port."""
        mock_get_store.return_value = mock_content_store
        mock_monitor_class.return_value = mock_monitor

        mock_app = Mock()

        with patch(
            "sys.argv",
            ["__main__.py", "dashboard", "--host", "localhost", "--port", "8080"],
        ):
            with patch("app.content_store.dashboard.app", mock_app):
                main()

        mock_app.run.assert_called_once_with(host="localhost", port=8080, debug=False)

        captured = capsys.readouterr()
        assert "Starting Content Store Dashboard on http://localhost:8080" in captured.out

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_no_command(
        self,
        mock_get_store,
        mock_monitor_class,
        mock_content_store,
        mock_monitor,
        capsys,
    ):
        """Test main with no command - should show help."""
        mock_get_store.return_value = mock_content_store
        mock_monitor_class.return_value = mock_monitor

        with patch("sys.argv", ["__main__.py"]):
            main()

        captured = capsys.readouterr()
        assert "usage:" in captured.out
        assert "Content Store Management Tool" in captured.out

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_unknown_command(
        self,
        mock_get_store,
        mock_monitor_class,
        mock_content_store,
        mock_monitor,
        capsys,
    ):
        """Test main with unknown command - should exit with error."""
        mock_get_store.return_value = mock_content_store
        mock_monitor_class.return_value = mock_monitor

        with patch("sys.argv", ["__main__.py", "unknown"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 2  # argparse error exit code

        captured = capsys.readouterr()
        assert "invalid choice: 'unknown'" in captured.err

    @patch("app.content_store.__main__.get_content_store")
    def test_main_help_message(self, mock_get_store, capsys):
        """Test that help message contains expected commands and examples."""
        mock_get_store.return_value = Mock(spec=ContentStore)

        with patch("sys.argv", ["__main__.py", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "Content Store Management Tool" in captured.out
        assert "python -m app.content_store status" in captured.out
        assert "python -m app.content_store report --output report.json" in captured.out
        assert "python -m app.content_store duplicates" in captured.out
        assert "python -m app.content_store efficiency" in captured.out

    def test_argument_parser_creation(self):
        """Test that argument parser is created correctly."""
        # This tests the parser structure without executing main()
        with patch("app.content_store.__main__.get_content_store") as mock_get_store:
            mock_get_store.return_value = None

            # Test that parser handles various command combinations
            test_cases = [
                ["status"],
                ["status", "--detailed"],
                ["report"],
                ["report", "--output", "test.json"],
                ["report", "-o", "test.json"],
                ["duplicates"],
                ["duplicates", "--limit", "5"],
                ["efficiency"],
                ["stats"],
                ["stats", "--days", "30"],
                ["dashboard"],
                ["dashboard", "--host", "localhost"],
                ["dashboard", "--port", "3000"],
                ["dashboard", "--host", "localhost", "--port", "8000"],
            ]

            for args in test_cases:
                with patch("sys.argv", ["__main__.py", *args]):
                    # Should not raise ArgumentParser errors
                    try:
                        main()
                    except SystemExit as e:
                        # SystemExit with code 1 is expected due to no content store
                        assert e.code == 1

    @patch("app.content_store.__main__.ContentStoreMonitor")
    @patch("app.content_store.__main__.get_content_store")
    def test_main_error_handling_in_monitor_calls(
        self, mock_get_store, mock_monitor_class, mock_content_store
    ):
        """Test error handling when monitor methods raise exceptions."""
        mock_get_store.return_value = mock_content_store
        mock_monitor = Mock(spec=ContentStoreMonitor)
        mock_monitor.print_summary.side_effect = Exception("Monitor error")
        mock_monitor_class.return_value = mock_monitor

        with patch("sys.argv", ["__main__.py", "status"]):
            # Should propagate the exception (no explicit error handling in main)
            with pytest.raises(Exception, match="Monitor error"):
                main()


class TestMainEntryPoint:
    """Test the module entry point."""

    def test_main_entry_point_structure(self):
        """Test that the module has the correct entry point structure."""
        # Read the module source to verify it has the correct pattern
        import app.content_store.__main__ as main_module
        import inspect

        # Check that main function exists
        assert hasattr(main_module, "main")
        assert callable(main_module.main)

        # Check the source contains the if __name__ == "__main__" pattern
        source = inspect.getsource(main_module)
        assert 'if __name__ == "__main__":' in source
        assert "main()" in source


if __name__ == "__main__":
    # Test the module entry point pattern
    pytest.main([__file__])

