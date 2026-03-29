"""Tests for submarine worker."""

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.submarine.crawler import CrawlResult
from app.submarine.extractor import ExtractionError
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
    @patch("app.submarine.worker._process_job")
    def test_returns_job_result_for_success(
        self, mock_process_job, mock_update, sample_job_data
    ):
        """Worker returns JobResult dict when extraction succeeds."""
        from app.submarine.worker import process_submarine_job

        mock_result = {
            "job_id": "submarine-sub-001",
            "status": "completed",
            "job": {"metadata": {"scraper_id": "submarine", "location_id": "loc-123"}},
        }
        mock_process_job.return_value = (mock_result, "loc-123", "success")

        result = process_submarine_job(sample_job_data)

        assert result is not None
        assert result["job"]["metadata"]["scraper_id"] == "submarine"
        assert result["job"]["metadata"]["location_id"] == "loc-123"
        assert result["status"] == "completed"
        mock_update.assert_called_once_with("loc-123", "success")

    @patch("app.submarine.worker._update_location_status")
    @patch("app.submarine.worker._process_job")
    def test_returns_job_result_for_partial(
        self, mock_process_job, mock_update, sample_job_data
    ):
        """Worker returns JobResult for partial extraction."""
        from app.submarine.worker import process_submarine_job

        mock_result = {"job_id": "submarine-sub-001", "status": "completed"}
        mock_process_job.return_value = (mock_result, "loc-123", "partial")

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

    @pytest.mark.asyncio
    async def test_process_async_success_path(self):
        """Successful crawl + extraction returns status=success with fields."""
        from app.submarine.worker import _process_async

        job = SubmarineJob(
            id="sub-004",
            location_id="loc-777",
            website_url="https://foodbank.example.com",
            missing_fields=["phone", "hours"],
            source_scraper_id="test",
        )

        with (
            patch("app.submarine.worker.SubmarineCrawler") as MockCrawler,
            patch("app.submarine.worker.SubmarineExtractor") as MockExtractor,
            patch("app.submarine.worker.create_provider") as mock_create_provider,
        ):
            # Mock crawler to return success with markdown
            mock_crawler = AsyncMock()
            mock_crawler.crawl.return_value = CrawlResult(
                url="https://foodbank.example.com",
                markdown="# Food Bank\nWe are a food pantry serving the community.\nPhone: 555-1234\nOpen Mon-Fri 9-5",
                pages_crawled=2,
                status="success",
                links_followed=["https://foodbank.example.com/contact"],
            )
            MockCrawler.return_value = mock_crawler

            # Mock extractor to return extracted fields
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(
                return_value={
                    "phone": "(555) 123-4567",
                    "hours": [
                        {"day": "Monday", "opens_at": "09:00", "closes_at": "17:00"}
                    ],
                }
            )
            MockExtractor.return_value = mock_extractor

            # Mock provider
            mock_create_provider.return_value = MagicMock()

            result = await _process_async(job)

        assert result.status == "success"
        assert result.extracted_fields["phone"] == "(555) 123-4567"
        assert len(result.extracted_fields["hours"]) == 1
        assert result.crawl_metadata["pages_crawled"] == 2

    @pytest.mark.asyncio
    async def test_process_async_extraction_error_returns_error_status(self):
        """ExtractionError from extractor maps to status=error, not no_data."""
        from app.submarine.worker import _process_async

        job = SubmarineJob(
            id="sub-005",
            location_id="loc-666",
            website_url="https://foodbank.example.com",
            missing_fields=["phone"],
            source_scraper_id="test",
        )

        with (
            patch("app.submarine.worker.SubmarineCrawler") as MockCrawler,
            patch("app.submarine.worker.SubmarineExtractor") as MockExtractor,
            patch("app.submarine.worker.create_provider") as mock_create_provider,
        ):
            # Crawler succeeds with content
            mock_crawler = AsyncMock()
            mock_crawler.crawl.return_value = CrawlResult(
                url="https://foodbank.example.com",
                markdown="# Community Food Pantry\nOur food bank provides grocery assistance to families in need.",
                pages_crawled=1,
                status="success",
                links_followed=[],
            )
            MockCrawler.return_value = mock_crawler

            # Extractor raises ExtractionError
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(
                side_effect=ExtractionError("LLM provider timeout")
            )
            MockExtractor.return_value = mock_extractor

            mock_create_provider.return_value = MagicMock()

            result = await _process_async(job)

        assert result.status == "error"
        assert "LLM extraction failed" in result.error


