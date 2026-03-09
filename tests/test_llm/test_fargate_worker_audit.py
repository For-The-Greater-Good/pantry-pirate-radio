"""Tests for FargateWorker audit fixes (H5 heartbeat retry)."""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.llm.queue.fargate_worker import _HeartbeatThread


class TestH5HeartbeatRetry:
    """H5: Heartbeat thread should retry on transient failure before giving up."""

    @patch("app.llm.queue.fargate_worker.time")
    def test_heartbeat_retries_before_giving_up(self, mock_time):
        """Heartbeat should retry _MAX_RETRIES times before setting failed."""
        mock_time.sleep = MagicMock()
        call_count = 0

        def always_fail():
            nonlocal call_count
            call_count += 1
            raise Exception("transient error")

        heartbeat = _HeartbeatThread(interval=0.5, callback=always_fail)
        heartbeat.start()

        # Wait for thread to complete (retries are instant due to mock)
        heartbeat._thread.join(timeout=10)
        heartbeat.stop()

        assert heartbeat.failed is True
        # Should have retried _MAX_RETRIES times
        assert call_count == _HeartbeatThread._MAX_RETRIES

    def test_heartbeat_recovers_after_transient_failure(self):
        """Heartbeat should continue if callback succeeds after retry."""
        call_count = 0

        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("transient")
            # Succeed on subsequent calls

        heartbeat = _HeartbeatThread(interval=0.5, callback=fail_then_succeed)
        heartbeat.start()

        # Wait for multiple intervals
        time.sleep(3)
        heartbeat.stop()

        assert heartbeat.failed is False
        # Should have been called multiple times (retries + successful calls)
        assert call_count >= 2

    def test_heartbeat_starts_with_failed_false(self):
        """Heartbeat should start with failed=False."""
        heartbeat = _HeartbeatThread(interval=1.0, callback=lambda: None)
        assert heartbeat.failed is False

    def test_heartbeat_stop_is_idempotent(self):
        """Stopping a heartbeat multiple times should not raise."""
        heartbeat = _HeartbeatThread(interval=1.0, callback=lambda: None)
        heartbeat.start()
        heartbeat.stop()
        heartbeat.stop()  # Second stop should be safe


class TestM6ValidatorLazyImport:
    """M6: Validator __init__.py should provide lazy import factories."""

    def test_get_process_validation_job_is_callable(self):
        """get_process_validation_job should return the function."""
        from app.validator import get_process_validation_job

        fn = get_process_validation_job()
        assert callable(fn)

    def test_get_enqueue_to_reconciler_is_callable(self):
        """get_enqueue_to_reconciler should return the function."""
        from app.validator import get_enqueue_to_reconciler

        fn = get_enqueue_to_reconciler()
        assert callable(fn)

    def test_module_imports_without_redis(self):
        """Importing app.validator should not crash in SQS mode (no Redis)."""
        # This test verifies the lazy import pattern works
        import app.validator

        assert hasattr(app.validator, "get_process_validation_job")
        assert hasattr(app.validator, "get_enqueue_to_reconciler")
        assert hasattr(app.validator, "is_validator_enabled")
