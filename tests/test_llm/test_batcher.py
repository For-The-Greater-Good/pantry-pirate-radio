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
            mock_sqs,
            "https://sqs/staging.fifo",
            s3_client=MagicMock(),
            bucket="test-batch-bucket",
            recovery_id="exec-1_req-1",
            source="scraper",
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
            mock_sqs,
            "https://sqs/staging.fifo",
            s3_client=MagicMock(),
            bucket="test-batch-bucket",
            recovery_id="exec-1_req-1",
            source="scraper",
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
            mock_sqs,
            "https://sqs/staging.fifo",
            s3_client=MagicMock(),
            bucket="test-batch-bucket",
            recovery_id="exec-1_req-1",
            source="scraper",
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
            mock_sqs,
            "https://sqs/staging.fifo",
            s3_client=MagicMock(),
            bucket="test-batch-bucket",
            recovery_id="exec-1_req-1",
            source="scraper",
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


def _make_drain_file(count: int) -> tuple[int, str, bool]:
    """Build a temp staging file simulating _drain_staging_queue output."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    for i in range(count):
        body = json.loads(_make_sqs_message(f"job-{i}")["Body"])
        tmp.write(json.dumps(body) + "\n")
    tmp.close()
    return count, tmp.name, True


class TestHandlerBatchPath:
    """Tests for batch path (>= BATCH_THRESHOLD records)."""

    @patch("app.llm.queue.batcher._get_clients")
    def test_handler_batch_path_gte_threshold(self, mock_get_clients):
        """With >= threshold records, should create batch job."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
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
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)

        # Capture S3JsonlWriter put_object payloads (small payloads skip multipart).
        captured = {}

        def capture_put(**kwargs):
            captured[kwargs["Key"]] = kwargs["Body"].decode("utf-8")

        mock_s3.put_object.side_effect = capture_put

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
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
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
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)

        captured = {}

        def capture_put(**kwargs):
            captured[kwargs["Key"]] = kwargs["Body"].decode("utf-8")

        mock_s3.put_object.side_effect = capture_put

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
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
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
        assert result["record_count"] == 5
        assert mock_send.call_count == 5
        mock_bedrock.create_model_invocation_job.assert_not_called()


class TestHandlerEmptyQueue:
    """Tests for empty queue scenario."""

    @patch("app.llm.queue.batcher._get_clients")
    def test_handler_empty_queue(self, mock_get_clients):
        """0 messages should result in graceful no-op."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = _make_drain_file(0)

            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                result = handler({"execution_id": "exec-123", "scrapers": []}, None)

        assert result["mode"] == "on-demand"
        assert result["record_count"] == 0


class TestHandlerLogging:
    """Tests for structured logging."""

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher.logger")
    def test_handler_logs_decision_with_structlog(self, mock_logger, mock_get_clients):
        """Should log the batch decision with structured context."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
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
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
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
        assert result["record_count"] == 0
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
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
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
        assert result["record_count"] == 2
        assert result["failed"] == 1

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher.send_to_sqs")
    def test_all_succeed_returns_full_count(self, mock_send, mock_get_clients):
        """All successful re-enqueue should return full count with 0 failures."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
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
        assert result["record_count"] == 5
        assert result["failed"] == 0

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher.send_to_sqs")
    def test_partial_failure_continues_processing_remaining(
        self, mock_send, mock_get_clients
    ):
        """A failure on one record should not stop processing of remaining records."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
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
        assert result["record_count"] == 4
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


# ──────────────────────────────────────────────────────────────────────────
# LLM-2: durable checkpoint-before-delete + crash recovery
# ──────────────────────────────────────────────────────────────────────────

from datetime import timedelta  # noqa: E402

from botocore.exceptions import ClientError  # noqa: E402

from app.llm.queue.batcher import (  # noqa: E402
    _ORPHAN_MIN_AGE_S,
    _recover_orphaned_checkpoints,
)

_DRAIN_KW = {
    "s3_client": None,  # overridden per-test
    "bucket": "test-batch-bucket",
    "recovery_id": "exec-1_req-aaa",
    "source": "scraper",
}


def _fake_s3_body(text: str) -> MagicMock:
    """A StreamingBody-like object whose .read() returns the encoded text."""
    body = MagicMock()
    body.read.return_value = text.encode("utf-8")
    return body


