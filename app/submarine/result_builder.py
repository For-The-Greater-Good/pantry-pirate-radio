"""Converts submarine extraction results into JobResult for the Reconciler.

Maps extracted fields (phone, hours, email, description) to HSDS-structured
data that the Reconciler knows how to process. Sets metadata for:
- Cycle prevention (scraper_id="submarine")
- Direct ID update (location_id in metadata)
- Provenance (source_scraper_id)
- Corroboration exclusion (source_type='submarine' excluded from multi-source scoring)
"""

import structlog
from datetime import UTC, datetime
from typing import Any

from app.llm.queue.job import LLMJob
from app.llm.queue.types import JobResult, JobStatus
from app.submarine.models import SubmarineJob, SubmarineResult

logger = structlog.get_logger(__name__)


class SubmarineResultBuilder:
    """Converts SubmarineResult into a JobResult for the Reconciler."""

    def build(self, job: SubmarineJob, result: SubmarineResult) -> JobResult | None:
        """Build a JobResult from a submarine crawl result.

        Args:
            job: The original SubmarineJob with location context.
            result: The extraction result from the crawler + LLM.

        Returns:
            JobResult ready for the Reconciler queue, or None if
            no useful data was extracted.
        """
        if result.status in ("no_data", "error", "blocked"):
            return None

        if not result.extracted_fields:
            return None

        data = self._build_hsds_data(job, result.extracted_fields)

        llm_job = LLMJob(
            id=f"submarine-{job.id}",
            prompt="",
            format={"type": "hsds"},
            metadata={
                "scraper_id": "submarine",
                "source_type": "submarine",
                "location_id": job.location_id,
                "source_scraper_id": job.source_scraper_id,
                "website_url": job.website_url,
                "submarine_job_id": job.id,
            },
            created_at=datetime.now(UTC),
        )

        return JobResult(
            job_id=f"submarine-{job.id}",
            job=llm_job,
            status=JobStatus.COMPLETED,
            data=data,
        )

    def _build_hsds_data(
        self, job: SubmarineJob, fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Map extracted fields to HSDS-structured data dict.

        The Reconciler expects data with organization/service/location
        arrays matching the standard pipeline format.
        """
        location: dict[str, Any] = {
            "name": job.location_name,
            "latitude": job.latitude,
            "longitude": job.longitude,
            "phones": [],
            "schedules": [],
        }

        organization: dict[str, Any] = {
            "name": job.location_name,
        }

        # Map phone
        phone = fields.get("phone")
        if phone:
            location["phones"] = [{"number": phone, "type": "voice"}]

        # Map hours to schedules (LLM may return a string instead of list)
        hours = fields.get("hours")
        if hours and isinstance(hours, list):
            schedules = []
            for entry in hours:
                if isinstance(entry, dict):
                    schedules.append(
                        {
                            "byday": entry.get("day", ""),
                            "opens_at": entry.get("opens_at", ""),
                            "closes_at": entry.get("closes_at", ""),
                            "freq": "WEEKLY",
                        }
                    )
            location["schedules"] = schedules

        # Map description
        description = fields.get("description")
        location["description"] = description if description else None

        # Map email to organization
        email = fields.get("email")
        if email:
            organization["email"] = email

        return {
            "organization": [organization],
            "service": [],
            "location": [location],
        }
