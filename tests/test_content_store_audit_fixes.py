"""Tests for content store audit fixes (H2 SQS mode dedup)."""

from unittest.mock import MagicMock, patch

import pytest

from app.content_store.store import ContentStore
from datetime import UTC


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
        # Legacy link (no timestamp) → not stale → never cleared in SQS mode.
        mock_backend.index_get_job_linked_at.return_value = None
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


class TestContent1StaleJobLink:
    """content-1: SQS-mode stale job-link clearing.

    In SQS mode we can't probe RQ for job liveness, so a job that failed
    before writing a result used to dedup-skip its content forever. The fix
    clears a job_id once it has outlived a safe processing threshold without a
    result (age-based), while leaving recent (in-flight) links alone so the
    124k re-enqueue storm is never reproduced.
    """

    def _make_store(self, *, redis_url=None, backend=None, **kwargs):
        mock_backend = backend or MagicMock()
        mock_backend.store_path = "/tmp/test"  # noqa: S108
        mock_backend.content_store_path = "/tmp/test/content_store"  # noqa: S108
        return ContentStore(backend=mock_backend, redis_url=redis_url, **kwargs)

    @staticmethod
    def _pending_backend(linked_at):
        """A mock backend with a pending (no-result) job linked at `linked_at`."""
        mock_backend = MagicMock()
        mock_backend.store_path = "/tmp/test"  # noqa: S108
        mock_backend.content_store_path = "/tmp/test/content_store"  # noqa: S108
        mock_backend.read_result.return_value = None
        mock_backend.index_get_job_id.return_value = "old-job-123"
        mock_backend.index_get_job_linked_at.return_value = linked_at
        mock_backend.content_exists.return_value = True
        return mock_backend

    def test_stale_sqs_link_with_no_result_is_cleared(self):
        """A job linked longer ago than the threshold is cleared → re-enqueue."""
        from datetime import datetime, timedelta, timezone

        old = datetime.now(UTC) - timedelta(hours=200)
        mock_backend = self._pending_backend(old)
        store = self._make_store(redis_url=None, backend=mock_backend)  # 72h default

        result = store.store_content("test content", {"scraper_id": "test"})

        mock_backend.index_clear_job_id.assert_called_once()
        assert result.job_id is None
        assert result.status == "pending"

    def test_recent_sqs_link_is_not_cleared(self):
        """A recently-linked (in-flight) job is preserved → still dedup-skipped."""
        from datetime import datetime, timedelta, timezone

        recent = datetime.now(UTC) - timedelta(hours=1)
        mock_backend = self._pending_backend(recent)
        store = self._make_store(redis_url=None, backend=mock_backend)  # 72h default

        result = store.store_content("test content", {"scraper_id": "test"})

        mock_backend.index_clear_job_id.assert_not_called()
        assert result.job_id == "old-job-123"

    def test_missing_linked_at_is_not_cleared(self):
        """Legacy links with no timestamp are NOT cleared (storm-safe)."""
        mock_backend = self._pending_backend(None)
        store = self._make_store(redis_url=None, backend=mock_backend)

        result = store.store_content("test content", {"scraper_id": "test"})

        mock_backend.index_clear_job_id.assert_not_called()
        assert result.job_id == "old-job-123"

    def test_configurable_threshold(self):
        """An explicit threshold overrides the default."""
        from datetime import datetime, timedelta, timezone

        linked = datetime.now(UTC) - timedelta(hours=10)
        mock_backend = self._pending_backend(linked)
        # 5h threshold → a 10h-old link is stale.
        store = self._make_store(
            redis_url=None, backend=mock_backend, stale_job_threshold_hours=5
        )

        result = store.store_content("test content", {"scraper_id": "test"})

        mock_backend.index_clear_job_id.assert_called_once()
        assert result.job_id is None

    def test_stale_link_with_result_returns_completed(self):
        """A result short-circuits before any staleness check."""
        import json
        from datetime import datetime, timedelta, timezone

        old = datetime.now(UTC) - timedelta(hours=200)
        mock_backend = self._pending_backend(old)
        mock_backend.read_result.return_value = json.dumps(
            {"result": "processed data", "job_id": "old-job-123"}
        )
        store = self._make_store(redis_url=None, backend=mock_backend)

        result = store.store_content("test content", {"scraper_id": "test"})

        assert result.status == "completed"
        mock_backend.index_clear_job_id.assert_not_called()
        mock_backend.index_get_job_linked_at.assert_not_called()

    def test_redis_mode_ignores_link_age(self):
        """In Redis mode staleness is decided by RQ liveness, not link age."""
        from datetime import datetime, timedelta, timezone

        old = datetime.now(UTC) - timedelta(hours=200)
        mock_backend = self._pending_backend(old)
        store = self._make_store(redis_url=None, backend=mock_backend)
        store.redis_conn = MagicMock()  # simulate Redis present

        with patch.object(store, "_is_job_active", return_value=True):
            result = store.store_content("test content", {"scraper_id": "test"})

        # Live RQ job → not cleared; link-age path must not be consulted.
        mock_backend.index_clear_job_id.assert_not_called()
        mock_backend.index_get_job_linked_at.assert_not_called()
        assert result.job_id == "old-job-123"
