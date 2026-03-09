"""Tests for batch result processor audit fixes (H4 idempotency)."""

import json
from unittest.mock import MagicMock, patch

import pytest


class TestH4IdempotencyCheck:
    """H4: Batch result processor should skip already-processed batches."""

    @patch("app.llm.queue.batch_result_processor._get_clients")
    @patch("app.llm.queue.batch_result_processor._get_batch_metadata")
    @patch.dict(
        "os.environ",
        {
            "BATCH_BUCKET": "test-bucket",
            "VALIDATOR_QUEUE_URL": "https://sqs.../validator.fifo",
            "RECONCILER_QUEUE_URL": "https://sqs.../reconciler.fifo",
            "RECORDER_QUEUE_URL": "https://sqs.../recorder.fifo",
            "LLM_QUEUE_URL": "https://sqs.../llm.fifo",
            "SQS_JOBS_TABLE": "test-jobs-table",
        },
        clear=False,
    )
    def test_skips_already_processed_batch(self, mock_metadata, mock_clients):
        """Handler should return early if batch was already processed."""
        mock_s3 = MagicMock()
        mock_dynamodb = MagicMock()
        mock_clients.return_value = (mock_s3, mock_dynamodb)

        # Simulate ConditionalCheckFailedException (already processed)
        class ConditionalCheckFailedError(Exception):
            def __init__(self):
                self.response = {
                    "Error": {"Code": "ConditionalCheckFailedException"}
                }
                super().__init__("ConditionalCheckFailedException")

        mock_dynamodb.update_item.side_effect = ConditionalCheckFailedError()

        from app.llm.queue.batch_result_processor import handler

        result = handler(
            {
                "detail": {
                    "batchJobArn": "arn:aws:bedrock:...:job/test-123",
                    "status": "Completed",
                }
            },
            None,
        )

        assert result["status"] == "already_processed"
        # Should NOT have fetched metadata or processed records
        mock_metadata.assert_not_called()

    @patch("app.llm.queue.batch_result_processor._get_clients")
    @patch("app.llm.queue.batch_result_processor._get_batch_metadata")
    @patch("app.llm.queue.batch_result_processor._read_output_jsonl")
    @patch.dict(
        "os.environ",
        {
            "BATCH_BUCKET": "test-bucket",
            "VALIDATOR_QUEUE_URL": "https://sqs.../validator.fifo",
            "RECONCILER_QUEUE_URL": "https://sqs.../reconciler.fifo",
            "RECORDER_QUEUE_URL": "https://sqs.../recorder.fifo",
            "LLM_QUEUE_URL": "https://sqs.../llm.fifo",
            "SQS_JOBS_TABLE": "test-jobs-table",
        },
        clear=False,
    )
    def test_processes_new_batch(self, mock_read, mock_metadata, mock_clients):
        """Handler should process batch if not already processed."""
        mock_s3 = MagicMock()
        mock_dynamodb = MagicMock()
        mock_clients.return_value = (mock_s3, mock_dynamodb)

        # update_item succeeds (no ConditionalCheckFailedError = first processing)
        mock_dynamodb.update_item.return_value = {}

        mock_metadata.return_value = {
            "output_key_prefix": "output/test/",
            "original_jobs": {},
        }
        mock_read.return_value = ([], 0)  # No output records

        from app.llm.queue.batch_result_processor import handler

        result = handler(
            {
                "detail": {
                    "batchJobArn": "arn:aws:bedrock:...:job/test-123",
                    "status": "Completed",
                }
            },
            None,
        )

        assert result["status"] == "Completed"
        assert result["processed"] == 0
