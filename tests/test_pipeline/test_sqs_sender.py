"""Tests for SQS message sender utility."""

import json
from unittest.mock import MagicMock, call, patch

import pytest

from app.pipeline.sqs_sender import _is_retryable, reset_sqs_client, send_to_sqs


@pytest.fixture(autouse=True)
def cleanup_sqs_client():
    """Reset the module-level SQS client between tests."""
    reset_sqs_client()
    yield
    reset_sqs_client()


@pytest.fixture
def mock_sqs_client():
    """Create a mock SQS client."""
    client = MagicMock()
    client.send_message.return_value = {"MessageId": "test-msg-id-123"}
    return client


class TestSendToSqs:
    """Tests for send_to_sqs function."""

    @patch("app.pipeline.sqs_sender._get_sqs_client")
    def test_sends_message_to_fifo_queue(self, mock_get_client, mock_sqs_client):
        """Should send message with FIFO attributes for .fifo queues."""
        mock_get_client.return_value = mock_sqs_client
        queue_url = "https://sqs.us-east-1.amazonaws.com/123/test.fifo"

        result = send_to_sqs(
            queue_url=queue_url,
            message_body={"job_id": "abc-123", "key": "value"},
            message_group_id="scraper-1",
            deduplication_id="dedup-1",
            source="test-service",
        )

        assert result == "test-msg-id-123"
        mock_sqs_client.send_message.assert_called_once()

        call_kwargs = mock_sqs_client.send_message.call_args.kwargs
        assert call_kwargs["QueueUrl"] == queue_url
        assert call_kwargs["MessageDeduplicationId"] == "dedup-1"
        assert call_kwargs["MessageGroupId"] == "scraper-1"

        # Verify message body envelope
        body = json.loads(call_kwargs["MessageBody"])
        assert body["job_id"] == "abc-123"
        assert body["data"]["key"] == "value"
        assert body["source"] == "test-service"
        assert "enqueued_at" in body

    @patch("app.pipeline.sqs_sender._get_sqs_client")
    def test_sends_message_to_standard_queue(self, mock_get_client, mock_sqs_client):
        """Should not include FIFO attributes for standard queues."""
        mock_get_client.return_value = mock_sqs_client
        queue_url = "https://sqs.us-east-1.amazonaws.com/123/test-queue"

        send_to_sqs(
            queue_url=queue_url,
            message_body={"job_id": "abc-123"},
        )

        call_kwargs = mock_sqs_client.send_message.call_args.kwargs
        assert "MessageDeduplicationId" not in call_kwargs
        assert "MessageGroupId" not in call_kwargs

    @patch("app.pipeline.sqs_sender._get_sqs_client")
    def test_auto_generates_deduplication_id(self, mock_get_client, mock_sqs_client):
        """Should use job_id as deduplication ID when not provided."""
        mock_get_client.return_value = mock_sqs_client
        queue_url = "https://sqs.us-east-1.amazonaws.com/123/test.fifo"

        send_to_sqs(
            queue_url=queue_url,
            message_body={"job_id": "my-job-id"},
        )

        call_kwargs = mock_sqs_client.send_message.call_args.kwargs
        assert call_kwargs["MessageDeduplicationId"] == "my-job-id"

    def test_raises_on_empty_queue_url(self):
        """Should raise ValueError if queue_url is empty."""
        with pytest.raises(ValueError, match="queue_url is required"):
            send_to_sqs(
                queue_url="",
                message_body={"test": True},
            )

    @patch("app.pipeline.sqs_sender._get_sqs_client")
    def test_generates_job_id_if_missing(self, mock_get_client, mock_sqs_client):
        """Should auto-generate job_id if not in message body."""
        mock_get_client.return_value = mock_sqs_client
        queue_url = "https://sqs.us-east-1.amazonaws.com/123/test.fifo"

        send_to_sqs(
            queue_url=queue_url,
            message_body={"data": "no-job-id"},
        )

        call_kwargs = mock_sqs_client.send_message.call_args.kwargs
        body = json.loads(call_kwargs["MessageBody"])
        # Should have auto-generated a UUID job_id
        assert len(body["job_id"]) == 36  # UUID format


