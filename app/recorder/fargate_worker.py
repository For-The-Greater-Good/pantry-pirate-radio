"""Fargate worker for the recorder service.

Polls SQS for recording jobs and archives job results to the
filesystem/S3. This is the terminal stage of the pipeline — no
forwarding to downstream queues.

Usage:
    Set environment variables:
        QUEUE_BACKEND=sqs
        RECORDER_QUEUE_URL=https://sqs.../recorder.fifo

    Then run:
        python -m app.recorder.fargate_worker
"""

import os
import sys
from typing import Any

import structlog

from app.pipeline.sqs_worker import PipelineWorker

logger = structlog.get_logger(__name__)


def process_recorder_message(data: dict[str, Any]) -> dict[str, Any] | None:
    """Process a recorder message from SQS.

    Archives the job result data to the filesystem or S3.

    Args:
        data: Message data containing job result to record

    Returns:
        None — recorder is the terminal pipeline stage
    """
    from app.recorder.utils import record_result

    record_result(data)

    # Terminal stage — no forwarding
    return None


def main() -> int:
    """Main entry point for recorder Fargate worker."""
    try:
        queue_url = os.environ.get("RECORDER_QUEUE_URL")
        if not queue_url:
            logger.error("RECORDER_QUEUE_URL environment variable is required")
            sys.exit(1)

        worker = PipelineWorker(
            queue_url=queue_url,
            process_fn=process_recorder_message,
            service_name="recorder",
            next_queue_url=None,  # Terminal stage
            visibility_timeout=120,
        )
        worker.run()
        return 0

    except KeyboardInterrupt:
        logger.info("recorder_worker_interrupted")
        return 0
    except Exception as e:
        logger.error("recorder_worker_startup_failed", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
