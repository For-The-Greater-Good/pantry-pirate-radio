"""Tests for replay tool validation routing - Issue #369."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

import pytest

from app.llm.providers.types import LLMResponse
from app.llm.queue.job import LLMJob
from app.llm.queue.types import JobResult, JobStatus


class TestReplayValidationRouting:
    """Test replay tool routes through validator by default."""

    def test_replay_file_uses_validator_by_default(self, tmp_path: Path) -> None:
        """Test that replay_file routes through validator by default."""
        # Arrange
        from app.replay.replay import replay_file, read_job_file, create_job_result

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
            "result": {
                "organizations": [{"name": "Test Org"}],
                "locations": [
                    {
                        "name": "Test Location",
                        "latitude": 40.7128,
                        "longitude": -74.0060,
                    }
                ],
            },
            "error": None,
        }

        test_file = tmp_path / "test_job.json"
        test_file.write_text(json.dumps(test_data))

        # Mock the validator queue
        with patch("app.replay.replay.enqueue_to_validator") as mock_enqueue_validator:
            mock_enqueue_validator.return_value = "validator-job-123"

            # Act
            result = replay_file(str(test_file), dry_run=False, skip_validation=False)

            # Assert
            assert result is True
            mock_enqueue_validator.assert_called_once()
            # Verify the job_result passed to validator
            call_args = mock_enqueue_validator.call_args[0]
            assert call_args[0].job_id == "test-123"

    def test_replay_file_skips_validator_when_flag_set(self, tmp_path: Path) -> None:
        """Test that replay_file skips validator when skip_validation=True."""
        # Arrange
        from app.replay.replay import replay_file

        test_data = {
            "job_id": "test-456",
            "job": {
                "id": "test-456",
                "prompt": "Test prompt",
                "format": {"type": "object"},
                "provider_config": {"temperature": 0.7},
                "metadata": {"scraper_id": "test_scraper"},
                "created_at": "2025-07-21T16:22:14.978038+00:00",
            },
            "result": {
                "organizations": [{"name": "Test Org"}],
                "locations": [
                    {
                        "name": "Test Location",
                        "latitude": 40.7128,
                        "longitude": -74.0060,
                    }
                ],
            },
            "error": None,
        }

        test_file = tmp_path / "test_job.json"
        test_file.write_text(json.dumps(test_data))

        # Mock both routes
        with patch(
            "app.replay.replay.enqueue_to_validator"
        ) as mock_enqueue_validator, patch(
            "app.replay.replay.process_job_result"
        ) as mock_process_reconciler:
            mock_process_reconciler.return_value = {"status": "success"}

            # Act
            result = replay_file(str(test_file), dry_run=False, skip_validation=True)

            # Assert
            assert result is True
            mock_enqueue_validator.assert_not_called()  # Should NOT call validator
            mock_process_reconciler.assert_called_once()  # Should call reconciler directly

    def test_enqueue_to_validator_function_exists(self) -> None:
        """Test that enqueue_to_validator function is implemented."""
        # This will fail initially since the function doesn't exist yet
        from app.replay.replay import enqueue_to_validator

        # Should be callable
        assert callable(enqueue_to_validator)

    def test_enqueue_to_validator_sends_to_validator_queue(self) -> None:
        """Test that enqueue_to_validator properly enqueues to validator queue."""
        # Arrange
        from app.replay.replay import enqueue_to_validator

        # Create a simple mock JobResult
        mock_job_result = MagicMock()
        mock_job_result.job_id = "test-789"

        with patch("app.validator.queues.get_validator_queue") as mock_get_queue:
            mock_queue = MagicMock()
            mock_queue.enqueue_call.return_value = MagicMock(id="validator-job-789")
            mock_get_queue.return_value = mock_queue

            # Act
            job_id = enqueue_to_validator(mock_job_result)

            # Assert
            assert job_id == "validator-job-789"
            mock_queue.enqueue_call.assert_called_once()
            # Check the basic call structure
            call_args, call_kwargs = mock_queue.enqueue_call.call_args
            assert (
                call_kwargs["func"]
                == "app.validator.job_processor.process_validation_job"
            )
            assert call_kwargs["args"] == (mock_job_result,)
            assert call_kwargs["meta"]["source"] == "replay"
            assert call_kwargs["meta"]["original_job_id"] == "test-789"

    def test_replay_directory_uses_validator_by_default(self, tmp_path: Path) -> None:
        """Test that replay_directory routes through validator by default."""
        # Arrange
        from app.replay.replay import replay_directory

        # Create multiple test files
        for i in range(3):
            test_data = {
                "job_id": f"test-dir-{i}",
                "job": {
                    "id": f"test-dir-{i}",
                    "prompt": "Test prompt",
                    "format": {"type": "object"},
                    "provider_config": {"temperature": 0.7},
                    "metadata": {"scraper_id": "test_scraper"},
                    "created_at": "2025-07-21T16:22:14.978038+00:00",
                },
                "result": {"test": f"data-{i}"},
                "error": None,
            }
            test_file = tmp_path / f"test_job_{i}.json"
            test_file.write_text(json.dumps(test_data))

        with patch("app.replay.replay.enqueue_to_validator") as mock_enqueue_validator:
            mock_enqueue_validator.return_value = "validator-job-id"

            # Act
            stats = replay_directory(
                str(tmp_path), pattern="*.json", dry_run=False, skip_validation=False
            )

            # Assert
            assert stats["total_files"] == 3
            assert stats["successful"] == 3
            assert stats["failed"] == 0
            assert mock_enqueue_validator.call_count == 3

    def test_replay_directory_skips_validator_when_flag_set(
        self, tmp_path: Path
    ) -> None:
        """Test that replay_directory skips validator when skip_validation=True."""
        # Arrange
        from app.replay.replay import replay_directory

        # Create test file
        test_data = {
            "job_id": "test-skip-dir",
            "job": {
                "id": "test-skip-dir",
                "prompt": "Test prompt",
                "format": {"type": "object"},
                "provider_config": {"temperature": 0.7},
                "metadata": {"scraper_id": "test_scraper"},
                "created_at": "2025-07-21T16:22:14.978038+00:00",
            },
            "result": {"test": "data"},
            "error": None,
        }
        test_file = tmp_path / "test_job.json"
        test_file.write_text(json.dumps(test_data))

        with patch(
            "app.replay.replay.enqueue_to_validator"
        ) as mock_enqueue_validator, patch(
            "app.replay.replay.process_job_result"
        ) as mock_process_reconciler:
            mock_process_reconciler.return_value = {"status": "success"}

            # Act
            stats = replay_directory(
                str(tmp_path), pattern="*.json", dry_run=False, skip_validation=True
            )

            # Assert
            assert stats["successful"] == 1
            mock_enqueue_validator.assert_not_called()
            mock_process_reconciler.assert_called_once()

    def test_dry_run_works_with_validation(self, tmp_path: Path) -> None:
        """Test that dry_run mode works correctly with validation."""
        # Arrange
        from app.replay.replay import replay_file

        test_data = {
            "job_id": "test-dry-run",
            "job": {
                "id": "test-dry-run",
                "prompt": "Test prompt",
                "format": {"type": "object"},
                "provider_config": {"temperature": 0.7},
                "metadata": {"scraper_id": "test_scraper"},
                "created_at": "2025-07-21T16:22:14.978038+00:00",
            },
            "result": {"test": "data"},
            "error": None,
        }
        test_file = tmp_path / "test_job.json"
        test_file.write_text(json.dumps(test_data))

        with patch("app.replay.replay.enqueue_to_validator") as mock_enqueue_validator:
            # Act
            result = replay_file(str(test_file), dry_run=True, skip_validation=False)

            # Assert
            assert result is True
            mock_enqueue_validator.assert_not_called()  # Should not enqueue in dry_run mode

    def test_validation_respects_validator_enabled_setting(
        self, tmp_path: Path
    ) -> None:
        """Test that validation respects VALIDATOR_ENABLED setting."""
        # Arrange
        from app.replay.replay import replay_file

        test_data = {
            "job_id": "test-config",
            "job": {
                "id": "test-config",
                "prompt": "Test prompt",
                "format": {"type": "object"},
                "provider_config": {"temperature": 0.7},
                "metadata": {"scraper_id": "test_scraper"},
                "created_at": "2025-07-21T16:22:14.978038+00:00",
            },
            "result": {"test": "data"},
            "error": None,
        }
        test_file = tmp_path / "test_job.json"
        test_file.write_text(json.dumps(test_data))

        # Test with VALIDATOR_ENABLED=False
        with patch("app.core.config.settings.VALIDATOR_ENABLED", False), patch(
            "app.replay.replay.enqueue_to_validator"
        ) as mock_enqueue_validator, patch(
            "app.replay.replay.process_job_result"
        ) as mock_process_reconciler:
            mock_process_reconciler.return_value = {"status": "success"}

            # Act
            result = replay_file(str(test_file), dry_run=False, skip_validation=False)

            # Assert - should skip validator when disabled in settings
            assert result is True
            mock_enqueue_validator.assert_not_called()
            mock_process_reconciler.assert_called_once()

    def test_progress_logging_shows_validation_step(
        self, tmp_path: Path, caplog
    ) -> None:
        """Test that progress logging shows validation step."""
        # Arrange
        from app.replay.replay import replay_file
        import logging

        test_data = {
            "job_id": "test-logging",
            "job": {
                "id": "test-logging",
                "prompt": "Test prompt",
                "format": {"type": "object"},
                "provider_config": {"temperature": 0.7},
                "metadata": {"scraper_id": "test_scraper"},
                "created_at": "2025-07-21T16:22:14.978038+00:00",
            },
            "result": {"test": "data"},
            "error": None,
        }
        test_file = tmp_path / "test_job.json"
        test_file.write_text(json.dumps(test_data))

        with patch("app.replay.replay.enqueue_to_validator") as mock_enqueue_validator:
            mock_enqueue_validator.return_value = "validator-job-123"
            caplog.set_level(logging.INFO)

            # Act
            result = replay_file(str(test_file), dry_run=False, skip_validation=False)

            # Assert
            assert result is True
            assert (
                "Sending to validator" in caplog.text
                or "validator" in caplog.text.lower()
            )

    def test_validation_error_handling(self, tmp_path: Path) -> None:
        """Test that validation errors are handled gracefully."""
        # Arrange
        from app.replay.replay import replay_file

        test_data = {
            "job_id": "test-error",
            "job": {
                "id": "test-error",
                "prompt": "Test prompt",
                "format": {"type": "object"},
                "provider_config": {"temperature": 0.7},
                "metadata": {"scraper_id": "test_scraper"},
                "created_at": "2025-07-21T16:22:14.978038+00:00",
            },
            "result": {"test": "data"},
            "error": None,
        }
        test_file = tmp_path / "test_job.json"
        test_file.write_text(json.dumps(test_data))

        with patch("app.replay.replay.enqueue_to_validator") as mock_enqueue_validator:
            mock_enqueue_validator.side_effect = Exception("Validator queue error")

            # Act
            result = replay_file(str(test_file), dry_run=False, skip_validation=False)

            # Assert - should handle error and return False
            assert result is False
