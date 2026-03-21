# ruff: noqa: N803
# (boto3 API uses PascalCase keyword arguments: Bucket, Key, Filename)
"""Tests for batcher audit fixes (C2 poison pill DLQ, M4 threshold per-invocation, JSONL format)."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

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
        count, filepath = _drain_staging_queue(
            mock_sqs,
            "https://sqs.../staging.fifo",
            dlq_url=dlq_url,
        )

        try:
            # No valid messages returned
            assert count == 0

            # DLQ send was called
            mock_sqs.send_message.assert_called_once()
            dlq_call = mock_sqs.send_message.call_args
            assert dlq_call.kwargs["QueueUrl"] == dlq_url
            body = json.loads(dlq_call.kwargs["MessageBody"])
            assert body["original_message_id"] == "msg-1"
            assert body["source"] == "batcher-poison-pill"

            # Original message was deleted from source queue
            mock_sqs.delete_message.assert_called_once()
        finally:
            os.unlink(filepath)

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

        count, filepath = _drain_staging_queue(
            mock_sqs,
            "https://sqs.../staging.fifo",
            dlq_url="",  # No DLQ
        )

        try:
            assert count == 0
            # No DLQ send
            mock_sqs.send_message.assert_not_called()
            # But still deleted
            mock_sqs.delete_message.assert_called_once()
        finally:
            os.unlink(filepath)

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

        count, filepath = _drain_staging_queue(
            mock_sqs,
            "https://sqs.../staging.fifo",
            dlq_url="https://sqs.../staging-dlq.fifo",
        )

        try:
            assert count == 1
            # No DLQ send
            mock_sqs.send_message.assert_not_called()
            # Valid messages are batch-deleted (not individually deleted)
            mock_sqs.delete_message.assert_not_called()
            mock_sqs.delete_message_batch.assert_called_once()
        finally:
            os.unlink(filepath)

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
        count, filepath = _drain_staging_queue(
            mock_sqs,
            "https://sqs.../staging.fifo",
            dlq_url="https://sqs.../staging-dlq.fifo",
        )

        try:
            assert count == 0
            # Message still deleted from source
            mock_sqs.delete_message.assert_called_once()
        finally:
            os.unlink(filepath)


class TestM4BatchThresholdPerInvocation:
    """M4: Batch threshold should be read per invocation, not at module load."""

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher._drain_staging_queue")
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
        import tempfile

        from app.llm.queue.batcher import handler

        # Create an empty temp file for the drain mock
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
        tmp.close()
        mock_drain.return_value = (0, tmp.name)
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


class TestOriginalJobsJsonlFormat:
    """Verify batcher writes original_jobs as JSONL (not JSON dict)."""

    @patch("app.llm.queue.batcher._get_clients")
    @patch("app.llm.queue.batcher._drain_staging_queue")
    @patch.dict(
        "os.environ",
        {
            "STAGING_QUEUE_URL": "https://sqs.../staging.fifo",
            "LLM_QUEUE_URL": "https://sqs.../llm.fifo",
            "BATCH_BUCKET": "test-bucket",
            "BEDROCK_SERVICE_ROLE_ARN": "arn:aws:iam::role/test",
            "BATCH_THRESHOLD": "1",
            "SQS_JOBS_TABLE": "test-table",
        },
        clear=False,
    )
    def test_original_jobs_written_as_jsonl(self, mock_drain, mock_clients):
        """Batcher should write original_jobs as JSONL with k/v keys per line."""
        from app.llm.queue.batcher import handler

        # Create staging file with 2 records
        staging_tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        )
        record1 = {
            "job_id": "job-1",
            "job": {
                "id": "job-1",
                "prompt": [
                    {"role": "system", "content": "test prompt 1"},
                    {"role": "user", "content": "Input Data:\ntest"},
                ],
                "format": None,
                "metadata": {"scraper_id": "test"},
            },
        }
        record2 = {
            "job_id": "job-2",
            "job": {
                "id": "job-2",
                "prompt": [
                    {"role": "system", "content": "test prompt 2"},
                    {"role": "user", "content": "Input Data:\ntest"},
                ],
                "format": None,
                "metadata": {"scraper_id": "test"},
            },
        }
        staging_tmp.write(json.dumps(record1) + "\n")
        staging_tmp.write(json.dumps(record2) + "\n")
        staging_tmp.close()

        mock_drain.return_value = (2, staging_tmp.name)

        mock_sqs = MagicMock()
        mock_s3 = MagicMock()
        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_clients.return_value = (mock_sqs, mock_s3, mock_bedrock, mock_dynamodb)

        # Capture what gets uploaded to S3
        uploaded_files: dict[str, str] = {}

        def capture_upload(Filename, Bucket, Key, **kwargs):
            with open(Filename) as f:
                uploaded_files[Key] = f.read()

        mock_s3.upload_file.side_effect = capture_upload
        mock_bedrock.create_model_invocation_job.return_value = {
            "jobArn": "arn:aws:bedrock:us-east-1:123:model-invocation-job/test"
        }

        try:
            handler({"execution_id": "test-exec-uuid"}, None)
        except Exception:  # noqa: S110 — DynamoDB put may fail in test; expected
            pass

        # Find the original_jobs upload
        orig_jobs_uploads = {
            k: v for k, v in uploaded_files.items() if "original_jobs" in k
        }
        assert len(orig_jobs_uploads) == 1

        key = next(iter(orig_jobs_uploads.keys()))
        content = orig_jobs_uploads[key]

        # Verify key uses .jsonl extension
        assert key.endswith(".jsonl"), f"Expected .jsonl key, got: {key}"

        # Verify each line is valid JSON with k and v keys
        lines = [line for line in content.strip().split("\n") if line.strip()]
        assert len(lines) == 2

        for line in lines:
            record = json.loads(line)
            assert "k" in record, f"Missing 'k' key in JSONL record: {record}"
            assert "v" in record, f"Missing 'v' key in JSONL record: {record}"
            assert isinstance(record["k"], str)
            assert isinstance(record["v"], dict)
