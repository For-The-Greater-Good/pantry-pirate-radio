"""Tests for SQS message sender utility."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.pipeline.sqs_sender import reset_sqs_client, send_to_sqs


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
