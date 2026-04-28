"""Tests for the recovery script that clears stuck content-store entries.

This script issues delete_item against a production DynamoDB table — a regression
where --dry-run silently deletes is irreversible, so the safety gates are
load-bearing tests, not optional.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

# Required env vars for backend construction. Must be set before importing
# the script's `main` so its argparse + backend builder can run.
_BACKEND_ENV = {
    "CONTENT_STORE_S3_BUCKET": "test-content-bucket",
    "CONTENT_STORE_DYNAMODB_TABLE": "test-content-index",
    "AWS_DEFAULT_REGION": "us-east-1",
}


def _entries(n: int) -> list[dict]:
    return [
        {
            "content_hash": f"h{i:06x}",
            "created_at": "2026-04-26T01:00:00+00:00",
            "content_path": f"s3://b/h{i:06x}",
            "status": "pending",
            "job_id": None,
        }
        for i in range(n)
    ]


def _run(args: list[str]) -> int:
    from scripts.recovery import clear_failed_executions as mod

    with patch.object(mod.sys, "argv", ["clear_failed_executions", *args]):
        return mod.main()


@pytest.fixture
def mock_backend():
    """Patch _build_backend so tests don't construct real boto3 clients."""
    backend = MagicMock()
    backend.index_scan_pending_since.return_value = []
    backend.index_delete_entry.return_value = None
    with patch.dict(os.environ, _BACKEND_ENV, clear=False):
        with patch(
            "scripts.recovery.clear_failed_executions._build_backend",
            return_value=backend,
        ):
            yield backend


class TestDryRunSafety:
    """--dry-run must NEVER call index_delete_entry, period."""

    def test_dry_run_does_not_delete(self, mock_backend):
        mock_backend.index_scan_pending_since.return_value = _entries(50)
        rc = _run(["--since", "2026-04-26", "--dry-run"])
        assert rc == 0
        mock_backend.index_delete_entry.assert_not_called()

    def test_dry_run_with_yes_still_does_not_delete(self, mock_backend):
        mock_backend.index_scan_pending_since.return_value = _entries(50)
        rc = _run(["--since", "2026-04-26", "--dry-run", "--yes"])
        assert rc == 0
        mock_backend.index_delete_entry.assert_not_called()

    def test_dry_run_with_zero_matches(self, mock_backend):
        mock_backend.index_scan_pending_since.return_value = []
        rc = _run(["--since", "2026-04-26", "--dry-run"])
        assert rc == 0
        mock_backend.index_delete_entry.assert_not_called()


class TestSinceParsing:
    """Malformed --since must reject before any AWS call."""

    def test_malformed_since_rejected(self, mock_backend):
        rc = _run(["--since", "not-a-date"])
        assert rc == 2
        # Must not have even contacted DynamoDB
        mock_backend.index_scan_pending_since.assert_not_called()
        mock_backend.index_delete_entry.assert_not_called()

    def test_iso_date_accepted(self, mock_backend):
        mock_backend.index_scan_pending_since.return_value = []
        rc = _run(["--since", "2026-04-26", "--dry-run"])
        assert rc == 0

    def test_iso_datetime_accepted(self, mock_backend):
        mock_backend.index_scan_pending_since.return_value = []
        rc = _run(["--since", "2026-04-26T12:00:00+00:00", "--dry-run"])
        assert rc == 0


class TestSafetyCaps:
    """Refuse runs that look like a typo (huge result set or ancient --since)."""

    def test_refuses_too_many_entries_without_force(self, mock_backend):
        mock_backend.index_scan_pending_since.return_value = _entries(60_000)
        rc = _run(["--since", "2026-04-26", "--yes"])
        assert rc == 2
        mock_backend.index_delete_entry.assert_not_called()

    def test_force_overrides_max_entries(self, mock_backend):
        mock_backend.index_scan_pending_since.return_value = _entries(60_000)
        rc = _run(["--since", "2026-04-26", "--yes", "--force"])
        assert rc == 0
        assert mock_backend.index_delete_entry.call_count == 60_000

    def test_refuses_ancient_since_without_force(self, mock_backend):
        # 2010 is well past the 90-day cap.
        rc = _run(["--since", "2010-01-01", "--yes"])
        assert rc == 2
        mock_backend.index_scan_pending_since.assert_not_called()

    def test_force_overrides_max_age(self, mock_backend):
        mock_backend.index_scan_pending_since.return_value = _entries(2)
        rc = _run(["--since", "2010-01-01", "--yes", "--force"])
        assert rc == 0
        assert mock_backend.index_delete_entry.call_count == 2


class TestDeletionPath:
    """--yes path actually deletes; per-failure logging + circuit breaker."""

    def test_yes_skips_prompt_and_deletes(self, mock_backend):
        entries = _entries(5)
        mock_backend.index_scan_pending_since.return_value = entries
        rc = _run(["--since", "2026-04-26", "--yes"])
        assert rc == 0
        assert mock_backend.index_delete_entry.call_count == 5
        called_hashes = [
            c.args[0] for c in mock_backend.index_delete_entry.call_args_list
        ]
        assert called_hashes == [e["content_hash"] for e in entries]

    def test_per_failure_continues_and_returns_nonzero(self, mock_backend):
        entries = _entries(5)
        mock_backend.index_scan_pending_since.return_value = entries
        # Fail the 3rd delete only; remaining must still be attempted.
        mock_backend.index_delete_entry.side_effect = [
            None,
            None,
            RuntimeError("transient throttle"),
            None,
            None,
        ]
        rc = _run(["--since", "2026-04-26", "--yes"])
        # Non-zero because there were failures
        assert rc == 1
        # All 5 attempted (continued past the failure)
        assert mock_backend.index_delete_entry.call_count == 5

    def test_circuit_breaker_aborts_on_consecutive_failures(self, mock_backend):
        # Cap is 100 consecutive failures. Build 200 entries that all fail.
        entries = _entries(200)
        mock_backend.index_scan_pending_since.return_value = entries
        mock_backend.index_delete_entry.side_effect = RuntimeError("IAM denied")
        rc = _run(["--since", "2026-04-26", "--yes"])
        assert rc == 1
        # Stopped at the cap, didn't try all 200
        assert mock_backend.index_delete_entry.call_count == 100


class TestPromptHandling:
    """Without --yes, the user must type 'yes' to proceed."""

    def test_prompt_yes_proceeds(self, mock_backend):
        mock_backend.index_scan_pending_since.return_value = _entries(2)
        with patch("builtins.input", return_value="yes"):
            rc = _run(["--since", "2026-04-26"])
        assert rc == 0
        assert mock_backend.index_delete_entry.call_count == 2

    def test_prompt_anything_else_aborts(self, mock_backend):
        mock_backend.index_scan_pending_since.return_value = _entries(2)
        with patch("builtins.input", return_value="y"):  # not the literal "yes"
            rc = _run(["--since", "2026-04-26"])
        assert rc == 1
        mock_backend.index_delete_entry.assert_not_called()
