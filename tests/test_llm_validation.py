"""Tests for LLM validation models and utilities."""

import pytest

from app.llm.hsds_aligner.validation import (
    ValidationConfig,
    ValidationResult,
    ValidationResultDict,
)


class TestValidationConfig:
    """Test ValidationConfig validation."""

    def test_valid_config(self):
        """Test creating a valid configuration."""
        config = ValidationConfig(
            min_confidence=0.85,
            retry_threshold=0.5,
            max_retries=3,
            validation_model="test-model",
            load_from_env=False,
        )
        assert config.min_confidence == 0.85
        assert config.retry_threshold == 0.5
        assert config.max_retries == 3
        assert config.validation_model == "test-model"

    def test_default_config(self):
        """Test default configuration values."""
        config = ValidationConfig(load_from_env=False)
        assert (
            config.min_confidence == 0.82
        )  # Updated to match new HSDS_MIN_CONFIDENCE default
        assert (
            config.retry_threshold == 0.65
        )  # Updated to match new HSDS_RETRY_THRESHOLD default
        assert config.max_retries == 5
        assert config.validation_model is None

    def test_invalid_min_confidence_low(self):
        """Test validation of min_confidence (too low)."""
        with pytest.raises(
            ValueError, match="min_confidence must be between 0.0 and 1.0"
        ):
            ValidationConfig(min_confidence=-0.1, load_from_env=False)

    def test_invalid_min_confidence_high(self):
        """Test validation of min_confidence (too high)."""
        with pytest.raises(
            ValueError, match="min_confidence must be between 0.0 and 1.0"
        ):
            ValidationConfig(min_confidence=1.1, load_from_env=False)

    def test_invalid_retry_threshold_low(self):
        """Test validation of retry_threshold (too low)."""
        with pytest.raises(
            ValueError, match="retry_threshold must be between 0.0 and 1.0"
        ):
            ValidationConfig(retry_threshold=-0.1, load_from_env=False)

    def test_invalid_retry_threshold_high(self):
        """Test validation of retry_threshold (too high)."""
        with pytest.raises(
            ValueError, match="retry_threshold must be between 0.0 and 1.0"
        ):
            ValidationConfig(retry_threshold=1.1, load_from_env=False)

    def test_invalid_max_retries(self):
        """Test validation of max_retries."""
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            ValidationConfig(max_retries=-1, load_from_env=False)

    def test_boundary_values(self):
        """Test boundary values are accepted."""
        config = ValidationConfig(
            min_confidence=0.0, retry_threshold=1.0, max_retries=0, load_from_env=False
        )
        assert config.min_confidence == 0.0
        assert config.retry_threshold == 1.0
        assert config.max_retries == 0


class TestValidationResult:
    """Test ValidationResult functionality."""

    def test_valid_result(self):
        """Test creating a valid result."""
        result = ValidationResult(
            confidence=0.9,
            hallucination_detected=False,
            missing_required_fields=["name"],
            feedback="Good alignment",
            mismatched_fields=["email"],
            suggested_corrections={"phone": "555-1234"},
        )
        assert result.confidence == 0.9
        assert result.hallucination_detected is False
        assert result.missing_required_fields == ["name"]
        assert result.feedback == "Good alignment"
        assert result.mismatched_fields == ["email"]
        assert result.suggested_corrections == {"phone": "555-1234"}

    def test_minimal_result(self):
        """Test creating a minimal result."""
        result = ValidationResult(
            confidence=0.8,
            hallucination_detected=True,
            missing_required_fields=[],
        )
        assert result.confidence == 0.8
        assert result.hallucination_detected is True
        assert result.missing_required_fields == []
        assert result.feedback is None
        assert result.mismatched_fields is None
        assert result.suggested_corrections is None

    def test_invalid_confidence_low(self):
        """Test validation of confidence (too low)."""
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            ValidationResult(
                confidence=-0.1,
                hallucination_detected=False,
                missing_required_fields=[],
            )

    def test_invalid_confidence_high(self):
        """Test validation of confidence (too high)."""
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            ValidationResult(
                confidence=1.1,
                hallucination_detected=False,
                missing_required_fields=[],
            )

    def test_boundary_confidence_values(self):
        """Test boundary confidence values are accepted."""
        result1 = ValidationResult(
            confidence=0.0,
            hallucination_detected=False,
            missing_required_fields=[],
        )
        assert result1.confidence == 0.0

        result2 = ValidationResult(
            confidence=1.0,
            hallucination_detected=False,
            missing_required_fields=[],
        )
        assert result2.confidence == 1.0

    def test_model_validate_full_data(self):
        """Test model_validate with full data."""
        data = {
            "confidence": 0.95,
            "hallucination_detected": False,
            "missing_required_fields": ["description"],
            "feedback": "Excellent alignment",
            "mismatched_fields": ["phone"],
            "suggested_corrections": {"email": "test@example.com"},
        }

        result = ValidationResult.model_validate(data)
        assert result.confidence == 0.95
        assert result.hallucination_detected is False
        assert result.missing_required_fields == ["description"]
        assert result.feedback == "Excellent alignment"
        assert result.mismatched_fields == ["phone"]
        assert result.suggested_corrections == {"email": "test@example.com"}

    def test_model_validate_minimal_data(self):
        """Test model_validate with minimal data."""
        data = {
            "confidence": 0.7,
            "hallucination_detected": True,
        }

        result = ValidationResult.model_validate(data)
        assert result.confidence == 0.7
        assert result.hallucination_detected is True
        assert result.missing_required_fields == []
        assert result.feedback is None
        assert result.mismatched_fields is None
        assert result.suggested_corrections is None

    def test_dict_conversion_full(self):
        """Test dictionary conversion with all fields."""
        result = ValidationResult(
            confidence=0.88,
            hallucination_detected=True,
            missing_required_fields=["name", "description"],
            feedback="Some issues found",
            mismatched_fields=["email", "phone"],
            suggested_corrections={"name": "Corrected Name"},
        )

        result_dict = result.dict()
        expected: ValidationResultDict = {
            "confidence": 0.88,
            "hallucination_detected": True,
            "missing_required_fields": ["name", "description"],
            "feedback": "Some issues found",
            "mismatched_fields": ["email", "phone"],
            "suggested_corrections": {"name": "Corrected Name"},
        }

        assert result_dict == expected

    def test_dict_conversion_minimal(self):
        """Test dictionary conversion with minimal fields."""
        result = ValidationResult(
            confidence=0.6,
            hallucination_detected=False,
            missing_required_fields=["email"],
        )

        result_dict = result.dict()
        expected: ValidationResultDict = {
            "confidence": 0.6,
            "hallucination_detected": False,
            "missing_required_fields": ["email"],
        }

        assert result_dict == expected
        # Check that optional fields are not present
        assert "feedback" not in result_dict
        assert "mismatched_fields" not in result_dict
        assert "suggested_corrections" not in result_dict

    def test_dict_conversion_partial_optional(self):
        """Test dictionary conversion with some optional fields."""
        result = ValidationResult(
            confidence=0.75,
            hallucination_detected=True,
            missing_required_fields=[],
            feedback="Minor issues",
            mismatched_fields=None,
            suggested_corrections={"fix": "this"},
        )

        result_dict = result.dict()
        expected: ValidationResultDict = {
            "confidence": 0.75,
            "hallucination_detected": True,
            "missing_required_fields": [],
            "feedback": "Minor issues",
            "suggested_corrections": {"fix": "this"},
        }

        assert result_dict == expected
        # Check that None mismatched_fields is not included
        assert "mismatched_fields" not in result_dict
