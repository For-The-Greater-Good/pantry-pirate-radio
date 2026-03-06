"""Tests for reconciler Fargate worker."""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestProcessReconcilerMessage:
    """Tests for the reconciler message processing function."""

    @patch("app.reconciler.job_processor.process_job_result")
    def test_processes_job_result(self, mock_process):
        """Should deserialize and process the job result through the reconciler."""
        from app.reconciler.fargate_worker import process_reconciler_message

        mock_process.return_value = {
            "organizations_created": 1,
            "locations_created": 3,
        }

        data = {
            "job_id": "test-123",
            "status": "completed",
            "job": {
                "id": "test-123",
                "prompt": "test",
                "format": {},
                "metadata": {"scraper_id": "test_scraper"},
                "created_at": "2026-03-04T00:00:00Z",
            },
            "result": {
                "text": '{"location": []}',
                "model": "test",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        }

        result = process_reconciler_message(data)

        assert result is not None
        assert result["job_id"] == "test-123"
        assert result["result"] == {"organizations_created": 1, "locations_created": 3}
        assert result["error"] is None
        mock_process.assert_called_once()

    @patch("app.reconciler.job_processor.process_job_result")
    def test_returns_recorder_format(self, mock_process):
        """Should return data in the recorder's expected format."""
        from app.reconciler.fargate_worker import process_reconciler_message

        mock_process.return_value = {"status": "ok"}

        data = {
            "job_id": "test-789",
            "status": "completed",
            "job": {
                "id": "test-789",
                "prompt": "test",
                "format": {},
                "metadata": {},
                "created_at": "2026-03-04T00:00:00Z",
            },
        }

        result = process_reconciler_message(data)

        assert "job_id" in result
        assert "job" in result
        assert "result" in result
        assert "error" in result


class TestReconcilerWorkerMain:
    """Tests for the reconciler worker entry point."""

    def test_returns_error_without_queue_url(self):
        """Should return 1 when RECONCILER_QUEUE_URL is not set."""
        from app.reconciler.fargate_worker import main

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("RECONCILER_QUEUE_URL", None)
            result = main()
            assert result == 1

    @patch("app.reconciler.fargate_worker.PipelineWorker")
    def test_creates_worker_with_correct_config(self, mock_worker_class):
        """Should configure PipelineWorker with reconciler settings."""
        from app.reconciler.fargate_worker import main

        mock_worker = MagicMock()
        mock_worker_class.return_value = mock_worker

        with patch.dict(
            os.environ,
            {
                "RECONCILER_QUEUE_URL": "https://sqs.../reconciler.fifo",
                "RECORDER_QUEUE_URL": "https://sqs.../recorder.fifo",
            },
        ):
            main()

        mock_worker_class.assert_called_once()
        call_kwargs = mock_worker_class.call_args.kwargs
        assert call_kwargs["queue_url"] == "https://sqs.../reconciler.fifo"
        assert call_kwargs["service_name"] == "reconciler"
        assert call_kwargs["next_queue_url"] == "https://sqs.../recorder.fifo"
        assert call_kwargs["visibility_timeout"] == 300
        mock_worker.run.assert_called_once()
