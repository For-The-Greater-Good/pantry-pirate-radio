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
from app.submarine.models import SubmarineJob, SubmarineResult

logger = structlog.get_logger(__name__)

# Day name → RRULE two-letter abbreviation (RFC 5545)
_DAY_ABBREV = {
    "monday": "MO",
    "tuesday": "TU",
    "wednesday": "WE",
    "thursday": "TH",
    "friday": "FR",
    "saturday": "SA",
    "sunday": "SU",
}


def _normalize_byday(day: str) -> str:
    """Convert full day name to RRULE abbreviation. Pass through if already short."""
    return _DAY_ABBREV.get(day.lower(), day)


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
                    sched = {
                        "byday": _normalize_byday(entry.get("day", "")),
                        "opens_at": entry.get("opens_at", ""),
                        "closes_at": entry.get("closes_at", ""),
                        "freq": "WEEKLY",
                        "wkst": "MO",
                    }
                    try:
                        ScheduleInfo(**sched)
                        # Reject schedules with empty time fields
                        if not sched["opens_at"] or not sched["closes_at"]:
                            raise ValidationError
                        schedules.append(sched)
                    except (ValidationError, Exception):
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

        return {
            "organization": [organization],
            "service": [],
            "location": [location],
        }
