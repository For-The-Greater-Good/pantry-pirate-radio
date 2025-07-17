"""Additional edge case tests for LLM jobs."""

from unittest.mock import MagicMock, patch

import pytest

from app.llm.jobs import JobProcessor
from app.llm.providers.types import LLMResponse
from app.llm.queue.models import JobResult, JobStatus


class TestJobProcessorEdgeCases:
    """Test edge cases for JobProcessor."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock LLM provider."""
        return MagicMock()

    @pytest.fixture
    def job_processor(self, mock_provider):
        """Create a JobProcessor instance."""
        return JobProcessor(provider=mock_provider)

    def test_get_result_no_job_data_in_meta(self, job_processor):
        """Test get_result when job has no metadata."""
        with patch("app.llm.jobs.llm_queue") as mock_queue:
            # Mock RQ job with empty meta
            mock_rq_job = MagicMock()
            mock_rq_job.meta = {}  # No job data in meta
            mock_queue.fetch_job.return_value = mock_rq_job

            result = job_processor.get_result("test-job")

            assert result is None

    def test_get_result_job_disappears_during_wait(self, job_processor):
        """Test get_result when job disappears during wait."""
        with patch("app.llm.jobs.llm_queue") as mock_queue:
            # Mock initial job fetch success
            mock_rq_job = MagicMock()
            mock_rq_job.meta = {
                "job": {
                    "id": "test",
                    "prompt": "test",
                    "metadata": {},
                    "format": {},
                    "provider_config": {},
                    "created_at": "2024-01-01T00:00:00",
                }
            }

            # First call returns job, second returns None (job disappeared)
            mock_queue.fetch_job.side_effect = [mock_rq_job, None]

            result = job_processor.get_result("test-job", wait=True)

            assert result is None

    def test_get_result_pending_job(self, job_processor):
        """Test get_result for a job that's still pending."""
        with patch("app.llm.jobs.llm_queue") as mock_queue:
            # Mock RQ job that's still pending
            mock_rq_job = MagicMock()
            mock_rq_job.meta = {
                "job": {
                    "id": "test-job",
                    "prompt": "test prompt",
                    "metadata": {},
                    "format": {},
                    "provider_config": {},
                    "created_at": "2024-01-01T00:00:00",
                }
            }
            mock_rq_job.is_finished = False
            mock_rq_job.is_failed = False
            mock_queue.fetch_job.return_value = mock_rq_job

            result = job_processor.get_result("test-job", wait=False)

            assert result is not None
            assert result.status == JobStatus.QUEUED
            assert result.result is None
            assert result.error is None
            assert result.completed_at is None
            assert result.processing_time is None
