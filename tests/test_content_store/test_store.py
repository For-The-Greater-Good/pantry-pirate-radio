"""Tests for ContentStore class."""

import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.content_store import ContentStore


class TestContentStore:
    """Test cases for ContentStore."""

    @pytest.fixture
    def temp_store_path(self):
        """Create a temporary directory for content store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def content_store(self, temp_store_path):
        """Create a ContentStore instance with temporary storage."""
        with patch("redis.from_url") as mock_redis:
            # Mock Redis connection
            mock_conn = Mock()
            mock_redis.return_value = mock_conn
            return ContentStore(store_path=temp_store_path)

    def test_should_initialize_with_store_path(self, temp_store_path):
        """ContentStore should initialize with a store path."""
        with patch("redis.from_url") as mock_redis:
            mock_conn = Mock()
            mock_redis.return_value = mock_conn
            store = ContentStore(store_path=temp_store_path)
        assert store.store_path == temp_store_path
        assert (temp_store_path / "content-store").exists()
        assert (temp_store_path / "content-store" / "content").exists()
        assert (temp_store_path / "content-store" / "results").exists()
        assert (temp_store_path / "content-store" / "index.db").exists()

    def test_should_hash_content_deterministically(self, content_store):
        """Content hashing should be deterministic."""
        content = '{"name": "Test Pantry", "address": "123 Main St"}'

        hash1 = content_store.hash_content(content)
        hash2 = content_store.hash_content(content)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 produces 64 hex characters

        # Verify it matches expected SHA-256
        expected = hashlib.sha256(content.encode()).hexdigest()
        assert hash1 == expected

    def test_should_detect_new_content(self, content_store):
        """Should correctly identify content that hasn't been seen before."""
        content = '{"name": "New Pantry", "location": "456 Oak Ave"}'
        content_hash = content_store.hash_content(content)

        assert not content_store.has_content(content_hash)
        assert content_store.get_result(content_hash) is None

    def test_should_store_new_content(self, content_store):
        """Should store new content and return pending status."""
        content = '{"name": "Test Pantry", "hours": "Mon-Fri 9-5"}'
        metadata = {"scraper_id": "test_scraper", "timestamp": "2024-01-01"}

        entry = content_store.store_content(content, metadata)

        assert entry.hash == content_store.hash_content(content)
        assert entry.status == "pending"
        assert entry.result is None
        assert entry.job_id is None

        # Verify content was written to disk
        content_path = content_store._get_content_path(entry.hash)
        assert content_path.exists()

        stored_data = json.loads(content_path.read_text())
        assert stored_data["content"] == content
        assert stored_data["metadata"] == metadata

    def test_should_return_cached_result_for_existing_content(self, content_store):
        """Should return cached result when content already processed."""
        content = '{"name": "Cached Pantry", "phone": "555-1234"}'
        content_hash = content_store.hash_content(content)

        # Simulate storing a result
        result = {"processed": "data", "confidence": 0.95}
        content_store.store_result(content_hash, json.dumps(result), "job-123")

        # Now try to store the same content
        entry = content_store.store_content(content, {})

        assert entry.hash == content_hash
        assert entry.status == "completed"
        assert entry.result == json.dumps(result)
        assert entry.job_id == "job-123"

    def test_should_store_result_for_content(self, content_store):
        """Should store processing result for content hash."""
        # Use valid 64-character hex hash
        content_hash = "abc123def456" + "0" * 52  # Pad to 64 chars
        result = '{"organization": {"name": "Processed Pantry"}}'
        job_id = "job-456"

        content_store.store_result(content_hash, result, job_id)

        # Verify result was stored
        result_path = content_store._get_result_path(content_hash)
        assert result_path.exists()

        stored_data = json.loads(result_path.read_text())
        assert stored_data["result"] == result
        assert stored_data["job_id"] == job_id
        assert "timestamp" in stored_data

    def test_should_track_content_in_sqlite_index(self, content_store):
        """Should maintain SQLite index of all content."""
        content1 = '{"id": 1, "name": "Pantry 1"}'
        content2 = '{"id": 2, "name": "Pantry 2"}'

        entry1 = content_store.store_content(content1, {"scraper_id": "test"})
        entry2 = content_store.store_content(content2, {"scraper_id": "test"})

        # Both should be tracked in index
        assert content_store.has_content(entry1.hash)
        assert content_store.has_content(entry2.hash)

        # Store result for one
        content_store.store_result(entry1.hash, '{"processed": true}', "job-1")

        # Check index reflects the status
        assert content_store.get_result(entry1.hash) is not None
        assert content_store.get_result(entry2.hash) is None

    def test_should_handle_concurrent_access(self, content_store):
        """Should handle concurrent access to the same content."""
        content = '{"name": "Concurrent Pantry"}'

        # Simulate concurrent attempts to store same content
        entry1 = content_store.store_content(content, {"attempt": 1})
        entry2 = content_store.store_content(content, {"attempt": 2})

        # Both should get the same hash
        assert entry1.hash == entry2.hash

        # Second attempt should not overwrite the first
        content_path = content_store._get_content_path(entry1.hash)
        stored_data = json.loads(content_path.read_text())
        assert stored_data["metadata"]["attempt"] == 1

    def test_should_create_directory_structure_with_prefix(self, content_store):
        """Should organize files by hash prefix for better file system performance."""
        content = '{"test": "data"}'
        content_hash = content_store.hash_content(content)

        content_store.store_content(content, {})

        # Should create subdirectory with first 2 chars of hash
        prefix = content_hash[:2]
        content_dir = content_store.store_path / "content-store" / "content" / prefix
        assert content_dir.exists()
        assert (content_dir / f"{content_hash}.json").exists()

    def test_should_get_statistics(self, content_store):
        """Should provide statistics about stored content."""
        # Store some content
        for i in range(5):
            content = f'{{"id": {i}}}'
            content_store.store_content(content, {"scraper_id": "test"})

        # Process some of them
        for i in range(3):
            content = f'{{"id": {i}}}'
            hash = content_store.hash_content(content)
            content_store.store_result(hash, f'{{"processed": {i}}}', f"job-{i}")

        stats = content_store.get_statistics()

        assert stats["total_content"] == 5
        assert stats["processed_content"] == 3
        assert stats["pending_content"] == 2
        assert "store_size_bytes" in stats

    def test_should_track_job_id_for_pending_content(self, content_store):
        """Should track job ID when content is linked to a job."""
        content = '{"name": "Job Tracked Pantry"}'
        metadata = {"scraper_id": "test_scraper"}

        # Store content first
        entry = content_store.store_content(content, metadata)
        assert entry.job_id is None

        # Link a job to this content
        job_id = "job-789"
        content_store.link_job(entry.hash, job_id)

        # Verify job ID is tracked
        stored_job_id = content_store.get_job_id(entry.hash)
        assert stored_job_id == job_id

    def test_should_not_return_pending_job_for_duplicate_content(self, content_store):
        """Should NOT return existing job ID for pending content (allow reprocessing)."""
        content = '{"name": "Duplicate Pantry", "address": "789 Pine St"}'
        metadata = {"scraper_id": "test_scraper"}

        # Mock the _is_job_active method to return True for our job
        with patch.object(content_store, "_is_job_active") as mock_is_active:
            mock_is_active.return_value = True

            # First time: store content
            entry1 = content_store.store_content(content, metadata)
            assert entry1.status == "pending"
            assert entry1.job_id is None

            # Link a job
            job_id = "job-999"
            content_store.link_job(entry1.hash, job_id)

            # Second time: should allow new processing (not return existing job)
            entry2 = content_store.store_content(content, metadata)
            assert entry2.hash == entry1.hash
            assert entry2.status == "pending"
            assert entry2.job_id is None  # Should NOT return the existing job

    def test_should_cleanup_failed_job_and_allow_reprocessing(self, content_store):
        """Should clear failed job IDs and allow reprocessing."""
        content = '{"name": "Failed Job Pantry"}'
        metadata = {"scraper_id": "test_scraper"}

        # Mock the _is_job_active method to return False (job failed/expired)
        with patch.object(content_store, "_is_job_active") as mock_is_active:
            mock_is_active.return_value = False

            # First time: store content and link a job
            entry1 = content_store.store_content(content, metadata)
            content_store.link_job(entry1.hash, "job-failed-123")

            # Verify job is linked
            assert content_store.get_job_id(entry1.hash) == "job-failed-123"

            # Second time: should clear the failed job and allow new processing
            entry2 = content_store.store_content(content, metadata)
            assert entry2.hash == entry1.hash
            assert entry2.status == "pending"
            assert entry2.job_id is None

            # Verify the old job_id was cleared
            assert content_store.get_job_id(entry1.hash) is None

    def test_should_prioritize_completed_over_pending(self, content_store):
        """Should return completed result even if job_id exists for pending."""
        content = '{"name": "Priority Pantry"}'
        content_hash = content_store.hash_content(content)

        # First store as pending with job ID
        entry1 = content_store.store_content(content, {})
        content_store.link_job(content_hash, "job-111")

        # Then store a result
        result = '{"processed": "complete"}'
        content_store.store_result(content_hash, result, "job-111")

        # Should return completed status
        entry2 = content_store.store_content(content, {})
        assert entry2.status == "completed"
        assert entry2.result == result
        assert entry2.job_id == "job-111"

    def test_should_validate_hash_format(self, content_store):
        """Should validate hash format for security."""
        import pytest

        # Valid hash (64 hex characters)
        valid_hash = "a" * 64
        assert content_store._validate_hash(valid_hash) is None

        # Invalid hashes
        invalid_hashes = [
            "not-a-hash",  # Not hex
            "a" * 63,  # Too short
            "a" * 65,  # Too long
            "g" * 64,  # Invalid hex char
            "../etc/passwd",  # Path traversal attempt
            "../../secret",  # Path traversal attempt
            "",  # Empty
            "A" * 64,  # Uppercase (we expect lowercase)
        ]

        for invalid_hash in invalid_hashes:
            with pytest.raises(ValueError, match="Invalid hash format"):
                content_store._validate_hash(invalid_hash)

    def test_public_methods_validate_hash(self, content_store):
        """Public methods should validate hash before use."""
        import pytest

        invalid_hash = "../malicious/path"

        # Test has_content
        with pytest.raises(ValueError, match="Invalid hash format"):
            content_store.has_content(invalid_hash)

        # Test get_result
        with pytest.raises(ValueError, match="Invalid hash format"):
            content_store.get_result(invalid_hash)

        # Test store_result
        with pytest.raises(ValueError, match="Invalid hash format"):
            content_store.store_result(invalid_hash, '{"test": "data"}', "job-123")

        # Test get_job_id
        with pytest.raises(ValueError, match="Invalid hash format"):
            content_store.get_job_id(invalid_hash)

        # Test link_job
        with pytest.raises(ValueError, match="Invalid hash format"):
            content_store.link_job(invalid_hash, "job-123")

    def test_path_methods_validate_hash(self, content_store):
        """Path methods should validate hash before constructing paths."""
        import pytest

        invalid_hash = "../../etc/passwd"

        # Test _get_content_path
        with pytest.raises(ValueError, match="Invalid hash format"):
            content_store._get_content_path(invalid_hash)

        # Test _get_result_path
        with pytest.raises(ValueError, match="Invalid hash format"):
            content_store._get_result_path(invalid_hash)
