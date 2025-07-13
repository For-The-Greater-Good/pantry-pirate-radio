"""Utilities for recording job results."""

import json
import os
from pathlib import Path
from typing import Any

import structlog
from prometheus_client import Counter

logger = structlog.get_logger()

# Prometheus metrics
RECORDER_JOBS = Counter(
    "recorder_jobs_total", "Total number of jobs recorded", ["scraper_id", "status"]
)


def record_result(data: dict[str, Any]) -> dict[str, Any]:
    """Record the result of a job execution.

    Args:
        data: Dictionary containing job result data including:
            - job_id: Unique identifier for the job
            - job: Job details and parameters
            - result: Result of the job execution
            - error: Error information if job failed

    Returns:
        Dict containing status and any error information
    """
    try:
        # Validate required fields
        if not data.get("job_id"):
            raise ValueError("Missing required field: job_id")

        # Get output directory from environment
        output_dir = os.getenv("OUTPUT_DIR")
        if not output_dir:
            raise ValueError("OUTPUT_DIR environment variable not set")

        # Create output directory if it doesn't exist
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Save result to file
        output_file = output_path / f"{data['job_id']}.json"
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(
            "Job result recorded successfully",
            job_id=data["job_id"],
            output_file=str(output_file),
        )

        # Update metrics
        scraper_id = (
            data.get("job", {}).get("metadata", {}).get("scraper_id", "unknown")
        )
        RECORDER_JOBS.labels(scraper_id=scraper_id, status="success").inc()

        return {"status": "completed", "error": None}

    except Exception as e:
        error_msg = str(e)
        logger.error("Failed to record job result", error=error_msg, job_data=data)

        # Update metrics
        RECORDER_JOBS.labels(scraper_id="unknown", status="failure").inc()

        return {"status": "failed", "error": error_msg}
