# ruff: noqa: N803
# (boto3 API uses PascalCase keyword arguments: Bucket, Key, Filename)
"""Tests for the Batcher Lambda handler."""

import json
import os
import tempfile
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.llm.queue.batcher import (
    _DEFAULT_BATCH_THRESHOLD,
    _drain_staging_queue,
    handler,
)

BATCH_THRESHOLD = _DEFAULT_BATCH_THRESHOLD

# Required env vars for handler() validation gate
_HANDLER_ENV = {
    "STAGING_QUEUE_URL": "https://sqs/staging.fifo",
    "LLM_QUEUE_URL": "https://sqs/llm.fifo",
    "BATCH_BUCKET": "test-batch-bucket",
    "BEDROCK_SERVICE_ROLE_ARN": "arn:aws:iam::123456789012:role/BedrockBatchRole",
}


def _make_sqs_message(job_id: str, prompt: object = None) -> dict:
    """Create a mock SQS message matching SQSQueueBackend.enqueue() format."""
    if prompt is None:
        prompt = [
            {"role": "system", "content": "Align this data"},
            {"role": "user", "content": "Input Data:\ntest"},
        ]
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


def _read_drain_file(filepath: str) -> list[dict]:
    """Read records from a drain temp file."""
    records = []
    with open(filepath) as f:
        for line in f:
            records.append(json.loads(line))
    return records


class TestDrainStagingQueue:
    """Tests for _drain_staging_queue helper."""

    def test_drains_all_messages(self):
        """Should drain all messages, delete per batch, and write to file."""
        mock_sqs = MagicMock()
        messages = [_make_sqs_message(f"job-{i}") for i in range(3)]
        mock_sqs.receive_message.side_effect = [
            {"Messages": messages},
            {"Messages": []},
        ]

        count, filepath, _queue_empty = _drain_staging_queue(
            mock_sqs, "https://sqs/staging.fifo"
        )
        try:
            assert count == 3
            records = _read_drain_file(filepath)
            assert len(records) == 3
            for body in records:
                assert isinstance(body, dict)
            mock_sqs.delete_message_batch.assert_called_once()
        finally:
            os.unlink(filepath)

    def test_handles_empty_queue(self):
        """Should return 0 count for empty queue."""
        mock_sqs = MagicMock()
        mock_sqs.receive_message.return_value = {"Messages": []}

        count, filepath, _queue_empty = _drain_staging_queue(
            mock_sqs, "https://sqs/staging.fifo"
        )
        try:
            assert count == 0
            assert _read_drain_file(filepath) == []
        finally:
            os.unlink(filepath)

    def test_drain_batch_deletes_valid_messages(self):
        """Valid messages should be batch-deleted during drain to unlock FIFO groups."""
        mock_sqs = MagicMock()
        messages = [_make_sqs_message(f"job-{i}") for i in range(3)]
        mock_sqs.receive_message.side_effect = [
            {"Messages": messages},
            {"Messages": []},
        ]

        count, filepath, _queue_empty = _drain_staging_queue(
            mock_sqs, "https://sqs/staging.fifo"
        )
        try:
            mock_sqs.delete_message_batch.assert_called_once()
            entries = mock_sqs.delete_message_batch.call_args[1]["Entries"]
            assert len(entries) == 3
            mock_sqs.delete_message.assert_not_called()
        finally:
            os.unlink(filepath)

    def test_drain_deletes_malformed_messages(self):
        """Malformed (unparseable) messages should be deleted individually."""
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

        count, filepath, _queue_empty = _drain_staging_queue(
            mock_sqs, "https://sqs/staging.fifo"
        )
        try:
            assert count == 1
            records = _read_drain_file(filepath)
            assert len(records) == 1
            assert records[0]["job_id"] == "job-valid"
            mock_sqs.delete_message.assert_called_once_with(
                QueueUrl="https://sqs/staging.fifo",
                ReceiptHandle="receipt-bad",
            )
            mock_sqs.delete_message_batch.assert_called_once()
        finally:
            os.unlink(filepath)


