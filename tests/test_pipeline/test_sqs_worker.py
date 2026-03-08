"""Tests for PipelineWorker SQS polling worker."""

import json
import signal
from unittest.mock import MagicMock, call, patch

import pytest

from app.pipeline.sqs_worker import PipelineWorker


@pytest.fixture
def mock_sqs_client():
    """Create a mock SQS client."""
    client = MagicMock()
    client.receive_message.return_value = {"Messages": []}
    return client


@pytest.fixture
def sample_process_fn():
    """Create a sample processing function."""
    fn = MagicMock(return_value={"processed": True, "job_id": "test-123"})
    return fn


@pytest.fixture
def worker(mock_sqs_client, sample_process_fn):
    """Create a PipelineWorker with mocked SQS client."""
    w = PipelineWorker(
        queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue.fifo",
        process_fn=sample_process_fn,
        service_name="test-service",
        next_queue_url="https://sqs.us-east-1.amazonaws.com/123/next-queue.fifo",
        max_messages=1,
        wait_time_seconds=1,
    )
    w._sqs_client = mock_sqs_client
    return w


class TestPipelineWorkerInit:
    """Tests for PipelineWorker initialization."""

    def test_init_stores_config(self):
        """PipelineWorker should store all configuration."""
        fn = MagicMock()
        worker = PipelineWorker(
            queue_url="https://sqs.../queue.fifo",
            process_fn=fn,
            service_name="validator",
            next_queue_url="https://sqs.../next.fifo",
            max_messages=5,
            wait_time_seconds=10,
            visibility_timeout=600,
            max_consecutive_errors=5,
        )

        assert worker.queue_url == "https://sqs.../queue.fifo"
        assert worker.process_fn is fn
        assert worker.service_name == "validator"
        assert worker.next_queue_url == "https://sqs.../next.fifo"
        assert worker.max_messages == 5
        assert worker.wait_time_seconds == 10
        assert worker.visibility_timeout == 600
        assert worker.max_consecutive_errors == 5

    def test_init_defaults(self):
        """PipelineWorker should have sensible defaults."""
        fn = MagicMock()
        worker = PipelineWorker(
            queue_url="https://sqs.../queue.fifo",
            process_fn=fn,
            service_name="test",
        )

        assert worker.next_queue_url is None
        assert worker.max_messages == 1
        assert worker.wait_time_seconds == 20
        assert worker.visibility_timeout == 300
        assert worker.max_consecutive_errors == 10
        assert worker._running is False
        assert worker._shutdown_requested is False


class TestPipelineWorkerSignalHandling:
    """Tests for signal handling."""

    def test_setup_signal_handlers(self, worker):
        """Signal handlers should set shutdown flag."""
        worker._setup_signal_handlers()

        # Simulate SIGTERM
        handler = signal.getsignal(signal.SIGTERM)
        handler(signal.SIGTERM, None)

        assert worker._shutdown_requested is True

    def test_stop_method(self, worker):
        """stop() should set shutdown flags."""
        worker.stop()

        assert worker._shutdown_requested is True
        assert worker._running is False


