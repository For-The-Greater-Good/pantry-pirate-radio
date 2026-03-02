"""Regression test: enrichment failure must not cause automatic rejection."""

import json
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session
from datetime import datetime

from app.llm.queue.models import JobResult, JobStatus, LLMJob
from app.llm.providers.types import LLMResponse
from app.validator.job_processor import ValidationProcessor


class TestEnrichmentFailureRecovery:
    def _make_job_result(self):
        data = {
            "organization": [{"name": "Test Org", "description": "Test"}],
            "location": [
                {
                    "name": "Test Loc",
                    "latitude": None,
                    "longitude": None,
                    "address": [
                        {
                            "address_1": "123 Main St",
                            "city": "Boston",
                            "state_province": "MA",
                            "postal_code": "02101",
                        }
                    ],
                }
            ],
            "service": [],
        }
        return JobResult(
            job_id="test-1",
            job=LLMJob(
                id="test-1",
                prompt="test",
                format={},
                provider_config={},
                metadata={"scraper_id": "test"},
                created_at=datetime.now(),
            ),
            status=JobStatus.COMPLETED,
            result=LLMResponse(
                text=json.dumps(data),
                model="test",
                usage={"total_tokens": 1},
                raw={},
            ),
        )

    def test_enrichment_failure_does_not_reject(self):
        """Locations needing geocoding must NOT be rejected when enrichment service fails."""
        with patch(
            "app.validator.job_processor.ValidationProcessor._is_enabled",
            return_value=True,
        ):
            processor = ValidationProcessor(db=MagicMock(spec=Session))

        # Make enrichment fail
        with (
            patch.object(
                processor,
                "_enrich_data",
                side_effect=Exception("API timeout"),
            ),
            patch("app.validator.job_processor.ValidationProcessor._commit_changes"),
        ):
            result = processor.process_job_result(self._make_job_result())

        locations = result["data"].get("location", [])
        for loc in locations:
            if loc.get("latitude") is None:
                assert loc.get("validation_status") != "rejected", (
                    "Location without coords due to enrichment failure "
                    "must not be rejected"
                )
