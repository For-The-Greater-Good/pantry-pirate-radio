"""Tests for replay functionality."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.llm.providers.types import LLMResponse
from app.llm.queue.job import LLMJob
from app.llm.queue.types import JobResult, JobStatus


class TestReplayModule:
    """Test cases for the replay module."""

    def test_should_read_json_file_when_valid_path_provided(
        self, tmp_path: Path
    ) -> None:
        """Test reading a valid JSON file."""
        # Arrange
        from app.replay.replay import read_job_file

        test_data = {
            "job_id": "test-123",
            "job": {
                "id": "test-123",
                "prompt": "Test prompt",
                "format": {"type": "object"},
                "provider_config": {"temperature": 0.7},
                "metadata": {"scraper_id": "test_scraper"},
                "created_at": "2025-07-21T16:22:14.978038+00:00",
            },
            "result": {"text": "Test response"},
            "error": None,
        }

        test_file = tmp_path / "test_job.json"
        test_file.write_text(json.dumps(test_data))

        # Act
        result = read_job_file(str(test_file))

        # Assert
        assert result is not None
        assert result["job_id"] == "test-123"
        assert result["job"]["prompt"] == "Test prompt"

    def test_should_return_none_when_file_not_found(self) -> None:
        """Test handling of missing files."""
        # Arrange
        from app.replay.replay import read_job_file

        # Act
        result = read_job_file("/nonexistent/file.json")

        # Assert
        assert result is None

    def test_should_return_none_when_invalid_json(self, tmp_path: Path) -> None:
        """Test handling of invalid JSON."""
        # Arrange
        from app.replay.replay import read_job_file

        test_file = tmp_path / "invalid.json"
        test_file.write_text("{ invalid json")

        # Act
        result = read_job_file(str(test_file))

        # Assert
        assert result is None

    def test_should_create_job_result_when_valid_data(self) -> None:
        """Test creating JobResult from JSON data."""
        # Arrange
        from app.replay.replay import create_job_result

        data = {
            "job_id": "test-123",
            "job": {
                "id": "test-123",
                "prompt": "Test prompt",
                "format": {"type": "object"},
                "provider_config": {"temperature": 0.7},
                "metadata": {"scraper_id": "test_scraper"},
                "created_at": "2025-07-21T16:22:14.978038+00:00",
            },
            "result": {"text": "Test response"},
            "error": None,
        }

        # Act
        job_result = create_job_result(data)

        # Assert
        assert job_result is not None
        assert job_result.job_id == "test-123"
        assert job_result.status == JobStatus.COMPLETED
        assert isinstance(job_result.result, LLMResponse)
        # Result is stored as a dict but converted to string for LLMResponse
        assert "Test response" in job_result.result.text
        assert job_result.error is None

    def test_should_handle_failed_job_when_error_present(self) -> None:
        """Test handling of failed jobs with errors."""
        # Arrange
        from app.replay.replay import create_job_result

        data = {
            "job_id": "test-456",
            "job": {
                "id": "test-456",
                "prompt": "Test prompt",
                "format": {"type": "object"},
                "provider_config": {},
                "metadata": {},
                "created_at": "2025-07-21T16:22:14.978038+00:00",
            },
            "result": None,
            "error": "Test error message",
        }

        # Act
        job_result = create_job_result(data)

        # Assert
        assert job_result is not None
        assert job_result.job_id == "test-456"
        assert job_result.status == JobStatus.FAILED
        assert job_result.result is None
        assert job_result.error == "Test error message"

    def test_should_return_none_when_missing_required_fields(self) -> None:
        """Test handling of incomplete data."""
        # Arrange
        from app.replay.replay import create_job_result

        # Missing job_id
        data1 = {"job": {}, "result": None}

        # Missing job
        data2 = {"job_id": "test-789", "result": None}

        # Act & Assert
        assert create_job_result(data1) is None
        assert create_job_result(data2) is None

    @patch("app.replay.replay.process_job_result")
    def test_should_enqueue_job_when_replay_single_file(
        self, mock_process: Mock, tmp_path: Path
    ) -> None:
        """Test replaying a single file."""
        # Arrange
        from app.replay.replay import replay_file

        test_data = {
            "job_id": "test-123",
            "job": {
                "id": "test-123",
                "prompt": "Test prompt",
                "format": {"type": "object"},
                "provider_config": {"temperature": 0.7},
                "metadata": {"scraper_id": "test_scraper"},
                "created_at": "2025-07-21T16:22:14.978038+00:00",
            },
            "result": {"text": "Test response"},
            "error": None,
        }

        test_file = tmp_path / "test_job.json"
        test_file.write_text(json.dumps(test_data))

        mock_process.return_value = {"status": "completed"}

        # Act
        result = replay_file(str(test_file))

        # Assert
        assert result is True
        mock_process.assert_called_once()
        call_args = mock_process.call_args[0][0]
        assert isinstance(call_args, JobResult)
        assert call_args.job_id == "test-123"

    @patch("app.replay.replay.process_job_result")
    def test_should_skip_file_when_dry_run_enabled(
        self, mock_process: Mock, tmp_path: Path
    ) -> None:
        """Test dry run mode."""
        # Arrange
        from app.replay.replay import replay_file

        test_data = {
            "job_id": "test-123",
            "job": {
                "id": "test-123",
                "prompt": "Test prompt",
                "format": {"type": "object"},
                "provider_config": {},
                "metadata": {},
                "created_at": "2025-07-21T16:22:14.978038+00:00",
            },
            "result": {"text": "Test response"},
            "error": None,
        }

        test_file = tmp_path / "test_job.json"
        test_file.write_text(json.dumps(test_data))

        # Act
        result = replay_file(str(test_file), dry_run=True)

        # Assert
        assert result is True
        mock_process.assert_not_called()

    @patch("app.replay.replay.replay_file")
    def test_should_process_all_json_files_in_directory(
        self, mock_replay_file: Mock, tmp_path: Path
    ) -> None:
        """Test batch processing of directory."""
        # Arrange
        from app.replay.replay import replay_directory

        # Create test files
        (tmp_path / "job1.json").write_text("{}")
        (tmp_path / "job2.json").write_text("{}")
        (tmp_path / "not_json.txt").write_text("text")

        mock_replay_file.return_value = True

        # Act
        results = replay_directory(str(tmp_path))

        # Assert
        assert results["total_files"] == 2
        assert results["successful"] == 2
        assert results["failed"] == 0
        assert mock_replay_file.call_count == 2

    def test_should_filter_by_pattern_when_provided(self, tmp_path: Path) -> None:
        """Test file pattern filtering."""
        # Arrange
        from app.replay.replay import replay_directory

        # Create test files
        (tmp_path / "job_123.json").write_text(
            json.dumps(
                {
                    "job_id": "123",
                    "job": {
                        "id": "123",
                        "prompt": "Test",
                        "format": {},
                        "provider_config": {},
                        "metadata": {},
                        "created_at": "2025-07-21T16:22:14.978038+00:00",
                    },
                    "result": "test",
                }
            )
        )
        (tmp_path / "other_456.json").write_text("{}")

        # Act
        with patch("app.replay.replay.process_job_result"):
            results = replay_directory(str(tmp_path), pattern="job_*.json")

        # Assert
        assert results["total_files"] == 1
        assert results["successful"] == 1

    def test_should_continue_on_error_when_file_fails(self, tmp_path: Path) -> None:
        """Test error handling during batch processing."""
        # Arrange
        from app.replay.replay import replay_directory

        # Create test files
        (tmp_path / "good.json").write_text(
            json.dumps(
                {
                    "job_id": "123",
                    "job": {
                        "id": "123",
                        "prompt": "Test",
                        "format": {},
                        "provider_config": {},
                        "metadata": {},
                        "created_at": "2025-07-21T16:22:14.978038+00:00",
                    },
                    "result": "test",
                }
            )
        )
        (tmp_path / "bad.json").write_text("{ invalid json")

        # Act
        with patch("app.replay.replay.process_job_result"):
            results = replay_directory(str(tmp_path))

        # Assert
        assert results["total_files"] == 2
        assert results["successful"] == 1
        assert results["failed"] == 1

    def test_should_only_process_completed_jobs_when_filtering_enabled(self) -> None:
        """Test filtering of non-completed jobs."""
        # Arrange
        from app.replay.replay import should_process_job

        # Completed job
        completed_data = {
            "job_id": "123",
            "job": {"id": "123"},
            "result": {"text": "response"},
            "error": None,
        }

        # Failed job
        failed_data = {
            "job_id": "456",
            "job": {"id": "456"},
            "result": None,
            "error": "Error message",
        }

        # Incomplete job (no result or error)
        incomplete_data = {
            "job_id": "789",
            "job": {"id": "789"},
            "result": None,
            "error": None,
        }

        # Act & Assert
        assert should_process_job(completed_data) is True
        assert should_process_job(failed_data) is False  # Skip failed jobs
        assert should_process_job(incomplete_data) is False  # Skip incomplete jobs
