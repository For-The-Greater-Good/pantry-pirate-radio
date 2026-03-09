"""Tests for FileContentStoreBackend.

RED phase: These tests define the expected behavior of the FileContentStoreBackend
which will implement the ContentStoreBackend protocol.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest


class TestFileContentStoreBackend:
    """Test cases for FileContentStoreBackend implementation."""

    @pytest.fixture
    def backend(self, tmp_path: Path):
        """Create a FileContentStoreBackend instance with temporary storage."""
        # Import here - will fail until implementation exists (RED phase)
        from app.content_store.backend import FileContentStoreBackend

        backend = FileContentStoreBackend(store_path=tmp_path)
        backend.initialize()
        return backend

    @pytest.fixture
    def valid_hash(self) -> str:
        """Return a valid 64-character hex hash for testing."""
        return "a" * 64

    # --- Initialization Tests ---

    def test_initialize_creates_directory_structure(self, tmp_path: Path):
        """initialize() should create content and results directories."""
        from app.content_store.backend import FileContentStoreBackend

        backend = FileContentStoreBackend(store_path=tmp_path)
        backend.initialize()

        content_store_path = tmp_path / "content_store"
        assert content_store_path.exists()
        assert (content_store_path / "content").exists()
        assert (content_store_path / "results").exists()
        assert (content_store_path / "index.db").exists()

    def test_initialize_creates_sqlite_with_wal_mode(self, tmp_path: Path):
        """initialize() should create SQLite database with WAL mode enabled."""
        import sqlite3

        from app.content_store.backend import FileContentStoreBackend

        backend = FileContentStoreBackend(store_path=tmp_path)
        backend.initialize()

        db_path = tmp_path / "content_store" / "index.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode.lower() == "wal"

    def test_initialize_is_idempotent(self, tmp_path: Path):
        """initialize() should be safe to call multiple times."""
        from app.content_store.backend import FileContentStoreBackend

        backend = FileContentStoreBackend(store_path=tmp_path)
        backend.initialize()
        backend.initialize()  # Should not raise

        assert (tmp_path / "content_store" / "content").exists()

    # --- Property Tests ---

    def test_store_path_property(self, backend, tmp_path: Path):
        """store_path property should return the base store path."""
        assert backend.store_path == tmp_path

    def test_content_store_path_property(self, backend, tmp_path: Path):
        """content_store_path property should return the content_store subdirectory."""
        assert backend.content_store_path == tmp_path / "content_store"

    # --- Content Write/Read Tests ---

    def test_write_content_creates_file(self, backend, valid_hash: str):
        """write_content() should create a JSON file and return its path."""
        data = json.dumps({"content": "test data", "metadata": {"key": "value"}})

        result_path = backend.write_content(valid_hash, data)

        assert Path(result_path).exists()
        assert valid_hash in result_path
        assert result_path.endswith(".json")

    def test_write_content_uses_prefix_subdirectory(self, backend, valid_hash: str):
        """write_content() should organize files by hash prefix."""
        data = json.dumps({"content": "test"})

        result_path = backend.write_content(valid_hash, data)

        # First 2 chars of hash should be the subdirectory
        prefix = valid_hash[:2]
        assert f"/content/{prefix}/" in result_path

    def test_read_content_returns_stored_data(self, backend, valid_hash: str):
        """read_content() should return the data that was written."""
        original_data = json.dumps({"content": "roundtrip test", "metadata": {}})
        backend.write_content(valid_hash, original_data)

        result = backend.read_content(valid_hash)

        assert result == original_data

    def test_read_content_returns_none_for_missing(self, backend, valid_hash: str):
        """read_content() should return None for non-existent content."""
        result = backend.read_content(valid_hash)
        assert result is None

    def test_content_exists_returns_true_for_existing(self, backend, valid_hash: str):
        """content_exists() should return True after content is written."""
        data = json.dumps({"test": "data"})
        backend.write_content(valid_hash, data)

        assert backend.content_exists(valid_hash) is True

    def test_content_exists_returns_false_for_missing(self, backend, valid_hash: str):
        """content_exists() should return False for non-existent content."""
        assert backend.content_exists(valid_hash) is False

    # --- Result Write/Read Tests ---

    def test_write_result_creates_file(self, backend, valid_hash: str):
        """write_result() should create a JSON file and return its path."""
        data = json.dumps({"result": "processed data", "job_id": "job-123"})

        result_path = backend.write_result(valid_hash, data)

        assert Path(result_path).exists()
        assert valid_hash in result_path
        assert result_path.endswith(".json")

    def test_write_result_uses_results_directory(self, backend, valid_hash: str):
        """write_result() should store in the results directory."""
        data = json.dumps({"result": "test"})

        result_path = backend.write_result(valid_hash, data)

        assert "/results/" in result_path

    def test_read_result_returns_stored_data(self, backend, valid_hash: str):
        """read_result() should return the data that was written."""
        original_data = json.dumps({"result": "roundtrip", "job_id": "job-456"})
        backend.write_result(valid_hash, original_data)

        result = backend.read_result(valid_hash)

        assert result == original_data

    def test_read_result_returns_none_for_missing(self, backend, valid_hash: str):
        """read_result() should return None for non-existent results."""
        result = backend.read_result(valid_hash)
        assert result is None

    # --- Index Tests ---

    def test_index_has_content_returns_false_initially(self, backend, valid_hash: str):
        """index_has_content() should return False for unindexed content."""
        assert backend.index_has_content(valid_hash) is False

    def test_index_insert_content_adds_entry(self, backend, valid_hash: str):
        """index_insert_content() should add an entry to the index."""
        content_path = "/path/to/content.json"
        created_at = datetime.utcnow()

        backend.index_insert_content(valid_hash, content_path, created_at)

        assert backend.index_has_content(valid_hash) is True

    def test_index_insert_content_is_idempotent(self, backend, valid_hash: str):
        """index_insert_content() should not fail on duplicate inserts."""
        content_path = "/path/to/content.json"
        created_at = datetime.utcnow()

        backend.index_insert_content(valid_hash, content_path, created_at)
        # Second insert should not raise
        backend.index_insert_content(valid_hash, content_path, created_at)

        assert backend.index_has_content(valid_hash) is True

    def test_index_update_result_updates_entry(self, backend, valid_hash: str):
        """index_update_result() should update an existing index entry."""
        # First insert content
        backend.index_insert_content(
            valid_hash, "/path/content.json", datetime.utcnow()
        )

        # Then update with result
        result_path = "/path/result.json"
        job_id = "job-789"
        processed_at = datetime.utcnow()

        backend.index_update_result(valid_hash, result_path, job_id, processed_at)

        # Verify job_id was set
        assert backend.index_get_job_id(valid_hash) == job_id

    def test_index_update_result_creates_entry_if_missing(
        self, backend, valid_hash: str
    ):
        """index_update_result() should create entry if content wasn't indexed."""
        result_path = "/path/result.json"
        job_id = "job-orphan"
        processed_at = datetime.utcnow()

        # Update without prior insert
        backend.index_update_result(valid_hash, result_path, job_id, processed_at)

        assert backend.index_has_content(valid_hash) is True
        assert backend.index_get_job_id(valid_hash) == job_id

    def test_index_get_job_id_returns_none_initially(self, backend, valid_hash: str):
        """index_get_job_id() should return None for content without job."""
        backend.index_insert_content(
            valid_hash, "/path/content.json", datetime.utcnow()
        )

        assert backend.index_get_job_id(valid_hash) is None

    def test_index_set_job_id_updates_job(self, backend, valid_hash: str):
        """index_set_job_id() should set the job ID for indexed content."""
        backend.index_insert_content(
            valid_hash, "/path/content.json", datetime.utcnow()
        )

        backend.index_set_job_id(valid_hash, "job-new-123")

        assert backend.index_get_job_id(valid_hash) == "job-new-123"

    def test_index_clear_job_id_removes_job(self, backend, valid_hash: str):
        """index_clear_job_id() should set job ID to None."""
        backend.index_insert_content(
            valid_hash, "/path/content.json", datetime.utcnow()
        )
        backend.index_set_job_id(valid_hash, "job-to-clear")

        backend.index_clear_job_id(valid_hash)

        assert backend.index_get_job_id(valid_hash) is None

    # --- Statistics Tests ---

    def test_index_get_statistics_empty_store(self, backend):
        """index_get_statistics() should return zeros for empty store."""
        stats = backend.index_get_statistics()

        assert stats["total_content"] == 0
        assert stats["processed_content"] == 0
        assert stats["pending_content"] == 0

    def test_index_get_statistics_counts_content(self, backend):
        """index_get_statistics() should count content entries."""
        for i in range(5):
            content_hash = f"{i:064d}"
            backend.index_insert_content(
                content_hash, f"/path/content_{i}.json", datetime.utcnow()
            )

        stats = backend.index_get_statistics()

        assert stats["total_content"] == 5
        assert stats["pending_content"] == 5
        assert stats["processed_content"] == 0

    def test_index_get_statistics_tracks_processed(self, backend):
        """index_get_statistics() should track processed vs pending."""
        # Create 5 entries
        for i in range(5):
            content_hash = f"{i:064d}"
            backend.index_insert_content(
                content_hash, f"/path/content_{i}.json", datetime.utcnow()
            )

        # Mark 3 as processed
        for i in range(3):
            content_hash = f"{i:064d}"
            backend.index_update_result(
                content_hash, f"/path/result_{i}.json", f"job-{i}", datetime.utcnow()
            )

        stats = backend.index_get_statistics()

        assert stats["total_content"] == 5
        assert stats["processed_content"] == 3
        assert stats["pending_content"] == 2

    def test_get_store_size_bytes(self, backend, valid_hash: str):
        """get_store_size_bytes() should return total size of stored files."""
        # Write some content
        data = json.dumps({"content": "x" * 1000})  # ~1KB of content
        backend.write_content(valid_hash, data)

        size = backend.get_store_size_bytes()

        assert size > 0
        assert size >= len(data)  # At least as big as the data written


class TestContentStoreBackendProtocol:
    """Test that FileContentStoreBackend implements ContentStoreBackend protocol."""

    def test_implements_protocol(self, tmp_path: Path):
        """FileContentStoreBackend should implement ContentStoreBackend protocol."""
        from app.content_store.backend import (
            ContentStoreBackend,
            FileContentStoreBackend,
        )

        backend = FileContentStoreBackend(store_path=tmp_path)

        # Check it's recognized as implementing the protocol
        assert isinstance(backend, ContentStoreBackend)

    def test_protocol_is_runtime_checkable(self):
        """ContentStoreBackend should be runtime_checkable."""
        from typing import runtime_checkable

        from app.content_store.backend import ContentStoreBackend

        # Protocol should have @runtime_checkable decorator
        assert hasattr(ContentStoreBackend, "__protocol_attrs__") or hasattr(
            ContentStoreBackend, "_is_protocol"
        )
