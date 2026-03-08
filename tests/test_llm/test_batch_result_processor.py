"""Tests for the Batch Result Processor Lambda handler."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, call, patch

import pytest

from app.llm.queue.batch_result_processor import handler


def _make_batch_output_record(
    record_id: str,
    success: bool = True,
    text: str = '{"name": "Food Bank"}',
) -> dict:
    """Create a mock Bedrock batch output record."""
    if success:
        return {
            "recordId": record_id,
            "modelOutput": {
                "output": {
                    "message": {
                        "content": [
                            {
                                "toolUse": {
                                    "name": "structured_output",
                                    "input": json.loads(text),
                                    "toolUseId": "tool-123",
                                }
                            }
                        ]
                    }
                },
                "stopReason": "tool_use",
                "usage": {"inputTokens": 100, "outputTokens": 50},
            },
        }
    else:
        return {
            "recordId": record_id,
            "error": {
                "errorCode": "InternalError",
                "errorMessage": "Model invocation failed",
            },
        }


def _make_original_job(job_id: str) -> dict:
    """Create a mock original job record (as stored in DynamoDB)."""
    return {
        "job_id": job_id,
        "job": {
            "id": job_id,
            "prompt": "Align this data",
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


def _make_event(
    status: str = "Completed",
    job_arn: str = "arn:aws:bedrock:us-east-1:123:model-invocation-job/test",
) -> dict:
    """Create an EventBridge event for batch job state change."""
    return {
        "detail-type": "Batch Inference Job State Change",
        "source": "aws.bedrock",
        "detail": {
            "batchJobArn": job_arn,
            "status": status,
        },
    }


class TestCompletedRouting:
    """Tests for successful batch job completion routing."""

    @patch("app.llm.queue.batch_result_processor._get_clients")
    @patch("app.llm.queue.batch_result_processor.send_to_sqs")
    @patch("app.llm.queue.batch_result_processor.settings")
    def test_completed_routes_to_validator_queue(
        self, mock_settings, mock_send, mock_get_clients
    ):
        """Successful records route to validator when enabled."""
        mock_settings.VALIDATOR_ENABLED = True
        mock_s3 = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_s3, mock_dynamodb)

        job_arn = "arn:aws:bedrock:us-east-1:123:model-invocation-job/test"
        original_jobs = {"job-1": _make_original_job("job-1")}

        # DynamoDB returns batch metadata with original_jobs_key
        mock_dynamodb.get_item.return_value = {
            "Item": {
                "output_key_prefix": {"S": "output/exec-123/"},
                "original_jobs_key": {"S": "input/exec-123/original_jobs.json"},
            }
        }

        # S3 returns original_jobs and output JSONL
        output_record = _make_batch_output_record("job-1")

        def s3_get_object(**kwargs):
            key = kwargs.get("Key", "")
            if "original_jobs" in key:
                return {"Body": MagicMock(read=lambda: json.dumps(original_jobs).encode())}
            return {"Body": MagicMock(read=lambda: json.dumps(output_record).encode())}

        mock_s3.get_object.side_effect = s3_get_object
        mock_s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "output/exec-123/output.jsonl.out"}]
        }

        event = _make_event("Completed", job_arn)
        with patch.dict(
            "os.environ",
            {
                "VALIDATOR_QUEUE_URL": "https://sqs/validator.fifo",
                "RECONCILER_QUEUE_URL": "https://sqs/reconciler.fifo",
                "RECORDER_QUEUE_URL": "https://sqs/recorder.fifo",
                "LLM_QUEUE_URL": "https://sqs/llm.fifo",
                "BATCH_BUCKET": "batch-bucket",
                "SQS_JOBS_TABLE": "jobs-table",
            },
        ):
            result = handler(event, None)

        assert result["processed"] == 1
        # Should send to validator queue (not reconciler)
        validator_calls = [
            c
            for c in mock_send.call_args_list
            if c[1].get("queue_url") == "https://sqs/validator.fifo"
            or (c[0] and c[0][0] == "https://sqs/validator.fifo")
        ]
        assert len(validator_calls) >= 1

    @patch("app.llm.queue.batch_result_processor._get_clients")
    @patch("app.llm.queue.batch_result_processor.send_to_sqs")
    @patch("app.llm.queue.batch_result_processor.settings")
    def test_completed_routes_to_reconciler_when_validator_disabled(
        self, mock_settings, mock_send, mock_get_clients
    ):
        """Successful records route to reconciler when validator disabled."""
        mock_settings.VALIDATOR_ENABLED = False
        mock_s3 = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_s3, mock_dynamodb)

        job_arn = "arn:aws:bedrock:us-east-1:123:model-invocation-job/test"
        original_jobs = {"job-1": _make_original_job("job-1")}

        mock_dynamodb.get_item.return_value = {
            "Item": {
                "output_key_prefix": {"S": "output/exec-123/"},
                "original_jobs_key": {"S": "input/exec-123/original_jobs.json"},
            }
        }

        output_record = _make_batch_output_record("job-1")

        def s3_get_object(**kwargs):
            key = kwargs.get("Key", "")
            if "original_jobs" in key:
                return {"Body": MagicMock(read=lambda: json.dumps(original_jobs).encode())}
            return {"Body": MagicMock(read=lambda: json.dumps(output_record).encode())}

        mock_s3.get_object.side_effect = s3_get_object
        mock_s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "output/exec-123/output.jsonl.out"}]
        }

        event = _make_event("Completed", job_arn)
        with patch.dict(
            "os.environ",
            {
                "VALIDATOR_QUEUE_URL": "https://sqs/validator.fifo",
                "RECONCILER_QUEUE_URL": "https://sqs/reconciler.fifo",
                "RECORDER_QUEUE_URL": "https://sqs/recorder.fifo",
                "LLM_QUEUE_URL": "https://sqs/llm.fifo",
                "BATCH_BUCKET": "batch-bucket",
                "SQS_JOBS_TABLE": "jobs-table",
            },
        ):
            result = handler(event, None)

        reconciler_calls = [
            c
            for c in mock_send.call_args_list
            if c[1].get("queue_url") == "https://sqs/reconciler.fifo"
            or (c[0] and c[0][0] == "https://sqs/reconciler.fifo")
        ]
        assert len(reconciler_calls) >= 1

    @patch("app.llm.queue.batch_result_processor._get_clients")
    @patch("app.llm.queue.batch_result_processor.send_to_sqs")
    @patch("app.llm.queue.batch_result_processor.settings")
    def test_completed_sends_to_recorder_queue(
        self, mock_settings, mock_send, mock_get_clients
    ):
        """Successful records also send a copy to recorder queue."""
        mock_settings.VALIDATOR_ENABLED = True
        mock_s3 = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_s3, mock_dynamodb)

        original_jobs = {"job-1": _make_original_job("job-1")}

        mock_dynamodb.get_item.return_value = {
            "Item": {
                "output_key_prefix": {"S": "output/exec-123/"},
                "original_jobs_key": {"S": "input/exec-123/original_jobs.json"},
            }
        }

        output_record = _make_batch_output_record("job-1")

        def s3_get_object(**kwargs):
            key = kwargs.get("Key", "")
            if "original_jobs" in key:
                return {"Body": MagicMock(read=lambda: json.dumps(original_jobs).encode())}
            return {"Body": MagicMock(read=lambda: json.dumps(output_record).encode())}

        mock_s3.get_object.side_effect = s3_get_object
        mock_s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "output/exec-123/output.jsonl.out"}]
        }

        event = _make_event("Completed")
        with patch.dict(
            "os.environ",
            {
                "VALIDATOR_QUEUE_URL": "https://sqs/validator.fifo",
                "RECONCILER_QUEUE_URL": "https://sqs/reconciler.fifo",
                "RECORDER_QUEUE_URL": "https://sqs/recorder.fifo",
                "LLM_QUEUE_URL": "https://sqs/llm.fifo",
                "BATCH_BUCKET": "batch-bucket",
                "SQS_JOBS_TABLE": "jobs-table",
            },
        ):
            handler(event, None)

        recorder_calls = [
            c
            for c in mock_send.call_args_list
            if c[1].get("queue_url") == "https://sqs/recorder.fifo"
            or (c[0] and c[0][0] == "https://sqs/recorder.fifo")
        ]
        assert len(recorder_calls) >= 1


class TestFailureHandling:
    """Tests for batch job failure handling."""

    @patch("app.llm.queue.batch_result_processor._get_clients")
    @patch("app.llm.queue.batch_result_processor.send_to_sqs")
    def test_failed_reenqueues_all_to_sqs(self, mock_send, mock_get_clients):
        """Full failure should re-enqueue all original jobs to LLM queue."""
        mock_s3 = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_s3, mock_dynamodb)
        mock_send.return_value = "msg-id"

        original_jobs = {
            "job-1": _make_original_job("job-1"),
            "job-2": _make_original_job("job-2"),
        }
        mock_dynamodb.get_item.return_value = {
            "Item": {
                "output_key_prefix": {"S": "output/exec-123/"},
                "original_jobs_key": {"S": "input/exec-123/original_jobs.json"},
            }
        }
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: json.dumps(original_jobs).encode())
        }

        event = _make_event("Failed")
        with patch.dict(
            "os.environ",
            {
                "VALIDATOR_QUEUE_URL": "https://sqs/validator.fifo",
                "RECONCILER_QUEUE_URL": "https://sqs/reconciler.fifo",
                "RECORDER_QUEUE_URL": "https://sqs/recorder.fifo",
                "LLM_QUEUE_URL": "https://sqs/llm.fifo",
                "BATCH_BUCKET": "batch-bucket",
                "SQS_JOBS_TABLE": "jobs-table",
            },
        ):
            result = handler(event, None)

        assert result["requeued"] == 2
        # All should go to LLM queue
        llm_calls = [
            c
            for c in mock_send.call_args_list
            if c[1].get("queue_url") == "https://sqs/llm.fifo"
        ]
        assert len(llm_calls) == 2

    @patch("app.llm.queue.batch_result_processor._get_clients")
    @patch("app.llm.queue.batch_result_processor.send_to_sqs")
    @patch("app.llm.queue.batch_result_processor.settings")
    def test_per_record_error_reenqueues(
        self, mock_settings, mock_send, mock_get_clients
    ):
        """Individual error records should be re-enqueued to LLM queue."""
        mock_settings.VALIDATOR_ENABLED = True
        mock_s3 = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_s3, mock_dynamodb)
        mock_send.return_value = "msg-id"

        original_jobs = {
            "job-1": _make_original_job("job-1"),
            "job-2": _make_original_job("job-2"),
        }
        mock_dynamodb.get_item.return_value = {
            "Item": {
                "output_key_prefix": {"S": "output/exec-123/"},
                "original_jobs_key": {"S": "input/exec-123/original_jobs.json"},
            }
        }

        # One success, one error
        success_record = _make_batch_output_record("job-1", success=True)
        error_record = _make_batch_output_record("job-2", success=False)
        jsonl_output = json.dumps(success_record) + "\n" + json.dumps(error_record)

        call_count = [0]

        def s3_get_object(**kwargs):
            key = kwargs.get("Key", "")
            if "original_jobs" in key:
                return {"Body": MagicMock(read=lambda: json.dumps(original_jobs).encode())}
            return {"Body": MagicMock(read=lambda: jsonl_output.encode())}

        mock_s3.get_object.side_effect = s3_get_object
        mock_s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "output/exec-123/output.jsonl.out"}]
        }

        event = _make_event("PartiallyCompleted")
        with patch.dict(
            "os.environ",
            {
                "VALIDATOR_QUEUE_URL": "https://sqs/validator.fifo",
                "RECONCILER_QUEUE_URL": "https://sqs/reconciler.fifo",
                "RECORDER_QUEUE_URL": "https://sqs/recorder.fifo",
                "LLM_QUEUE_URL": "https://sqs/llm.fifo",
                "BATCH_BUCKET": "batch-bucket",
                "SQS_JOBS_TABLE": "jobs-table",
            },
        ):
            result = handler(event, None)

        assert result["processed"] == 1
        assert result["errors"] == 1

        # Error record should go to LLM queue for retry
        llm_calls = [
            c
            for c in mock_send.call_args_list
            if c[1].get("queue_url") == "https://sqs/llm.fifo"
        ]
        assert len(llm_calls) == 1


class TestLogging:
    """Tests for structured logging."""

    @patch("app.llm.queue.batch_result_processor._get_clients")
    @patch("app.llm.queue.batch_result_processor.send_to_sqs")
    @patch("app.llm.queue.batch_result_processor.logger")
    def test_logs_with_structlog(self, mock_logger, mock_send, mock_get_clients):
        """Should log with structured context fields."""
        mock_s3 = MagicMock()
        mock_dynamodb = MagicMock()
        mock_get_clients.return_value = (mock_s3, mock_dynamodb)
        mock_send.return_value = "msg-id"

        original_jobs = {"job-1": _make_original_job("job-1")}
        mock_dynamodb.get_item.return_value = {
            "Item": {
                "output_key_prefix": {"S": "output/exec-123/"},
                "original_jobs_key": {"S": "input/exec-123/original_jobs.json"},
            }
        }
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: json.dumps(original_jobs).encode())
        }

        event = _make_event("Failed")
        with patch.dict(
            "os.environ",
            {
                "VALIDATOR_QUEUE_URL": "",
                "RECONCILER_QUEUE_URL": "",
                "RECORDER_QUEUE_URL": "",
                "LLM_QUEUE_URL": "https://sqs/llm.fifo",
                "BATCH_BUCKET": "batch-bucket",
                "SQS_JOBS_TABLE": "jobs-table",
            },
        ):
            handler(event, None)

        # Verify structlog was called with batch_job_arn
        assert any(
            "batch_job_arn" in str(c) or "batch_result" in str(c)
            for c in mock_logger.info.call_args_list
        )