class TestSendToSqsRetry:
    """Tests for H27: send_to_sqs retry logic on transient failures."""

    @patch("app.pipeline.sqs_sender.time.sleep")
    @patch("app.pipeline.sqs_sender._get_sqs_client")
    def test_retries_on_throttling_error(self, mock_get_client, mock_sleep):
        """Should retry on throttling errors and succeed."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Create a real botocore ClientError with throttling
        from botocore.exceptions import ClientError

        throttle_error = ClientError(
            error_response={
                "Error": {"Code": "Throttling", "Message": "Rate exceeded"}
            },
            operation_name="SendMessage",
        )

        # First call throttles, second succeeds
        mock_client.send_message.side_effect = [
            throttle_error,
            {"MessageId": "msg-after-retry"},
        ]

        queue_url = "https://sqs.us-east-1.amazonaws.com/123/test-queue"
        result = send_to_sqs(queue_url=queue_url, message_body={"job_id": "j1"})

        assert result == "msg-after-retry"
        assert mock_client.send_message.call_count == 2
        mock_sleep.assert_called_once()

    @patch("app.pipeline.sqs_sender.time.sleep")
    @patch("app.pipeline.sqs_sender._get_sqs_client")
    def test_retries_on_connection_error(self, mock_get_client, mock_sleep):
        """Should retry on ConnectionError."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.send_message.side_effect = [
            ConnectionError("Connection reset"),
            {"MessageId": "msg-ok"},
        ]

        queue_url = "https://sqs.us-east-1.amazonaws.com/123/test-queue"
        result = send_to_sqs(queue_url=queue_url, message_body={"job_id": "j2"})

        assert result == "msg-ok"
        assert mock_client.send_message.call_count == 2

    @patch("app.pipeline.sqs_sender.time.sleep")
    @patch("app.pipeline.sqs_sender._get_sqs_client")
    def test_does_not_retry_on_non_retryable_error(self, mock_get_client, mock_sleep):
        """Should NOT retry on non-retryable errors like ValueError."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.send_message.side_effect = ValueError("Bad input")

        queue_url = "https://sqs.us-east-1.amazonaws.com/123/test-queue"
        with pytest.raises(ValueError, match="Bad input"):
            send_to_sqs(queue_url=queue_url, message_body={"job_id": "j3"})

        # Should have tried only once
        assert mock_client.send_message.call_count == 1
        mock_sleep.assert_not_called()

    @patch("app.pipeline.sqs_sender.time.sleep")
    @patch("app.pipeline.sqs_sender._get_sqs_client")
    def test_raises_after_max_retries_exhausted(self, mock_get_client, mock_sleep):
        """Should raise after all retry attempts are exhausted."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # All calls fail with retryable error
        mock_client.send_message.side_effect = ConnectionError("Persistent failure")

        queue_url = "https://sqs.us-east-1.amazonaws.com/123/test-queue"
        with pytest.raises(ConnectionError, match="Persistent failure"):
            send_to_sqs(queue_url=queue_url, message_body={"job_id": "j4"})

        # 1 initial + 3 retries = 4 total attempts
        assert mock_client.send_message.call_count == 4

    @patch("app.pipeline.sqs_sender.time.sleep")
    @patch("app.pipeline.sqs_sender._get_sqs_client")
    def test_exponential_backoff_delays(self, mock_get_client, mock_sleep):
        """Should use exponential backoff delays between retries."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # All calls fail with retryable error
        mock_client.send_message.side_effect = ConnectionError("Timeout")

        queue_url = "https://sqs.us-east-1.amazonaws.com/123/test-queue"
        with pytest.raises(ConnectionError):
            send_to_sqs(queue_url=queue_url, message_body={"job_id": "j5"})

        # Verify exponential backoff delays: 1.0, 2.0, 4.0
        assert mock_sleep.call_count == 3
        delays = [c[0][0] for c in mock_sleep.call_args_list]
        assert delays == [1.0, 2.0, 4.0]


class TestIsRetryable:
    """Tests for _is_retryable helper."""

    def test_connection_error_is_retryable(self):
        """ConnectionError should be retryable."""
        assert _is_retryable(ConnectionError("reset")) is True

    def test_timeout_error_is_retryable(self):
        """TimeoutError should be retryable."""
        assert _is_retryable(TimeoutError("timed out")) is True

    def test_value_error_is_not_retryable(self):
        """ValueError should NOT be retryable."""
        assert _is_retryable(ValueError("bad input")) is False

    def test_client_error_throttling_is_retryable(self):
        """ClientError with Throttling code should be retryable."""
        from botocore.exceptions import ClientError

        err = ClientError(
            error_response={
                "Error": {"Code": "Throttling", "Message": "Rate exceeded"}
            },
            operation_name="SendMessage",
        )
        assert _is_retryable(err) is True

    def test_client_error_access_denied_is_not_retryable(self):
        """ClientError with AccessDenied code should NOT be retryable."""
        from botocore.exceptions import ClientError

        err = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "Denied"}},
            operation_name="SendMessage",
        )
        assert _is_retryable(err) is False