class TestDrainCheckpoint:
    """LLM-2: each drained batch is checkpointed to S3 before the SQS delete."""

    def test_checkpoints_before_delete(self):
        """put_object(recovery/...) must be recorded BEFORE delete_message_batch."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
        calls: list[str] = []
        mock_s3.put_object.side_effect = lambda **k: calls.append(f"put:{k['Key']}")

        def _record_delete(**k):
            calls.append("delete")
            return {"Failed": []}

        mock_sqs.delete_message_batch.side_effect = _record_delete
        mock_sqs.receive_message.side_effect = [
            {"Messages": [_make_sqs_message(f"job-{i}") for i in range(3)]},
            {"Messages": []},
        ]

        kw = {**_DRAIN_KW, "s3_client": mock_s3}
        count, filepath, _ = _drain_staging_queue(
            mock_sqs, "https://sqs/staging.fifo", **kw
        )
        try:
            assert count == 3
            assert calls == [
                "put:recovery/scraper/exec-1_req-aaa/000000.jsonl",
                "delete",
            ], calls
        finally:
            os.unlink(filepath)

    def test_checkpoint_stores_raw_body_verbatim(self):
        """The checkpoint object stores the original msg['Body'] strings verbatim."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
        captured: dict[str, bytes] = {}
        mock_s3.put_object.side_effect = lambda **k: captured.update(
            {k["Key"]: k["Body"]}
        )
        messages = [_make_sqs_message(f"job-{i}") for i in range(2)]
        mock_sqs.receive_message.side_effect = [
            {"Messages": messages},
            {"Messages": []},
        ]

        kw = {**_DRAIN_KW, "s3_client": mock_s3}
        _, filepath, _ = _drain_staging_queue(
            mock_sqs, "https://sqs/staging.fifo", **kw
        )
        try:
            key = "recovery/scraper/exec-1_req-aaa/000000.jsonl"
            lines = captured[key].decode("utf-8").splitlines()
            assert lines == [messages[0]["Body"], messages[1]["Body"]]
        finally:
            os.unlink(filepath)

    def test_poison_pill_excluded_from_checkpoint(self):
        """Malformed messages are DLQ'd, not checkpointed (never replayed)."""
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
        captured: dict[str, bytes] = {}
        mock_s3.put_object.side_effect = lambda **k: captured.update(
            {k["Key"]: k["Body"]}
        )
        valid = _make_sqs_message("job-valid")
        bad = {"MessageId": "bad", "ReceiptHandle": "r-bad", "Body": "NOT JSON {{{"}
        mock_sqs.receive_message.side_effect = [
            {"Messages": [valid, bad]},
            {"Messages": []},
        ]

        kw = {**_DRAIN_KW, "s3_client": mock_s3}
        count, filepath, _ = _drain_staging_queue(
            mock_sqs, "https://sqs/staging.fifo", **kw
        )
        try:
            assert count == 1
            key = "recovery/scraper/exec-1_req-aaa/000000.jsonl"
            lines = captured[key].decode("utf-8").splitlines()
            assert lines == [valid["Body"]]  # poison pill not present
        finally:
            os.unlink(filepath)

    def test_no_delete_when_checkpoint_fails_and_loop_continues(self):
        """A failed checkpoint put must skip that batch's delete and continue.

        The records are neither counted nor deleted (they return via visibility
        timeout) — no loss, and the drain does not abort/wedge.
        """
        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
        # First batch put fails; second batch put succeeds.
        mock_s3.put_object.side_effect = [
            ClientError({"Error": {"Code": "Slow"}}, "PutObject"),
            None,
        ]
        batch1 = [_make_sqs_message("job-a")]
        batch2 = [_make_sqs_message("job-b")]
        mock_sqs.receive_message.side_effect = [
            {"Messages": batch1},
            {"Messages": batch2},
            {"Messages": []},
        ]

        kw = {**_DRAIN_KW, "s3_client": mock_s3}
        count, filepath, _ = _drain_staging_queue(
            mock_sqs, "https://sqs/staging.fifo", **kw
        )
        try:
            # Only batch2 was checkpointed+counted+deleted; batch1 skipped.
            assert count == 1
            assert mock_sqs.delete_message_batch.call_count == 1
            records = _read_drain_file(filepath)
            assert [r["job_id"] for r in records] == ["job-b"]
        finally:
            os.unlink(filepath)

    def test_drain_requires_checkpoint_kwargs(self):
        """The checkpoint params are required — no silent loss-reintroducing no-op."""
        mock_sqs = MagicMock()
        mock_sqs.receive_message.return_value = {"Messages": []}
        with pytest.raises(TypeError):
            _drain_staging_queue(mock_sqs, "https://sqs/staging.fifo")


