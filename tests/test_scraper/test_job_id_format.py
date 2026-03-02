"""Regression test: job IDs must be UUID4, not timestamps."""

import uuid
from unittest.mock import patch, MagicMock, PropertyMock
from app.scraper.utils import ScraperUtils


class TestJobIdFormat:
    def test_job_id_is_valid_uuid4(self):
        """Job IDs must be UUID4 to prevent collisions in parallel scraping."""
        # Capture the LLMJob created by queue_for_processing
        with (
            patch("app.scraper.utils.llm_queue") as mock_queue,
            patch("app.scraper.utils.get_content_store", return_value=None),
            patch.object(ScraperUtils, "_load_system_prompt", return_value="prompt"),
            patch.object(ScraperUtils, "_load_hsds_schema", return_value={}),
            patch("app.scraper.utils.get_setting") as mock_setting,
        ):
            mock_setting.side_effect = lambda key, type_, *a, **kw: {
                "llm_provider": "openai",
                "llm_model_name": "test",
                "llm_temperature": 0.7,
                "llm_max_tokens": 100,
            }.get(key)
            mock_queue.enqueue_call.return_value = MagicMock(id="result-id")

            utils = ScraperUtils.__new__(ScraperUtils)
            utils.scraper_id = "test"
            utils.system_prompt = "test prompt"
            utils.hsds_schema = {}
            utils.schema_converter = MagicMock()
            utils.queue_for_processing("test content")

            call_args = mock_queue.enqueue_call.call_args
            # job_id is passed as keyword arg to enqueue_call
            job_id = call_args[1].get("job_id")
            assert job_id is not None
            # Must be a valid UUID4, not a timestamp float
            parsed = uuid.UUID(job_id, version=4)
            assert str(parsed) == job_id
