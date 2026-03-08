"""Tests for validator Fargate worker."""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestProcessValidationMessage:
    """Tests for the validator message processing function."""

    @patch("app.validator.job_processor.process_validation_job")
    def test_processes_job_result_from_message(self, mock_process):
        """Should deserialize and process the job result."""
        from app.validator.fargate_worker import process_validation_message

        mock_process.return_value = {
            "job_id": "test-123",
            "status": "passed_validation",
            "data": {"location": []},
        }

        data = {
            "job_id": "test-123",
            "status": "completed",
            "result": {
                "text": '{"location": []}',
                "model": "test",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        }

        result = process_validation_message(data)

        assert result is not None
        assert result["job_id"] == "test-123"
        mock_process.assert_called_once()

    @patch("app.validator.job_processor.process_validation_job")
    def test_returns_serializable_result(self, mock_process):
        """Should return a JSON-serializable dict for forwarding."""
        from app.validator.fargate_worker import process_validation_message

        mock_process.return_value = {"status": "passed"}

        data = {
            "job_id": "test-456",
            "status": "completed",
            "result": {
                "text": '{"location": []}',
                "model": "test",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        }

        result = process_validation_message(data)

        # Result should be a dict (serializable for SQS forwarding)
        assert isinstance(result, dict)


class TestValidatorWorkerMain:
    """Tests for the validator worker entry point."""

    def test_returns_error_without_queue_url(self):
        """Should exit with code 1 when VALIDATOR_QUEUE_URL is not set."""
        from app.validator.fargate_worker import main

        with patch.dict(os.environ, {}, clear=True):
            # Ensure VALIDATOR_QUEUE_URL is not set
            os.environ.pop("VALIDATOR_QUEUE_URL", None)
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    @patch("app.validator.fargate_worker.PipelineWorker")
    def test_creates_worker_with_correct_config(self, mock_worker_class):
        """Should configure PipelineWorker with validator settings."""
        from app.validator.fargate_worker import main

        mock_worker = MagicMock()
        mock_worker_class.return_value = mock_worker

        with patch.dict(
            os.environ,
            {
                "VALIDATOR_QUEUE_URL": "https://sqs.../validator.fifo",
                "RECONCILER_QUEUE_URL": "https://sqs.../reconciler.fifo",
            },
        ):
            main()

        mock_worker_class.assert_called_once()
        call_kwargs = mock_worker_class.call_args.kwargs
        assert call_kwargs["queue_url"] == "https://sqs.../validator.fifo"
        assert call_kwargs["service_name"] == "validator"
        assert call_kwargs["next_queue_url"] == "https://sqs.../reconciler.fifo"
        assert call_kwargs["visibility_timeout"] == 600
        mock_worker.run.assert_called_once()
