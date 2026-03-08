"""Tests for the Batcher Lambda handler."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.llm.queue.batcher import (
    BATCH_THRESHOLD,
    _delete_messages,
    _drain_staging_queue,
    handler,
)

# Required env vars for handler() validation gate
_HANDLER_ENV = {
    "STAGING_QUEUE_URL": "https://sqs/staging.fifo",
    "LLM_QUEUE_URL": "https://sqs/llm.fifo",
    "BATCH_BUCKET": "test-batch-bucket",
    "BEDROCK_SERVICE_ROLE_ARN": "arn:aws:iam::123456789012:role/BedrockBatchRole",
}


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
        """Should drain all messages and return (body, receipt_handle) tuples."""
        mock_sqs = MagicMock()
        messages = [_make_sqs_message(f"job-{i}") for i in range(3)]
        # First call returns messages, second returns empty (queue drained)
        mock_sqs.receive_message.side_effect = [
            {"Messages": messages},
            {"Messages": []},
        ]

        result = _drain_staging_queue(mock_sqs, "https://sqs/staging.fifo")
        assert len(result) == 3
        # Each element should be a (body_dict, receipt_handle) tuple
        for body, receipt_handle in result:
            assert isinstance(body, dict)
            assert isinstance(receipt_handle, str)
            assert receipt_handle.startswith("receipt-")

    def test_handles_empty_queue(self):
        """Should return empty list for empty queue."""
        mock_sqs = MagicMock()
        mock_sqs.receive_message.return_value = {"Messages": []}

        result = _drain_staging_queue(mock_sqs, "https://sqs/staging.fifo")
        assert result == []

    def test_drain_does_not_delete_valid_messages(self):
        """Valid messages should NOT be deleted during drain."""
        mock_sqs = MagicMock()
        messages = [_make_sqs_message(f"job-{i}") for i in range(3)]
        mock_sqs.receive_message.side_effect = [
            {"Messages": messages},
            {"Messages": []},
        ]

        _drain_staging_queue(mock_sqs, "https://sqs/staging.fifo")
        # delete_message should NOT be called for valid messages
        mock_sqs.delete_message.assert_not_called()

    def test_drain_deletes_malformed_messages(self):
        """Malformed (unparseable) messages should be deleted immediately."""
        mock_sqs = MagicMock()
        valid_msg = _make_sqs_message("job-valid")
        malformed_msg = {
            "MessageId": "msg-bad",
            "ReceiptHandle": "receipt-bad",
            "Body": "NOT VALID JSON {{{",
        }
        mock_sqs.receive_message.side_effect = [
            {"Messages": [valid_msg, malformed_msg]},
            {"Messages": []},
        ]

        result = _drain_staging_queue(mock_sqs, "https://sqs/staging.fifo")
        # Only valid message should be returned
        assert len(result) == 1
        body, handle = result[0]
        assert body["job_id"] == "job-valid"
        assert handle == "receipt-job-valid"
        # Malformed message should be deleted immediately
        mock_sqs.delete_message.assert_called_once_with(
            QueueUrl="https://sqs/staging.fifo",
            ReceiptHandle="receipt-bad",
        )


def _make_drain_return(count: int) -> list[tuple[dict, str]]:
    """Build _drain_staging_queue return value: list of (body, receipt_handle)."""
    return [
        (json.loads(_make_sqs_message(f"job-{i}")["Body"]), f"receipt-job-{i}")
        for i in range(count)
    ]


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

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = _make_drain_return(BATCH_THRESHOLD)
            mock_bedrock.create_model_invocation_job.return_value = {
                "jobArn": "arn:aws:bedrock:us-east-1:123:model-invocation-job/test-job"
            }

            event = {"execution_id": "exec-123", "scrapers": ["vivery_api"]}
            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
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
            mock_drain.return_value = _make_drain_return(BATCH_THRESHOLD)
            mock_bedrock.create_model_invocation_job.return_value = {
                "jobArn": "arn:aws:bedrock:us-east-1:123:model-invocation-job/test"
            }

            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
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
            mock_drain.return_value = _make_drain_return(BATCH_THRESHOLD)
            mock_bedrock.create_model_invocation_job.return_value = {"jobArn": job_arn}

            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
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
            mock_drain.return_value = _make_drain_return(5)

            event = {"execution_id": "exec-123", "scrapers": ["vivery_api"]}
            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
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

            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
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
            mock_drain.return_value = _make_drain_return(1)
            with patch("app.llm.queue.batcher.send_to_sqs", return_value="msg-id"):
                with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                    handler({"execution_id": "exec-123", "scrapers": []}, None)

        # Verify structlog info was called with expected fields
        mock_logger.info.assert_any_call(
            "batch_decision",
            record_count=1,
            decision="on-demand",
            execution_id="exec-123",
            threshold=BATCH_THRESHOLD,
        )


class TestHandlerMessageDeletion:
    """Tests for deferred message deletion (C1 fix)."""

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher.send_to_sqs")
    def test_handler_deletes_messages_only_after_success(
        self, mock_send, mock_get_clients
    ):
        """Messages should only be deleted after successful processing."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)
        mock_send.return_value = "msg-123"

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = _make_drain_return(3)

            with patch("app.llm.queue.batcher._delete_messages") as mock_delete:
                with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                    handler(
                        {"execution_id": "exec-123", "scrapers": ["vivery_api"]},
                        None,
                    )

                # _delete_messages should have been called exactly once
                mock_delete.assert_called_once()
                call_args = mock_delete.call_args
                # Should pass all 3 receipt handles
                assert len(call_args[0][2]) == 3

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher.send_to_sqs")
    def test_handler_all_failures_does_not_delete_messages(
        self, mock_send, mock_get_clients
    ):
        """When ALL re-enqueue attempts fail, no staging messages should be deleted."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)
        # All send_to_sqs calls fail
        mock_send.side_effect = RuntimeError("SQS send failed")

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = _make_drain_return(3)

            with patch("app.llm.queue.batcher._delete_messages") as mock_delete:
                with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                    result = handler(
                        {"execution_id": "exec-123", "scrapers": ["vivery_api"]},
                        None,
                    )

                # _delete_messages should NOT have been called (no successes)
                mock_delete.assert_not_called()

        # Should report 0 successes and 3 failures
        assert result["mode"] == "on-demand"
        assert result["count"] == 0
        assert result["failed"] == 3


class TestHandlerOnDemandPartialFailure:
    """Tests for H29: per-record error handling in on-demand re-enqueue."""

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher.send_to_sqs")
    def test_partial_failure_only_deletes_successful_handles(
        self, mock_send, mock_get_clients
    ):
        """Only staging messages for successfully re-enqueued records should be deleted."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)

        # First and third succeed, second fails
        mock_send.side_effect = [
            "msg-0",
            RuntimeError("Throttled"),
            "msg-2",
        ]

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = _make_drain_return(3)

            with patch("app.llm.queue.batcher._delete_messages") as mock_delete:
                with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                    result = handler(
                        {"execution_id": "exec-123", "scrapers": ["vivery_api"]},
                        None,
                    )

                # Only 2 successful handles should be deleted
                mock_delete.assert_called_once()
                deleted_handles = mock_delete.call_args[0][2]
                assert len(deleted_handles) == 2
                assert "receipt-job-0" in deleted_handles
                assert "receipt-job-2" in deleted_handles
                # The failed record's handle should NOT be deleted
                assert "receipt-job-1" not in deleted_handles

        assert result["mode"] == "on-demand"
        assert result["count"] == 2
        assert result["failed"] == 1

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher.send_to_sqs")
    def test_all_succeed_returns_full_count(self, mock_send, mock_get_clients):
        """All successful re-enqueue should return full count with 0 failures."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)
        mock_send.return_value = "msg-ok"

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = _make_drain_return(5)

            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                result = handler(
                    {"execution_id": "exec-123", "scrapers": ["vivery_api"]},
                    None,
                )

        assert result["mode"] == "on-demand"
        assert result["count"] == 5
        assert result["failed"] == 0

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher.send_to_sqs")
    def test_partial_failure_continues_processing_remaining(
        self, mock_send, mock_get_clients
    ):
        """A failure on one record should not stop processing of remaining records."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)

        # First fails, rest succeed
        mock_send.side_effect = [
            RuntimeError("First fails"),
            "msg-1",
            "msg-2",
            "msg-3",
            "msg-4",
        ]

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = _make_drain_return(5)

            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                result = handler(
                    {"execution_id": "exec-123", "scrapers": []},
                    None,
                )

        # All 5 records should have been attempted
        assert mock_send.call_count == 5
        assert result["count"] == 4
        assert result["failed"] == 1


