"""Tests for batcher audit fixes (C2 poison pill DLQ, M4 threshold per-invocation)."""

import json
from unittest.mock import MagicMock, call, patch

import pytest

from app.llm.queue.batcher import _drain_staging_queue, _forward_to_dlq


class TestC2PoisonPillDlqForwarding:
    """C2: Unparseable messages should be forwarded to DLQ, not silently deleted."""

    def test_poison_pill_forwarded_to_dlq(self):
        """Malformed messages should be sent to DLQ before deletion."""
        mock_sqs = MagicMock()
        mock_sqs.receive_message.side_effect = [
            {
                "Messages": [
                    {
                        "MessageId": "msg-1",
                        "Body": "not-json!!!",
                        "ReceiptHandle": "handle-1",
                    }
                ]
            },
            {"Messages": []},  # Empty to stop draining
        ]

        dlq_url = "https://sqs.../staging-dlq.fifo"
        result = _drain_staging_queue(
            mock_sqs,
            "https://sqs.../staging.fifo",
            dlq_url=dlq_url,
        )

        # No valid messages returned
        assert len(result) == 0

        # DLQ send was called
        mock_sqs.send_message.assert_called_once()
        dlq_call = mock_sqs.send_message.call_args
        assert dlq_call.kwargs["QueueUrl"] == dlq_url
        body = json.loads(dlq_call.kwargs["MessageBody"])
        assert body["original_message_id"] == "msg-1"
        assert body["source"] == "batcher-poison-pill"

        # Original message was deleted from source queue
        mock_sqs.delete_message.assert_called_once()

    def test_poison_pill_deleted_when_no_dlq_configured(self):
        """Without DLQ URL, malformed messages are still deleted (backward compat)."""
        mock_sqs = MagicMock()
        mock_sqs.receive_message.side_effect = [
            {
                "Messages": [
                    {
                        "MessageId": "msg-1",
                        "Body": "{invalid json",
                        "ReceiptHandle": "handle-1",
                    }
                ]
            },
            {"Messages": []},
        ]

        result = _drain_staging_queue(
            mock_sqs,
            "https://sqs.../staging.fifo",
            dlq_url="",  # No DLQ
        )

        assert len(result) == 0
        # No DLQ send
        mock_sqs.send_message.assert_not_called()
        # But still deleted
        mock_sqs.delete_message.assert_called_once()

    def test_valid_messages_not_forwarded_to_dlq(self):
        """Valid messages should be collected normally, not sent to DLQ."""
        mock_sqs = MagicMock()
        valid_body = json.dumps({"job": {"id": "j1"}, "job_id": "j1"})
        mock_sqs.receive_message.side_effect = [
            {
                "Messages": [
                    {
                        "MessageId": "msg-1",
                        "Body": valid_body,
                        "ReceiptHandle": "handle-1",
                    }
                ]
            },
            {"Messages": []},
        ]

        result = _drain_staging_queue(
            mock_sqs,
            "https://sqs.../staging.fifo",
            dlq_url="https://sqs.../staging-dlq.fifo",
        )

        assert len(result) == 1
        # No DLQ send, no deletion (caller deletes after processing)
        mock_sqs.send_message.assert_not_called()
        mock_sqs.delete_message.assert_not_called()

    def test_dlq_forward_failure_does_not_crash_drain(self):
        """If DLQ forwarding fails, drain should continue (message still deleted)."""
        mock_sqs = MagicMock()
        mock_sqs.receive_message.side_effect = [
            {
                "Messages": [
                    {
                        "MessageId": "msg-1",
                        "Body": "not-json",
                        "ReceiptHandle": "handle-1",
                    }
                ]
            },
            {"Messages": []},
        ]
        # DLQ send fails
        mock_sqs.send_message.side_effect = Exception("DLQ unavailable")

        # Should not raise
        result = _drain_staging_queue(
            mock_sqs,
            "https://sqs.../staging.fifo",
            dlq_url="https://sqs.../staging-dlq.fifo",
        )

        assert len(result) == 0
        # Message still deleted from source
        mock_sqs.delete_message.assert_called_once()


class TestM4BatchThresholdPerInvocation:
    """M4: Batch threshold should be read per invocation, not at module load."""

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher._drain_staging_queue", return_value=[])
    @patch.dict(
        "os.environ",
        {
            "STAGING_QUEUE_URL": "https://sqs.../staging.fifo",
            "LLM_QUEUE_URL": "https://sqs.../llm.fifo",
            "BATCH_BUCKET": "test-bucket",
            "BEDROCK_SERVICE_ROLE_ARN": "arn:aws:iam::role/test",
            "BATCH_THRESHOLD": "50",
        },
        clear=False,
    )
    def test_threshold_read_from_env_per_invocation(self, mock_drain, mock_clients):
        """Batch threshold should be read from env var at handler call time."""
        from app.llm.queue.batcher import handler

        mock_clients.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock())

        result = handler({"execution_id": "test-exec"}, None)

        # With 0 records, should be on-demand regardless of threshold
        assert result["mode"] == "on-demand"
        assert result["count"] == 0


class TestForwardToDlq:
    """Tests for _forward_to_dlq helper function."""

    def test_forward_sends_correctly_formatted_message(self):
        """DLQ message should contain original body, message ID, and error."""
        mock_sqs = MagicMock()
        _forward_to_dlq(
            sqs_client=mock_sqs,
            dlq_url="https://sqs.../dlq.fifo",
            original_body="bad data",
            message_id="msg-123",
            error="JSON decode error",
        )

        mock_sqs.send_message.assert_called_once()
        call_kwargs = mock_sqs.send_message.call_args.kwargs
        assert call_kwargs["QueueUrl"] == "https://sqs.../dlq.fifo"
        assert call_kwargs["MessageGroupId"] == "poison-pills"

        body = json.loads(call_kwargs["MessageBody"])
        assert body["original_body"] == "bad data"
        assert body["original_message_id"] == "msg-123"
        assert body["error"] == "JSON decode error"
        assert body["source"] == "batcher-poison-pill"