class TestPipelineWorkerReceiveMessages:
    """Tests for message reception."""

    def test_receive_parses_valid_messages(self, worker, mock_sqs_client):
        """Should parse valid SQS messages into structured dicts."""
        mock_sqs_client.receive_message.return_value = {
            "Messages": [
                {
                    "MessageId": "msg-1",
                    "ReceiptHandle": "receipt-1",
                    "Body": json.dumps(
                        {
                            "job_id": "job-123",
                            "data": {"key": "value"},
                            "source": "llm-worker",
                            "enqueued_at": "2026-03-03T12:00:00Z",
                        }
                    ),
                }
            ]
        }

        messages = worker._receive_messages()

        assert len(messages) == 1
        assert messages[0]["job_id"] == "job-123"
        assert messages[0]["data"] == {"key": "value"}
        assert messages[0]["source"] == "llm-worker"
        assert messages[0]["receipt_handle"] == "receipt-1"

    def test_receive_no_messages(self, worker, mock_sqs_client):
        """Should return empty list when no messages available."""
        mock_sqs_client.receive_message.return_value = {"Messages": []}

        messages = worker._receive_messages()

        assert messages == []

    def test_receive_deletes_malformed_messages(self, worker, mock_sqs_client):
        """Should delete poison pill messages that can't be parsed."""
        mock_sqs_client.receive_message.return_value = {
            "Messages": [
                {
                    "MessageId": "msg-bad",
                    "ReceiptHandle": "receipt-bad",
                    "Body": "not valid json{{{",
                }
            ]
        }

        messages = worker._receive_messages()

        assert messages == []
        mock_sqs_client.delete_message.assert_called_once_with(
            QueueUrl=worker.queue_url,
            ReceiptHandle="receipt-bad",
        )

    def test_receive_handles_body_without_envelope(self, worker, mock_sqs_client):
        """Should handle messages that don't have the standard envelope."""
        mock_sqs_client.receive_message.return_value = {
            "Messages": [
                {
                    "MessageId": "msg-2",
                    "ReceiptHandle": "receipt-2",
                    "Body": json.dumps({"some": "data"}),
                }
            ]
        }

        messages = worker._receive_messages()

        assert len(messages) == 1
        assert messages[0]["job_id"] == "unknown"
        # When no 'data' key, the whole body becomes the data
        assert messages[0]["data"] == {"some": "data"}


class TestPipelineWorkerProcessMessage:
    """Tests for message processing."""

    @patch("app.pipeline.sqs_worker.send_to_sqs")
    def test_process_calls_function_with_data(
        self, mock_send, worker, sample_process_fn, mock_sqs_client
    ):
        """Should call process_fn with the message data."""
        message = {
            "job_id": "job-123",
            "receipt_handle": "receipt-1",
            "data": {"key": "value"},
            "source": "llm-worker",
        }

        result = worker._process_single_message(message)

        assert result is True
        sample_process_fn.assert_called_once_with({"key": "value"})

    @patch("app.pipeline.sqs_worker.send_to_sqs")
    def test_process_deletes_message_on_success(
        self, mock_send, worker, sample_process_fn, mock_sqs_client
    ):
        """Should delete the SQS message after successful processing."""
        message = {
            "job_id": "job-123",
            "receipt_handle": "receipt-1",
            "data": {"key": "value"},
            "source": "test",
        }

        worker._process_single_message(message)

        mock_sqs_client.delete_message.assert_called_once_with(
            QueueUrl=worker.queue_url,
            ReceiptHandle="receipt-1",
        )

    @patch("app.pipeline.sqs_worker.send_to_sqs")
    def test_process_forwards_to_next_queue(self, mock_send, worker, sample_process_fn):
        """Should forward results to next queue when configured."""
        message = {
            "job_id": "job-123",
            "receipt_handle": "receipt-1",
            "data": {"key": "value"},
            "source": "test",
        }

        worker._process_single_message(message)

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        assert call_kwargs.kwargs["queue_url"] == worker.next_queue_url

    @patch("app.pipeline.sqs_worker.send_to_sqs")
    def test_process_skips_forwarding_when_result_is_none(
        self, mock_send, worker, sample_process_fn
    ):
        """Should not forward when process_fn returns None."""
        sample_process_fn.return_value = None

        message = {
            "job_id": "job-123",
            "receipt_handle": "receipt-1",
            "data": {"key": "value"},
            "source": "test",
        }

        worker._process_single_message(message)

        mock_send.assert_not_called()

    def test_process_skips_forwarding_when_no_next_queue(
        self, sample_process_fn, mock_sqs_client
    ):
        """Should not forward when no next_queue_url configured."""
        worker = PipelineWorker(
            queue_url="https://sqs.../queue.fifo",
            process_fn=sample_process_fn,
            service_name="recorder",
            next_queue_url=None,
        )
        worker._sqs_client = mock_sqs_client

        message = {
            "job_id": "job-123",
            "receipt_handle": "receipt-1",
            "data": {"key": "value"},
            "source": "test",
        }

        result = worker._process_single_message(message)

        assert result is True

    def test_process_returns_false_on_error(
        self, worker, sample_process_fn, mock_sqs_client
    ):
        """Should return False and not delete message on processing error."""
        sample_process_fn.side_effect = ValueError("Processing failed")

        message = {
            "job_id": "job-123",
            "receipt_handle": "receipt-1",
            "data": {"key": "value"},
            "source": "test",
        }

        result = worker._process_single_message(message)

        assert result is False
        # Message should NOT be deleted on failure (will retry via visibility timeout)
        mock_sqs_client.delete_message.assert_not_called()


