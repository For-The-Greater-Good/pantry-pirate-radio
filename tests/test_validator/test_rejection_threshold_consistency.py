"""Regression test: _get_rejection_reason must use settings threshold, not hardcoded 10."""

from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session

from app.validator.job_processor import ValidationProcessor


class TestRejectionThresholdConsistency:
    def test_rejection_reason_uses_settings_threshold(self):
        """When threshold=30, score 25 should produce a rejection reason."""
        with patch(
            "app.validator.job_processor.ValidationProcessor._is_enabled",
            return_value=True,
        ):
            processor = ValidationProcessor(db=MagicMock(spec=Session))

        with patch("app.core.config.settings") as mock_settings:
            mock_settings.VALIDATION_REJECTION_THRESHOLD = 30
            reason = processor._get_rejection_reason(
                confidence_score=25,
                validation_results={
                    "has_coordinates": True,
                    "is_zero_coordinates": False,
                    "within_us_bounds": True,
                    "is_test_data": False,
                },
            )
            # Score 25 < threshold 30, so reason must NOT be None
            assert reason is not None

    def test_rejection_reason_none_above_threshold(self):
        """Score above threshold should return no rejection reason."""
        with patch(
            "app.validator.job_processor.ValidationProcessor._is_enabled",
            return_value=True,
        ):
            processor = ValidationProcessor(db=MagicMock(spec=Session))

        with patch("app.core.config.settings") as mock_settings:
            mock_settings.VALIDATION_REJECTION_THRESHOLD = 30
            reason = processor._get_rejection_reason(
                confidence_score=35,
                validation_results={"has_coordinates": True},
            )
            assert reason is None
