"""Tests for content store high concurrency scenarios (scouting party)."""

import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.content_store import ContentStore


class TestContentStoreHighConcurrency:
    """Test content store behavior under high concurrency (scouting party scenarios)."""

    @pytest.fixture
    def temp_store_path(self):
        """Create temporary content store for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def content_store(self, temp_store_path):
        """Create content store instance for testing."""
        return ContentStore(store_path=temp_store_path)

    def test_content_store_handles_database_locks_with_retry(self, content_store):
        """Content store should retry on database lock failures."""
        # Test that retry logic works by using the mock to simulate lock conditions

        content = '{"test": "data"}'
        metadata = {"scraper_id": "test_scraper"}

        # Patch sqlite3.connect to simulate initial lock, then success
        with patch("sqlite3.connect") as mock_connect:
            # Create a real connection for the successful retry
            real_db_path = content_store.content_store_path / "index.db"

            # First call fails with lock, then provide enough real connections for all operations
            real_conn = sqlite3.connect(real_db_path)
            mock_connect.side_effect = [
                sqlite3.OperationalError("database is locked"),
                real_conn,  # For get_job_id retry
                sqlite3.connect(real_db_path),  # For clear_job_id
                sqlite3.connect(real_db_path),  # For _store_content_index
                sqlite3.connect(real_db_path),  # For any additional operations
            ]

            # Should succeed after retry
            result = content_store.store_content(content, metadata)

            assert result.status == "pending"
            assert result.hash is not None
            # Verify retry logic was triggered (should be multiple calls due to multiple operations)
            assert mock_connect.call_count >= 2  # At least initial fail + retry success

    def test_content_store_exponential_backoff(self, content_store):
        """Content store should use exponential backoff on retries."""
        # Test retry timing behavior by patching sqlite3.connect

        content = '{"test": "backoff_test"}'
        metadata = {"scraper_id": "test_scraper"}

        with patch("time.sleep") as mock_sleep:
            with patch("sqlite3.connect") as mock_connect:
                # Simulate multiple database lock failures then success
                real_db_path = content_store.content_store_path / "index.db"
                mock_connect.side_effect = [
                    sqlite3.OperationalError("database is locked"),
                    sqlite3.OperationalError("database is locked"),
                    sqlite3.connect(
                        real_db_path
                    ),  # Success on third try for get_job_id
                    sqlite3.connect(real_db_path),  # For clear_job_id
                    sqlite3.connect(real_db_path),  # For _store_content_index
                    sqlite3.connect(real_db_path),  # For any additional operations
                ]

                # This should trigger exponential backoff
                result = content_store.store_content(content, metadata)

                # Should have called sleep with increasing delays
                assert mock_sleep.call_count >= 2
                # First retry: ~0.1s, second retry: ~0.2s (exponential backoff)
                sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
                assert sleep_calls[0] < sleep_calls[1]  # Exponential increase

                # Verify operation eventually succeeded
                assert result.status == "pending"
                assert result.hash is not None

    def test_content_store_atomic_operations(self, content_store):
        """All content store operations should be atomic."""
        # RED: Test that partial failures don't corrupt state

        content = '{"test": "atomic_test"}'
        metadata = {"scraper_id": "test_scraper"}

        with patch.object(content_store, "_get_content_path") as mock_path:
            # Simulate filesystem failure after database write
            mock_content_path = Mock()
            mock_content_path.exists.return_value = False
            mock_content_path.parent.mkdir = Mock()
            mock_content_path.write_text.side_effect = OSError("Disk full")
            mock_path.return_value = mock_content_path

            # This should raise exception and not leave partial state
            with pytest.raises(OSError):
                content_store.store_content(content, metadata)

            # Database should not have the entry (rolled back)
            content_hash = content_store.hash_content(content)
            assert not content_store.has_content(content_hash)

    def test_store_content_never_silent_fails(self, content_store):
        """store_content should raise exceptions on failure, never silent fail."""
        # RED: Test that failures are properly propagated

        content = '{"test": "no_silent_fails"}'
        metadata = {"scraper_id": "test_scraper"}

        # Simulate various failure conditions that should raise exceptions
        failure_scenarios = [
            (OSError("Permission denied"), OSError),
            (sqlite3.OperationalError("database is locked"), sqlite3.OperationalError),
            (MemoryError("Out of memory"), MemoryError),
        ]

        for exception, expected_type in failure_scenarios:
            with patch("sqlite3.connect") as mock_connect:
                mock_connect.side_effect = exception

                # Should raise the exception, not return a result silently
                with pytest.raises(expected_type):
                    content_store.store_content(content, metadata)

    def test_concurrent_content_storage_consistency(self, content_store):
        """Multiple threads storing content simultaneously should maintain consistency."""
        # RED: Test that concurrent operations don't interfere

        num_threads = 10
        num_items_per_thread = 5
        results = {}
        errors = []

        def store_content_worker(thread_id):
            """Worker function for concurrent content storage."""
            try:
                thread_results = []
                for i in range(num_items_per_thread):
                    content = f'{{"thread": {thread_id}, "item": {i}}}'
                    metadata = {"scraper_id": f"scraper_{thread_id}"}

                    result = content_store.store_content(content, metadata)
                    thread_results.append(result)

                results[thread_id] = thread_results
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")

        # Start all threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=store_content_worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify no errors occurred
        assert not errors, f"Errors during concurrent operations: {errors}"

        # Verify all operations succeeded
        assert len(results) == num_threads
        for thread_results in results.values():
            assert len(thread_results) == num_items_per_thread
            for result in thread_results:
                assert result.status == "pending"
                assert result.hash is not None

    def test_rapid_fire_job_submissions(self, content_store):
        """Test rapid-fire job submissions like in scouting party scenarios."""
        # RED: Test behavior under rapid job submission

        # Simulate a scraper submitting many jobs quickly
        num_submissions = 50
        submission_delay = 0.01  # 10ms between submissions

        results = []
        start_time = time.time()

        for i in range(num_submissions):
            content = f'{{"rapid_fire": "test", "item": {i}}}'
            metadata = {"scraper_id": "rapid_fire_scraper"}

            result = content_store.store_content(content, metadata)
            results.append(result)

            time.sleep(submission_delay)

        end_time = time.time()

        # Verify all submissions succeeded
        assert len(results) == num_submissions
        for result in results:
            assert result.status == "pending"
            assert result.hash is not None

        # Verify reasonable performance (should complete in under 2 seconds)
        total_time = end_time - start_time
        assert total_time < 2.0, f"Rapid submissions took too long: {total_time}s"

    def test_scouting_party_simulation(self, content_store):
        """Simulate actual scouting party conditions with 30 scrapers."""
        # RED: Integration test for full scouting party scenario

        num_scrapers = 30
        jobs_per_scraper = 10
        results_by_scraper = {}
        errors = []

        def scraper_worker(scraper_id):
            """Simulate a scraper submitting multiple jobs rapidly."""
            try:
                scraper_results = []
                for job_id in range(jobs_per_scraper):
                    content = f'{{"scraper": "{scraper_id}", "job": {job_id}, "data": "test_data"}}'
                    metadata = {"scraper_id": scraper_id}

                    result = content_store.store_content(content, metadata)
                    scraper_results.append(result)

                    # Small delay to simulate processing time
                    time.sleep(0.005)  # 5ms

                results_by_scraper[scraper_id] = scraper_results
            except Exception as e:
                errors.append(f"Scraper {scraper_id}: {e}")

        # Start all scrapers
        threads = []
        start_time = time.time()

        for i in range(num_scrapers):
            scraper_id = f"scraper_{i:02d}"
            thread = threading.Thread(target=scraper_worker, args=(scraper_id,))
            threads.append(thread)
            thread.start()

        # Wait for all scrapers to complete
        for thread in threads:
            thread.join()

        end_time = time.time()

        # Verify no errors occurred
        assert not errors, f"Errors during scouting party simulation: {errors}"

        # Verify all scrapers completed successfully
        assert len(results_by_scraper) == num_scrapers

        total_jobs = 0
        for scraper_results in results_by_scraper.values():
            assert len(scraper_results) == jobs_per_scraper
            total_jobs += len(scraper_results)

            for result in scraper_results:
                assert result.status == "pending"
                assert result.hash is not None

        # Verify total job count
        expected_total = num_scrapers * jobs_per_scraper
        assert total_jobs == expected_total

        # Verify content store statistics match
        stats = content_store.get_statistics()
        assert stats["total_content"] == expected_total
        assert stats["pending_content"] == expected_total

        print(f"Scouting party simulation completed in {end_time - start_time:.2f}s")
        print(f"Processed {total_jobs} jobs from {num_scrapers} scrapers")


class TestContentStoreRetryMechanisms:
    """Test content store retry mechanisms specifically."""

    @pytest.fixture
    def temp_store_path(self):
        """Create temporary content store for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def content_store(self, temp_store_path):
        """Create content store instance for testing."""
        return ContentStore(store_path=temp_store_path)

    def test_has_content_with_retry(self, content_store):
        """has_content should retry on database lock failures."""
        # RED: Test retry behavior for read operations

        content = '{"test": "has_content_retry"}'
        metadata = {"scraper_id": "test_scraper"}

        # First store the content successfully
        result = content_store.store_content(content, metadata)
        content_hash = result.hash

        # Now test has_content with simulated lock
        with patch("sqlite3.connect") as mock_connect:
            # First call fails with lock, second succeeds
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = (1,)  # Content exists
            mock_conn.execute.return_value = mock_cursor
            mock_conn.__enter__ = Mock(return_value=mock_conn)
            mock_conn.__exit__ = Mock(return_value=None)

            mock_connect.side_effect = [
                sqlite3.OperationalError("database is locked"),
                mock_conn,
            ]

            # Should succeed after retry
            assert content_store.has_content(content_hash) is True

    def test_get_result_with_retry(self, content_store):
        """get_result should work properly after content storage."""
        # Test basic get_result functionality (get_result doesn't actually use database operations)

        content = '{"test": "get_result_retry"}'
        metadata = {"scraper_id": "test_scraper"}

        # Store content and result
        result = content_store.store_content(content, metadata)
        content_hash = result.hash
        content_store.store_result(content_hash, '{"processed": "data"}', "job_123")

        # Should be able to retrieve the result
        result_data = content_store.get_result(content_hash)
        assert result_data == '{"processed": "data"}'

    def test_store_result_with_retry(self, content_store):
        """store_result should retry on database lock failures."""
        # RED: Test retry behavior for result storage

        content = '{"test": "store_result_retry"}'
        metadata = {"scraper_id": "test_scraper"}

        # Store content first
        result = content_store.store_content(content, metadata)
        content_hash = result.hash

        with patch("sqlite3.connect") as mock_connect:
            # Simulate database lock on first attempt
            mock_connect.side_effect = [
                sqlite3.OperationalError("database is locked"),
                sqlite3.connect(
                    content_store.content_store_path / "index.db"
                ),  # Real connection
            ]

            # Should succeed after retry
            content_store.store_result(
                content_hash, '{"processed": "retry_test"}', "job_retry"
            )

            # Verify result was stored
            stored_result = content_store.get_result(content_hash)
            assert stored_result == '{"processed": "retry_test"}'
