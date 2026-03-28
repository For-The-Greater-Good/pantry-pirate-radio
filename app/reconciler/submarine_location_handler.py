"""Submarine-specific location resolution and update logic.

Extracted from job_processor.py per Constitution Principle IX (file size limits).
Submarine results use direct ID-based location matching instead of coordinate
matching, and only update fields that were actually extracted.
"""

import uuid
from typing import Any, Callable

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = structlog.get_logger(__name__)


class SubmarineLocationHandler:
    """Handles submarine-specific location resolution, updates, and schedule persistence."""

    def __init__(self, db: Session):
        self.db = db

    def is_submarine_job(self, job_metadata: dict[str, Any]) -> bool:
        """Check if this job result came from the submarine pipeline."""
        return job_metadata.get("scraper_id") == "submarine" and bool(
            job_metadata.get("location_id")
        )

    def resolve_target_location(self, job_metadata: dict[str, Any]) -> str | None:
        """Resolve location by direct ID for submarine results.

        Submarine results carry the target location_id in metadata. This method
        verifies the location exists in the database.

        Returns:
            Verified location_id string, or None if not a submarine job
            or the target location doesn't exist.
        """
        if not self.is_submarine_job(job_metadata):
            return None

        target_id = str(job_metadata["location_id"])
        verify_result = self.db.execute(
            text("SELECT id FROM location WHERE id = :id"),
            {"id": target_id},
        )
        if verify_result.first():
            return target_id

        logger.warning(
            "submarine_target_location_not_found",
            extra={"location_id": target_id},
        )
        return None

    def update_location(
        self,
        location_id: uuid.UUID,
        location: dict[str, Any],
        org_id: uuid.UUID | None,
    ) -> str | None:
        """Update location with only the fields present in the dict.

        Builds a dynamic SET clause so omitted fields (not extracted by
        submarine) are not overwritten. Always updates name, latitude,
        longitude, and organization_id (structural fields).

        Returns:
            The description value used in the update, or None if description
            was not updated.
        """
        set_clauses = [
            "name=:name",
            "latitude=:latitude",
            "longitude=:longitude",
            "organization_id=:organization_id",
        ]
        params: dict[str, Any] = {
            "id": str(location_id),
            "name": location["name"],
            "latitude": float(location["latitude"]),
            "longitude": float(location["longitude"]),
            "organization_id": str(org_id) if org_id else None,
        }

        update_description = None
        if "description" in location:
            update_description = location.get("description")
            if not update_description:
                update_description = f"Food service location: {location['name']}"
                logger.warning(
                    "submarine_missing_description",
                    extra={
                        "location_id": str(location_id),
                        "location_name": location["name"],
                    },
                )
            set_clauses.append("description=:description")
            params["description"] = update_description

        set_clause = ", ".join(set_clauses)
        # S608: set_clauses are hardcoded column names, not user input
        query = text(f"UPDATE location SET {set_clause} WHERE id=:id")  # noqa: S608

        self.db.execute(query, params)
        self.db.commit()

        return update_description

    def persist_schedules(
        self,
        location_id: uuid.UUID,
        location: dict[str, Any],
        metadata: dict[str, Any],
        service_creator: Any,
        transform_fn: Callable[[dict], dict | None],
    ) -> int:
        """Persist submarine schedules directly to location.

        Submarine results have no services, so schedules can't flow through the
        normal service_at_location path. This writes them directly to the
        location using the existing update_or_create_schedule infrastructure.

        Returns:
            Count of schedules created or updated.
        """
        schedules = location.get("schedules")
        if not schedules:
            return 0

        count = 0
        for sched in schedules:
            transformed = transform_fn(sched)
            if not transformed:
                continue

            service_creator.update_or_create_schedule(
                freq=transformed["freq"],
                wkst=transformed.get("wkst", "MO"),
                opens_at=transformed["opens_at"],
                closes_at=transformed["closes_at"],
                metadata=metadata,
                location_id=location_id,
                service_at_location_id=None,
                byday=transformed.get("byday"),
                description=transformed.get("description"),
            )
            count += 1

        if count:
            logger.info(
                "submarine_schedules_persisted",
                extra={
                    "location_id": str(location_id),
                    "schedule_count": count,
                },
            )

        return count
