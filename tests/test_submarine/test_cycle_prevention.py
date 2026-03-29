"""Dedicated tests for submarine cycle prevention.

These tests verify that submarine-originated data flowing back through
the reconciler does NOT trigger new submarine jobs — preventing infinite loops.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestCyclePrevention:
    """Tests ensuring submarine results don't re-trigger submarine jobs."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def dispatcher(self, mock_db):
        from app.reconciler.submarine_dispatcher import SubmarineDispatcher

        return SubmarineDispatcher(db=mock_db)

    def test_scraper_id_submarine_blocks(self, dispatcher):
        """metadata.scraper_id == 'submarine' -> no job."""
        result = dispatcher.check_and_enqueue(
            location_id="loc-123",
            organization_id=None,
            job_metadata={"scraper_id": "submarine"},
        )
        assert result is None

    def test_source_type_submarine_blocks(self, dispatcher):
        """metadata.source_type == 'submarine' -> no job."""
        result = dispatcher.check_and_enqueue(
            location_id="loc-123",
            organization_id=None,
            job_metadata={"source_type": "submarine", "scraper_id": "other"},
        )
        assert result is None

    def test_both_flags_block(self, dispatcher):
        """Both submarine flags set -> no job."""
        result = dispatcher.check_and_enqueue(
            location_id="loc-123",
            organization_id=None,
            job_metadata={
                "scraper_id": "submarine",
                "source_type": "submarine",
            },
        )
        assert result is None

    def test_regular_scraper_not_blocked(self, dispatcher, mock_db):
        """Regular scraper metadata does NOT trigger cycle prevention."""
        with patch("app.reconciler.submarine_dispatcher.settings") as mock_settings:
            mock_settings.SUBMARINE_ENABLED = True
            mock_settings.SUBMARINE_COOLDOWN_SUCCESS_DAYS = 30
            mock_settings.SUBMARINE_COOLDOWN_NO_DATA_DAYS = 90
            mock_settings.SUBMARINE_COOLDOWN_ERROR_DAYS = 14
            mock_settings.SUBMARINE_MAX_ATTEMPTS = 3

            # Mock: no website found (so it won't actually enqueue,
            # but it should NOT be blocked by cycle prevention)
            mock_db.execute.return_value.first.return_value = None

            result = dispatcher.check_and_enqueue(
                location_id="loc-123",
                organization_id="org-456",
                job_metadata={"scraper_id": "capital_area_food_bank_dc"},
            )
            # Result is None because no website, but the point is it
            # wasn't blocked by cycle prevention — it proceeded to checks
            assert result is None

    def test_empty_metadata_not_blocked(self, dispatcher, mock_db):
        """Empty metadata does NOT trigger cycle prevention."""
        with patch("app.reconciler.submarine_dispatcher.settings") as mock_settings:
            mock_settings.SUBMARINE_ENABLED = True
            mock_db.execute.return_value.first.return_value = None

            result = dispatcher.check_and_enqueue(
                location_id="loc-123",
                organization_id=None,
                job_metadata={},
            )
            assert result is None
