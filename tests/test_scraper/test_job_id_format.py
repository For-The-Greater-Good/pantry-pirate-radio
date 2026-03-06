"""Regression test: job IDs must be UUID4, not timestamps."""

import uuid
from unittest.mock import patch, MagicMock
from app.scraper.utils import ScraperUtils


class TestJobIdFormat:
    def test_job_id_is_valid_uuid4(self):
        """Job IDs must be UUID4 to prevent collisions in parallel scraping."""
        mock_backend = MagicMock()
        mock_backend.enqueue.return_value = "result-id"

        with (
            patch(
                "app.llm.queue.backend.get_queue_backend",
                return_value=mock_backend,
            ),
            patch(
                "app.content_store.config.get_content_store",
                return_value=None,
            ),
            patch("app.core.events.get_setting") as mock_setting,
            patch.dict("os.environ", {"QUEUE_BACKEND": "sqs"}),
        ):
            mock_setting.side_effect = lambda key, type_, *a, **_kw: {
                "llm_provider": "openai",
                "llm_model_name": "test",
                "llm_temperature": 0.7,
                "llm_max_tokens": 100,
            }.get(key)

            utils = ScraperUtils.__new__(ScraperUtils)
            utils.scraper_id = "test"
            utils.system_prompt = "test prompt"
            utils.hsds_schema = {}
            utils.schema_converter = MagicMock()
            utils.queue_for_processing("test content")

            call_args = mock_backend.enqueue.call_args
            # First positional arg is the LLMJob
            job = call_args[0][0]
            job_id = job.id
            assert job_id is not None
            # Must be a valid UUID4, not a timestamp float
            parsed = uuid.UUID(job_id, version=4)
            assert str(parsed) == job_id
