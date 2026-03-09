"""Tests for S3+DynamoDB content store backend - index operations.

Tests for DynamoDB index operations: index_has_content, index_insert_content,
index_update_result, index_get_job_id, index_set_job_id, index_clear_job_id.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


class TestS3ContentStoreBackendIndexOperations:
    """Tests for S3ContentStoreBackend DynamoDB index operations."""

    @pytest.fixture
    def backend(self):
        """Create S3ContentStoreBackend for testing."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        b = S3ContentStoreBackend(
            s3_bucket="test-bucket",
            dynamodb_table="test-table",
        )
        b._initialized = True
        return b

    def test_index_has_content_returns_false_initially(self, backend):
        """index_has_content() should return False for new hash."""
        mock_dynamodb = MagicMock()
        content_hash = "abc123" + "0" * 58
        mock_dynamodb.get_item.return_value = {}  # No Item key = not found

        with patch.object(backend, "_get_dynamodb_client", return_value=mock_dynamodb):
            result = backend.index_has_content(content_hash)

        assert result is False

    def test_index_has_content_returns_true_for_existing(self, backend):
        """index_has_content() should return True for existing hash."""
        mock_dynamodb = MagicMock()
        content_hash = "abc123" + "0" * 58
        mock_dynamodb.get_item.return_value = {
            "Item": {"content_hash": {"S": content_hash}}
        }

        with patch.object(backend, "_get_dynamodb_client", return_value=mock_dynamodb):
            result = backend.index_has_content(content_hash)

        assert result is True

    def test_index_insert_content_creates_item(self, backend):
        """index_insert_content() should create DynamoDB item."""
        mock_dynamodb = MagicMock()
        content_hash = "abc123" + "0" * 58
        content_path = "s3://test-bucket/content/ab/abc123..."
        created_at = datetime.utcnow()

        with patch.object(backend, "_get_dynamodb_client", return_value=mock_dynamodb):
            backend.index_insert_content(content_hash, content_path, created_at)

        mock_dynamodb.put_item.assert_called_once()
        call_args = mock_dynamodb.put_item.call_args
        assert call_args.kwargs["TableName"] == "test-table"
        assert "content_hash" in call_args.kwargs["Item"]

    def test_index_update_result_updates_item(self, backend):
        """index_update_result() should update DynamoDB item."""
        mock_dynamodb = MagicMock()
        content_hash = "abc123" + "0" * 58
        result_path = "s3://test-bucket/results/ab/abc123..."
        job_id = "job-456"
        processed_at = datetime.utcnow()

        with patch.object(backend, "_get_dynamodb_client", return_value=mock_dynamodb):
            backend.index_update_result(content_hash, result_path, job_id, processed_at)

        mock_dynamodb.update_item.assert_called_once()

    def test_index_get_job_id_returns_none_initially(self, backend):
        """index_get_job_id() should return None for new content."""
        mock_dynamodb = MagicMock()
        content_hash = "abc123" + "0" * 58
        mock_dynamodb.get_item.return_value = {}

        with patch.object(backend, "_get_dynamodb_client", return_value=mock_dynamodb):
            result = backend.index_get_job_id(content_hash)

        assert result is None

    def test_index_get_job_id_returns_job_id(self, backend):
        """index_get_job_id() should return stored job_id."""
        mock_dynamodb = MagicMock()
        content_hash = "abc123" + "0" * 58
        mock_dynamodb.get_item.return_value = {
            "Item": {
                "content_hash": {"S": content_hash},
                "job_id": {"S": "job-789"},
            }
        }

        with patch.object(backend, "_get_dynamodb_client", return_value=mock_dynamodb):
            result = backend.index_get_job_id(content_hash)

        assert result == "job-789"

    def test_index_set_job_id_updates_item(self, backend):
        """index_set_job_id() should update job_id in DynamoDB."""
        mock_dynamodb = MagicMock()
        content_hash = "abc123" + "0" * 58
        job_id = "job-123"

        with patch.object(backend, "_get_dynamodb_client", return_value=mock_dynamodb):
            backend.index_set_job_id(content_hash, job_id)

        mock_dynamodb.update_item.assert_called_once()

    def test_index_clear_job_id_removes_job_id(self, backend):
        """index_clear_job_id() should remove job_id from item."""
        mock_dynamodb = MagicMock()
        content_hash = "abc123" + "0" * 58

        with patch.object(backend, "_get_dynamodb_client", return_value=mock_dynamodb):
            backend.index_clear_job_id(content_hash)

        mock_dynamodb.update_item.assert_called_once()
