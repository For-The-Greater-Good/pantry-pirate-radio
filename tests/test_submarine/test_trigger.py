"""Tests for SubmarineDispatcher — gap detection and job enqueueing."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.submarine.models import SubmarineJob


class TestSubmarineDispatcher:
    """Tests for the SubmarineDispatcher class."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        db = MagicMock()
        return db

    @pytest.fixture
    def dispatcher(self, mock_db):
        """Create a SubmarineDispatcher with mocked dependencies."""
        from app.reconciler.submarine_dispatcher import SubmarineDispatcher

        return SubmarineDispatcher(db=mock_db)

    def test_skips_when_source_is_submarine(self, dispatcher):
        """CRITICAL: Submarine results must NOT re-trigger submarine jobs."""
        result = dispatcher.check_and_enqueue(
            location_id="loc-123",
            organization_id="org-456",
            job_metadata={"scraper_id": "submarine"},
        )
        assert result is None

    def test_skips_when_source_type_is_submarine(self, dispatcher):
        """Belt-and-suspenders: also check source_type metadata."""
        result = dispatcher.check_and_enqueue(
            location_id="loc-123",
            organization_id="org-456",
            job_metadata={"source_type": "submarine"},
        )
        assert result is None

    def test_skips_when_disabled(self, dispatcher):
        """SUBMARINE_ENABLED=false -> no submarine jobs."""
        with patch("app.reconciler.submarine_dispatcher.settings") as mock_settings:
            mock_settings.SUBMARINE_ENABLED = False
            result = dispatcher.check_and_enqueue(
                location_id="loc-123",
                organization_id="org-456",
                job_metadata={"scraper_id": "some_scraper"},
            )
        assert result is None

    def test_skips_when_no_website_url(self, dispatcher, mock_db):
        """Location without website URL -> no submarine job."""
        with patch("app.reconciler.submarine_dispatcher.settings") as mock_settings:
            mock_settings.SUBMARINE_ENABLED = True
            # Mock DB queries: no website found
            mock_db.execute.return_value.first.return_value = None
            result = dispatcher.check_and_enqueue(
                location_id="loc-123",
                organization_id="org-456",
                job_metadata={"scraper_id": "some_scraper"},
            )
        assert result is None

    def test_skips_when_all_fields_present(self, dispatcher, mock_db):
        """Location with all target fields present -> no submarine job."""
        with patch("app.reconciler.submarine_dispatcher.settings") as mock_settings:
            mock_settings.SUBMARINE_ENABLED = True
            # Mock: website exists
            mock_db.execute.return_value.first.side_effect = [
                ("https://foodbank.example.com",),  # website URL found
                (None, None),  # submarine_last_crawled_at, status (no cooldown)
            ]
            # Mock: no missing fields
            dispatcher._detect_missing_fields = MagicMock(return_value=[])
            result = dispatcher.check_and_enqueue(
                location_id="loc-123",
                organization_id="org-456",
                job_metadata={"scraper_id": "some_scraper"},
            )
        assert result is None

    def test_enqueues_when_location_has_gaps_and_website(self, dispatcher, mock_db):
        """Location with website + missing fields -> submarine job created."""
        with patch("app.reconciler.submarine_dispatcher.settings") as mock_settings:
            mock_settings.SUBMARINE_ENABLED = True
            mock_settings.SUBMARINE_COOLDOWN_SUCCESS_DAYS = 30
            mock_settings.SUBMARINE_COOLDOWN_NO_DATA_DAYS = 90
            mock_settings.SUBMARINE_COOLDOWN_ERROR_DAYS = 14
            mock_settings.SUBMARINE_MAX_ATTEMPTS = 3

            # Mock: website found, no cooldown, has missing fields
            mock_db.execute.return_value.first.side_effect = [
                ("https://foodbank.example.com",),  # website URL
                (None, None),  # no previous crawl
                ("Food Bank Name", 40.7128, -74.0060),  # location data
            ]
            dispatcher._detect_missing_fields = MagicMock(
                return_value=["phone", "hours"]
            )

            with patch(
                "app.reconciler.submarine_dispatcher.SubmarineDispatcher._enqueue"
            ) as mock_enqueue:
                mock_enqueue.return_value = "sub-001"
                result = dispatcher.check_and_enqueue(
                    location_id="loc-123",
                    organization_id="org-456",
                    job_metadata={"scraper_id": "some_scraper"},
                )

            assert result == "sub-001"
            mock_enqueue.assert_called_once()
            job = mock_enqueue.call_args[0][0]
            assert isinstance(job, SubmarineJob)
            assert job.location_id == "loc-123"
            assert job.missing_fields == ["phone", "hours"]
            assert job.website_url == "https://foodbank.example.com"


class TestAdaptiveCooldown:
    """Tests for adaptive cooldown based on last crawl status."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def dispatcher(self, mock_db):
        from app.reconciler.submarine_dispatcher import SubmarineDispatcher

        return SubmarineDispatcher(db=mock_db)

    def test_success_cooldown_active(self, dispatcher):
        """Skip if last crawl was success within cooldown period."""
        last_crawled = datetime.now(UTC) - timedelta(days=10)  # 10 days ago
        assert dispatcher._is_in_cooldown(last_crawled, cooldown_days=30)

    def test_success_cooldown_expired(self, dispatcher):
        """Allow if success cooldown has expired."""
        last_crawled = datetime.now(UTC) - timedelta(days=35)  # 35 days ago
        assert not dispatcher._is_in_cooldown(last_crawled, cooldown_days=30)

    def test_no_data_cooldown_active(self, dispatcher):
        """Skip if no_data crawl within long cooldown period."""
        last_crawled = datetime.now(UTC) - timedelta(days=45)  # 45 days ago
        assert dispatcher._is_in_cooldown(last_crawled, cooldown_days=90)

    def test_no_data_cooldown_expired(self, dispatcher):
        """Allow if no_data long cooldown has expired."""
        last_crawled = datetime.now(UTC) - timedelta(days=95)
        assert not dispatcher._is_in_cooldown(last_crawled, cooldown_days=90)

    def test_error_cooldown_active(self, dispatcher):
        """Skip if error crawl within short cooldown."""
        last_crawled = datetime.now(UTC) - timedelta(days=7)
        assert dispatcher._is_in_cooldown(last_crawled, cooldown_days=14)

    def test_error_cooldown_expired(self, dispatcher):
        """Allow if error short cooldown has expired."""
        last_crawled = datetime.now(UTC) - timedelta(days=16)
        assert not dispatcher._is_in_cooldown(last_crawled, cooldown_days=14)

    def test_no_previous_crawl(self, dispatcher):
        """No previous crawl -> no cooldown."""
        assert not dispatcher._is_in_cooldown(None, cooldown_days=30)

    def test_blocked_uses_no_data_cooldown(self, dispatcher):
        """Blocked status uses the long (no_data) cooldown."""
        last_crawled = datetime.now(UTC) - timedelta(days=45)
        assert dispatcher._is_in_cooldown(last_crawled, cooldown_days=90)
