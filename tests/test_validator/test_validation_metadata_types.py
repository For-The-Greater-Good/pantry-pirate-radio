"""Regression test: _extract_validation_metadata must return correct types."""

from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session
from app.validator.job_processor import ValidationProcessor


class TestValidationMetadataTypes:
    def test_confidence_score_is_int(self):
        """confidence_score must be int 0-100, not float."""
        with patch(
            "app.validator.job_processor.ValidationProcessor._is_enabled",
            return_value=True,
        ):
            processor = ValidationProcessor(db=MagicMock(spec=Session))
        processor._validation_errors = []
        metadata = processor._extract_validation_metadata({"organization": []})
        assert isinstance(metadata["confidence_score"], int)

    def test_status_uses_valid_enum(self):
        """status must be verified/needs_review/rejected, not 'validated'/'failed'."""
        with patch(
            "app.validator.job_processor.ValidationProcessor._is_enabled",
            return_value=True,
        ):
            processor = ValidationProcessor(db=MagicMock(spec=Session))
        processor._validation_errors = []
        metadata = processor._extract_validation_metadata({"organization": []})
        assert metadata["status"] in (
            "verified",
            "needs_review",
            "rejected",
            "pending",
        )
