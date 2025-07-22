"""Tests for datasette/cli.py module."""

import pytest
from unittest.mock import patch, MagicMock, call
from click.testing import CliRunner
import logging

from app.datasette.cli import cli, export, schedule


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
            mock_export.return_value = {"tables": 3, "rows": 500}

            result = runner.invoke(
                export,
                [
                    "--output",
                    "custom.sqlite",
                    "--tables",
                    "organizations",
                    "--tables",
                    "locations",
                    "--batch-size",
                    "500",
                    "--verbose",
                ],
            )

            assert result.exit_code == 0
            mock_export.assert_called_once_with(
                "custom.sqlite", ["organizations", "locations"], 500
            )
            assert "Export completed:" in result.output

    def test_should_configure_verbose_logging_for_export(self):
        """Test verbose logging configuration for export command."""
        runner = CliRunner()

        with patch("app.datasette.cli.export_to_sqlite"):
            with patch("app.datasette.cli.logging.basicConfig") as mock_logging:
                result = runner.invoke(export, ["--verbose"])

                assert result.exit_code == 0
                mock_logging.assert_called_once()
                assert mock_logging.call_args[1]["level"] == logging.INFO

    def test_should_configure_quiet_logging_for_export(self):
        """Test quiet logging configuration for export command."""
        runner = CliRunner()

        with patch("app.datasette.cli.export_to_sqlite"):
            with patch("app.datasette.cli.logging.basicConfig") as mock_logging:
                result = runner.invoke(export)

                assert result.exit_code == 0
                mock_logging.assert_called_once()
                assert mock_logging.call_args[1]["level"] == logging.WARNING

    def test_should_schedule_with_default_options(self):
        """Test schedule command with default options."""
        runner = CliRunner()

        with patch("app.datasette.cli.get_interval_from_env") as mock_get_interval:
            mock_get_interval.return_value = 3600

            with patch("app.datasette.cli.scheduled_export") as mock_scheduled:
                result = runner.invoke(schedule)

                assert result.exit_code == 0
                mock_get_interval.assert_called_once()
                mock_scheduled.assert_called_once_with(
                    output_dir="/data",
                    interval_seconds=3600,
                    filename_template="pantry_pirate_radio_{timestamp}.sqlite",
                    keep_latest_link=True,
                    max_files=5,
                )
                assert (
                    "Starting scheduled export with 3600 second interval"
                    in result.output
                )

    def test_should_schedule_with_custom_options(self):
        """Test schedule command with custom options."""
        runner = CliRunner()

        with patch("app.datasette.cli.scheduled_export") as mock_scheduled:
            result = runner.invoke(
                schedule,
                [
                    "--output-dir",
                    "/custom/path",
                    "--interval",
                    "1800",
                    "--filename-template",
                    "export_{timestamp}.db",
                    "--no-keep-latest",
                    "--max-files",
                    "10",
                    "--verbose",
                ],
            )

            assert result.exit_code == 0
            mock_scheduled.assert_called_once_with(
                output_dir="/custom/path",
                interval_seconds=1800,
                filename_template="export_{timestamp}.db",
                keep_latest_link=False,
                max_files=10,
            )
            assert (
                "Starting scheduled export with 1800 second interval" in result.output
            )
            assert "Keeping latest link: False" in result.output

    def test_should_handle_unlimited_files(self):
        """Test schedule command with unlimited file retention."""
        runner = CliRunner()

        with patch("app.datasette.cli.get_interval_from_env") as mock_get_interval:
            mock_get_interval.return_value = 3600

            with patch("app.datasette.cli.scheduled_export") as mock_scheduled:
                result = runner.invoke(schedule, ["--max-files", "0"])

                assert result.exit_code == 0
                mock_scheduled.assert_called_once()
                # When max_files is 0, it should pass None
                assert mock_scheduled.call_args[1]["max_files"] is None
                assert "Maximum files to keep: unlimited" in result.output

    def test_should_use_environment_interval_when_not_specified(self):
        """Test that schedule uses environment variable for interval when not specified."""
        runner = CliRunner()

        with patch("app.datasette.cli.get_interval_from_env") as mock_get_interval:
            mock_get_interval.return_value = 7200

            with patch("app.datasette.cli.scheduled_export") as mock_scheduled:
                result = runner.invoke(schedule)

                assert result.exit_code == 0
                mock_get_interval.assert_called_once()
                assert mock_scheduled.call_args[1]["interval_seconds"] == 7200

    def test_should_override_environment_interval_when_specified(self):
        """Test that command line interval overrides environment variable."""
        runner = CliRunner()

        with patch("app.datasette.cli.get_interval_from_env") as mock_get_interval:
            with patch("app.datasette.cli.scheduled_export") as mock_scheduled:
                result = runner.invoke(schedule, ["--interval", "900"])

                assert result.exit_code == 0
                # Should not call get_interval_from_env when interval is specified
                mock_get_interval.assert_not_called()
                assert mock_scheduled.call_args[1]["interval_seconds"] == 900

    def test_should_run_cli_when_executed_directly(self):
        """Test CLI execution when module is run directly."""
        # Test that the module can be imported and has the expected attributes

        assert hasattr(app.datasette.cli, "cli")
        assert hasattr(app.datasette.cli, "export")
        assert hasattr(app.datasette.cli, "schedule")

    def test_should_show_help_for_cli_group(self):
        """Test help display for main CLI group."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "PostgreSQL to SQLite exporter for Datasette" in result.output
        assert "export" in result.output
        assert "schedule" in result.output


# Import for the __name__ test
import app.datasette.cli
