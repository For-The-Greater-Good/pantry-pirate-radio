"""Regression test: language records must not be created when phone_id is None."""

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.llm.queue.models import JobResult, JobStatus, LLMJob
from app.llm.providers.types import LLMResponse
from app.reconciler.job_processor import JobProcessor


class TestPhoneLanguageOrphan:
    def _make_job_result(self, org_phones):
        """Helper to create JobResult with org phones."""
        data = {
            "organization": [
                {
                    "name": "Test Org",
                    "description": "Test",
                    "phones": org_phones,
                }
            ],
            "service": [],
            "location": [],
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

    def test_language_not_created_when_phone_returns_none(self):
        """When create_phone returns None, create_language must NOT be called."""
        job_result = self._make_job_result(
            [
                {
                    "number": "",
                    "type": "voice",
                    "languages": [{"name": "English", "code": "en"}],
                },
            ]
        )
        mock_db = MagicMock(spec=Session)
        processor = JobProcessor(db=mock_db)

        with (
            patch.object(processor, "db", mock_db),
            patch(
                "app.reconciler.job_processor.OrganizationCreator"
            ) as MockOrgCreator,
            patch("app.reconciler.job_processor.LocationCreator"),
            patch(
                "app.reconciler.job_processor.ServiceCreator"
            ) as MockSvcCreator,
            patch("app.reconciler.job_processor.VersionTracker"),
        ):
            mock_org = MockOrgCreator.return_value
            mock_org.process_organization.return_value = (
                uuid.uuid4(),
                True,
            )
            mock_org.create_organization.return_value = uuid.uuid4()
            mock_svc = MockSvcCreator.return_value
            mock_svc.create_phone.return_value = None  # Phone creation fails

            processor.process_job_result(job_result)

            mock_svc.create_language.assert_not_called()

    def test_language_created_when_phone_succeeds(self):
        """When create_phone returns a UUID, create_language SHOULD be called."""
        job_result = self._make_job_result(
            [
                {
                    "number": "555-0123",
                    "type": "voice",
                    "languages": [{"name": "English", "code": "en"}],
                },
            ]
        )
        mock_db = MagicMock(spec=Session)
        processor = JobProcessor(db=mock_db)
        phone_uuid = uuid.uuid4()

        with (
            patch.object(processor, "db", mock_db),
            patch(
                "app.reconciler.job_processor.OrganizationCreator"
            ) as MockOrgCreator,
            patch("app.reconciler.job_processor.LocationCreator"),
            patch(
                "app.reconciler.job_processor.ServiceCreator"
            ) as MockSvcCreator,
            patch("app.reconciler.job_processor.VersionTracker"),
        ):
            mock_org = MockOrgCreator.return_value
            mock_org.process_organization.return_value = (
                uuid.uuid4(),
                True,
            )
            mock_org.create_organization.return_value = uuid.uuid4()
            mock_svc = MockSvcCreator.return_value
            mock_svc.create_phone.return_value = phone_uuid

            processor.process_job_result(job_result)

            mock_svc.create_language.assert_called()