class TestHandlerMissingEnvVars:
    """Tests for T6: handler behavior when critical env vars are missing."""

    def test_handler_with_empty_staging_queue_url(self):
        """Handler should raise ValueError when STAGING_QUEUE_URL is empty."""
        with patch.dict(
            "os.environ",
            {
                "STAGING_QUEUE_URL": "",
                "LLM_QUEUE_URL": "",
                "BATCH_BUCKET": "",
                "BEDROCK_SERVICE_ROLE_ARN": "",
            },
            clear=False,
        ):
            with pytest.raises(
                ValueError, match="Missing required environment variables"
            ):
                handler({"execution_id": "exec-123", "scrapers": []}, None)

    def test_handler_with_empty_llm_queue_url_on_demand(self):
        """When LLM_QUEUE_URL is empty, handler should raise ValueError
        before reaching the on-demand re-enqueue path."""
        with patch.dict(
            "os.environ",
            {
                "STAGING_QUEUE_URL": "https://sqs/staging.fifo",
                "LLM_QUEUE_URL": "",
                "BATCH_BUCKET": "test-bucket",
                "BEDROCK_SERVICE_ROLE_ARN": "arn:aws:iam::123:role/Role",
            },
            clear=False,
        ):
            with pytest.raises(ValueError, match="LLM_QUEUE_URL"):
                handler({"execution_id": "exec-123", "scrapers": []}, None)