def _make_drain_file(count: int) -> tuple[int, str]:
    """Build a temp staging file simulating _drain_staging_queue output."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    for i in range(count):
        body = json.loads(_make_sqs_message(f"job-{i}")["Body"])
        tmp.write(json.dumps(body) + "\n")
    tmp.close()
    return count, tmp.name


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
            mock_drain.return_value = _make_drain_file(BATCH_THRESHOLD)
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
        """Each JSONL line should have recordId and modelInput with Messages API format."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)

        # Capture uploaded file contents before cleanup
        captured = {}

        def capture_upload(Filename, Bucket, Key, **kwargs):
            with open(Filename) as f:
                captured[Key] = f.read()

        mock_s3.upload_file.side_effect = capture_upload

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = _make_drain_file(BATCH_THRESHOLD)
            mock_bedrock.create_model_invocation_job.return_value = {
                "jobArn": "arn:aws:bedrock:us-east-1:123:model-invocation-job/test"
            }

            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                handler({"execution_id": "exec-123", "scrapers": []}, None)

        # Find the JSONL upload (key ends with input.jsonl)
        jsonl_key = next(k for k in captured if k.endswith("input.jsonl"))
        lines = captured[jsonl_key].strip().split("\n")
        assert len(lines) == BATCH_THRESHOLD

        for line in lines:
            record = json.loads(line)
            assert "recordId" in record
            assert "modelInput" in record
            model_input = record["modelInput"]
            assert "messages" in model_input
            assert "anthropic_version" in model_input
            assert "max_tokens" in model_input

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
            mock_drain.return_value = _make_drain_file(BATCH_THRESHOLD)
            mock_bedrock.create_model_invocation_job.return_value = {"jobArn": job_arn}

            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                handler({"execution_id": "exec-123", "scrapers": []}, None)

        mock_dynamodb.put_item.assert_called_once()
        put_args = mock_dynamodb.put_item.call_args[1]
        assert put_args["Item"]["batch_job_arn"]["S"] == job_arn

    @patch("app.llm.queue.batcher._get_clients")
    def test_handler_uploads_valid_original_jobs_jsonl(self, mock_get_clients):
        """original_jobs.jsonl should be valid JSONL with k/v pairs."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)

        captured = {}

        def capture_upload(Filename, Bucket, Key, **kwargs):
            with open(Filename) as f:
                captured[Key] = f.read()

        mock_s3.upload_file.side_effect = capture_upload

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = _make_drain_file(3)
            mock_bedrock.create_model_invocation_job.return_value = {
                "jobArn": "arn:aws:bedrock:us-east-1:123:model-invocation-job/test"
            }

            env = {**_HANDLER_ENV, "BATCH_THRESHOLD": "2"}
            with patch.dict("os.environ", env, clear=False):
                handler({"execution_id": "exec-123", "scrapers": []}, None)

        oj_key = next(k for k in captured if k.endswith("original_jobs.jsonl"))
        lines = [line for line in captured[oj_key].strip().split("\n") if line]
        assert len(lines) == 3
        for line in lines:
            record = json.loads(line)
            assert "k" in record
            assert "v" in record
            assert "job" in record["v"]
            assert "job_id" in record["v"]


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
            mock_drain.return_value = _make_drain_file(5)

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
            mock_drain.return_value = _make_drain_file(0)

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
            mock_drain.return_value = _make_drain_file(1)
            with patch("app.llm.queue.batcher.send_to_sqs", return_value="msg-id"):
                with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                    handler({"execution_id": "exec-123", "scrapers": []}, None)

        mock_logger.info.assert_any_call(
            "batch_decision",
            record_count=1,
            decision="on-demand",
            execution_id="exec-123",
            threshold=BATCH_THRESHOLD,
        )


class TestHandlerMessageDeletion:
    """Tests for message deletion (drain deletes immediately)."""

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher.send_to_sqs")
    def test_handler_all_failures_reports_correctly(self, mock_send, mock_get_clients):
        """When ALL re-enqueue attempts fail, should report 0 count and N failures."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)
        mock_send.side_effect = RuntimeError("SQS send failed")

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = _make_drain_file(3)

            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                result = handler(
                    {"execution_id": "exec-123", "scrapers": ["vivery_api"]},
                    None,
                )

        assert result["mode"] == "on-demand"
        assert result["count"] == 0
        assert result["failed"] == 3


class TestHandlerOnDemandPartialFailure:
    """Tests for H29: per-record error handling in on-demand re-enqueue."""

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher.send_to_sqs")
    def test_partial_failure_reports_counts_correctly(
        self, mock_send, mock_get_clients
    ):
        """Partial re-enqueue failure should report correct success/failure counts."""
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
            mock_drain.return_value = _make_drain_file(3)

            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                result = handler(
                    {"execution_id": "exec-123", "scrapers": ["vivery_api"]},
                    None,
                )

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
            mock_drain.return_value = _make_drain_file(5)

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
            mock_drain.return_value = _make_drain_file(5)

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
