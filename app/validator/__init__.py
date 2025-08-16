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
from app.validator.job_processor import (
    ValidationProcessor,
    process_validation_job,
    enqueue_to_reconciler,
)
from app.validator.queues import (
    get_validator_queue,
    setup_validator_queues,
    get_queue_chain,
)

# Import the actual queue object
from app.validator.queues import validator_queue

__version__ = "1.0.0"

__all__ = [
    # Core classes
    "ValidationService",
    "ValidationProcessor",
    "ValidatorConfig",
    # Main functions
    "process_validation_job",
    "enqueue_to_reconciler",
    # Queue management
    "validator_queue",
    "get_validator_queue",
    "setup_validator_queues",
    "get_queue_chain",
    # Configuration
    "is_validator_enabled",
    "get_validator_config",
    "should_log_data_flow",
    "get_validation_thresholds",
    "get_feature_flags",
]
