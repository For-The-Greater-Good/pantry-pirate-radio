"""Tests for content store CLI commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import click
import pytest
from click.testing import CliRunner

from app.content_store.cli import cli, dashboard, inspect, status


class TestCLICommands:
    """Test CLI commands for content store."""

    def test_cli_group(self):
        """Test the main CLI group."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Content store management commands" in result.output

    @patch("app.content_store.ContentStore")
    def test_status_command(self, mock_content_store_class):
        """Test status command displays store statistics."""
        # Setup mock
        mock_store = MagicMock()
        mock_store.get_statistics.return_value = {
            "total_content": 100,
            "processed_content": 75,
            "pending_content": 25,
            "store_size_bytes": 1024 * 1024 * 50,  # 50 MB
        }
        mock_content_store_class.return_value = mock_store

        # Run command
        runner = CliRunner()
        result = runner.invoke(status)

        # Verify
        assert result.exit_code == 0
        assert "Content Store Status:" in result.output
        assert "Total entries: 100" in result.output
        assert "Completed: 75" in result.output
        assert "Pending: 25" in result.output
        assert "Store size: 50.00 MB" in result.output
        mock_content_store_class.assert_called_once_with(Path("/data-repo"))
        mock_store.get_statistics.assert_called_once()

    @patch("app.content_store.ContentStore")
    def test_status_command_empty_store(self, mock_content_store_class):
        """Test status command with empty store."""
        # Setup mock
        mock_store = MagicMock()
        mock_store.get_statistics.return_value = {
            "total_content": 0,
            "processed_content": 0,
            "pending_content": 0,
            "store_size_bytes": 0,
        }
        mock_content_store_class.return_value = mock_store

        # Run command
        runner = CliRunner()
        result = runner.invoke(status)

        # Verify
        assert result.exit_code == 0
        assert "Total entries: 0" in result.output
        assert "Store size: 0.00 MB" in result.output

    @patch("app.content_store.dashboard.app")
    def test_dashboard_command_default(self, mock_app):
        """Test dashboard command with default options."""
        runner = CliRunner()
        result = runner.invoke(dashboard)

        # Verify
        assert result.exit_code == 0
        assert (
            "Starting Content Store Dashboard on http://127.0.0.1:5050" in result.output
        )
        assert "Access the dashboard at http://localhost:5050" in result.output
        mock_app.run.assert_called_once_with(host="127.0.0.1", port=5050, debug=False)

    @patch("app.content_store.dashboard.app")
    def test_dashboard_command_custom_host_port(self, mock_app):
        """Test dashboard command with custom host and port."""
        runner = CliRunner()
        result = runner.invoke(dashboard, ["--host", "127.0.0.1", "--port", "8080"])

        # Verify
        assert result.exit_code == 0
        assert (
            "Starting Content Store Dashboard on http://127.0.0.1:8080" in result.output
        )
        mock_app.run.assert_called_once_with(host="127.0.0.1", port=8080, debug=False)

    @patch("app.content_store.ContentStore")
    def test_inspect_command_valid_hash(self, mock_content_store_class):
        """Test inspect command with valid content hash."""
        # Setup mock
        mock_store = MagicMock()
        mock_store.has_content.return_value = True
        mock_store.get_result.return_value = '{"status": "completed", "data": "test"}'

        # Mock the content path
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = json.dumps(
            {
                "timestamp": "2024-01-01T00:00:00",
                "metadata": {"source": "test"},
                "content": "This is a test content that is longer than 200 characters"
                * 5,
            }
        )
        mock_store._get_content_path.return_value = mock_path

        mock_content_store_class.return_value = mock_store

        # Run command
        runner = CliRunner()
        result = runner.invoke(inspect, ["abc123def456"])

        # Verify
        assert result.exit_code == 0
        assert "Content Hash: abc123def456" in result.output
        assert "Content:" in result.output
        assert "Stored at: 2024-01-01T00:00:00" in result.output
        assert "Result:" in result.output
        assert "Status: Completed" in result.output
        mock_store._validate_hash.assert_called_once_with("abc123def456")
        mock_store.has_content.assert_called_once_with("abc123def456")

    @patch("app.content_store.ContentStore")
    def test_inspect_command_invalid_hash(self, mock_content_store_class):
        """Test inspect command with invalid hash format."""
        # Setup mock
        mock_store = MagicMock()
        mock_store._validate_hash.side_effect = ValueError("Invalid hash format")
        mock_content_store_class.return_value = mock_store

        # Run command
        runner = CliRunner()
        result = runner.invoke(inspect, ["invalid"])

        # Verify
        assert result.exit_code == 0
        assert "Error: Invalid hash format" in result.output
        mock_store._validate_hash.assert_called_once_with("invalid")
        mock_store.has_content.assert_not_called()

    @patch("app.content_store.ContentStore")
    def test_inspect_command_hash_not_found(self, mock_content_store_class):
        """Test inspect command when hash doesn't exist."""
        # Setup mock
        mock_store = MagicMock()
        mock_store.has_content.return_value = False
        mock_content_store_class.return_value = mock_store

        # Run command
        runner = CliRunner()
        result = runner.invoke(inspect, ["abc123def456"])

        # Verify
        assert result.exit_code == 0
        assert "Content hash abc123def456 not found in store" in result.output
        mock_store.has_content.assert_called_once_with("abc123def456")

    @patch("app.content_store.ContentStore")
    def test_inspect_command_pending_result(self, mock_content_store_class):
        """Test inspect command with pending result."""
        # Setup mock
        mock_store = MagicMock()
        mock_store.has_content.return_value = True
        mock_store.get_result.return_value = None  # No result yet
        mock_store.get_job_id.return_value = "job-123"

        # Mock the content path
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = json.dumps(
            {
                "timestamp": "2024-01-01T00:00:00",
                "metadata": {},
                "content": "Test content",
            }
        )
        mock_store._get_content_path.return_value = mock_path

        mock_content_store_class.return_value = mock_store

        # Run command
        runner = CliRunner()
        result = runner.invoke(inspect, ["abc123def456"])

        # Verify
        assert result.exit_code == 0
        assert "Result: Not yet processed" in result.output
        assert "Job ID: job-123" in result.output
        mock_store.get_result.assert_called_once_with("abc123def456")
        mock_store.get_job_id.assert_called_once_with("abc123def456")

    @patch("app.content_store.ContentStore")
    def test_inspect_command_no_content_file(self, mock_content_store_class):
        """Test inspect command when content file doesn't exist."""
        # Setup mock
        mock_store = MagicMock()
        mock_store.has_content.return_value = True
        mock_store.get_result.return_value = None
        mock_store.get_job_id.return_value = None

        # Mock the content path
        mock_path = MagicMock()
        mock_path.exists.return_value = False  # File doesn't exist
        mock_store._get_content_path.return_value = mock_path

        mock_content_store_class.return_value = mock_store

        # Run command
        runner = CliRunner()
        result = runner.invoke(inspect, ["abc123def456"])

        # Verify
        assert result.exit_code == 0
        assert "Content Hash: abc123def456" in result.output
        # Content section should not be printed
        assert "Stored at:" not in result.output
        assert "Result: Not yet processed" in result.output

    def test_cli_subcommands_exist(self):
        """Test that all expected subcommands are registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "dashboard" in result.output
        assert "inspect" in result.output
        assert "status" in result.output
