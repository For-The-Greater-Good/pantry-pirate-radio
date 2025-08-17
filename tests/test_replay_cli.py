"""Tests for replay CLI interface."""

import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.replay.__main__ import main


class TestReplayCLI:
    """Test cases for the replay CLI."""

    @patch("app.replay.__main__.replay_file")
    def test_should_process_single_file_when_file_option_provided(
        self, mock_replay_file: Mock, tmp_path: Path
    ) -> None:
        """Test processing a single file with --file option."""
        # Arrange
        test_file = tmp_path / "test.json"
        test_file.write_text("{}")
        mock_replay_file.return_value = True

        # Act
        with patch.object(sys, "argv", ["replay", "--file", str(test_file)]):
            exit_code = main()

        # Assert
        assert exit_code == 0
        mock_replay_file.assert_called_once_with(
            str(test_file), dry_run=False, skip_validation=False
        )

    def test_should_return_error_when_file_not_found(self) -> None:
        """Test error handling for missing file."""
        # Act
        with patch.object(sys, "argv", ["replay", "--file", "/nonexistent.json"]):
            exit_code = main()

        # Assert
        assert exit_code == 1

    @patch("app.replay.__main__.replay_directory")
    def test_should_process_directory_when_directory_option_provided(
        self, mock_replay_directory: Mock, tmp_path: Path
    ) -> None:
        """Test processing a directory with --directory option."""
        # Arrange
        mock_replay_directory.return_value = {
            "total_files": 5,
            "successful": 5,
            "failed": 0,
        }

        # Act
        with patch.object(sys, "argv", ["replay", "--directory", str(tmp_path)]):
            exit_code = main()

        # Assert
        assert exit_code == 0
        mock_replay_directory.assert_called_once_with(
            str(tmp_path), pattern="*.json", dry_run=False, skip_validation=False
        )

    @patch("app.replay.__main__.replay_directory")
    def test_should_use_custom_pattern_when_provided(
        self, mock_replay_directory: Mock, tmp_path: Path
    ) -> None:
        """Test custom pattern option."""
        # Arrange
        mock_replay_directory.return_value = {
            "total_files": 3,
            "successful": 3,
            "failed": 0,
        }

        # Act
        with patch.object(
            sys,
            "argv",
            ["replay", "--directory", str(tmp_path), "--pattern", "job_*.json"],
        ):
            exit_code = main()

        # Assert
        assert exit_code == 0
        mock_replay_directory.assert_called_once_with(
            str(tmp_path), pattern="job_*.json", dry_run=False, skip_validation=False
        )

    @patch("app.replay.__main__.replay_file")
    def test_should_enable_dry_run_when_option_provided(
        self, mock_replay_file: Mock, tmp_path: Path
    ) -> None:
        """Test dry run option."""
        # Arrange
        test_file = tmp_path / "test.json"
        test_file.write_text("{}")
        mock_replay_file.return_value = True

        # Act
        with patch.object(
            sys, "argv", ["replay", "--file", str(test_file), "--dry-run"]
        ):
            exit_code = main()

        # Assert
        assert exit_code == 0
        mock_replay_file.assert_called_once_with(
            str(test_file), dry_run=True, skip_validation=False
        )

    @patch("app.replay.__main__.replay_directory")
    def test_should_return_error_when_files_fail(
        self, mock_replay_directory: Mock, tmp_path: Path
    ) -> None:
        """Test exit code when some files fail."""
        # Arrange
        mock_replay_directory.return_value = {
            "total_files": 5,
            "successful": 3,
            "failed": 2,
        }

        # Act
        with patch.object(sys, "argv", ["replay", "--directory", str(tmp_path)]):
            exit_code = main()

        # Assert
        assert exit_code == 1

    @patch("app.replay.__main__.replay_directory")
    @patch.dict(os.environ, {"OUTPUT_DIR": "test_output"})
    def test_should_use_default_output_dir_when_option_provided(
        self, mock_replay_directory: Mock, tmp_path: Path
    ) -> None:
        """Test --use-default-output-dir option."""
        # Arrange
        output_dir = tmp_path / "test_output"
        output_dir.mkdir()
        mock_replay_directory.return_value = {
            "total_files": 2,
            "successful": 2,
            "failed": 0,
        }

        # Act
        with patch.dict(os.environ, {"OUTPUT_DIR": str(output_dir)}):
            with patch.object(sys, "argv", ["replay", "--use-default-output-dir"]):
                exit_code = main()

        # Assert
        assert exit_code == 0
        mock_replay_directory.assert_called_once_with(
            str(output_dir), pattern="*.json", dry_run=False, skip_validation=False
        )

    def test_should_show_help_when_no_arguments(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Test help display when no arguments provided."""
        # Act
        with patch.object(sys, "argv", ["replay"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        # Assert
        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "usage:" in captured.err
        assert "required" in captured.err

    @patch("app.replay.__main__.replay_file")
    def test_should_handle_keyboard_interrupt(
        self, mock_replay_file: Mock, tmp_path: Path
    ) -> None:
        """Test handling of keyboard interrupt."""
        # Arrange
        test_file = tmp_path / "test.json"
        test_file.write_text("{}")
        mock_replay_file.side_effect = KeyboardInterrupt()

        # Act
        with patch.object(sys, "argv", ["replay", "--file", str(test_file)]):
            exit_code = main()

        # Assert
        assert exit_code == 130  # Standard exit code for SIGINT
