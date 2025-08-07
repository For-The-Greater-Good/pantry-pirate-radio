"""Tests for datasette/cli.py module."""

import pytest
from unittest.mock import patch, MagicMock, call
from click.testing import CliRunner
import logging

from app.datasette.cli import cli, export


class TestDatasetteCLI:
    """Test cases for the Datasette CLI module."""

    def test_should_export_with_default_options(self):
        """Test export command with default options."""
        runner = CliRunner()

        with patch("app.datasette.cli.export_to_sqlite") as mock_export:
            mock_export.return_value = {"tables": 5, "rows": 1000}

            result = runner.invoke(export)

            assert result.exit_code == 0
            mock_export.assert_called_once_with(
                "pantry_pirate_radio.sqlite", None, 1000
            )
            assert "Export completed:" in result.output

    def test_should_export_with_custom_options(self):
        """Test export command with custom options."""
        runner = CliRunner()

        with patch("app.datasette.cli.export_to_sqlite") as mock_export:
            mock_export.return_value = {"tables": 5, "rows": 1000}

            result = runner.invoke(
                export,
                [
                    "--output",
                    "custom.sqlite",
                    "--tables",
                    "organization",
                    "--tables",
                    "location",
                    "--batch-size",
                    "500",
                    "--verbose",
                ],
            )

            assert result.exit_code == 0
            mock_export.assert_called_once_with(
                "custom.sqlite", ["organization", "location"], 500
            )
            assert "Export completed:" in result.output

    def test_should_configure_logging_with_verbose_flag(self):
        """Test verbose logging configuration."""
        runner = CliRunner()

        with patch("app.datasette.cli.export_to_sqlite") as mock_export:
            mock_export.return_value = {"tables": 5, "rows": 1000}

            with patch("app.datasette.cli.logging.basicConfig") as mock_config:
                result = runner.invoke(export, ["--verbose"])

                assert result.exit_code == 0
                mock_config.assert_called_once()
                # Check that logging level is INFO for verbose
                assert mock_config.call_args[1]["level"] == logging.INFO

    def test_should_configure_logging_without_verbose_flag(self):
        """Test standard logging configuration."""
        runner = CliRunner()

        with patch("app.datasette.cli.export_to_sqlite") as mock_export:
            mock_export.return_value = {"tables": 5, "rows": 1000}

            with patch("app.datasette.cli.logging.basicConfig") as mock_config:
                result = runner.invoke(export)

                assert result.exit_code == 0
                mock_config.assert_called_once()
                # Check that logging level is WARNING for non-verbose
                assert mock_config.call_args[1]["level"] == logging.WARNING

    def test_should_run_cli_when_executed_directly(self):
        """Test CLI execution when module is run directly."""
        # Test that the module can be imported and has the expected attributes

        assert hasattr(app.datasette.cli, "cli")
        assert hasattr(app.datasette.cli, "export")
        # schedule should no longer exist
        assert not hasattr(app.datasette.cli, "schedule")

    def test_should_show_help_for_cli_group(self):
        """Test help display for main CLI group."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "PostgreSQL to SQLite exporter for Datasette" in result.output
        assert "export" in result.output
        # schedule should no longer be in help
        assert "schedule" not in result.output


# Import for the __name__ test
import app.datasette.cli
