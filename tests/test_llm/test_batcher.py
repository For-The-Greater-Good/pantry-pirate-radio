"""Tests for the Batcher Lambda handler."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, call, patch

import pytest

from app.llm.queue.batcher import (
    BATCH_THRESHOLD,
    _drain_staging_queue,
    handler,
)


def _make_sqs_message(job_id: str, prompt: str = "Align this data") -> dict:
    """Create a mock SQS message matching SQSQueueBackend.enqueue() format."""
    return {
        "MessageId": f"msg-{job_id}",
        "ReceiptHandle": f"receipt-{job_id}",
        "Body": json.dumps(
            {
                "job_id": job_id,
                "job": {
                    "id": job_id,
                    "prompt": prompt,
                    "format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "response",
                            "schema": {
                                "type": "object",
                                "properties": {"name": {"type": "string"}},
                            },
                        },
                    },
                    "provider_config": {},
                    "metadata": {"scraper_id": "test_scraper"},
                    "created_at": datetime.now(UTC).isoformat(),
                },
                "provider_config": {
                    "model_name": "us.anthropic.claude-haiku-4-5-20251001-v1:0"
                },
                "enqueued_at": datetime.now(UTC).isoformat(),
            }
        ),
    }


class TestDrainStagingQueue:
    """Tests for _drain_staging_queue helper."""

    def test_drains_all_messages(self):
        """Should drain all messages from the staging queue."""
        mock_sqs = MagicMock()
        messages = [_make_sqs_message(f"job-{i}") for i in range(3)]
        # First call returns messages, second returns empty (queue drained)
        mock_sqs.receive_message.side_effect = [
            {"Messages": messages},
            {"Messages": []},
        ]

        result = _drain_staging_queue(mock_sqs, "https://sqs/staging.fifo")
        assert len(result) == 3
        # Verify all messages were deleted
        assert mock_sqs.delete_message.call_count == 3

    def test_handles_empty_queue(self):
        """Should return empty list for empty queue."""
        mock_sqs = MagicMock()
        mock_sqs.receive_message.return_value = {"Messages": []}

        result = _drain_staging_queue(mock_sqs, "https://sqs/staging.fifo")
        assert result == []


class TestHandlerBatchPath:
    """Tests for batch path (>= BATCH_THRESHOLD records)."""

    @patch("app.llm.queue.batcher._get_clients")
    def test_handler_batch_path_gte_threshold(self, mock_get_clients):
        """With >= threshold records, should create batch job."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)

        # Create enough messages to trigger batch path
        messages = [_make_sqs_message(f"job-{i}") for i in range(BATCH_THRESHOLD)]

        # Drain returns all messages in one batch, then empty
        mock_sqs.receive_message.side_effect = (
            [
                {"Messages": messages[:10]},
            ]
            * (BATCH_THRESHOLD // 10)
            + [{"Messages": messages[BATCH_THRESHOLD - (BATCH_THRESHOLD % 10) :]}]
            * (1 if BATCH_THRESHOLD % 10 else 0)
            + [{"Messages": []}]
        )

        # Actually let's simplify - just mock _drain_staging_queue
        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = [
                json.loads(_make_sqs_message(f"job-{i}")["Body"])
                for i in range(BATCH_THRESHOLD)
            ]
            mock_bedrock.create_model_invocation_job.return_value = {
                "jobArn": "arn:aws:bedrock:us-east-1:123:model-invocation-job/test-job"
            }

            event = {"execution_id": "exec-123", "scrapers": ["vivery_api"]}
            result = handler(event, None)

        assert result["mode"] == "batch"
        assert "job_arn" in result
        mock_bedrock.create_model_invocation_job.assert_called_once()

    @patch("app.llm.queue.batcher._get_clients")
    def test_handler_builds_valid_jsonl(self, mock_get_clients):
        """Each JSONL line should have recordId and modelInput with Converse format."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = [
                json.loads(_make_sqs_message(f"job-{i}")["Body"])
                for i in range(BATCH_THRESHOLD)
            ]
            mock_bedrock.create_model_invocation_job.return_value = {
                "jobArn": "arn:aws:bedrock:us-east-1:123:model-invocation-job/test"
            }

            handler({"execution_id": "exec-123", "scrapers": []}, None)

        # Verify S3 put_object was called with JSONL content (first call)
        put_call = mock_s3.put_object.call_args_list[0]
        body = put_call[1]["Body"] if "Body" in put_call[1] else put_call[0][0]
        lines = body.strip().split("\n")
        assert len(lines) == BATCH_THRESHOLD

        # Verify each line is valid JSONL with correct structure
        for line in lines:
            record = json.loads(line)
            assert "recordId" in record
            assert "modelInput" in record
            model_input = record["modelInput"]
            assert "messages" in model_input
            assert "inferenceConfig" in model_input

    @patch("app.llm.queue.batcher._get_clients")
    def test_handler_stores_batch_job_arn_in_dynamodb(self, mock_get_clients):
        """Should store batch job ARN in DynamoDB for tracking."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)

        job_arn = "arn:aws:bedrock:us-east-1:123:model-invocation-job/test"
        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = [
                json.loads(_make_sqs_message(f"job-{i}")["Body"])
                for i in range(BATCH_THRESHOLD)
            ]
            mock_bedrock.create_model_invocation_job.return_value = {"jobArn": job_arn}

            handler({"execution_id": "exec-123", "scrapers": []}, None)

        # Verify DynamoDB put_item was called
        mock_dynamodb.put_item.assert_called_once()
        put_args = mock_dynamodb.put_item.call_args[1]
        assert put_args["Item"]["batch_job_arn"]["S"] == job_arn


class TestHandlerOnDemandPath:
    """Tests for on-demand path (< BATCH_THRESHOLD records)."""

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher.send_to_sqs")
    def test_handler_on_demand_fallback_lt_threshold(self, mock_send, mock_get_clients):
        """With < threshold records, should re-enqueue to LLM queue."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)
        mock_send.return_value = "msg-123"

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = [
                json.loads(_make_sqs_message(f"job-{i}")["Body"]) for i in range(5)
            ]

            event = {"execution_id": "exec-123", "scrapers": ["vivery_api"]}
            result = handler(event, None)

        assert result["mode"] == "on-demand"
        assert result["count"] == 5
        assert mock_send.call_count == 5
        mock_bedrock.create_model_invocation_job.assert_not_called()


class TestHandlerEmptyQueue:
    """Tests for empty queue scenario."""

    @patch("app.llm.queue.batcher._get_clients")
    def test_handler_empty_queue(self, mock_get_clients):
        """0 messages should result in graceful no-op."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = []

            result = handler({"execution_id": "exec-123", "scrapers": []}, None)

        assert result["mode"] == "on-demand"
        assert result["count"] == 0


class TestHandlerLogging:
    """Tests for structured logging."""

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher.logger")
    def test_handler_logs_decision_with_structlog(self, mock_logger, mock_get_clients):
        """Should log the batch decision with structured context."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = [json.loads(_make_sqs_message("job-0")["Body"])]
            with patch("app.llm.queue.batcher.send_to_sqs", return_value="msg-id"):
                handler({"execution_id": "exec-123", "scrapers": []}, None)

        # Verify structlog info was called with expected fields
        mock_logger.info.assert_any_call(
            "batch_decision",
            record_count=1,
            decision="on-demand",
            execution_id="exec-123",
            threshold=BATCH_THRESHOLD,
        )