class TestRecoverOrphanedCheckpoints:
    """LLM-2: orphaned checkpoints from crashed runs are replayed verbatim."""

    def _list_resp(self, key: str, age_s: int) -> dict:
        lm = datetime.now(UTC) - timedelta(seconds=age_s)
        return {"Contents": [{"Key": key, "LastModified": lm}], "IsTruncated": False}

    def test_replays_orphan_verbatim_via_raw_send_message(self):
        """An aged orphan checkpoint replays each stored body verbatim to staging
        via raw send_message (NOT send_to_sqs, which would double-wrap it)."""
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
        mock_sqs = MagicMock()
        key = "recovery/scraper/old-rid/000000.jsonl"
        body_line = _make_sqs_message("job-x")["Body"]
        mock_s3.list_objects_v2.return_value = self._list_resp(
            key, _ORPHAN_MIN_AGE_S + 60
        )
        mock_s3.get_object.return_value = {"Body": _fake_s3_body(body_line + "\n")}

        with patch("app.llm.queue.batcher.send_to_sqs") as mock_send_to_sqs:
            replayed = _recover_orphaned_checkpoints(
                mock_s3,
                mock_sqs,
                "test-batch-bucket",
                "https://sqs/staging.fifo",
                "scraper",
                "exec-1_req-current",
            )

        assert replayed == 1
        mock_send_to_sqs.assert_not_called()  # must NOT re-wrap
        mock_sqs.send_message.assert_called_once()
        sent = mock_sqs.send_message.call_args.kwargs
        assert sent["MessageBody"] == body_line  # byte-identical
        # Group id from nested job.metadata.scraper_id, not a top-level field.
        assert sent["MessageGroupId"] == "test_scraper"
        # FIFO dedup id is the replayed body's job_id.
        assert sent["MessageDeduplicationId"] == "job-x"
        mock_s3.delete_object.assert_called_once_with(
            Bucket="test-batch-bucket", Key=key
        )

    def test_replays_all_objects_and_lines_in_order(self):
        """A recovery_id with multiple checkpoint objects, each multi-line, must
        replay EVERY line across ALL objects (sorted), then delete each object."""
        mock_s3 = MagicMock()
        mock_sqs = MagicMock()
        lm = datetime.now(UTC) - timedelta(seconds=_ORPHAN_MIN_AGE_S + 60)
        k0 = "recovery/scraper/old-rid/000000.jsonl"
        k1 = "recovery/scraper/old-rid/000001.jsonl"
        # Return keys out of order to prove sorting.
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": k1, "LastModified": lm},
                {"Key": k0, "LastModified": lm},
            ],
            "IsTruncated": False,
        }
        b = [_make_sqs_message(f"job-{i}")["Body"] for i in range(3)]
        bodies = {
            k0: _fake_s3_body(b[0] + "\n" + b[1] + "\n"),
            k1: _fake_s3_body(b[2] + "\n"),
        }
        mock_s3.get_object.side_effect = lambda **kw: {"Body": bodies[kw["Key"]]}

        with patch("app.llm.queue.batcher.send_to_sqs"):
            replayed = _recover_orphaned_checkpoints(
                mock_s3,
                mock_sqs,
                "test-batch-bucket",
                "https://sqs/staging.fifo",
                "scraper",
                "exec-1_req-current",
            )

        assert replayed == 3
        sent_bodies = [
            c.kwargs["MessageBody"] for c in mock_sqs.send_message.call_args_list
        ]
        # 000000's two lines first (sorted), then 000001's line.
        assert sent_bodies == [b[0], b[1], b[2]]
        assert mock_s3.delete_object.call_count == 2

    def test_submarine_orphan_replays_under_single_group(self):
        """A submarine-source orphan replays under the constant 'submarine'
        FIFO group (not a scraper_id)."""
        mock_s3 = MagicMock()
        mock_sqs = MagicMock()
        lm = datetime.now(UTC) - timedelta(seconds=_ORPHAN_MIN_AGE_S + 60)
        key = "recovery/submarine/old-rid/000000.jsonl"
        body_line = _make_sqs_message("sub-job")["Body"]
        mock_s3.list_objects_v2.return_value = {
            "Contents": [{"Key": key, "LastModified": lm}],
            "IsTruncated": False,
        }
        mock_s3.get_object.return_value = {"Body": _fake_s3_body(body_line + "\n")}

        replayed = _recover_orphaned_checkpoints(
            mock_s3,
            mock_sqs,
            "test-batch-bucket",
            "https://sqs/submarine-staging.fifo",
            "submarine",
            "exec-1_req-current",
        )

        assert replayed == 1
        assert mock_sqs.send_message.call_args.kwargs["MessageGroupId"] == "submarine"

    def test_recovery_scan_paginates(self):
        """The recovery scan must follow IsTruncated/NextContinuationToken across
        pages (orphans on page 2 are not missed)."""
        mock_s3 = MagicMock()
        mock_sqs = MagicMock()
        lm = datetime.now(UTC) - timedelta(seconds=_ORPHAN_MIN_AGE_S + 60)
        mock_s3.list_objects_v2.side_effect = [
            {
                "Contents": [
                    {"Key": "recovery/scraper/rid-a/000000.jsonl", "LastModified": lm}
                ],
                "IsTruncated": True,
                "NextContinuationToken": "tok-1",
            },
            {
                "Contents": [
                    {"Key": "recovery/scraper/rid-b/000000.jsonl", "LastModified": lm}
                ],
                "IsTruncated": False,
            },
        ]
        body_line = _make_sqs_message("job-p")["Body"]
        mock_s3.get_object.return_value = {"Body": _fake_s3_body(body_line + "\n")}

        replayed = _recover_orphaned_checkpoints(
            mock_s3,
            mock_sqs,
            "test-batch-bucket",
            "https://sqs/staging.fifo",
            "scraper",
            "exec-1_req-current",
        )

        # Both pages' orphans replayed (one record each).
        assert replayed == 2
        second_call = mock_s3.list_objects_v2.call_args_list[1]
        assert second_call.kwargs.get("ContinuationToken") == "tok-1"

    def test_skips_in_flight_prefix_by_age(self):
        """A checkpoint younger than _ORPHAN_MIN_AGE_S belongs to a live run and
        must NOT be replayed (prevents grabbing a concurrent execution's batch)."""
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
        mock_sqs = MagicMock()
        mock_s3.list_objects_v2.return_value = self._list_resp(
            "recovery/scraper/young-rid/000000.jsonl", _ORPHAN_MIN_AGE_S - 60
        )

        replayed = _recover_orphaned_checkpoints(
            mock_s3,
            mock_sqs,
            "test-batch-bucket",
            "https://sqs/staging.fifo",
            "scraper",
            "exec-1_req-current",
        )

        assert replayed == 0
        mock_sqs.send_message.assert_not_called()
        mock_s3.delete_object.assert_not_called()

    def test_excludes_current_recovery_id(self):
        """This invocation's own (current) prefix is never replayed."""
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
        mock_sqs = MagicMock()
        mock_s3.list_objects_v2.return_value = self._list_resp(
            "recovery/scraper/exec-1_req-current/000000.jsonl", _ORPHAN_MIN_AGE_S + 999
        )

        replayed = _recover_orphaned_checkpoints(
            mock_s3,
            mock_sqs,
            "test-batch-bucket",
            "https://sqs/staging.fifo",
            "scraper",
            "exec-1_req-current",
        )

        assert replayed == 0
        mock_sqs.send_message.assert_not_called()

    def test_noop_when_no_orphans(self):
        """Empty recovery prefix → nothing replayed, no errors."""
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
        mock_sqs = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}

        replayed = _recover_orphaned_checkpoints(
            mock_s3,
            mock_sqs,
            "test-batch-bucket",
            "https://sqs/staging.fifo",
            "scraper",
            "exec-1_req-current",
        )

        assert replayed == 0


