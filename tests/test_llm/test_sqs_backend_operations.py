"""Tests for SQSQueueBackend message operations.

Tests for receive_messages, delete_message, change_visibility,
and poison pill handling.
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.llm.queue.job import LLMJob


@pytest.fixture
def sample_llm_job() -> LLMJob:
    """Create a sample LLM job for testing."""
    return LLMJob(
        id=str(uuid4()),
        prompt="Test prompt for SQS backend testing",
        format={"type": "object", "properties": {"text": {"type": "string"}}},
        provider_config={"temperature": 0.7},
        metadata={"scraper_id": "test_scraper", "content_hash": "abc123"},
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_sqs_client():
    """Create a mock SQS client."""
    client = MagicMock()
    client.send_message.return_value = {
        "MessageId": "msg-123",
        "MD5OfMessageBody": "abc",
    }
    client.get_queue_attributes.return_value = {
        "Attributes": {"QueueArn": "arn:aws:sqs:us-east-1:123456789:test-queue"}
    }
    return client


@pytest.fixture
def mock_dynamodb_client():
    """Create a mock DynamoDB client."""
    client = MagicMock()
    client.describe_table.return_value = {"Table": {"TableName": "test-jobs"}}
    return client


class TestSQSQueueBackendReceiveMessages:
    """Tests for SQSQueueBackend receive_messages method."""

    def test_receive_messages_returns_empty_list_when_no_messages(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """receive_messages() should return empty list when queue is empty."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_sqs_client.receive_message.return_value = {}  # No Messages key

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        messages = backend.receive_messages()

        assert messages == []

    def test_receive_messages_parses_valid_message(
        self, mock_sqs_client, mock_dynamodb_client, sample_llm_job
    ):
        """receive_messages() should parse valid SQS message correctly."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        message_body = {
            "job_id": sample_llm_job.id,
            "job": sample_llm_job.model_dump(mode="json"),
            "enqueued_at": datetime.now(UTC).isoformat(),
        }

        mock_sqs_client.receive_message.return_value = {
            "Messages": [
                {
                    "MessageId": "msg-123",
                    "ReceiptHandle": "receipt-abc",
                    "Body": json.dumps(message_body),
                }
            ]
        }

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        messages = backend.receive_messages()

        assert len(messages) == 1
        assert messages[0]["job_id"] == sample_llm_job.id
        assert messages[0]["message_id"] == "msg-123"
        assert messages[0]["receipt_handle"] == "receipt-abc"

    def test_receive_messages_handles_malformed_json(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """receive_messages() should delete and skip malformed JSON messages."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_sqs_client.receive_message.return_value = {
            "Messages": [
                {
                    "MessageId": "msg-bad",
                    "ReceiptHandle": "receipt-bad",
                    "Body": "not valid json {{{",
                }
            ]
        }

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        messages = backend.receive_messages()

        # Should return empty since malformed message was skipped
        assert messages == []
        # Should have attempted to delete the malformed message
        mock_sqs_client.delete_message.assert_called_once_with(
            QueueUrl="https://sqs.us-east-1.amazonaws.com/123/queue",
            ReceiptHandle="receipt-bad",
        )

    def test_receive_messages_handles_missing_job_data(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """receive_messages() should delete and skip messages with missing job data."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_sqs_client.receive_message.return_value = {
            "Messages": [
                {
                    "MessageId": "msg-incomplete",
                    "ReceiptHandle": "receipt-incomplete",
                    "Body": json.dumps({"job_id": "123"}),  # Missing 'job' key
                }
            ]
        }

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        messages = backend.receive_messages()

        # Should return empty since incomplete message was skipped
        assert messages == []
        # Should have attempted to delete the incomplete message
        mock_sqs_client.delete_message.assert_called_once()

    def test_receive_messages_respects_max_messages(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """receive_messages() should respect max_messages parameter."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_sqs_client.receive_message.return_value = {"Messages": []}

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        backend.receive_messages(max_messages=5, wait_time_seconds=10)

        call_kwargs = mock_sqs_client.receive_message.call_args.kwargs
        assert call_kwargs["MaxNumberOfMessages"] == 5
        assert call_kwargs["WaitTimeSeconds"] == 10


class TestSQSQueueBackendDeleteMessage:
    """Tests for SQSQueueBackend delete_message method."""

    def test_delete_message_calls_sqs(self, mock_sqs_client, mock_dynamodb_client):
        """delete_message() should call SQS delete_message."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        backend.delete_message("receipt-handle-123")

        mock_sqs_client.delete_message.assert_called_once_with(
            QueueUrl="https://sqs.us-east-1.amazonaws.com/123/queue",
            ReceiptHandle="receipt-handle-123",
        )

    def test_delete_message_raises_on_invalid_receipt(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """delete_message() should raise on invalid receipt handle."""
        from botocore.exceptions import ClientError

        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_sqs_client.delete_message.side_effect = ClientError(
            {"Error": {"Code": "ReceiptHandleIsInvalid"}}, "DeleteMessage"
        )

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        with pytest.raises(ClientError):
            backend.delete_message("invalid-receipt")


class TestSQSQueueBackendChangeVisibility:
    """Tests for SQSQueueBackend change_visibility method."""

    def test_change_visibility_calls_sqs(self, mock_sqs_client, mock_dynamodb_client):
        """change_visibility() should call SQS change_message_visibility."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        backend.change_visibility("receipt-handle-123", 300)

        mock_sqs_client.change_message_visibility.assert_called_once_with(
            QueueUrl="https://sqs.us-east-1.amazonaws.com/123/queue",
            ReceiptHandle="receipt-handle-123",
            VisibilityTimeout=300,
        )

    def test_change_visibility_raises_on_invalid_receipt(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """change_visibility() should raise on invalid receipt handle."""
        from botocore.exceptions import ClientError

        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_sqs_client.change_message_visibility.side_effect = ClientError(
            {"Error": {"Code": "ReceiptHandleIsInvalid"}}, "ChangeMessageVisibility"
        )

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        with pytest.raises(ClientError):
            backend.change_visibility("invalid-receipt", 300)

    def test_change_visibility_with_zero_timeout(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """change_visibility() with timeout=0 should make message immediately visible."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        backend.change_visibility("receipt-handle-123", 0)

        mock_sqs_client.change_message_visibility.assert_called_once_with(
            QueueUrl="https://sqs.us-east-1.amazonaws.com/123/queue",
            ReceiptHandle="receipt-handle-123",
            VisibilityTimeout=0,
        )


class TestSQSQueueBackendPoisonPillDeleteFailure:
    """Tests for T4: graceful handling when poison pill deletion fails."""

    def test_receive_messages_handles_delete_failure_for_malformed_message(
        self, mock_sqs_client, mock_dynamodb_client, sample_llm_job
    ):
        """When deleting a malformed message fails, receive_messages should
        still return valid messages and not crash."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        valid_body = {
            "job_id": sample_llm_job.id,
            "job": sample_llm_job.model_dump(mode="json"),
            "enqueued_at": datetime.now(UTC).isoformat(),
        }

        mock_sqs_client.receive_message.return_value = {
            "Messages": [
                {
                    "MessageId": "msg-bad",
                    "ReceiptHandle": "receipt-bad",
                    "Body": "NOT VALID JSON {{{",
                },
                {
                    "MessageId": "msg-good",
                    "ReceiptHandle": "receipt-good",
                    "Body": json.dumps(valid_body),
                },
            ]
        }

        # Make delete fail for the poison pill
        mock_sqs_client.delete_message.side_effect = Exception("SQS delete failed")

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        # Should not crash, and should return the valid message
        messages = backend.receive_messages()

        assert len(messages) == 1
        assert messages[0]["job_id"] == sample_llm_job.id

        # The delete was attempted
        mock_sqs_client.delete_message.assert_called_once_with(
            QueueUrl="https://sqs.us-east-1.amazonaws.com/123/queue",
            ReceiptHandle="receipt-bad",
        )

    def test_receive_messages_continues_after_multiple_poison_pills(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """Multiple malformed messages with delete failures should all be handled gracefully."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_sqs_client.receive_message.return_value = {
            "Messages": [
                {
                    "MessageId": "msg-bad-1",
                    "ReceiptHandle": "receipt-bad-1",
                    "Body": "bad json 1",
                },
                {
                    "MessageId": "msg-bad-2",
                    "ReceiptHandle": "receipt-bad-2",
                    "Body": "bad json 2",
                },
            ]
        }

        # All deletes fail
        mock_sqs_client.delete_message.side_effect = Exception("SQS unavailable")

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        # Should not crash
        messages = backend.receive_messages()

        # No valid messages to return
        assert messages == []
        # Both deletes were attempted
        assert mock_sqs_client.delete_message.call_count == 2
