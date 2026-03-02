"""Regression test: no debug prints in LLM processor (Constitution XII)."""

from unittest.mock import MagicMock, patch
from datetime import datetime

from app.llm.queue.models import LLMJob, JobResult, JobStatus
from app.llm.providers.types import LLMResponse
from app.llm.queue.processor import process_llm_job


class TestNoDebugPrints:
    def test_process_llm_job_no_print_calls(self):
        """process_llm_job must not call print() — Constitution XII mandates structlog."""
        job = LLMJob(
            id="test-1",
            prompt="test",
            format={},
            provider_config={},
            metadata={"scraper_id": "test"},
            created_at=datetime.now(),
        )
        provider = MagicMock()
        provider.model_name = "test-model"
        response = LLMResponse(
            text='{"organization":[],"service":[],"location":[]}',
            model="test",
            usage={"total_tokens": 1},
            raw={},
        )
        provider.generate.return_value = response

        with (
            patch("builtins.print") as mock_print,
            patch("app.llm.queue.processor.reconciler_queue"),
            patch("app.llm.queue.processor.recorder_queue"),
            patch(
                "app.content_store.config.get_content_store", return_value=None
            ),
            patch(
                "app.llm.queue.processor.should_use_validator",
                return_value=False,
            ),
        ):
            process_llm_job(job, provider)
            mock_print.assert_not_called()
