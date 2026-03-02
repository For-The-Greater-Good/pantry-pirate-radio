"""Regression test: reconciler must use enriched data from validator, not re-parse LLM text."""

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.llm.queue.models import JobResult, JobStatus, LLMJob
from app.llm.providers.types import LLMResponse
from app.reconciler.job_processor import JobProcessor


class TestEnrichmentDataUsage:
    def test_uses_enriched_coordinates(self):
        """When validator enriched coordinates, reconciler must use them, not skip."""
        original_data = {
            "organization": [{"name": "Test Org", "description": "Test"}],
            "location": [
                {
                    "name": "Test Loc",
                    "latitude": None,
                    "longitude": None,
                }
            ],
            "service": [],
        }
        enriched_data = {
            "organization": [
                {
                    "name": "Test Org",
                    "description": "Test",
                    "confidence_score": 80,
                    "validation_status": "verified",
                }
            ],
            "location": [
                {
                    "name": "Test Loc",
                    "latitude": 40.7128,
                    "longitude": -74.006,
                    "geocoding_source": "arcgis",
                    "confidence_score": 90,
                    "validation_status": "verified",
                    "address": [
                        {
                            "address_1": "123 Main",
                            "city": "NY",
                            "state_province": "NY",
                            "postal_code": "10001",
                            "country": "US",
                            "address_type": "physical",
                        }
                    ],
                }
            ],
            "service": [],
        }

        job_result = JobResult(
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
                text=json.dumps(original_data),
                model="test",
                usage={"total_tokens": 1},
                raw={},
            ),
            data=enriched_data,  # Validator-enriched data
        )

        mock_db = MagicMock(spec=Session)
        processor = JobProcessor(db=mock_db)

        with (
            patch("app.reconciler.job_processor.OrganizationCreator") as MockOrg,
            patch("app.reconciler.job_processor.LocationCreator") as MockLoc,
            patch("app.reconciler.job_processor.ServiceCreator"),
            patch("app.reconciler.job_processor.VersionTracker"),
        ):
            mock_org = MockOrg.return_value
            mock_org.process_organization.return_value = (
                uuid.uuid4(),
                True,
            )
            mock_loc = MockLoc.return_value
            mock_loc.find_matching_location.return_value = None
            mock_loc.create_location.return_value = str(uuid.uuid4())

            processor.process_job_result(job_result)

            # LocationCreator.create_location MUST be called (not skipped)
            mock_loc.create_location.assert_called()

    def test_falls_back_to_result_text_when_no_data(self):
        """When data is None (no validator), reconciler must parse result.text."""
        raw_data = {
            "organization": [{"name": "Test Org", "description": "Test"}],
            "location": [
                {
                    "name": "Test Loc",
                    "latitude": 42.0,
                    "longitude": -71.0,
                    "address": [
                        {
                            "address_1": "1 Main",
                            "city": "Boston",
                            "state_province": "MA",
                            "postal_code": "02101",
                            "country": "US",
                            "address_type": "physical",
                        }
                    ],
                }
            ],
            "service": [],
        }
        job_result = JobResult(
            job_id="test-2",
            job=LLMJob(
                id="test-2",
                prompt="test",
                format={},
                provider_config={},
                metadata={"scraper_id": "test"},
                created_at=datetime.now(),
            ),
            status=JobStatus.COMPLETED,
            result=LLMResponse(
                text=json.dumps(raw_data),
                model="test",
                usage={"total_tokens": 1},
                raw={},
            ),
            # data is None — no validator
        )

        mock_db = MagicMock(spec=Session)
        processor = JobProcessor(db=mock_db)

        with (
            patch("app.reconciler.job_processor.OrganizationCreator") as MockOrg,
            patch("app.reconciler.job_processor.LocationCreator") as MockLoc,
            patch("app.reconciler.job_processor.ServiceCreator"),
            patch("app.reconciler.job_processor.VersionTracker"),
        ):
            mock_org = MockOrg.return_value
            mock_org.process_organization.return_value = (
                uuid.uuid4(),
                True,
            )
            mock_loc = MockLoc.return_value
            mock_loc.find_matching_location.return_value = None
            mock_loc.create_location.return_value = str(uuid.uuid4())

            processor.process_job_result(job_result)

            # Should still process the location from result.text
            mock_loc.create_location.assert_called()
