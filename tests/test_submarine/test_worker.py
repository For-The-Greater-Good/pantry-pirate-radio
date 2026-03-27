"""Tests for submarine worker."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.submarine.crawler import CrawlResult
from app.submarine.models import SubmarineJob


class TestProcessSubmarineJob:
    """Tests for the process_submarine_job function."""

    @pytest.fixture
    def sample_job_data(self):
        return SubmarineJob(
            id="sub-001",
            location_id="loc-123",
            organization_id="org-456",
            website_url="https://gracechurch.example.com",
            missing_fields=["phone", "hours"],
            source_scraper_id="test_scraper",
            location_name="Grace Food Pantry",
            latitude=39.7817,
            longitude=-89.6501,
            created_at=datetime.now(UTC),
        ).model_dump(mode="json")

    @patch("app.submarine.worker._update_location_status")
    @patch("app.submarine.worker._process_async")
    def test_returns_none_for_no_data(self, mock_process, mock_update, sample_job_data):
        """Worker returns None when crawl finds no useful data."""
        from app.submarine.models import SubmarineResult
        from app.submarine.worker import process_submarine_job

        mock_process.return_value = SubmarineResult(
            job_id="sub-001",
            location_id="loc-123",
            status="no_data",
        )

        result = process_submarine_job(sample_job_data)

        assert result is None
        mock_update.assert_called_once_with("loc-123", "no_data")

    @patch("app.submarine.worker._update_location_status")
    @patch("app.submarine.worker._process_async")
    def test_returns_none_for_error(self, mock_process, mock_update, sample_job_data):
        """Worker returns None when crawl errors."""
        from app.submarine.models import SubmarineResult
        from app.submarine.worker import process_submarine_job

        mock_process.return_value = SubmarineResult(
            job_id="sub-001",
            location_id="loc-123",
            status="error",
            error="Connection refused",
        )

        result = process_submarine_job(sample_job_data)

        assert result is None
        mock_update.assert_called_once_with("loc-123", "error")

    @patch("app.submarine.worker._update_location_status")
    @patch("app.submarine.worker._process_async")
    def test_returns_job_result_for_success(
        self, mock_process, mock_update, sample_job_data
    ):
        """Worker returns JobResult dict when extraction succeeds."""
        from app.submarine.models import SubmarineResult
        from app.submarine.worker import process_submarine_job

        mock_process.return_value = SubmarineResult(
            job_id="sub-001",
            location_id="loc-123",
            status="success",
            extracted_fields={
                "phone": "(555) 234-5678",
                "hours": [
                    {"day": "Tuesday", "opens_at": "10:00", "closes_at": "14:00"}
                ],
            },
            crawl_metadata={"pages_crawled": 2},
        )

        result = process_submarine_job(sample_job_data)

        assert result is not None
        assert result["job"]["metadata"]["scraper_id"] == "submarine"
        assert result["job"]["metadata"]["location_id"] == "loc-123"
        assert result["status"] == "completed"
        mock_update.assert_called_once_with("loc-123", "success")

    @patch("app.submarine.worker._update_location_status")
    @patch("app.submarine.worker._process_async")
    def test_returns_job_result_for_partial(
        self, mock_process, mock_update, sample_job_data
    ):
        """Worker returns JobResult for partial extraction."""
        from app.submarine.models import SubmarineResult
        from app.submarine.worker import process_submarine_job

        mock_process.return_value = SubmarineResult(
            job_id="sub-001",
            location_id="loc-123",
            status="partial",
            extracted_fields={"phone": "(555) 234-5678"},
            crawl_metadata={"pages_crawled": 1},
        )

        result = process_submarine_job(sample_job_data)

        assert result is not None
        mock_update.assert_called_once_with("loc-123", "partial")


class TestProcessAsync:
    """Tests for the async crawl+extract pipeline."""

    @pytest.mark.asyncio
    async def test_crawl_error_returns_error_result(self):
        """Crawl failure returns error SubmarineResult."""
        from app.submarine.worker import _process_async

        job = SubmarineJob(
            id="sub-002",
            location_id="loc-999",
            website_url="https://down.example.com",
            missing_fields=["phone"],
            source_scraper_id="test",
        )

        with patch("app.submarine.worker.SubmarineCrawler") as MockCrawler:
            mock_instance = AsyncMock()
            mock_instance.crawl.return_value = CrawlResult(
                url="https://down.example.com",
                markdown="",
                pages_crawled=0,
                status="error",
                error="Connection refused",
            )
            MockCrawler.return_value = mock_instance

            result = await _process_async(job)

        assert result.status == "error"
        assert result.error == "Connection refused"

    @pytest.mark.asyncio
    async def test_empty_markdown_returns_no_data(self):
        """Empty crawl content returns no_data."""
        from app.submarine.worker import _process_async

        job = SubmarineJob(
            id="sub-003",
            location_id="loc-888",
            website_url="https://empty.example.com",
            missing_fields=["phone"],
            source_scraper_id="test",
        )

        with patch("app.submarine.worker.SubmarineCrawler") as MockCrawler:
            mock_instance = AsyncMock()
            mock_instance.crawl.return_value = CrawlResult(
                url="https://empty.example.com",
                markdown="   ",
                pages_crawled=1,
                status="success",
            )
            MockCrawler.return_value = mock_instance

            result = await _process_async(job)

        assert result.status == "no_data"
