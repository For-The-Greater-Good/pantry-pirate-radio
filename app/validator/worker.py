"""Worker for validator service."""

import logging
import signal
import sys
from typing import Optional, List, Any

import redis
from redis.exceptions import ConnectionError as RedisConnectionError
from rq import Worker, Queue
from rq.job import Job, JobStatus
from rq.worker import WorkerStatus

from app.validator.queues import get_validator_queue, get_redis_connection
from app.validator.config import get_worker_config

logger = logging.getLogger(__name__)


class ValidatorWorker:
    """Worker for processing validation jobs.

    This worker processes jobs from the validation queue,
    handling errors gracefully and providing lifecycle management.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        """Initialize worker.

        Args:
            config: Optional worker configuration overrides
        """
        self.config = config or get_worker_config()
        self.queue: Optional[Queue] = None
        self.redis_conn: Optional[redis.Redis] = None
        self.rq_worker: Optional[Worker] = None
        self._shutdown_requested = False

        # Setup signal handlers
        self._setup_signal_handlers()

        logger.info(f"ValidatorWorker initialized with config: {self.config}")

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum: int, frame: Any) -> None:
            """Handle shutdown signals."""
            logger.info(f"Received signal {signum}, initiating graceful shutdown")
            self._shutdown_requested = True
            if self.rq_worker:
                self.rq_worker.request_stop(signum, frame)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    def setup(self) -> None:
        """Set up worker resources.

        Raises:
            RuntimeError: If setup fails
        """
        try:
            # Get queue
            self.queue = get_validator_queue()
            logger.debug(f"Got validator queue: {self.queue.name}")

            # Get Redis connection
            self.redis_conn = get_redis_connection()

            # Test connection
            self.redis_conn.ping()
            logger.debug("Redis connection verified")

            # Create RQ worker with configuration
            self.rq_worker = Worker(
                queues=[self.queue],
                connection=self.redis_conn,
                name=f"validator-worker-{id(self)}",
                log_job_description=self.config.get("log_level") == "DEBUG",
            )

            logger.info(
                f"Validator worker setup complete: "
                f"queue={self.queue.name}, "
                f"timeout={self.config.get('job_timeout')}s"
            )

        except RedisConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise RuntimeError(f"Redis connection failed: {e}") from e
        except Exception as e:
            logger.error(f"Worker setup failed: {e}")
            raise RuntimeError(f"Worker setup failed: {e}") from e

    def work(
        self,
        burst: bool = False,
        with_scheduler: bool = False,
        max_jobs: Optional[int] = None,
    ) -> None:
        """Start working on jobs.

        Args:
            burst: Process all jobs then exit
            with_scheduler: Enable job scheduling
            max_jobs: Maximum number of jobs to process
        """
        if not self.rq_worker:
            self.setup()

        if not self.rq_worker:
            raise RuntimeError("Worker not properly initialized")

        try:
            burst_mode = burst or self.config.get("burst_mode", False)
            max_jobs_to_process = max_jobs or self.config.get("max_jobs_per_worker")

            logger.info(
                f"Starting validator worker: "
                f"burst={burst_mode}, "
                f"with_scheduler={with_scheduler}, "
                f"max_jobs={max_jobs_to_process}"
            )

            if burst_mode:
                self.rq_worker.work(
                    burst=True,
                    with_scheduler=with_scheduler,
                    max_jobs=max_jobs_to_process,
                )
            else:
                self.rq_worker.work(
                    with_scheduler=with_scheduler,
                    max_jobs=max_jobs_to_process,
                )

        except KeyboardInterrupt:
            logger.info("Worker interrupted by user")
        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)
            raise
        finally:
            self.teardown()

    def teardown(self) -> None:
        """Tear down worker resources."""
        logger.info("Starting validator worker teardown")

        # Clean up RQ worker
        if self.rq_worker:
            try:
                if self.rq_worker.get_state() == WorkerStatus.BUSY:
                    logger.info("Waiting for current job to complete...")
                    self.rq_worker.request_stop(signal.SIGTERM, None)
            except Exception as e:
                logger.error(f"Error stopping worker: {e}")

        # Close Redis connection
        if self.redis_conn:
            try:
                self.redis_conn.close()
                logger.debug("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")

        logger.info("Validator worker shutdown complete")

    def get_status(self) -> dict[str, Any]:
        """Get worker status information.

        Returns:
            Status dictionary
        """
        status = {
            "initialized": self.rq_worker is not None,
            "shutdown_requested": self._shutdown_requested,
            "config": self.config,
        }

        if self.rq_worker:
            try:
                status.update(
                    {
                        "state": str(self.rq_worker.get_state()),
                        "current_job": self.rq_worker.get_current_job_id(),
                        "successful_job_count": self.rq_worker.successful_job_count,
                        "failed_job_count": self.rq_worker.failed_job_count,
                        "total_working_time": self.rq_worker.total_working_time,
                    }
                )
            except Exception as e:
                status["error"] = str(e)

        return status

    def process_single_job(self, job_id: str) -> Any:
        """Process a single job by ID.

        Useful for testing or manual job processing.

        Args:
            job_id: Job ID to process

        Returns:
            Job result
        """
        if not self.redis_conn:
            self.setup()

        job = Job.fetch(job_id, connection=self.redis_conn)

        if not job:
            raise ValueError(f"Job {job_id} not found")

        logger.info(f"Processing single job: {job_id}")

        # Execute the job
        result = job.func(*job.args, **job.kwargs)

        # Mark job as finished
        job.set_status(JobStatus.FINISHED)
        job.save()

        return result