class TestResultForwarding:
    """Tests for local result forwarding to reconciler queue."""

    @pytest.fixture
    def sample_job_data(self):
        return SubmarineJob(
            id="sub-fwd-001",
            location_id="loc-fwd-123",
            organization_id="org-456",
            website_url="https://gracechurch.example.com",
            missing_fields=["phone"],
            source_scraper_id="test_scraper",
            location_name="Grace Food Pantry",
            latitude=39.7817,
            longitude=-89.6501,
            created_at=datetime.now(UTC),
        ).model_dump(mode="json")

    @patch.dict(os.environ, {"QUEUE_BACKEND": "redis"}, clear=False)
    @patch("app.submarine.worker._update_location_status")
    @patch("app.submarine.worker._process_job")
    @patch("app.llm.queue.queues.reconciler_queue")
    def test_forwards_result_to_reconciler_on_redis(
        self, mock_reconciler_queue, mock_process, mock_update, sample_job_data
    ):
        """On Redis backend, successful results should be forwarded to reconciler queue."""
        from app.submarine.worker import process_submarine_job

        mock_result = {
            "job_id": "sub-fwd-001",
            "status": "completed",
            "data": {"phone": "555-1234"},
        }
        mock_process.return_value = (mock_result, "loc-fwd-123", "success")

        result = process_submarine_job(sample_job_data)

        assert result == mock_result
        mock_reconciler_queue.enqueue_call.assert_called_once()
        call_kwargs = mock_reconciler_queue.enqueue_call.call_args
        assert (
            call_kwargs.kwargs["func"]
            == "app.reconciler.job_processor.process_job_result"
        )
        assert call_kwargs.kwargs["args"] == (mock_result,)
        # Status update happens AFTER forwarding for success
        mock_update.assert_called_once_with("loc-fwd-123", "success")

    @patch.dict(os.environ, {"QUEUE_BACKEND": "sqs"}, clear=False)
    @patch("app.submarine.worker._update_location_status")
    @patch("app.submarine.worker._process_job")
    def test_skips_forwarding_on_sqs(self, mock_process, mock_update, sample_job_data):
        """On SQS backend, PipelineWorker handles forwarding — worker should not."""
        from app.submarine.worker import process_submarine_job

        mock_result = {"job_id": "sub-fwd-001", "status": "completed"}
        mock_process.return_value = (mock_result, "loc-fwd-123", "success")

        result = process_submarine_job(sample_job_data)
        assert result == mock_result
        # Status still updated even on SQS (forwarding is handled by PipelineWorker)
        mock_update.assert_called_once_with("loc-fwd-123", "success")

    @patch.dict(os.environ, {"QUEUE_BACKEND": "redis"}, clear=False)
    @patch("app.submarine.worker._process_job")
    def test_no_forwarding_when_result_is_none(self, mock_process, sample_job_data):
        """None results (no_data/error) should not be forwarded."""
        from app.submarine.worker import process_submarine_job

        mock_process.return_value = (None, "loc-fwd-123", "no_data")

        result = process_submarine_job(sample_job_data)
        assert result is None


class TestContentRelevanceGate:
    """Tests for the pre-extraction content relevance keyword check."""

    @pytest.mark.asyncio
    async def test_irrelevant_content_returns_no_data(self):
        """Website about a dental office should be rejected as NO_DATA."""
        from app.submarine.worker import _process_async

        job = SubmarineJob(
            id="sub-rel-001",
            location_id="loc-rel-1",
            website_url="https://dentist.example.com",
            missing_fields=["phone"],
            source_scraper_id="test",
        )

        with patch("app.submarine.worker.SubmarineCrawler") as MockCrawler:
            mock_crawler = AsyncMock()
            mock_crawler.crawl.return_value = CrawlResult(
                url="https://dentist.example.com",
                markdown=(
                    "# Smith Family Dentistry\n"
                    "We offer general dentistry, cosmetic procedures, and orthodontics.\n"
                    "Call us at (555) 999-0000 for an appointment.\n"
                    "Open Monday through Friday, 8am to 5pm."
                ),
                pages_crawled=1,
                status="success",
            )
            MockCrawler.return_value = mock_crawler

            result = await _process_async(job)

        assert result.status == "no_data"
        assert (
            result.crawl_metadata.get("rejection_reason") == "content_not_food_related"
        )

    @pytest.mark.asyncio
    async def test_relevant_content_proceeds_to_extraction(self):
        """Website with food bank content should pass the gate and hit the extractor."""
        from app.submarine.worker import _process_async

        job = SubmarineJob(
            id="sub-rel-002",
            location_id="loc-rel-2",
            website_url="https://foodbank.example.com",
            missing_fields=["phone"],
            source_scraper_id="test",
        )

        with (
            patch("app.submarine.worker.SubmarineCrawler") as MockCrawler,
            patch("app.submarine.worker.SubmarineExtractor") as MockExtractor,
            patch("app.submarine.worker.create_provider") as mock_create_provider,
        ):
            mock_crawler = AsyncMock()
            mock_crawler.crawl.return_value = CrawlResult(
                url="https://foodbank.example.com",
                markdown=(
                    "# Grace Community Food Pantry\n"
                    "Our food bank serves families in need with grocery assistance.\n"
                    "Free food distribution every Tuesday and Thursday."
                ),
                pages_crawled=1,
                status="success",
                links_followed=[],
            )
            MockCrawler.return_value = mock_crawler

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value={"phone": "(555) 123-4567"})
            MockExtractor.return_value = mock_extractor
            mock_create_provider.return_value = MagicMock()

            result = await _process_async(job)

        # Should have proceeded to extraction
        assert result.status in ("success", "partial")
        mock_extractor.extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_keyword_insufficient(self):
        """Content with only one food keyword should be rejected."""
        from app.submarine.worker import _process_async

        job = SubmarineJob(
            id="sub-rel-003",
            location_id="loc-rel-3",
            website_url="https://restaurant.example.com",
            missing_fields=["phone"],
            source_scraper_id="test",
        )

        with patch("app.submarine.worker.SubmarineCrawler") as MockCrawler:
            mock_crawler = AsyncMock()
            mock_crawler.crawl.return_value = CrawlResult(
                url="https://restaurant.example.com",
                markdown=(
                    "# Joe's Diner\n"
                    "We serve the best meal in town! Come try our burgers.\n"
                    "Open daily 11am-9pm. Call (555) 777-8888."
                ),
                pages_crawled=1,
                status="success",
            )
            MockCrawler.return_value = mock_crawler

            result = await _process_async(job)

        assert result.status == "no_data"
        assert (
            result.crawl_metadata.get("rejection_reason") == "content_not_food_related"
        )
