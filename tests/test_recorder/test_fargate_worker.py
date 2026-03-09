"""Tests for recorder Fargate worker."""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestProcessRecorderMessage:
    """Tests for the recorder message processing function."""

    @patch("app.recorder.utils.record_result")
    def test_calls_record_result(self, mock_record):
        """Should call record_result with the message data."""
        from app.recorder.fargate_worker import process_recorder_message

        mock_record.return_value = {"status": "completed", "error": None}

        data = {
            "job_id": "test-123",
            "job": {"id": "test-123", "metadata": {"scraper_id": "test"}},
            "result": {"text": "test data"},
            "error": None,
        }

        result = process_recorder_message(data)

        mock_record.assert_called_once_with(data)
        # Recorder is terminal — returns None
        assert result is None

    @patch("app.recorder.utils.record_result")
    def test_returns_none_always(self, mock_record):
        """Should always return None since recorder is the terminal stage."""
        from app.recorder.fargate_worker import process_recorder_message

        mock_record.return_value = {"status": "completed"}

        result = process_recorder_message({"job_id": "test"})

        assert result is None


class TestRecorderWorkerMain:
    """Tests for the recorder worker entry point."""

    def test_returns_error_without_queue_url(self):
        """Should exit with code 1 when RECORDER_QUEUE_URL is not set."""
        from app.recorder.fargate_worker import main

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("RECORDER_QUEUE_URL", None)
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    @patch("app.recorder.fargate_worker.PipelineWorker")
    def test_creates_worker_with_correct_config(self, mock_worker_class):
        """Should configure PipelineWorker with recorder settings."""
        from app.recorder.fargate_worker import main

        mock_worker = MagicMock()
        mock_worker_class.return_value = mock_worker

        with patch.dict(
            os.environ,
            {
                "RECORDER_QUEUE_URL": "https://sqs.../recorder.fifo",
            },
        ):
            main()

        mock_worker_class.assert_called_once()
        call_kwargs = mock_worker_class.call_args.kwargs
        assert call_kwargs["queue_url"] == "https://sqs.../recorder.fifo"
        assert call_kwargs["service_name"] == "recorder"
        assert call_kwargs["next_queue_url"] is None
        assert call_kwargs["visibility_timeout"] == 120
        mock_worker.run.assert_called_once()
