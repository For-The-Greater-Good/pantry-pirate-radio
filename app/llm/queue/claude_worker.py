"""Custom RQ Worker with Claude authentication checks."""

import asyncio
import time
from typing import Any, Optional

from redis import Redis
from rq import Worker
from rq.job import Job

from app.core.logging import get_logger
from app.llm.queue.auth_state import AuthStateManager
from app.llm.providers.claude import (
    ClaudeProvider,
    ClaudeQuotaExceededException,
    ClaudeNotAuthenticatedException,
)

logger = get_logger().bind(module="claude_worker")


class ClaudeWorker(Worker):
    """RQ Worker with Claude authentication state management."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize Claude worker with auth state manager."""
        super().__init__(*args, **kwargs)

        # Initialize auth state manager
        self.auth_manager = AuthStateManager(self.connection)

        # Track last auth check time
        self.last_auth_check: float = 0
        self.auth_check_interval: int = 30  # seconds

        # Provider will be set when first job is executed
        self.claude_provider: Optional[ClaudeProvider] = None

        logger.info("Claude worker initialized with auth state management")

    def execute_job(self, job: Job, queue: Any) -> None:
        """Execute job with pre-flight auth check.

        Args:
            job: The RQ job to execute
            queue: The queue the job came from
        """
        # Check auth state before executing
        is_healthy, error_details = self.auth_manager.is_healthy()

        if not is_healthy:
            # Log the issue
            error_type = (
                error_details.get("status", "unknown") if error_details else "unknown"
            )
            retry_in = error_details.get("retry_in_seconds", 0) if error_details else 0

            logger.warning(
                f"Worker skipping job {job.id} due to {error_type}. "
                f"Will retry in {retry_in} seconds"
            )

            # Requeue the job for later using RQ's retry mechanism
            # Calculate delay based on retry time
            retry_delay = max(1, min(retry_in, 300))  # 1 sec to 5 min delay

            from datetime import datetime, timedelta
            from rq.registry import ScheduledJobRegistry
            from rq.job import JobStatus

            # Add job to scheduled registry instead of immediate queue
            registry = ScheduledJobRegistry(queue=queue, connection=self.connection)
            scheduled_time = datetime.now() + timedelta(seconds=retry_delay)
            registry.schedule(job, scheduled_datetime=scheduled_time)

            logger.info(f"Scheduled job {job.id} for retry in {retry_delay}s")

            # Mark job as deferred (scheduled for retry)
            job.set_status(JobStatus.DEFERRED)
            job.save_meta()  # Save the updated metadata

            # Sleep briefly to avoid burning CPU
            time.sleep(1)
            return

        # Perform periodic auth check if needed
        if self.auth_manager.should_check_auth(self.auth_check_interval):
            self._perform_auth_check()

        try:
            # Execute the job normally
            super().execute_job(job, queue)
        except (ClaudeNotAuthenticatedException, ClaudeQuotaExceededException) as e:
            # Update auth state based on exception
            if isinstance(e, ClaudeNotAuthenticatedException):
                self.auth_manager.set_auth_failed(str(e), retry_after=e.retry_after)
            else:  # ClaudeQuotaExceededException
                self.auth_manager.set_quota_exceeded(str(e), retry_after=e.retry_after)

            # Re-raise to let RQ handle the failure
            raise

    def _perform_auth_check(self) -> None:
        """Perform background auth check."""
        try:
            # Initialize provider if not already done
            if self.claude_provider is None:
                from app.llm.providers.claude import ClaudeConfig, ClaudeProvider

                config = ClaudeConfig()
                self.claude_provider = ClaudeProvider(config)

            # Run auth check
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                is_authenticated = loop.run_until_complete(
                    self.claude_provider._check_authentication()
                )

                if is_authenticated:
                    self.auth_manager.set_healthy()
                    logger.info("Background auth check passed")
                else:
                    self.auth_manager.set_auth_failed(
                        "Background auth check failed", retry_after=300
                    )

            finally:
                loop.close()

        except Exception as e:
            logger.error(f"Error during background auth check: {e}")
            # Don't update state on check errors

    def work(self, *args, **kwargs):
        """Override work method to add startup auth check."""
        logger.info("Claude worker starting up...")

        # Perform initial auth check
        self._perform_auth_check()

        # Get current auth status
        status = self.auth_manager.get_status()
        if status["healthy"]:
            logger.info("✅ Claude worker started with healthy auth status")
        else:
            logger.warning(
                f"⚠️  Claude worker started with {status.get('error_type', 'unknown')} status. "
                f"Jobs will be paused."
            )

        # Start normal work loop
        super().work(*args, **kwargs)