class TestPipelineWorkerRunLoop:
    """Tests for the main run loop."""

    def test_run_processes_messages(self, worker, mock_sqs_client, sample_process_fn):
        """Should poll and process messages in a loop."""
        # First poll returns a message, second poll triggers shutdown
        call_count = 0

        def receive_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "Messages": [
                        {
                            "MessageId": "msg-1",
                            "ReceiptHandle": "receipt-1",
                            "Body": json.dumps(
                                {
                                    "job_id": "job-1",
                                    "data": {"test": True},
                                    "source": "test",
                                }
                            ),
                        }
                    ]
                }
            else:
                worker._shutdown_requested = True
                return {"Messages": []}

        mock_sqs_client.receive_message.side_effect = receive_side_effect

        with patch("app.pipeline.sqs_worker.send_to_sqs"):
            worker.run()

        sample_process_fn.assert_called_once_with({"test": True})

    def test_run_stops_on_shutdown_signal(self, worker, mock_sqs_client):
        """Should stop gracefully when shutdown is requested."""
        worker._shutdown_requested = True

        worker.run()

        # Should not poll when already shutting down
        mock_sqs_client.receive_message.assert_not_called()

    @patch("app.pipeline.sqs_worker.time.sleep")
    def test_run_applies_exponential_backoff_on_errors(
        self, mock_sleep, worker, mock_sqs_client
    ):
        """Should apply exponential backoff on consecutive errors."""
        error_count = 0

        def receive_side_effect(**kwargs):
            nonlocal error_count
            error_count += 1
            if error_count >= 3:
                worker._shutdown_requested = True
                return {"Messages": []}
            raise ConnectionError("SQS unavailable")

        mock_sqs_client.receive_message.side_effect = receive_side_effect

        worker.run()

        # Should have slept with exponential backoff
        assert mock_sleep.call_count >= 1
        # First delay should be 5s (base_delay * 2^0)
        mock_sleep.assert_any_call(5)

    @patch("app.pipeline.sqs_worker.time.sleep")
    def test_run_shuts_down_after_max_consecutive_errors(
        self, mock_sleep, mock_sqs_client, sample_process_fn
    ):
        """Should shut down after max consecutive errors."""
        worker = PipelineWorker(
            queue_url="https://sqs.../queue.fifo",
            process_fn=sample_process_fn,
            service_name="test",
            max_consecutive_errors=3,
        )
        worker._sqs_client = mock_sqs_client

        mock_sqs_client.receive_message.side_effect = ConnectionError("SQS down")

        worker.run()

        # Should have stopped after 3 errors
        assert worker._shutdown_requested is True


