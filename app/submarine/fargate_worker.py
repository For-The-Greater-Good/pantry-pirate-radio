"""Fargate worker for the submarine service.

Polls SQS for submarine jobs and processes them through the crawl + extract
pipeline, then forwards enriched results to the reconciler queue.

Usage:
    Set environment variables:
        QUEUE_BACKEND=sqs
        SUBMARINE_QUEUE_URL=https://sqs.../submarine.fifo
        RECONCILER_QUEUE_URL=https://sqs.../reconciler.fifo

    Then run:
        python -m app.submarine.fargate_worker
"""

import os
import sys
from typing import Any

import structlog

from app.pipeline.sqs_worker import PipelineWorker

logger = structlog.get_logger(__name__)


def process_submarine_message(data: dict[str, Any]) -> dict[str, Any] | None:
    """Process a submarine message from SQS.

    Args:
        data: Message data containing the submarine job.

    Returns:
        Enriched JobResult dict for the reconciler queue, or None.
    """
    from app.submarine.worker import process_submarine_job

    return process_submarine_job(data)


def main() -> int:
    """Main entry point for submarine Fargate worker."""
    try:
        queue_url = os.environ.get("SUBMARINE_QUEUE_URL")
        if not queue_url:
            logger.error("SUBMARINE_QUEUE_URL environment variable is required")
            sys.exit(1)

        next_queue_url = os.environ.get("RECONCILER_QUEUE_URL")
        if not next_queue_url:
            logger.error("RECONCILER_QUEUE_URL environment variable is required")
            sys.exit(1)

        worker = PipelineWorker(
            queue_url=queue_url,
            process_fn=process_submarine_message,
            service_name="submarine",
            next_queue_url=next_queue_url,
            visibility_timeout=600,  # Crawling + LLM extraction can be slow
        )
        worker.run()
        return 0

    except KeyboardInterrupt:
        logger.info("submarine_worker_interrupted")
        return 0
    except Exception as e:
        logger.error("submarine_worker_startup_failed", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
