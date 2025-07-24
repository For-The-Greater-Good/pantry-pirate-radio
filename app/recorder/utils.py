"""Utilities for recording job results."""

import json
import os
from datetime import datetime
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
        output_dir = os.getenv("OUTPUT_DIR", "outputs")
        if not output_dir:
            raise ValueError("OUTPUT_DIR environment variable not set")

        # Extract metadata
        job = data.get("job", {})
        metadata = job.get("metadata", {})
        scraper_id = metadata.get("scraper_id", "unknown")

        # Parse created_at timestamp
        created_at_str = job.get("created_at", "")
        if created_at_str:
            # Handle different timestamp formats
            try:
                # Try parsing with timezone
                created_at = datetime.fromisoformat(
                    created_at_str.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                # Fallback to current time if parsing fails
                created_at = datetime.utcnow()
        else:
            created_at = datetime.utcnow()

        # Create directory structure: outputs/daily/YYYY-MM-DD/scrapers/{scraper_id}/
        date_str = created_at.strftime("%Y-%m-%d")

        # Determine if this is a scraper job or processed result
        if scraper_id != "unknown" and scraper_id:
            # This is a scraper job result
            output_path = (
                Path(output_dir) / "daily" / date_str / "scrapers" / scraper_id
            )
        else:
            # This is a processed result (from LLM or other processing)
            output_path = Path(output_dir) / "daily" / date_str / "processed"

        # Create directory if it doesn't exist
        output_path.mkdir(parents=True, exist_ok=True)

        # Save result to file
        output_file = output_path / f"{data['job_id']}.json"
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

        # Create/update latest symlink to point to the date directory
        latest_link = Path(output_dir) / "latest"
        date_dir = Path(output_dir) / "daily" / date_str

        # Remove existing symlink if it exists
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()

        # Create relative symlink to the date directory
        relative_path = os.path.relpath(date_dir, output_dir)
        latest_link.symlink_to(relative_path)

        # Create daily summary file
        summary_file = Path(output_dir) / "daily" / date_str / "summary.json"
        update_daily_summary(summary_file, data["job_id"], scraper_id, created_at)

        logger.info(
            "Job result recorded successfully",
            job_id=data["job_id"],
            scraper_id=scraper_id,
            date=date_str,
            output_file=str(output_file),
        )

        # Update metrics
        RECORDER_JOBS.labels(scraper_id=scraper_id, status="success").inc()

        return {"status": "completed", "error": None, "output_file": str(output_file)}

    except Exception as e:
        error_msg = str(e)
        logger.error("Failed to record job result", error=error_msg, job_data=data)

        # Update metrics
        RECORDER_JOBS.labels(scraper_id="unknown", status="failure").inc()

        return {"status": "failed", "error": error_msg}


def update_daily_summary(
    summary_file: Path, job_id: str, scraper_id: str, timestamp: datetime
) -> None:
    """Update the daily summary file with job information.

    Args:
        summary_file: Path to the summary file
        job_id: ID of the job
        scraper_id: ID of the scraper
        timestamp: Timestamp of the job
    """
    try:
        # Load existing summary or create new one
        if summary_file.exists():
            with open(summary_file) as f:
                summary = json.load(f)
        else:
            summary = {
                "date": timestamp.strftime("%Y-%m-%d"),
                "total_jobs": 0,
                "scrapers": {},
                "jobs": [],
            }

        # Update summary
        summary["total_jobs"] += 1

        # Update scraper counts
        if scraper_id not in summary["scrapers"]:
            summary["scrapers"][scraper_id] = {
                "count": 0,
                "first_job": timestamp.isoformat(),
                "last_job": timestamp.isoformat(),
            }

        summary["scrapers"][scraper_id]["count"] += 1
        summary["scrapers"][scraper_id]["last_job"] = timestamp.isoformat()

        # Add job to list
        summary["jobs"].append(
            {
                "job_id": job_id,
                "scraper_id": scraper_id,
                "timestamp": timestamp.isoformat(),
            }
        )

        # Save updated summary
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)

    except Exception as e:
        logger.warning(
            "Failed to update daily summary",
            error=str(e),
            summary_file=str(summary_file),
        )
