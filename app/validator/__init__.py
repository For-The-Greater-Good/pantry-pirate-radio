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
# Import them directly from app.validator.job_processor and
# app.validator.queues where needed.

__version__ = "1.0.0"

__all__ = [
    # Core classes
    "ValidationService",
    "ValidatorConfig",
    # Configuration
    "is_validator_enabled",
    "get_validator_config",
    "should_log_data_flow",
    "get_validation_thresholds",
    "get_feature_flags",
]