class TestHandlerCheckpointLifecycle:
    """LLM-2: checkpoint prefix is deleted only on a completed durable handoff."""

    def _clients(self, mock_get_clients):
        mock_sqs, mock_s3, mock_bedrock, mock_dynamodb = (
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )
        # No orphans to recover; cleanup list returns the invocation's objects.
        mock_s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
        mock_get_clients.return_value = (
            mock_sqs,
            mock_s3,
            mock_bedrock,
            mock_dynamodb,
        )
        return mock_sqs, mock_s3, mock_bedrock, mock_dynamodb

    @patch("app.llm.queue.batcher._get_clients")
    def test_batch_path_deletes_prefix_after_dynamodb(self, mock_get_clients):
        """On the batch path, the checkpoint cleanup list happens AFTER the
        DynamoDB metadata write (the commit point)."""
        _, mock_s3, mock_bedrock, mock_dynamodb = self._clients(mock_get_clients)
        order: list[str] = []
        mock_dynamodb.put_item.side_effect = lambda **k: order.append("dynamodb")

        def _list(**k):
            # Distinguish the per-invocation cleanup list (prefix carries the
            # recovery_id, i.e. 4 path segments) from the recovery scan at
            # handler start (prefix recovery/scraper/, 3 segments).
            prefix = k.get("Prefix", "")
            depth = len([p for p in prefix.split("/") if p])
            order.append("cleanup_list" if depth >= 3 else "recovery_scan")
            return {"Contents": [], "IsTruncated": False}

        mock_s3.list_objects_v2.side_effect = _list
        mock_bedrock.create_model_invocation_job.return_value = {
            "jobArn": "arn:aws:bedrock:us-east-1:123:model-invocation-job/t"
        }

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = _make_drain_file(BATCH_THRESHOLD)
            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                handler({"execution_id": "exec-123", "scrapers": []}, None)

        # The cleanup list call for the recovery prefix comes after put_item.
        assert "dynamodb" in order
        assert "cleanup_list" in order
        assert order.index("dynamodb") < order.index("cleanup_list")

    @patch("app.llm.queue.batcher._get_clients")
    def test_crash_before_bedrock_leaves_checkpoint(self, mock_get_clients):
        """If Bedrock submit raises, the checkpoint prefix is NOT deleted."""
        _, mock_s3, mock_bedrock, _ = self._clients(mock_get_clients)
        mock_bedrock.create_model_invocation_job.side_effect = RuntimeError("boom")

        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = _make_drain_file(BATCH_THRESHOLD)
            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                with pytest.raises(RuntimeError):
                    handler({"execution_id": "exec-123", "scrapers": []}, None)

        # No delete_objects on the recovery prefix — checkpoint survives.
        mock_s3.delete_objects.assert_not_called()

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher.send_to_sqs")
    def test_on_demand_deletes_prefix_only_when_all_succeed(
        self, mock_send, mock_get_clients
    ):
        """On-demand cleanup deletes the prefix only on a fully-clean re-enqueue."""
        _, mock_s3, _, _ = self._clients(mock_get_clients)
        # Make cleanup actually call delete_objects when it lists something.
        mock_s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "recovery/scraper/rid/000000.jsonl"}],
            "IsTruncated": False,
        }

        # All succeed → prefix deleted.
        mock_send.return_value = "msg"
        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = _make_drain_file(3)
            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                handler({"execution_id": "e", "scrapers": []}, None)
        assert mock_s3.delete_objects.called

        # Reset; one failure → prefix NOT deleted.
        mock_s3.delete_objects.reset_mock()
        mock_send.side_effect = [RuntimeError("x"), "msg", "msg"]
        with patch("app.llm.queue.batcher._drain_staging_queue") as mock_drain:
            mock_drain.return_value = _make_drain_file(3)
            with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                handler({"execution_id": "e", "scrapers": []}, None)
        mock_s3.delete_objects.assert_not_called()


