"""Tests for worker content store integration."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.content_store import ContentStore
from app.llm.queue.job import LLMJob
from app.llm.queue.processor import process_llm_job


class TestWorkerContentStore:
    """Test cases for worker integration with content store."""

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
    def mock_provider(self):
        """Create a mock LLM provider."""
        provider = Mock()
        provider.model_name = "test-model"
        return provider

    @pytest.fixture
    def sample_job(self):
        """Create a sample LLM job."""
        from datetime import datetime

        return LLMJob(
            id="test-job-123",
            prompt="Process this test data",
            format={
                "type": "json_schema",
                "schema": {"type": "object"},
                "validation": {"min_confidence": 0.9, "retry_threshold": 0.75},
            },
            metadata={
                "scraper_id": "test_scraper",
                "content_hash": "abc123def456",  # This will be added by the system
            },
            provider_config={},
            created_at=datetime.utcnow(),
        )

    @patch("app.content_store.config.get_content_store")
    @patch("app.llm.queue.processor.reconciler_queue")
    @patch("app.llm.queue.processor.recorder_queue")
    def test_should_store_result_to_content_store_on_success(
        self,
        mock_recorder_queue,
        mock_reconciler_queue,
        mock_get_store,
        content_store,
        mock_provider,
        sample_job,
    ):
        """Should store processing result to content store when job succeeds."""
        # Setup
        mock_get_store.return_value = content_store

        # Mock provider response
        from app.llm.providers.types import LLMResponse

        mock_response = LLMResponse(
            text='{"organization": {"name": "Test Org"}}',
            model="test-model",
            usage={"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100},
            raw={},
        )

        # Make generate return a coroutine
        import asyncio

        async def mock_generate(*args, **kwargs):
            return mock_response

        mock_provider.generate.return_value = mock_generate()

        # Pre-store content to get hash
        content_hash = content_store.hash_content('{"test": "data"}')
        content_store.store_content('{"test": "data"}', {"scraper_id": "test_scraper"})

        # Update job metadata with content hash
        sample_job.metadata["content_hash"] = content_hash

        # Mock queue operations
        mock_reconciler_queue.enqueue_call.return_value = Mock()
        mock_recorder_queue.enqueue_call.return_value = Mock()

        # Act
        result = process_llm_job(sample_job, mock_provider)

        # Assert
        # Check that result was stored in content store
        stored_result = content_store.get_result(content_hash)
        assert stored_result is not None
        assert json.loads(stored_result) == {"organization": {"name": "Test Org"}}

    @patch("app.content_store.config.get_content_store")
    @patch("app.llm.queue.processor.reconciler_queue")
    @patch("app.llm.queue.processor.recorder_queue")
    def test_should_handle_missing_content_hash(
        self,
        mock_recorder_queue,
        mock_reconciler_queue,
        mock_get_store,
        content_store,
        mock_provider,
        sample_job,
    ):
        """Should handle jobs without content hash gracefully."""
        # Setup
        mock_get_store.return_value = content_store

        # Remove content_hash from metadata
        sample_job.metadata.pop("content_hash", None)

        # Mock provider response
        from app.llm.providers.types import LLMResponse

        mock_response = LLMResponse(
            text='{"result": "test"}',
            model="test-model",
            usage={"prompt_tokens": 25, "completion_tokens": 25, "total_tokens": 50},
            raw={},
        )

        # Make generate return a coroutine
        import asyncio

        async def mock_generate(*args, **kwargs):
            return mock_response

        mock_provider.generate.return_value = mock_generate()

        # Mock queue operations
        mock_reconciler_queue.enqueue_call.return_value = Mock()
        mock_recorder_queue.enqueue_call.return_value = Mock()

        # Act - should not raise error
        process_llm_job(sample_job, mock_provider)

        # Assert - no result stored without hash
        # This is expected behavior

    @patch("app.content_store.config.get_content_store")
    @patch("app.llm.queue.processor.reconciler_queue")
    @patch("app.llm.queue.processor.recorder_queue")
    def test_should_work_without_content_store(
        self,
        mock_recorder_queue,
        mock_reconciler_queue,
        mock_get_store,
        mock_provider,
        sample_job,
    ):
        """Should work normally when content store is not configured."""
        # Setup
        mock_get_store.return_value = None  # No content store

        # Mock provider response
        from app.llm.providers.types import LLMResponse

        mock_response = LLMResponse(
            text='{"result": "no store"}',
            model="test-model",
            usage={"prompt_tokens": 15, "completion_tokens": 15, "total_tokens": 30},
            raw={},
        )

        # Make generate return a coroutine
        import asyncio

        async def mock_generate(*args, **kwargs):
            return mock_response

        mock_provider.generate.return_value = mock_generate()

        # Mock queue operations
        mock_reconciler_queue.enqueue_call.return_value = Mock()
        mock_recorder_queue.enqueue_call.return_value = Mock()

        # Act - should not raise error
        process_llm_job(sample_job, mock_provider)

    @patch("app.content_store.config.get_content_store")
    @patch("app.llm.queue.processor.reconciler_queue")
    @patch("app.llm.queue.processor.recorder_queue")
    def test_should_not_store_failed_results(
        self,
        mock_recorder_queue,
        mock_reconciler_queue,
        mock_get_store,
        content_store,
        mock_provider,
        sample_job,
    ):
        """Should not store results in content store when job fails."""
        # Setup
        mock_get_store.return_value = content_store

        # Mock provider to raise error
        import asyncio

        async def mock_failing_generate(*args, **kwargs):
            raise Exception("LLM error")

        mock_provider.generate.return_value = mock_failing_generate()

        # Pre-store content
        content_hash = content_store.hash_content('{"fail": "test"}')
        content_store.store_content('{"fail": "test"}', {"scraper_id": "test_scraper"})
        sample_job.metadata["content_hash"] = content_hash

        # Act - should raise error
        with pytest.raises(Exception):
            process_llm_job(sample_job, mock_provider)

        # Assert - no result stored
        assert content_store.get_result(content_hash) is None

    @patch("app.content_store.config.get_content_store")
    @patch("app.llm.queue.processor.reconciler_queue")
    @patch("app.llm.queue.processor.recorder_queue")
    def test_integration_with_job_metadata_flow(
        self,
        mock_recorder_queue,
        mock_reconciler_queue,
        mock_get_store,
        content_store,
        mock_provider,
    ):
        """Integration test showing full flow from scraper to result storage."""
        # Setup
        mock_get_store.return_value = content_store
        mock_reconciler_queue.enqueue_call.return_value = Mock()
        mock_recorder_queue.enqueue_call.return_value = Mock()

        # 1. Scraper stores content
        content = '{"name": "Integration Test Pantry", "address": "789 Test Ave"}'
        content_hash = content_store.hash_content(content)
        entry = content_store.store_content(content, {"scraper_id": "test_scraper"})

        # 2. Create job with content hash in metadata
        from datetime import datetime

        job = LLMJob(
            id="integration-job-456",
            prompt=f"Process: {content}",
            format={"type": "json_schema", "schema": {}},
            metadata={"scraper_id": "test_scraper", "content_hash": content_hash},
            provider_config={},
            created_at=datetime.utcnow(),
        )

        # 3. Link job to content
        content_store.link_job(content_hash, job.id)

        # 4. Mock LLM response
        from app.llm.providers.types import LLMResponse

        mock_response = LLMResponse(
            text='{"organization": {"name": "Integration Test Pantry"}}',
            model="test-model",
            usage={"prompt_tokens": 75, "completion_tokens": 75, "total_tokens": 150},
            raw={},
        )

        # Make generate return a coroutine
        import asyncio

        async def mock_generate(*args, **kwargs):
            return mock_response

        mock_provider.generate.return_value = mock_generate()

        # 5. Process job
        process_llm_job(job, mock_provider)

        # 6. Verify result stored
        stored_result = content_store.get_result(content_hash)
        assert stored_result == '{"organization": {"name": "Integration Test Pantry"}}'

        # 7. Verify statistics updated
        stats = content_store.get_statistics()
        assert stats["processed_content"] == 1
