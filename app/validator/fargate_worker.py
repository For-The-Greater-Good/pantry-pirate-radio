"""Fargate worker for the validator service.

Polls SQS for validation jobs and processes them through the validation
pipeline (enrichment, confidence scoring, quality control), then forwards
enriched results to the reconciler queue.

Usage:
    Set environment variables:
        QUEUE_BACKEND=sqs
        VALIDATOR_QUEUE_URL=https://sqs.../validator.fifo
        RECONCILER_QUEUE_URL=https://sqs.../reconciler.fifo

    Then run:
        python -m app.validator.fargate_worker
"""

import os
import sys
from typing import Any

import structlog

from app.pipeline.sqs_worker import PipelineWorker

logger = structlog.get_logger(__name__)


def process_validation_message(data: dict[str, Any]) -> dict[str, Any] | None:
    """Process a validation message from SQS.

    Deserializes the job result, runs it through the validation pipeline,
    and returns the enriched result for forwarding to the reconciler.

    Args:
        data: Message data containing the job result

    Returns:
        Enriched job result dict for the reconciler queue
    """
    from app.llm.queue.models import JobResult

    # Reconstruct JobResult from the SQS message data
    job_result = JobResult.model_validate(data)

    # Process through the validation pipeline
    from app.validator.job_processor import process_validation_job

    process_validation_job(job_result)

    # Return the enriched job_result for forwarding to reconciler
    return job_result.model_dump(mode="json")


def main() -> int:
    """Main entry point for validator Fargate worker."""
    try:
        queue_url = os.environ.get("VALIDATOR_QUEUE_URL")
        if not queue_url:
            logger.error("VALIDATOR_QUEUE_URL environment variable is required")
            sys.exit(1)

        next_queue_url = os.environ.get("RECONCILER_QUEUE_URL")
        if not next_queue_url:
            logger.error("RECONCILER_QUEUE_URL environment variable is required")
            sys.exit(1)

        worker = PipelineWorker(
            queue_url=queue_url,
            process_fn=process_validation_message,
            service_name="validator",
            next_queue_url=next_queue_url,
            visibility_timeout=600,  # Geocoding can be slow
        )
        worker.run()
        return 0

    except KeyboardInterrupt:
        logger.info("validator_worker_interrupted")
        return 0
    except Exception as e:
        logger.error("validator_worker_startup_failed", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
