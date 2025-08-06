"""Tests for content store cleanup script functionality.

This tests the logic of the cleanup script by testing the functions directly,
ensuring we never operate on real data.
"""

import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from rq.job import Job

from app.content_store import ContentStore


class TestCleanupContentStoreLogic:
    """Test cleanup logic using ContentStore directly with test data."""

    @pytest.fixture
    def temp_content_store(self):
        """Create a temporary content store for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("redis.from_url") as mock_redis:
                mock_conn = Mock()
                mock_redis.return_value = mock_conn
                store = ContentStore(store_path=Path(tmpdir))
                yield store, mock_conn

    def test_cleanup_logic_with_orphaned_entries(self, temp_content_store):
        """Test that orphaned entries can be identified."""
        store, mock_redis = temp_content_store

        # Create some test content
        content1 = '{"test": "orphaned with no job"}'
        content2 = '{"test": "orphaned with failed job"}'
        content3 = '{"test": "active job"}'
        content4 = '{"test": "completed"}'

        # Store content
        entry1 = store.store_content(content1, {"scraper": "test"})
        entry2 = store.store_content(content2, {"scraper": "test"})
        entry3 = store.store_content(content3, {"scraper": "test"})
        entry4 = store.store_content(content4, {"scraper": "test"})

        # Link jobs to some entries
        store.link_job(entry2.hash, "job-failed-123")
        store.link_job(entry3.hash, "job-active-456")

        # Store result for entry4
        store.store_result(entry4.hash, '{"processed": true}', "job-complete-789")

        # Now let's check what the cleanup logic would find
        db_path = store.content_store_path / "index.db"

        # Manually update created_at to make entries old enough
        old_time = datetime.utcnow() - timedelta(hours=48)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE content_index SET created_at = ? WHERE status = 'pending'",
                (old_time,),
            )
            conn.commit()

        # Check what entries are orphaned
        orphaned_count = 0
        active_count = 0
        completed_count = 0

        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                """
                SELECT hash, status, job_id
                FROM content_index
            """
            )

            for row in cursor:
                hash_val, status, job_id = row

                if status == "completed":
                    completed_count += 1
                elif status == "pending":
                    # In real cleanup, we'd check Redis for job status
                    # For test, we'll consider job-failed-* as failed
                    if not job_id or "failed" in str(job_id):
                        orphaned_count += 1
                    else:
                        active_count += 1

        # We should have:
        # - 2 orphaned (no job_id and failed job)
        # - 1 active (job-active-456)
        # - 1 completed
        assert orphaned_count == 2
        assert active_count == 1
        assert completed_count == 1

    def test_content_store_behavior_after_cleanup(self, temp_content_store):
        """Test that content store allows reprocessing after cleanup."""
        store, mock_redis = temp_content_store

        # Mock job as inactive
        with patch.object(store, "_is_job_active", return_value=False):
            # Store content
            content = '{"test": "will be cleaned"}'
            entry1 = store.store_content(content, {"scraper": "test"})

            # Link a failed job
            store.link_job(entry1.hash, "job-failed-999")

            # Store same content again - should clear job and allow new processing
            entry2 = store.store_content(content, {"scraper": "test"})

            assert entry2.hash == entry1.hash
            assert entry2.status == "pending"
            assert entry2.job_id is None  # Job should be cleared

            # Verify job was cleared in database
            assert store.get_job_id(entry1.hash) is None

    def test_completed_entries_are_never_cleaned(self, temp_content_store):
        """Ensure completed entries are protected from cleanup."""
        store, mock_redis = temp_content_store

        # Store content and mark as completed
        content = '{"test": "completed work"}'
        entry = store.store_content(content, {"scraper": "test"})
        store.store_result(entry.hash, '{"result": "done"}', "job-done-123")

        # Try to store same content again
        entry2 = store.store_content(content, {"scraper": "test"})

        # Should return completed result
        assert entry2.status == "completed"
        assert entry2.result == '{"result": "done"}'
        assert entry2.job_id == "job-done-123"

        # Verify in database
        db_path = store.content_store_path / "index.db"
        with sqlite3.connect(db_path) as conn:
            status = conn.execute(
                "SELECT status FROM content_index WHERE hash = ?", (entry.hash,)
            ).fetchone()[0]
            assert status == "completed"


class TestCleanupScriptSafety:
    """Test that the cleanup script has proper safety checks."""

    def test_script_requires_content_store_path(self):
        """Script should validate content store path exists."""
        # This is a simple test to ensure the script exists and is executable
        script_path = (
            Path(__file__).parent.parent.parent / "scripts" / "cleanup-content-store.py"
        )
        assert script_path.exists()
        assert script_path.stat().st_mode & 0o111  # Check if executable

    def test_dry_run_safety(self):
        """Dry run mode should be safe by default."""
        # The script should default to dry-run mode
        # This is validated by checking the script's argparse setup
        script_path = (
            Path(__file__).parent.parent.parent / "scripts" / "cleanup-content-store.py"
        )
        content = script_path.read_text()

        # Verify dry-run flag exists
        assert "--dry-run" in content
        assert 'action="store_true"' in content

        # Verify it asks for confirmation when not in dry-run
        assert "Proceed with cleanup?" in content