class TestPipelineWorkerPoisonPillDeleteFailure:
    """Tests for T3: poison pill delete failure doesn't crash worker."""

    def test_receive_continues_after_poison_pill_delete_failure(
        self, mock_sqs_client, sample_process_fn
    ):
        """When a poison pill message can't be deleted, worker continues processing."""
        worker = PipelineWorker(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue.fifo",
            process_fn=sample_process_fn,
            service_name="test-service",
            next_queue_url="https://sqs.us-east-1.amazonaws.com/123/next-queue.fifo",
        )
        worker._sqs_client = mock_sqs_client

        # First message is malformed (poison pill), second is valid
        mock_sqs_client.receive_message.return_value = {
            "Messages": [
                {
                    "MessageId": "msg-bad",
                    "ReceiptHandle": "receipt-bad",
                    "Body": "not valid json{{{",
                },
                {
                    "MessageId": "msg-good",
                    "ReceiptHandle": "receipt-good",
                    "Body": json.dumps(
                        {
                            "job_id": "job-good",
                            "data": {"key": "value"},
                            "source": "test",
                        }
                    ),
                },
            ]
        }

        # Make delete fail for the poison pill
        mock_sqs_client.delete_message.side_effect = Exception("SQS delete failed")

        messages = worker._receive_messages()

        # The valid message should still be returned despite the delete failure
        assert len(messages) == 1
        assert messages[0]["job_id"] == "job-good"

        # delete_message was attempted (for the poison pill)
        mock_sqs_client.delete_message.assert_called_once_with(
            QueueUrl=worker.queue_url,
            ReceiptHandle="receipt-bad",
        )

    def test_worker_loop_survives_poison_pill_delete_failure(
        self, mock_sqs_client, sample_process_fn
    ):
        """The run loop should not crash when poison pill deletion fails."""
        worker = PipelineWorker(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue.fifo",
            process_fn=sample_process_fn,
            service_name="test-service",
        )
        worker._sqs_client = mock_sqs_client

        call_count = 0

        def receive_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "Messages": [
                        {
                            "MessageId": "msg-poison",
                            "ReceiptHandle": "receipt-poison",
                            "Body": "{{{{invalid",
                        }
                    ]
                }
            else:
                worker._shutdown_requested = True
                return {"Messages": []}

        mock_sqs_client.receive_message.side_effect = receive_side_effect
        mock_sqs_client.delete_message.side_effect = Exception("SQS delete failed")

        # Should not crash
        worker.run()

        # Worker processed both iterations without crashing
        assert call_count >= 2


class TestPipelineWorkerFIFOGroupId:
    """Tests for T12: FIFO message_group_id extraction from metadata."""

    @patch("app.pipeline.sqs_worker.send_to_sqs")
    def test_extracts_scraper_id_from_nested_job_metadata(
        self, mock_send, mock_sqs_client, sample_process_fn
    ):
        """Should extract scraper_id from data.job.metadata.scraper_id for FIFO ordering."""
        worker = PipelineWorker(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue.fifo",
            process_fn=sample_process_fn,
            service_name="test-service",
            next_queue_url="https://sqs.us-east-1.amazonaws.com/123/next-queue.fifo",
        )
        worker._sqs_client = mock_sqs_client

        message = {
            "job_id": "job-123",
            "receipt_handle": "receipt-1",
            "data": {
                "job": {
                    "metadata": {
                        "scraper_id": "feeding_america_scraper",
                    }
                }
            },
            "source": "llm-worker",
        }

        worker._process_single_message(message)

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["message_group_id"] == "feeding_america_scraper"

    @patch("app.pipeline.sqs_worker.send_to_sqs")
    def test_uses_default_group_id_when_no_metadata(
        self, mock_send, mock_sqs_client, sample_process_fn
    ):
        """Should use 'default' when data has no job.metadata.scraper_id."""
        worker = PipelineWorker(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue.fifo",
            process_fn=sample_process_fn,
            service_name="test-service",
            next_queue_url="https://sqs.us-east-1.amazonaws.com/123/next-queue.fifo",
        )
        worker._sqs_client = mock_sqs_client

        message = {
            "job_id": "job-123",
            "receipt_handle": "receipt-1",
            "data": {"some": "data_without_job_key"},
            "source": "test",
        }

        worker._process_single_message(message)

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["message_group_id"] == "default"

    @patch("app.pipeline.sqs_worker.send_to_sqs")
    def test_uses_default_when_metadata_has_no_scraper_id(
        self, mock_send, mock_sqs_client, sample_process_fn
    ):
        """Should use 'default' when metadata exists but has no scraper_id."""
        worker = PipelineWorker(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue.fifo",
            process_fn=sample_process_fn,
            service_name="test-service",
            next_queue_url="https://sqs.us-east-1.amazonaws.com/123/next-queue.fifo",
        )
        worker._sqs_client = mock_sqs_client

        message = {
            "job_id": "job-123",
            "receipt_handle": "receipt-1",
            "data": {"job": {"metadata": {"other_field": "value"}}},
            "source": "test",
        }

        worker._process_single_message(message)

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["message_group_id"] == "default"
