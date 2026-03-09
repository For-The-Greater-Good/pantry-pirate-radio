"""Tests for content store audit fixes (H2 SQS mode dedup)."""

from unittest.mock import MagicMock, patch

import pytest

from app.content_store.store import ContentStore


class TestH2SqsModeDedup:
    """H2: Content store dedup should not break in SQS mode (no Redis)."""

    def _make_store(self, *, redis_url=None, backend=None):
        """Helper to create a ContentStore with mock backend."""
        mock_backend = backend or MagicMock()
        mock_backend.store_path = "/tmp/test"  # noqa: S108
        mock_backend.content_store_path = "/tmp/test/content_store"  # noqa: S108
        return ContentStore(backend=mock_backend, redis_url=redis_url)

    def test_is_sqs_mode_returns_true_without_redis(self):
        """_is_sqs_mode should return True when redis_conn is None."""
        store = self._make_store(redis_url=None)
        assert store._is_sqs_mode() is True

    def test_store_content_skips_job_active_check_in_sqs_mode(self):
        """In SQS mode, store_content should NOT call _is_job_active."""
        mock_backend = MagicMock()
        mock_backend.store_path = "/tmp/test"  # noqa: S108
        mock_backend.content_store_path = "/tmp/test/content_store"  # noqa: S108
        mock_backend.read_result.return_value = None
        mock_backend.index_get_job_id.return_value = "old-job-123"
        mock_backend.content_exists.return_value = False
        mock_backend.write_content.return_value = (
            "/tmp/test/content/ab/abc.json"  # noqa: S108
        )

        store = self._make_store(redis_url=None, backend=mock_backend)

        result = store.store_content("test content", {"scraper_id": "test"})

        # Job ID should NOT have been cleared (since we can't check if active)
        mock_backend.index_clear_job_id.assert_not_called()
        assert result.status == "pending"

    def test_store_content_checks_job_active_with_redis(self):
        """With Redis, store_content SHOULD check _is_job_active and clear stale jobs."""
        mock_backend = MagicMock()
        mock_backend.store_path = "/tmp/test"  # noqa: S108
        mock_backend.content_store_path = "/tmp/test/content_store"  # noqa: S108
        mock_backend.read_result.return_value = None
        mock_backend.index_get_job_id.return_value = "old-job-123"
        mock_backend.content_exists.return_value = False
        mock_backend.write_content.return_value = (
            "/tmp/test/content/ab/abc.json"  # noqa: S108
        )

        store = self._make_store(redis_url=None, backend=mock_backend)
        # Simulate having Redis but with a mock
        mock_redis = MagicMock()
        store.redis_conn = mock_redis

        # Mock _is_job_active to return False (job is not active)
        with patch.object(store, "_is_job_active", return_value=False):
            result = store.store_content("test content", {"scraper_id": "test"})

        # Job ID SHOULD have been cleared since job is not active
        mock_backend.index_clear_job_id.assert_called_once()
        assert result.status == "pending"

    def test_is_job_active_returns_true_without_redis(self):
        """_is_job_active should return True (conservative) without Redis."""
        store = self._make_store(redis_url=None)
        # H2 fix: returns True to prevent clearing job_id
        result = store._is_job_active("some-job-id")
        assert result is True

    def test_completed_content_returned_regardless_of_mode(self):
        """Content with existing results should return 'completed' in any mode."""
        import json

        mock_backend = MagicMock()
        mock_backend.store_path = "/tmp/test"  # noqa: S108
        mock_backend.content_store_path = "/tmp/test/content_store"  # noqa: S108
        mock_backend.read_result.return_value = json.dumps(
            {"result": "processed data", "job_id": "completed-job"}
        )

        store = self._make_store(redis_url=None, backend=mock_backend)

        result = store.store_content("test content", {"scraper_id": "test"})

        assert result.status == "completed"
        assert result.result == "processed data"
