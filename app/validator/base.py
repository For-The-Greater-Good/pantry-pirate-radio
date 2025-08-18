"""Base validation service class."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TypeVar, Generic, Literal

from sqlalchemy.orm import Session

T = TypeVar("T")
R = TypeVar("R")


class BaseValidator(ABC, Generic[T, R]):
    """Abstract base class for validators."""

    @abstractmethod
    def validate(self, data: T) -> R:
        """Validate data.

        Args:
            data: Data to validate

        Returns:
            Validation result
        """
        pass


class ValidationService:
    """Base validation service for processing job data.

    This service provides a foundation for validation operations with:
    - Database session management
    - Configuration handling
    - Logging capabilities
    - Context manager support
    """

    def __init__(
        self,
        db: Session,
        log_data_flow: bool = False,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize validation service.

        Args:
            db: Database session for persistence operations
            log_data_flow: Enable detailed data flow logging for debugging
            config: Optional configuration dictionary with keys:
                - enabled: Whether validation is enabled (default: True)
                - queue_name: Name of validation queue (default: "validator")
                - redis_ttl: TTL for Redis entries in seconds (default: 3600)
                - log_data_flow: Override log_data_flow parameter
        """
        self.db = db
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Apply configuration
        self._apply_config(config, log_data_flow)

        # Log initialization
        if self.enabled:
            self.logger.debug(
                f"Validation service initialized (queue={self.queue_name}, "
                f"ttl={self.redis_ttl}s, logging={self.log_data_flow})"
            )
        else:
            self.logger.debug("Validation service initialized (disabled)")

    def _apply_config(
        self, config: Optional[Dict[str, Any]], default_log_data_flow: bool
    ) -> None:
        """Apply configuration settings.

        Args:
            config: Configuration dictionary
            default_log_data_flow: Default value for log_data_flow
        """
        if config:
            self.enabled = config.get("enabled", True)
            self.queue_name = config.get("queue_name", "validator")
            self.redis_ttl = config.get("redis_ttl", 3600)
            self.log_data_flow = config.get("log_data_flow", default_log_data_flow)
        else:
            self.enabled = True
            self.queue_name = "validator"
            self.redis_ttl = 3600
            self.log_data_flow = default_log_data_flow

    def __enter__(self) -> "ValidationService":
        """Enter context manager.

        Returns:
            Self for use in with statements
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        _exc_tb: object | None,
    ) -> Literal[False]:
        """Exit context manager with proper cleanup.

        Args:
            exc_type: Exception type if raised
            exc_val: Exception value if raised
            exc_tb: Exception traceback if raised

        Returns:
            False to propagate exceptions
        """
        if exc_val is not None:
            self.logger.error(
                f"Error in validation context: {exc_type.__name__ if exc_type else 'Unknown'}: {exc_val}"
            )
            # Ensure database is rolled back on error
            if self.db and hasattr(self.db, "rollback"):
                try:
                    self.db.rollback()
                except Exception as e:
                    self.logger.error(f"Failed to rollback database: {e}")
        return False  # Don't suppress exceptions

    def validate(self, data: Any) -> Any:
        """Validate data and return it unchanged (passthrough).

        This is the base implementation that simply passes data through.
        Subclasses should override this method to add actual validation logic.

        Args:
            data: Data to validate

        Returns:
            The same data unchanged (for now)
        """
        if self.log_data_flow:
            self.logger.info("Validation service received data for validation")
            self.logger.debug(f"Data type: {type(data).__name__}")
            self.logger.info(
                "Validation service passing through data unchanged (no validation rules applied)"
            )

        return data

    def process_job_result(self, job_result: Any) -> Any:
        """Process a job result through validation.

        Args:
            job_result: Job result to process

        Returns:
            Processed job result
        """
        if self.log_data_flow:
            self.logger.info(
                f"Processing job result: {getattr(job_result, 'job_id', 'unknown')}"
            )

        # Delegate to validate method for actual processing
        return self.validate(job_result)
