"""Tests for submarine Fargate worker."""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestProcessSubmarineMessage:
    """Tests for the submarine message processing function."""

    @patch("app.submarine.worker.process_submarine_job")
    def test_processes_job_data_from_message(self, mock_process):
        """Should delegate to process_submarine_job."""
        from app.submarine.fargate_worker import process_submarine_message

        mock_process.return_value = {
            "job": {"metadata": {"scraper_id": "submarine"}},
            "status": "completed",
        }

        data = {
            "id": "sub-001",
            "location_id": "loc-123",
            "website_url": "https://foodbank.example.com",
            "missing_fields": ["phone"],
            "source_scraper_id": "test_scraper",
        }

        result = process_submarine_message(data)

        assert result is not None
        mock_process.assert_called_once_with(data)


class TestSubmarineWorkerMain:
    """Tests for the submarine worker entry point."""

    def test_main_missing_submarine_queue_url(self):
        """Should exit with code 1 when SUBMARINE_QUEUE_URL is not set."""
        from app.submarine.fargate_worker import main

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SUBMARINE_QUEUE_URL", None)
            os.environ.pop("RECONCILER_QUEUE_URL", None)
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_main_missing_reconciler_queue_url(self):
        """Should exit with code 1 when RECONCILER_QUEUE_URL is not set."""
        from app.submarine.fargate_worker import main

        with patch.dict(
            os.environ,
            {"SUBMARINE_QUEUE_URL": "https://sqs.../submarine.fifo"},
            clear=True,
        ):
            os.environ.pop("RECONCILER_QUEUE_URL", None)
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    @patch("app.submarine.fargate_worker.PipelineWorker")
    def test_process_submarine_message_delegates(self, mock_worker_class):
        """Should configure PipelineWorker with submarine settings."""
        from app.submarine.fargate_worker import main

        mock_worker = MagicMock()
        mock_worker_class.return_value = mock_worker

        with patch.dict(
            os.environ,
            {
                "SUBMARINE_QUEUE_URL": "https://sqs.../submarine.fifo",
                "RECONCILER_QUEUE_URL": "https://sqs.../reconciler.fifo",
            },
        ):
            main()

        mock_worker_class.assert_called_once()
        call_kwargs = mock_worker_class.call_args.kwargs
        assert call_kwargs["queue_url"] == "https://sqs.../submarine.fifo"
        assert call_kwargs["service_name"] == "submarine"
        assert call_kwargs["next_queue_url"] == "https://sqs.../reconciler.fifo"
        assert call_kwargs["visibility_timeout"] == 600
        mock_worker.run.assert_called_once()
