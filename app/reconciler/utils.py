"""Utilities for reconciling HSDS records."""

import uuid

from sqlalchemy.orm import Session

from app.llm.queue.models import JobResult
from app.reconciler.base import BaseReconciler
from app.reconciler.job_processor import JobProcessor
from app.reconciler.location_creator import LocationCreator
from app.reconciler.service_creator import ServiceCreator


class ReconcilerUtils(BaseReconciler):
    """Utilities for reconciling HSDS records."""

    def __init__(self, db: Session) -> None:
        """Initialize reconciler utils.

        Args:
            db: Database session
        """
        super().__init__(db)
        self.location_creator = LocationCreator(db)
        self.service_creator = ServiceCreator(db)
        self.job_processor = JobProcessor(db)

    def find_matching_location(
        self, latitude: float, longitude: float, tolerance: float = None
    ) -> uuid.UUID | None:
        """Find matching location by coordinates."""
        if tolerance is None:
            tolerance = self.location_tolerance
        result = self.location_creator.find_matching_location(
            latitude, longitude, tolerance
        )
        return uuid.UUID(result) if result else None

    def create_location(
        self,
        name: str,
        description: str,
        latitude: float,
        longitude: float,
        metadata: dict[str, str],
    ) -> uuid.UUID:
        """Create new location."""
        result = self.location_creator.create_location(
            name, description, latitude, longitude, metadata
        )
        return uuid.UUID(result)

    def create_service(
        self,
        name: str,
        description: str,
        organization_id: uuid.UUID | None,
        metadata: dict[str, str],
    ) -> uuid.UUID:
        """Create new service."""
        return self.service_creator.create_service(
            name, description, organization_id, metadata
        )

    def create_service_at_location(
        self,
        service_id: uuid.UUID,
        location_id: uuid.UUID,
        description: str | None,
        metadata: dict[str, str],
    ) -> uuid.UUID:
        """Create new service at location."""
        return self.service_creator.create_service_at_location(
            service_id, location_id, description, metadata
        )

    def process_job_result(self, job_result: JobResult) -> None:
        """Process completed job result.

        Args:
            job_result: The job result to process
        """
        try:
            # Ensure job processor is initialized
            if not hasattr(self, "job_processor"):
                self.job_processor = JobProcessor(self.db)

            # Process the job result
            self.job_processor.process_job_result(job_result)
        except Exception:
            # Log error and re-raise
            raise

    def process_completed_jobs(self) -> list[str]:
        """Process all completed jobs."""
        result = self.job_processor.process_completed_jobs()
        # Return the result if it's not None (for mocking), otherwise return empty list
        return result if result is not None else []
