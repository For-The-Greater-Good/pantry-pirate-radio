"""Core replay functionality for processing recorder JSON outputs."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.llm.providers.types import LLMResponse
from app.llm.queue.job import LLMJob
from app.llm.queue.types import JobResult, JobStatus
from app.reconciler.job_processor import process_job_result

logger = logging.getLogger(__name__)


def read_job_file(file_path: str) -> dict[str, Any] | None:
    """Read a job JSON file and return its contents.

    Args:
        file_path: Path to the JSON file

    Returns:
        Parsed JSON data or None if error
    """
    try:
        with open(file_path) as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"File not found: {file_path}")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in file {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return None


def create_job_result(data: dict[str, Any]) -> JobResult | None:
    """Create a JobResult object from JSON data.

    Args:
        data: JSON data from recorder output

    Returns:
        JobResult object or None if data is invalid
    """
    try:
        # Validate required fields
        if not data.get("job_id") or not data.get("job"):
            logger.warning("Missing required fields: job_id or job")
            return None

        # Extract job data
        job_data = data["job"]

        # Create LLMJob instance
        llm_job = LLMJob(
            id=job_data.get("id", data["job_id"]),
            prompt=job_data.get("prompt", ""),
            format=job_data.get("format", {}),
            provider_config=job_data.get("provider_config", {}),
            metadata=job_data.get("metadata", {}),
            created_at=(
                datetime.fromisoformat(job_data["created_at"])
                if "created_at" in job_data
                else datetime.now()
            ),
        )

        # Determine status based on result and error
        if data.get("error"):
            status = JobStatus.FAILED
        elif data.get("result") is not None:
            status = JobStatus.COMPLETED
        else:
            # Job was recorded but has no result or error - skip it
            logger.info(f"Skipping incomplete job {data['job_id']}")
            return None

        # Convert result to LLMResponse if needed
        result = data.get("result")
        if result is not None and status == JobStatus.COMPLETED:
            # Check if result is already an LLMResponse-like dict
            if isinstance(result, dict) and "model" in result and "usage" in result:
                # Already in LLMResponse format
                llm_response = LLMResponse(**result)
            else:
                # Create LLMResponse from raw result
                llm_response = LLMResponse(
                    text=str(result) if not isinstance(result, str) else result,
                    model=job_data.get("provider_config", {}).get("model", "unknown"),
                    usage={
                        "total_tokens": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                    },
                    raw=result if isinstance(result, dict) else {"response": result},
                )
                result = llm_response

        # Create JobResult
        job_result = JobResult(
            job_id=data["job_id"],
            job=llm_job,
            status=status,
            result=result,
            error=data.get("error"),
            completed_at=datetime.now(),
            processing_time=0.0,
            retry_count=0,
        )

        return job_result

    except Exception as e:
        logger.error(f"Error creating JobResult: {e}")
        return None


def should_process_job(data: dict[str, Any]) -> bool:
    """Determine if a job should be processed.

    Only process completed jobs with valid results.
    Skip failed or incomplete jobs.

    Args:
        data: Job data from JSON file

    Returns:
        True if job should be processed
    """
    # Must have job_id and job data
    if not data.get("job_id") or not data.get("job"):
        return False

    # Only process if job has a result (skip errors and incomplete)
    return data.get("result") is not None


def replay_file(file_path: str, dry_run: bool = False) -> bool:
    """Replay a single JSON file.

    Args:
        file_path: Path to the JSON file
        dry_run: If True, only validate without processing

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Processing file: {file_path}")

    # Read the file
    data = read_job_file(file_path)
    if not data:
        logger.error(f"Failed to read file: {file_path}")
        return False

    # Check if we should process this job
    if not should_process_job(data):
        logger.info(f"Skipping job {data.get('job_id', 'unknown')} - no valid result")
        return True  # Not an error, just skipping

    # Create JobResult
    job_result = create_job_result(data)
    if not job_result:
        logger.error(f"Failed to create JobResult from file: {file_path}")
        return False

    # Process or log based on dry_run
    if dry_run:
        logger.info(f"[DRY RUN] Would process job {job_result.job_id}")
    else:
        try:
            # Send to reconciler for processing
            result = process_job_result(job_result)
            logger.info(f"Successfully processed job {job_result.job_id}: {result}")
        except Exception as e:
            logger.error(f"Failed to process job {job_result.job_id}: {e}")
            return False

    return True


def replay_directory(
    directory: str, pattern: str = "*.json", dry_run: bool = False
) -> dict[str, int]:
    """Replay all matching files in a directory.

    Args:
        directory: Directory containing JSON files
        pattern: Glob pattern for files (default: *.json)
        dry_run: If True, only validate without processing

    Returns:
        Dictionary with processing statistics
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        logger.error(f"Directory not found: {directory}")
        return {"total_files": 0, "successful": 0, "failed": 0}

    # Find all matching files
    files = list(dir_path.glob(pattern))
    logger.info(f"Found {len(files)} files matching pattern '{pattern}'")

    stats = {"total_files": len(files), "successful": 0, "failed": 0}

    # Process each file
    for file_path in files:
        try:
            if replay_file(str(file_path), dry_run=dry_run):
                stats["successful"] += 1
            else:
                stats["failed"] += 1
        except Exception as e:
            logger.error(f"Unexpected error processing {file_path}: {e}")
            stats["failed"] += 1

    logger.info(
        f"Processing complete: {stats['successful']} successful, "
        f"{stats['failed']} failed out of {stats['total_files']} total files"
    )

    return stats