class TestCheckpointHelpers:
    """LLM-2: unit-level invariants for the checkpoint helpers."""

    def test_delete_checkpoint_prefix_swallows_s3_errors(self):
        """Cleanup is best-effort — an S3 error must not propagate (a leftover
        checkpoint only causes a bounded, idempotent replay, never a failure)."""
        from app.llm.queue.batcher import _delete_checkpoint_prefix

        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.side_effect = RuntimeError("S3 down")
        # Must not raise.
        _delete_checkpoint_prefix(mock_s3, "bucket", "scraper", "rid")

    def test_recovery_id_uses_aws_request_id_not_timestamp(self):
        """The checkpoint recovery_id must derive from context.aws_request_id
        (globally unique per invocation), NOT the second-granularity s3_safe_id
        — otherwise drain-loop re-invocations / retries collide and overwrite
        each other's checkpoints, reintroducing the loss this fix closes."""
        captured = {}

        def _capture_drain(*args, **kwargs):
            captured["recovery_id"] = kwargs["recovery_id"]
            return _make_drain_file(0)

        ctx = MagicMock()
        ctx.aws_request_id = "req-UNIQUE-123"
        ctx.get_remaining_time_in_millis.return_value = 900_000

        with patch("app.llm.queue.batcher._get_clients") as mock_get_clients:
            mock_s3 = MagicMock()
            mock_s3.list_objects_v2.return_value = {
                "Contents": [],
                "IsTruncated": False,
            }
            mock_get_clients.return_value = (
                MagicMock(),
                mock_s3,
                MagicMock(),
                MagicMock(),
            )
            with patch(
                "app.llm.queue.batcher._drain_staging_queue",
                side_effect=_capture_drain,
            ):
                with patch.dict("os.environ", _HANDLER_ENV, clear=False):
                    handler({"execution_id": "arn:...:exec:name:exec-uuid"}, ctx)

        assert "req-UNIQUE-123" in captured["recovery_id"]
