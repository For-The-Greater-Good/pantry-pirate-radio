"""Routing logic for validator service."""

from typing import Dict, Any

from app.llm.queue.models import JobResult


def get_routing_config() -> Dict[str, Any]:
    """Get routing configuration.

    Returns:
        Routing configuration
    """
    from app.core.config import settings

    if getattr(settings, "VALIDATOR_ENABLED", True):
        return {
            "pipeline": ["llm", "validator", "reconciler"],
        }
    else:
        return {
            "pipeline": ["llm", "reconciler"],
        }


def should_validate_job(job_result: JobResult) -> bool:
    """Check if job should be validated.

    Args:
        job_result: Job result to check

    Returns:
        Whether job should be validated
    """
    from app.core.config import settings

    # Check if validator is enabled
    if not getattr(settings, "VALIDATOR_ENABLED", True):
        return False

    # Check if we only validate HSDS jobs
    if getattr(settings, "VALIDATOR_ONLY_HSDS", True):
        # Check if job has HSDS format
        if job_result.job.format.get("type") == "hsds":
            return True
        # Non-HSDS jobs skip validation
        return False

    # Validate all jobs if not limited to HSDS
    return True
