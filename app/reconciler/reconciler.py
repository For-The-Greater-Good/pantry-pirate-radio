"""Main reconciler functionality."""

from typing import Any

from sqlalchemy.orm import Session

from app.llm.queue.models import JobResult
from app.reconciler.job_processor import JobProcessor
from app.reconciler.location_creator import LocationCreator
from app.reconciler.organization_creator import OrganizationCreator
from app.reconciler.service_creator import ServiceCreator


class Reconciler:
    """Main reconciler class that coordinates all reconciliation operations."""

    def __init__(self, db: Session) -> None:
        """Initialize reconciler.

        Args:
            db: Database session
        """
        self.db = db
        self.job_processor = JobProcessor(db)
        self.location_creator = LocationCreator(db)
        self.service_creator = ServiceCreator(db)
        self.organization_creator = OrganizationCreator(db)

    def __enter__(self) -> "Reconciler":
        """Enter context."""
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: Any | None,
    ) -> None:
        """Exit context."""
        pass

    def reconcile_data(self, job_result: JobResult) -> None:
        """Process a completed job result.

        Args:
            job_result: Completed job result to process

        Raises:
            ValueError: If job result has no result
            json.JSONDecodeError: If result text is not valid JSON
        """
        self.job_processor.process_job_result(job_result)

    def process_completed_jobs(self) -> list[str]:
        """Process all completed jobs.

        This method is no longer needed since we're using RQ's worker system.
        Jobs are now processed directly by the RQ worker when they arrive.

        Returns:
            List of processed job IDs (empty list for deprecated method)
        """
        result = self.job_processor.process_completed_jobs()
        # Return the result if it's not None (for mocking), otherwise return empty list
        return result if result is not None else []
