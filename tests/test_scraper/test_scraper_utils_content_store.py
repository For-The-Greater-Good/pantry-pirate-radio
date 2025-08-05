"""Tests for ScraperUtils content store integration."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from rq.job import Job

from app.content_store import ContentStore
from app.content_store.models import ContentEntry
from app.scraper.utils import ScraperUtils


class TestScraperUtilsContentStore:
    """Test cases for ScraperUtils with content store integration."""

    @pytest.fixture
    def temp_store_path(self):
        """Create a temporary directory for content store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def content_store(self, temp_store_path):
        """Create a ContentStore instance."""
        return ContentStore(store_path=temp_store_path)

    @pytest.fixture
    def mock_content_store(self):
        """Create a mock ContentStore."""
        store = Mock(spec=ContentStore)
        return store

    @pytest.fixture
    def scraper_utils(self):
        """Create ScraperUtils instance."""
        return ScraperUtils(scraper_id="test_scraper")

    @patch("app.content_store.config.get_content_store")
    @patch("app.scraper.utils.llm_queue.enqueue_call")
    def test_should_check_content_store_before_queueing(
        self, mock_enqueue, mock_get_store, scraper_utils, mock_content_store
    ):
        """Should check content store before queueing to LLM."""
        # Setup
        mock_get_store.return_value = mock_content_store
        content = '{"name": "Test Pantry", "address": "123 Main St"}'
        metadata = {"source": "test"}

        # Content not yet processed
        mock_content_store.store_content.return_value = ContentEntry(
            hash="abc123", status="pending", result=None, job_id=None
        )

        mock_job = Mock(spec=Job)
        mock_job.id = "job-123"
        mock_enqueue.return_value = mock_job

        # Act
        job_id = scraper_utils.queue_for_processing(content, metadata)

        # Assert
        mock_content_store.store_content.assert_called_once_with(
            content, {"scraper_id": "test_scraper", "source": "test"}
        )
        mock_enqueue.assert_called_once()
        assert job_id == "job-123"

    @patch("app.content_store.config.get_content_store")
    @patch("app.scraper.utils.llm_queue.enqueue_call")
    def test_should_return_cached_job_id_for_processed_content(
        self, mock_enqueue, mock_get_store, scraper_utils, mock_content_store
    ):
        """Should return cached job ID when content already processed."""
        # Setup
        mock_get_store.return_value = mock_content_store
        content = '{"name": "Cached Pantry", "phone": "555-1234"}'

        # Content already processed
        mock_content_store.store_content.return_value = ContentEntry(
            hash="def456",
            status="completed",
            result='{"processed": true}',
            job_id="cached-job-456",
        )

        # Act
        job_id = scraper_utils.queue_for_processing(content)

        # Assert
        mock_content_store.store_content.assert_called_once()
        mock_enqueue.assert_not_called()  # Should not queue new job
        assert job_id == "cached-job-456"

    @patch("app.content_store.config.get_content_store")
    @patch("app.scraper.utils.llm_queue.enqueue_call")
    def test_should_link_job_to_content_hash(
        self, mock_enqueue, mock_get_store, scraper_utils, mock_content_store
    ):
        """Should link new job to content hash for later result storage."""
        # Setup
        mock_get_store.return_value = mock_content_store
        content = '{"name": "New Pantry"}'

        mock_content_store.store_content.return_value = ContentEntry(
            hash="ghi789", status="pending", result=None, job_id=None
        )

        mock_job = Mock(spec=Job)
        mock_job.id = "job-789"
        mock_enqueue.return_value = mock_job

        # Act
        job_id = scraper_utils.queue_for_processing(content)

        # Assert
        mock_content_store.link_job.assert_called_once_with("ghi789", "job-789")
        assert job_id == "job-789"

    @patch("app.content_store.config.get_content_store")
    @patch("app.scraper.utils.llm_queue.enqueue_call")
    def test_should_handle_content_store_not_configured(
        self, mock_enqueue, mock_get_store, scraper_utils
    ):
        """Should work normally if content store not configured."""
        # Setup
        mock_get_store.return_value = None  # No content store
        content = '{"name": "Test"}'

        mock_job = Mock(spec=Job)
        mock_job.id = "job-999"
        mock_enqueue.return_value = mock_job

        # Act
        job_id = scraper_utils.queue_for_processing(content)

        # Assert
        mock_enqueue.assert_called_once()
        assert job_id == "job-999"

    @patch("app.content_store.config.get_content_store")
    def test_should_preserve_original_metadata(
        self, mock_get_store, scraper_utils, mock_content_store
    ):
        """Should preserve original metadata when storing content."""
        # Setup
        mock_get_store.return_value = mock_content_store
        content = '{"test": "data"}'
        metadata = {
            "source": "test_source",
            "priority": "high",
            "custom_field": "value",
        }

        mock_content_store.store_content.return_value = ContentEntry(
            hash="xyz", status="pending", result=None, job_id=None
        )

        # Act
        scraper_utils.queue_for_processing(content, metadata)

        # Assert
        expected_metadata = {
            "scraper_id": "test_scraper",
            "source": "test_source",
            "priority": "high",
            "custom_field": "value",
        }
        mock_content_store.store_content.assert_called_once_with(
            content, expected_metadata
        )

    @patch("app.content_store.config.get_content_store")
    @patch("app.scraper.utils.SCRAPER_JOBS")
    def test_should_increment_metrics_for_cached_results(
        self, mock_metrics, mock_get_store, scraper_utils, mock_content_store
    ):
        """Should still increment metrics even for cached results."""
        # Setup
        mock_get_store.return_value = mock_content_store
        content = '{"cached": true}'

        mock_content_store.store_content.return_value = ContentEntry(
            hash="aaa",
            status="completed",
            result='{"processed": true}',
            job_id="cached-job",
        )

        # Act
        scraper_utils.queue_for_processing(content)

        # Assert
        mock_metrics.labels.assert_called_with(scraper_id="test_scraper")
        mock_metrics.labels().inc.assert_called_once()

    def test_integration_with_real_content_store(
        self, scraper_utils, content_store, monkeypatch
    ):
        """Integration test with real content store."""
        # Setup
        monkeypatch.setattr(
            "app.content_store.config.get_content_store", lambda: content_store
        )

        content = '{"integration": "test", "id": 123}'

        # First submission - should queue
        with patch("app.scraper.utils.llm_queue.enqueue_call") as mock_enqueue:
            mock_job = Mock(spec=Job)
            mock_job.id = "job-integration-1"
            mock_enqueue.return_value = mock_job

            job_id1 = scraper_utils.queue_for_processing(content)
            assert mock_enqueue.called
            assert job_id1 == "job-integration-1"

        # Simulate processing complete
        content_hash = content_store.hash_content(content)
        content_store.store_result(
            content_hash, '{"processed": "integration test"}', "job-integration-1"
        )

        # Second submission - should return cached
        with patch("app.scraper.utils.llm_queue.enqueue_call") as mock_enqueue:
            job_id2 = scraper_utils.queue_for_processing(content)
            assert not mock_enqueue.called
            assert job_id2 == "job-integration-1"

    @patch("app.content_store.config.get_content_store")
    @patch("app.scraper.utils.llm_queue.enqueue_call")
    def test_should_return_same_job_id_for_pending_duplicate_content(
        self, mock_enqueue, mock_get_store, scraper_utils, mock_content_store
    ):
        """Should return same job ID when duplicate content is queued while still pending."""
        # Setup
        mock_get_store.return_value = mock_content_store
        content = '{"name": "Pending Duplicate Pantry"}'

        # First call - new content
        mock_content_store.store_content.return_value = ContentEntry(
            hash="pending123", status="pending", result=None, job_id=None
        )
        mock_content_store.get_job_id.return_value = None

        mock_job = Mock(spec=Job)
        mock_job.id = "job-pending-1"
        mock_enqueue.return_value = mock_job

        job_id1 = scraper_utils.queue_for_processing(content)
        assert job_id1 == "job-pending-1"
        mock_content_store.link_job.assert_called_with("pending123", "job-pending-1")

        # Second call - same content, now has job_id
        mock_content_store.store_content.return_value = ContentEntry(
            hash="pending123", status="pending", result=None, job_id="job-pending-1"
        )
        mock_content_store.get_job_id.return_value = "job-pending-1"

        # Reset mock to verify it's not called again
        mock_enqueue.reset_mock()

        job_id2 = scraper_utils.queue_for_processing(content)
        assert job_id2 == "job-pending-1"  # Same job ID
        mock_enqueue.assert_not_called()  # Should not queue again

    def test_integration_deduplication_for_pending_content(
        self, scraper_utils, content_store, monkeypatch
    ):
        """Integration test for deduplication of pending content."""
        # Setup
        monkeypatch.setattr(
            "app.content_store.config.get_content_store", lambda: content_store
        )

        content = '{"dedup": "test", "timestamp": 12345}'

        # First submission
        with patch("app.scraper.utils.llm_queue.enqueue_call") as mock_enqueue:
            mock_job = Mock(spec=Job)
            mock_job.id = "job-dedup-1"
            mock_enqueue.return_value = mock_job

            job_id1 = scraper_utils.queue_for_processing(content)
            assert mock_enqueue.called
            assert job_id1 == "job-dedup-1"

        # Mock the store_content to return an entry with the existing job_id
        # This simulates the behavior we expect when content is already queued
        with patch.object(content_store, "store_content") as mock_store_content:
            # Return an entry with the existing job_id
            mock_store_content.return_value = ContentEntry(
                hash="test-hash", status="pending", result=None, job_id="job-dedup-1"
            )

            # Second submission before processing - should return same job ID
            with patch("app.scraper.utils.llm_queue.enqueue_call") as mock_enqueue:
                job_id2 = scraper_utils.queue_for_processing(content)
                assert not mock_enqueue.called  # Should not queue again
                assert job_id2 == "job-dedup-1"  # Same job ID as first submission
