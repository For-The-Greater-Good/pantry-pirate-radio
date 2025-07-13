"""Tests for the scraper testing utilities."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scraper.test_utils import TestScraperJob, run_scraper_test
from app.scraper.utils import ScraperJob


class MockScraper(ScraperJob):
    """Mock scraper for testing."""

    def __init__(
        self, scraper_id: str = "mock_scraper", should_fail: bool = False
    ) -> None:
        """Initialize mock scraper.

        Args:
            scraper_id: Scraper ID
            should_fail: Whether the scraper should fail
        """
        super().__init__(scraper_id=scraper_id)
        self.should_fail = should_fail

    async def scrape(self) -> str:
        """Mock scrape method.

        Returns:
            Mock result

        Raises:
            RuntimeError: If should_fail is True
        """
        if self.should_fail:
            raise RuntimeError("Mock scraper failure")

        # Return a mock result
        return json.dumps({"status": "success", "items": 5})


@pytest.mark.asyncio
async def test_test_scraper_job_success():
    """Test TestScraperJob with a successful scraper."""
    # Create a mock scraper
    mock_scraper = MockScraper(scraper_id="test_success")

    # Create test wrapper
    test_wrapper = TestScraperJob(mock_scraper)

    # Run test
    result = await test_wrapper.run_test()

    # Check result
    assert result["success"] is True
    assert result["error"] is None
    assert result["duration"] > 0
    assert result["timestamp"] > 0


@pytest.mark.asyncio
async def test_test_scraper_job_failure():
    """Test TestScraperJob with a failing scraper."""
    # Create a mock scraper that will fail
    mock_scraper = MockScraper(scraper_id="test_failure", should_fail=True)

    # Create test wrapper
    test_wrapper = TestScraperJob(mock_scraper)

    # Run test
    result = await test_wrapper.run_test()

    # Check result
    assert result["success"] is False
    assert "Mock scraper failure" in result["error"]
    assert result["duration"] > 0
    assert result["timestamp"] > 0


@pytest.mark.asyncio
@patch("app.scraper.test_utils.importlib.import_module")
async def test_run_scraper_test_function(mock_import_module):
    """Test the run_scraper_test function."""
    # Create a mock module with a mock scraper class
    mock_module = MagicMock()
    mock_scraper_class = MagicMock()
    mock_scraper_instance = MagicMock()

    # Configure the mock scraper
    mock_scraper_instance.scraper_id = "test_scraper"
    mock_scraper_instance.scrape = AsyncMock(
        return_value=json.dumps({"status": "success"})
    )
    mock_scraper_instance.submit_to_queue = MagicMock(return_value="test-job-id")

    # Configure the mock class to return the mock instance
    mock_scraper_class.return_value = mock_scraper_instance

    # Configure the mock module to have the mock class
    mock_module.TestScraper = mock_scraper_class

    # Configure the mock import_module to return the mock module
    mock_import_module.return_value = mock_module

    # Call the function
    result = await run_scraper_test("test")

    # Check that the function imported the correct module
    mock_import_module.assert_called_once_with("app.scraper.test_scraper")

    # Check that the scraper was created
    mock_scraper_class.assert_called_once_with(scraper_id="test")

    # Check that the scrape method was called
    mock_scraper_instance.scrape.assert_called_once()

    # Check the result
    assert result["success"] is True
    assert result["error"] is None
    assert result["duration"] > 0
    assert result["timestamp"] > 0


@pytest.mark.asyncio
@patch("app.scraper.test_utils.importlib.import_module")
async def test_run_scraper_test_function_import_error(mock_import_module):
    """Test the run_scraper_test function when import fails."""
    # Configure the mock import_module to raise an ImportError
    mock_import_module.side_effect = ImportError("Module not found")

    # Call the function
    result = await run_scraper_test("nonexistent")

    # Check the result
    assert result["success"] is False
    assert "Module not found" in result["error"]
    assert result["duration"] == 0
    assert result["timestamp"] > 0
