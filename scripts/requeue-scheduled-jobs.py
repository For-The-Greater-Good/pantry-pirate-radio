#!/usr/bin/env python3
"""Re-queue all scheduled jobs for immediate processing.

This script moves all jobs from the scheduled job registry back to their
respective queues for immediate processing. Useful when dealing with
authentication issues or when you want to retry all delayed jobs immediately.
"""

import argparse
import logging
import os
import sys
from datetime import datetime

import redis
from rq import Queue
from rq.registry import ScheduledJobRegistry

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Get Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Queue names to process
QUEUE_NAMES = ["llm", "reconciler", "recorder"]


def requeue_scheduled_jobs(queue_name: str, connection: redis.Redis) -> int:
    """Re-queue all scheduled jobs for a specific queue.

    Args:
        queue_name: Name of the queue to process
        connection: Redis connection

    Returns:
        Number of jobs re-queued
    """
    queue = Queue(queue_name, connection=connection)
    registry = ScheduledJobRegistry(queue=queue)

    requeued_count = 0
    job_ids = list(registry.get_job_ids())

    logger.info(f"Found {len(job_ids)} scheduled jobs in '{queue_name}' queue")

    for job_id in job_ids:
        try:
            job = queue.fetch_job(job_id)
            if job:
                # Get the scheduled time for logging
                scheduled_time = registry.get_scheduled_time(job_id)
                if scheduled_time:
                    # Handle both timestamp and datetime objects
                    if isinstance(scheduled_time, datetime):
                        scheduled_dt = scheduled_time
                    else:
                        scheduled_dt = datetime.fromtimestamp(scheduled_time)
                    logger.info(
                        f"Re-queueing job {job_id} (was scheduled for {scheduled_dt})"
                    )

                # Remove from scheduled registry and enqueue immediately
                registry.remove(job_id)
                queue.enqueue_job(job)
                requeued_count += 1

                logger.info(f"Successfully re-queued job {job_id}")
            else:
                logger.warning(f"Could not fetch job {job_id}")
        except Exception as e:
            logger.error(f"Failed to re-queue job {job_id}: {e}")

    return requeued_count


def list_scheduled_jobs(queue_name: str, connection: redis.Redis) -> None:
    """List all scheduled jobs for a specific queue.

    Args:
        queue_name: Name of the queue to check
        connection: Redis connection
    """
    queue = Queue(queue_name, connection=connection)
    registry = ScheduledJobRegistry(queue=queue)

    job_ids = list(registry.get_job_ids())

    if not job_ids:
        logger.info(f"No scheduled jobs in '{queue_name}' queue")
        return

    logger.info(f"\nScheduled jobs in '{queue_name}' queue ({len(job_ids)} total):")
    for job_id in job_ids:
        try:
            job = queue.fetch_job(job_id)
            scheduled_time = registry.get_scheduled_time(job_id)
            if job and scheduled_time:
                # Handle both timestamp and datetime objects
                if isinstance(scheduled_time, datetime):
                    scheduled_dt = scheduled_time
                else:
                    scheduled_dt = datetime.fromtimestamp(scheduled_time)
                time_diff = scheduled_dt - datetime.now()
                hours = int(time_diff.total_seconds() // 3600)
                minutes = int((time_diff.total_seconds() % 3600) // 60)

                logger.info(
                    f"  - {job_id}: scheduled for {scheduled_dt} "
                    f"(in {hours}h {minutes}m)"
                )
                if hasattr(job, "meta") and job.meta:
                    # Show retry counts if available
                    auth_retry = job.meta.get("auth_retry_count", 0)
                    quota_retry = job.meta.get("quota_retry_count", 0)
                    if auth_retry > 0:
                        logger.info(f"    Auth retry count: {auth_retry}")
                    if quota_retry > 0:
                        logger.info(f"    Quota retry count: {quota_retry}")
        except Exception as e:
            logger.warning(f"  - {job_id}: Error fetching details: {e}")


def main():
    """Main function to re-queue all scheduled jobs."""
    parser = argparse.ArgumentParser(
        description="Re-queue scheduled jobs for immediate processing"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List scheduled jobs without re-queuing them",
    )
    parser.add_argument(
        "--queue",
        choices=QUEUE_NAMES,
        help="Process only a specific queue",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually re-queuing",
    )

    args = parser.parse_args()

    try:
        # Connect to Redis
        logger.info(f"Connecting to Redis at {REDIS_URL}")
        redis_client = redis.Redis.from_url(
            REDIS_URL,
            decode_responses=False,
            socket_timeout=5,
            socket_connect_timeout=5,
        )

        # Verify connection
        redis_client.ping()
        logger.info("Successfully connected to Redis")

        # Determine which queues to process
        queues_to_process = [args.queue] if args.queue else QUEUE_NAMES

        if args.list:
            # List mode - just show scheduled jobs
            for queue_name in queues_to_process:
                list_scheduled_jobs(queue_name, redis_client)
        else:
            # Re-queue mode
            total_requeued = 0

            for queue_name in queues_to_process:
                logger.info(f"\nProcessing '{queue_name}' queue...")

                if args.dry_run:
                    # Dry run - just count jobs
                    queue = Queue(queue_name, connection=redis_client)
                    registry = ScheduledJobRegistry(queue=queue)
                    job_count = len(list(registry.get_job_ids()))
                    logger.info(
                        f"Would re-queue {job_count} jobs from '{queue_name}' queue"
                    )
                    total_requeued += job_count
                else:
                    # Actually re-queue jobs
                    requeued = requeue_scheduled_jobs(queue_name, redis_client)
                    total_requeued += requeued
                    logger.info(f"Re-queued {requeued} jobs from '{queue_name}' queue")

            logger.info(
                f"\nTotal jobs {'would be' if args.dry_run else ''} re-queued: {total_requeued}"
            )

            if not args.dry_run and total_requeued > 0:
                logger.info(
                    "Jobs have been re-queued for immediate processing. "
                    "Check worker logs for processing status."
                )
            elif total_requeued == 0:
                logger.info("No scheduled jobs found to re-queue.")

    except Exception as e:
        logger.error(f"Failed to connect to Redis or process jobs: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
