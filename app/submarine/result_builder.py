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

from pydantic import ValidationError

from app.llm.queue.job import LLMJob
from app.llm.queue.types import JobResult, JobStatus
from app.models.hsds.response import PhoneInfo, ScheduleInfo
from app.submarine.models import SubmarineJob, SubmarineResult, SubmarineStatus
from app.utils.ical import normalize_byday

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
        if result.status in (
            SubmarineStatus.NO_DATA,
            SubmarineStatus.ERROR,
            SubmarineStatus.BLOCKED,
        ):
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
        self,
        job: SubmarineJob,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Map extracted fields to HSDS-structured data dict.

        Only includes fields that are in job.missing_fields AND were actually
        extracted. Structural fields (name, lat, lon) are always included.
        This prevents submarine from overwriting existing data for fields
        it wasn't dispatched to fill.
        """
        missing = set(job.missing_fields)

        # Structural fields always included
        location: dict[str, Any] = {
            "name": job.location_name,
            "latitude": job.latitude,
            "longitude": job.longitude,
        }

        organization: dict[str, Any] = {
            "name": job.location_name,
        }

        # Map phone — only if phone was a missing field
        if "phone" in missing:
            phone = fields.get("phone")
            if phone:
                phone_entry = {"number": phone, "type": "voice"}
                try:
                    PhoneInfo(**phone_entry)
                    location["phones"] = [phone_entry]
                except ValidationError:
                    logger.warning(
                        "submarine_invalid_phone",
                        extra={"phone": phone},
                    )

        # Map hours to schedules — only if hours was a missing field
        if "hours" in missing:
            hours = fields.get("hours")
            if hours and isinstance(hours, list):
                schedules = []
                for entry in hours:
                    if not isinstance(entry, dict):
                        continue
                    raw_day = entry.get("day", "")
                    byday = normalize_byday(raw_day)
                    if byday is None:
                        logger.warning(
                            "submarine_unrecognized_byday",
                            extra={
                                "location_id": job.location_id,
                                "raw_day": raw_day,
                            },
                        )
                        continue
                    sched = {
                        "byday": byday,
                        "opens_at": entry.get("opens_at", ""),
                        "closes_at": entry.get("closes_at", ""),
                        "freq": "WEEKLY",
                        "wkst": "MO",
                    }
                    try:
                        ScheduleInfo(**sched)
                        # Skip schedules with empty time fields
                        if not sched["opens_at"] or not sched["closes_at"]:
                            continue
                        schedules.append(sched)
                    except (ValidationError, ValueError, TypeError):
                        logger.warning(
                            "submarine_invalid_schedule",
                            extra={"schedule": sched},
                        )
                if schedules:
                    location["schedules"] = schedules

        # Map description — only if description was a missing field
        if "description" in missing:
            description = fields.get("description")
            if description:
                location["description"] = description

        # Map email to organization — only if email was a missing field
        if "email" in missing:
            email = fields.get("email")
            if email:
                organization["email"] = email

        # Only include org if submarine actually has org-level data to contribute.
        # A bare name-only org creates noise in the merge strategy.
        has_org_data = len(organization) > 1  # More than just "name"
        result: dict[str, Any] = {
            "service": [],
            "location": [location],
        }
        if has_org_data:
            result["organization"] = [organization]

        return result
