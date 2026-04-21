"""Validator service for processing LLM output before reconciliation.

This module provides validation services for the data processing pipeline.
It implements a passthrough validation strategy currently, with hooks for
future validation logic implementation.

Main Components:
- ValidationService: Base service class for validation operations
- ValidationProcessor: Processes validation jobs from the queue
- ValidatorWorker: RQ worker for processing validation jobs
- ValidatorConfig: Configuration management for the validator

Usage:
    from app.validator import is_validator_enabled, process_validation_job

    if is_validator_enabled():
        result = process_validation_job(job_result)
"""

from app.validator.base import ValidationService
from app.validator.config import (
    ValidatorConfig,
    get_validator_config,
    is_validator_enabled,
    should_log_data_flow,
    get_validation_thresholds,
    get_feature_flags,
)

# NOTE: job_processor and queues are NOT imported here because queues.py
# imports from app.llm.queue.queues which creates a Redis connection at
# module load time, crashing in SQS-based environments (AWS Fargate).
# Use the lazy factory functions below instead.


def get_process_validation_job():
    """Lazy import factory for process_validation_job.

    M6 FIX: Provides a stable API so callers don't need to know about
    the Redis import constraint. Only imports job_processor when called.

    Returns:
        The process_validation_job function
    """
    from app.validator.job_processor import process_validation_job

    return process_validation_job


def get_enqueue_to_reconciler():
    """Lazy import factory for enqueue_to_reconciler.

    Returns:
        The enqueue_to_reconciler function
    """
    from app.validator.job_processor import enqueue_to_reconciler

    return enqueue_to_reconciler


__version__ = "1.0.0"

__all__ = [
    # Core classes
    "ValidationService",
    "ValidatorConfig",
    "get_enqueue_to_reconciler",
    "get_feature_flags",
    # Lazy import factories (M6)
    "get_process_validation_job",
    "get_validation_thresholds",
    "get_validator_config",
    # Configuration
    "is_validator_enabled",
    "should_log_data_flow",
]
