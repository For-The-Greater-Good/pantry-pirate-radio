"""HSDS validation models and utilities.

This module provides validation functionality for HSDS data alignment,
using LLMs to validate mapping quality and detect hallucinations.
"""

import os
from dataclasses import dataclass
from typing import Any, NotRequired, Required, TypedDict, cast


class ValidationResultDict(TypedDict):
    """Result of LLM-based HSDS validation."""

    confidence: Required[float]  # Score from 0.0 to 1.0
    # Whether any hallucinated data was detected
    hallucination_detected: Required[bool]
    # List of required fields that are missing
    missing_required_fields: Required[list[str]]
    feedback: NotRequired[str | None]  # Feedback about validation issues
    mismatched_fields: NotRequired[list[str] | None]  # Mismatched fields
    # Suggested corrections
    suggested_corrections: NotRequired[dict[str, str] | None]


@dataclass
class ValidationConfig:
    """Configuration for HSDS validation."""

    min_confidence: float = 0.82  # Default value
    retry_threshold: float = 0.65  # Default value
    max_retries: int = 5  # Default value
    # Optional different model to use for validation
    validation_model: str | None = None
    # Flag to control whether to load from environment
    load_from_env: bool = True

    def __post_init__(self) -> None:
        """Load from environment and validate configuration values."""
        # Only load from environment if flag is set (allows tests to disable)
        if self.load_from_env:
            # Load from environment, using class defaults as fallback
            self.min_confidence = float(
                os.getenv("HSDS_MIN_CONFIDENCE", str(self.min_confidence))
            )
            self.retry_threshold = float(
                os.getenv("HSDS_RETRY_THRESHOLD", str(self.retry_threshold))
            )
            self.max_retries = int(os.getenv("HSDS_MAX_RETRIES", str(self.max_retries)))

        # Validate values
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0.0 and 1.0")
        if not 0.0 <= self.retry_threshold <= 1.0:
            raise ValueError("retry_threshold must be between 0.0 and 1.0")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")


@dataclass
class ValidationResult:
    """Result of LLM-based HSDS validation."""

    confidence: float
    hallucination_detected: bool
    missing_required_fields: list[str]
    feedback: str | None = None
    mismatched_fields: list[str] | None = None
    suggested_corrections: dict[str, str] | None = None

    def __post_init__(self) -> None:
        """Validate result values."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")

    @classmethod
    def model_validate(cls, data: dict[str, Any]) -> "ValidationResult":
        """Create ValidationResult from dictionary data.

        Args:
            data: Dictionary containing validation result data

        Returns:
            ValidationResult: Validated result instance
        """
        return cls(
            confidence=cast(float, data["confidence"]),
            hallucination_detected=cast(bool, data["hallucination_detected"]),
            missing_required_fields=cast(
                list[str], data.get("missing_required_fields", [])
            ),
            feedback=cast(str | None, data.get("feedback")),
            mismatched_fields=cast(list[str] | None, data.get("mismatched_fields")),
            suggested_corrections=cast(
                dict[str, str] | None, data.get("suggested_corrections")
            ),
        )

    def dict(self) -> ValidationResultDict:
        """Convert to dictionary format.

        Returns:
            ValidationResultDict: Dictionary representation
        """
        result: ValidationResultDict = {
            "confidence": self.confidence,
            "hallucination_detected": self.hallucination_detected,
            "missing_required_fields": self.missing_required_fields,
        }
        if self.feedback is not None:
            result["feedback"] = self.feedback
        if self.mismatched_fields is not None:
            result["mismatched_fields"] = self.mismatched_fields
        if self.suggested_corrections is not None:
            result["suggested_corrections"] = self.suggested_corrections
        return result
