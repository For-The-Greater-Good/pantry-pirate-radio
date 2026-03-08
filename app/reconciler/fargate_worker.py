"""Fargate worker for the reconciler service.

Polls SQS for reconciliation jobs and processes them through the
reconciler (canonical record creation with version tracking), then
forwards results to the recorder queue.

Usage:
    Set environment variables:
        QUEUE_BACKEND=sqs
        RECONCILER_QUEUE_URL=https://sqs.../reconciler.fifo
        RECORDER_QUEUE_URL=https://sqs.../recorder.fifo

    Then run:
        python -m app.reconciler.fargate_worker
"""

import os
import sys
from typing import Any

import structlog

from app.pipeline.sqs_worker import PipelineWorker

logger = structlog.get_logger(__name__)


def process_reconciler_message(data: dict[str, Any]) -> dict[str, Any] | None:
    """Process a reconciler message from SQS.

    Deserializes the job result and runs it through the reconciler
    to create/update canonical records in the database.

    Args:
        data: Message data containing the job result

    Returns:
        Dict with job data for the recorder queue, or None on failure
    """
    from app.llm.queue.models import JobResult
    from app.reconciler.job_processor import process_job_result

    # Reconstruct JobResult from the SQS message data
    job_result = JobResult.model_validate(data)

    # Process through the reconciler
    result = process_job_result(job_result)

    # Forward to recorder with the standard recording format
    job_dict = job_result.job.model_dump(mode="json") if job_result.job else {}
    if not job_dict:
        logger.warning(
            "forwarding_empty_job_dict_to_recorder",
            job_id=job_result.job_id,
            has_job=job_result.job is not None,
        )
    return {
        "job_id": job_result.job_id,
        "job": job_dict,
        "result": result,
        "error": None,
    }


def main() -> int:
    """Main entry point for reconciler Fargate worker."""
    try:
        queue_url = os.environ.get("RECONCILER_QUEUE_URL")
        if not queue_url:
            logger.error("RECONCILER_QUEUE_URL environment variable is required")
            print("Error: RECONCILER_QUEUE_URL is required", file=sys.stderr)
            return 1

        next_queue_url = os.environ.get("RECORDER_QUEUE_URL")

        worker = PipelineWorker(
            queue_url=queue_url,
            process_fn=process_reconciler_message,
            service_name="reconciler",
            next_queue_url=next_queue_url,
            visibility_timeout=300,
        )
        worker.run()
        return 0

    except KeyboardInterrupt:
        logger.info("reconciler_worker_interrupted")
        return 0
    except Exception as e:
        logger.error("reconciler_worker_startup_failed", error=str(e))
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
