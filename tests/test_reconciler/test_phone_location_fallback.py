"""Tests for phone location fallback — phones should attach to location for single-location orgs."""

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.llm.queue.models import JobResult, JobStatus, LLMJob
from app.llm.providers.types import LLMResponse
from app.reconciler.job_processor import JobProcessor


def _make_job_result(locations, phones):
    """Build a JobResult with given locations and top-level phones."""
    data = {
        "organization": [
            {
                "name": "Phone Fallback Org",
                "description": "Test org for phone fallback",
            }
        ],
        "service": [],
        "location": locations,
        "phone": phones,
    }
    return JobResult(
        job_id="test-phone-fallback",
        job=LLMJob(
            id="test-phone-fallback",
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


class TestPhoneLocationFallback:
    """Top-level phones with no entity ref should fall back to location for single-location orgs."""

    def test_phone_attaches_to_single_location(self):
        """Phone with no entity reference should attach to location when org has exactly 1 location."""
        loc_uuid = uuid.uuid4()

        job_result = _make_job_result(
            locations=[
                {
                    "name": "Only Location",
                    "description": "The sole location",
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                }
            ],
            phones=[
                {"number": "555-0199", "type": "voice"},
            ],
        )

        mock_db = MagicMock(spec=Session)
        processor = JobProcessor(db=mock_db)
        org_uuid = uuid.uuid4()

        with (
            patch.object(processor, "db", mock_db),
            patch("app.reconciler.job_processor.OrganizationCreator") as MockOrgCreator,
            patch("app.reconciler.job_processor.LocationCreator") as MockLocCreator,
            patch("app.reconciler.job_processor.ServiceCreator") as MockSvcCreator,
            patch("app.reconciler.job_processor.VersionTracker"),
        ):
            mock_org = MockOrgCreator.return_value
            mock_org.process_organization.return_value = (org_uuid, True)
            mock_org.create_organization.return_value = org_uuid

            mock_loc = MockLocCreator.return_value
            # No existing location match — triggers create path
            mock_loc.find_matching_location.return_value = None
            # create_location returns a UUID string
            mock_loc.create_location.return_value = str(loc_uuid)

            mock_svc = MockSvcCreator.return_value
            mock_svc.create_phone.return_value = uuid.uuid4()

            processor.process_job_result(job_result)

            # Phone should be created with BOTH org and location
            mock_svc.create_phone.assert_called_once()
            call_kwargs = mock_svc.create_phone.call_args
            if call_kwargs.kwargs:
                assert call_kwargs.kwargs.get("organization_id") == org_uuid
                assert (
                    call_kwargs.kwargs.get("location_id") == loc_uuid
                ), "Phone should attach to location for single-location org"
            else:
                # Fallback: check by position (number, type, org_id, service_id, location_id, metadata)
                assert (
                    call_kwargs.args[4] == loc_uuid
                ), "Phone should attach to location for single-location org"

    def test_phone_org_only_with_multiple_locations(self):
        """Phone with no entity reference should attach to org only when multiple locations exist."""
        loc_a_uuid = uuid.uuid4()
        loc_b_uuid = uuid.uuid4()

        job_result = _make_job_result(
            locations=[
                {
                    "name": "Location A",
                    "description": "First",
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                },
                {
                    "name": "Location B",
                    "description": "Second",
                    "latitude": 40.7580,
                    "longitude": -73.9855,
                },
            ],
            phones=[
                {"number": "555-0200", "type": "voice"},
            ],
        )

        mock_db = MagicMock(spec=Session)
        processor = JobProcessor(db=mock_db)
        org_uuid = uuid.uuid4()

        with (
            patch.object(processor, "db", mock_db),
            patch("app.reconciler.job_processor.OrganizationCreator") as MockOrgCreator,
            patch("app.reconciler.job_processor.LocationCreator") as MockLocCreator,
            patch("app.reconciler.job_processor.ServiceCreator") as MockSvcCreator,
            patch("app.reconciler.job_processor.VersionTracker"),
        ):
            mock_org = MockOrgCreator.return_value
            mock_org.process_organization.return_value = (org_uuid, True)
            mock_org.create_organization.return_value = org_uuid

            mock_loc = MockLocCreator.return_value
            # No existing location match — triggers create path
            mock_loc.find_matching_location.return_value = None
            # create_location returns UUID strings
            mock_loc.create_location.side_effect = [str(loc_a_uuid), str(loc_b_uuid)]

            mock_svc = MockSvcCreator.return_value
            mock_svc.create_phone.return_value = uuid.uuid4()

            processor.process_job_result(job_result)

            # Phone should be created with org only, NOT location
            mock_svc.create_phone.assert_called_once()
            call_kwargs = mock_svc.create_phone.call_args
            if call_kwargs.kwargs:
                assert call_kwargs.kwargs.get("organization_id") == org_uuid
                assert (
                    call_kwargs.kwargs.get("location_id") is None
                ), "Phone should NOT attach to location when org has multiple locations"
            else:
                assert (
                    call_kwargs.args[4] is None
                ), "Phone should NOT attach to location when org has multiple locations"
