"""Submarine job dispatcher — detects locations with missing fields and enqueues crawl jobs.

Called by the reconciler after processing a location. Checks if the location
has a website URL and missing target fields, then enqueues a SubmarineJob
for the submarine worker to crawl and extract data.
"""

import os
import structlog
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.submarine.models import SUBMARINE_TARGET_FIELDS, SubmarineJob

logger = structlog.get_logger(__name__)


class SubmarineDispatcher:
    """Detects locations with missing fields and enqueues SubmarineJobs."""

    def __init__(self, db: Session):
        self.db = db

    def check_and_enqueue(
        self,
        location_id: str,
        organization_id: str | None,
        job_metadata: dict[str, Any],
        force: bool = False,
    ) -> str | None:
        """Check if a location needs submarine enrichment and enqueue if so.

        Args:
            location_id: Canonical location ID from the reconciler.
            organization_id: Parent organization ID (for website lookup).
            job_metadata: Original job metadata (used for cycle prevention).
            force: If True, bypass the SUBMARINE_ENABLED check (used by scanner).

        Returns:
            SubmarineJob ID if enqueued, None if not needed.
        """
        # --- Cycle prevention (first check, before anything else) ---
        if job_metadata.get("scraper_id") == "submarine":
            return None
        if job_metadata.get("source_type") == "submarine":
            return None

        # --- Feature flag (skipped when force=True for manual scans) ---
        if not force and not settings.SUBMARINE_ENABLED:
            return None

        # --- Website URL lookup ---
        website_url = self._get_website_url(location_id, organization_id)
        if not website_url:
            return None

        # --- Adaptive cooldown ---
        cooldown_row = self.db.execute(
            text(
                "SELECT submarine_last_crawled_at, submarine_last_status "
                "FROM location WHERE id = :id"
            ),
            {"id": location_id},
        ).first()

        if cooldown_row:
            last_crawled, last_status = cooldown_row
            cooldown_days = self._get_cooldown_days(last_status)
            if self._is_in_cooldown(last_crawled, cooldown_days):
                return None

        # --- Gap detection ---
        missing_fields = self._detect_missing_fields(location_id)
        if not missing_fields:
            return None

        # --- Get location data for the job ---
        loc_row = self.db.execute(
            text("SELECT name, latitude, longitude FROM location WHERE id = :id"),
            {"id": location_id},
        ).first()

        location_name = ""
        latitude = None
        longitude = None
        if loc_row:
            location_name = loc_row[0] or ""
            latitude = float(loc_row[1]) if loc_row[1] is not None else None
            longitude = float(loc_row[2]) if loc_row[2] is not None else None

        # --- Build and enqueue job ---
        job = SubmarineJob(
            id=str(uuid.uuid4()),
            location_id=location_id,
            organization_id=organization_id,
            website_url=website_url,
            missing_fields=missing_fields,
            source_scraper_id=job_metadata.get("scraper_id", "unknown"),
            location_name=location_name,
            latitude=latitude,
            longitude=longitude,
            max_attempts=settings.SUBMARINE_MAX_ATTEMPTS,
        )
        return self._enqueue(job)

    def _get_website_url(
        self, location_id: str, organization_id: str | None
    ) -> str | None:
        """Find a website URL from the organization or service."""
        # Check organization website first
        if organization_id:
            row = self.db.execute(
                text("SELECT website FROM organization WHERE id = :id"),
                {"id": organization_id},
            ).first()
            if row and row[0]:
                return row[0]

        # Check service URLs linked to this location
        row = self.db.execute(
            text(
                "SELECT s.url FROM service s "
                "JOIN service_at_location sal ON s.id = sal.service_id "
                "WHERE sal.location_id = :loc_id AND s.url IS NOT NULL "
                "LIMIT 1"
            ),
            {"loc_id": location_id},
        ).first()
        if row and row[0]:
            return row[0]

        return None

    def _detect_missing_fields(self, location_id: str) -> list[str]:
        """Query DB for which target fields are missing on a location."""
        missing = []

        # Check phone
        phone_row = self.db.execute(
            text("SELECT EXISTS(SELECT 1 FROM phone WHERE location_id = :id)"),
            {"id": location_id},
        ).first()
        if phone_row and not phone_row[0]:
            missing.append("phone")

        # Check schedules (hours)
        schedule_row = self.db.execute(
            text("SELECT EXISTS(SELECT 1 FROM schedule WHERE location_id = :id)"),
            {"id": location_id},
        ).first()
        if schedule_row and not schedule_row[0]:
            missing.append("hours")

        # Check email (on parent organization)
        email_row = self.db.execute(
            text(
                "SELECT email FROM organization o "
                "JOIN location l ON l.organization_id = o.id "
                "WHERE l.id = :id"
            ),
            {"id": location_id},
        ).first()
        if not email_row or not email_row[0]:
            missing.append("email")

        # Check description (missing or generic)
        desc_row = self.db.execute(
            text("SELECT description FROM location WHERE id = :id"),
            {"id": location_id},
        ).first()
        if (
            not desc_row
            or not desc_row[0]
            # The reconciler generates "Food service location: {name}" as a placeholder
            # when no description is available (see job_processor.py:871). Treat as missing.
            or desc_row[0].startswith("Food service location:")
        ):
            missing.append("description")

        return missing

    def _get_cooldown_days(self, last_status: str | None) -> int:
        """Get the appropriate cooldown period based on last crawl status."""
        if last_status in ("success", "partial"):
            return settings.SUBMARINE_COOLDOWN_SUCCESS_DAYS
        if last_status in ("no_data", "blocked"):
            return settings.SUBMARINE_COOLDOWN_NO_DATA_DAYS
        if last_status == "error":
            return settings.SUBMARINE_COOLDOWN_ERROR_DAYS
        # Unknown status or None — no cooldown
        return 0

    @staticmethod
    def _is_in_cooldown(
        last_crawled: datetime | None,
        cooldown_days: int,
    ) -> bool:
        """Check if a location is still within its cooldown period."""
        if last_crawled is None:
            return False
        if cooldown_days <= 0:
            return False
        cutoff = datetime.now(UTC) - timedelta(days=cooldown_days)
        return last_crawled > cutoff

    def _enqueue(self, job: SubmarineJob) -> str:
        """Enqueue a SubmarineJob to the submarine queue.

        Uses Redis/RQ locally or SQS on AWS, following the existing
        dual-backend pattern (QUEUE_BACKEND env var).
        """
        job_data = job.model_dump(mode="json")

        if os.environ.get("QUEUE_BACKEND", "redis").lower() == "sqs":
            from app.pipeline.sqs_sender import send_to_sqs

            queue_url = os.environ.get("SUBMARINE_QUEUE_URL", "")
            if not queue_url:
                logger.error(
                    "submarine_enqueue_failed",
                    reason="SUBMARINE_QUEUE_URL not set",
                    job_id=job.id,
                )
                return job.id
            send_to_sqs(
                queue_url=queue_url,
                message_body=job_data,
                message_group_id=job.source_scraper_id,
                deduplication_id=job.id,
                source="submarine-dispatcher",
            )
        else:
            from app.llm.queue.queues import submarine_queue

            submarine_queue.enqueue_call(
                func="app.submarine.worker.process_submarine_job",
                args=(job_data,),
                result_ttl=settings.REDIS_TTL_SECONDS,
                failure_ttl=settings.REDIS_TTL_SECONDS,
            )

        logger.info(
            "submarine_job_enqueued",
            job_id=job.id,
            location_id=job.location_id,
            website_url=job.website_url,
            missing_fields=job.missing_fields,
        )
        return job.id
