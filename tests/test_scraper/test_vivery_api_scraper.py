"""Tests for Vivery API scraper."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.geographic import GridPoint
from app.scraper.vivery_api_scraper import (
    ScheduleData,
    ServiceData,
    SpecialHoursData,
    Vivery_ApiScraper,
)


@pytest.fixture(name="scraper")
def fixture_scraper() -> Vivery_ApiScraper:
    """Create test scraper instance."""
    return Vivery_ApiScraper()


@pytest.fixture(name="mock_location")
def fixture_mock_location() -> dict[str, Any]:
    """Create mock location data."""
    return {
        "locationId": 123,
        "organizationId": 456,
        "locationName": "Test Food Pantry",
        "address1": "123 Main St",
        "city": "Testville",
        "state": "CA",
        "zipCode": "12345",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "foodPrograms": "Food Pantry|Meals",
        "serviceLanguages": "English|Spanish",
        "locationFeatures": "Wheelchair Accessible|Parking",
        "aboutUs": "<p>We help people</p>",
        "networkAffiliationsList": ["Network 1", "Network 2"],
    }


@pytest.fixture(name="mock_schedule")
def fixture_mock_schedule() -> ScheduleData:
    """Create mock schedule data."""
    return {
        "locationId": 123,
        "weekDayDescr": "Monday",
        "startTimeDescr": "9:00 AM",
        "endTimeDescr": "5:00 PM",
        "notes": "By appointment",
        "weeksOfMonth": "1,3",
    }


@pytest.fixture(name="mock_service")
def fixture_mock_service() -> ServiceData:
    """Create mock service data."""
    return {
        "locationId": 123,
        "serviceName": "Food Distribution",
        "serviceCategoryDescription": "Food",
        "overview": "<p>Weekly distribution</p>",
        "qualifications": "None",
        "contactName": "John Doe",
        "contactPhone": "555-1234",
    }


@pytest.fixture(name="mock_special_hours")
def fixture_mock_special_hours() -> SpecialHoursData:
    """Create mock special hours data."""
    return {"id": 123, "data": [{"date": "2025-02-13", "hours": "9:00 AM - 5:00 PM"}]}


@pytest.mark.asyncio
async def test_search_locations(
    scraper: Vivery_ApiScraper, mock_location: dict[str, Any]
) -> None:
    """Test location search."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"item1": [mock_location]}
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        results = await scraper.search_locations(37.7749, -122.4194)
        assert len(results) == 1
        assert results[0]["locationId"] == 123


@pytest.mark.asyncio
async def test_fetch_additional_data(
    scraper: Vivery_ApiScraper,
    mock_schedule: ScheduleData,
    mock_service: ServiceData,
    mock_special_hours: SpecialHoursData,
) -> None:
    """Test fetching additional location data."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_responses = [
            MagicMock(status_code=200, json=MagicMock(return_value=[mock_schedule])),
            MagicMock(status_code=200, json=MagicMock(return_value=[mock_service])),
            MagicMock(
                status_code=200, json=MagicMock(return_value=[mock_special_hours])
            ),
        ]

        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=mock_responses
        )

        schedules, services, special_hours = await scraper.fetch_additional_data(
            ["123"]
        )
        assert len(schedules) == 1
        assert len(services) == 1
        assert len(special_hours) == 1
        assert schedules[0]["locationId"] == 123
        assert services[0]["locationId"] == 123
        assert special_hours[0]["id"] == 123


def test_format_schedule(
    scraper: Vivery_ApiScraper, mock_schedule: ScheduleData
) -> None:
    """Test schedule formatting."""
    formatted = scraper.format_schedule(mock_schedule)
    assert "Monday" in formatted
    assert "9:00 AM-5:00 PM" in formatted
    assert "(By appointment)" in formatted
    assert "[1,3 week(s)]" in formatted


def test_format_service(scraper: Vivery_ApiScraper, mock_service: ServiceData) -> None:
    """Test service formatting."""
    formatted = scraper.format_service(mock_service)
    assert formatted["name"] == "Food Distribution"
    assert formatted["category"] == "Food"
    assert formatted["overview"] == "Weekly distribution"
    assert formatted["contact"] == "John Doe (555-1234)"


@pytest.mark.asyncio
async def test_process_batch(
    scraper: Vivery_ApiScraper,
    mock_location: dict[str, Any],
    mock_schedule: ScheduleData,
    mock_service: ServiceData,
    mock_special_hours: SpecialHoursData,
) -> None:
    """Test batch processing."""
    coordinates = [GridPoint(name="test", latitude=37.7749, longitude=-122.4194)]

    # Mock search_locations to return a list with the mock location
    scraper.search_locations = AsyncMock(return_value=[mock_location])

    # Mock fetch_additional_data to return properly structured data
    scraper.fetch_additional_data = AsyncMock(
        return_value=([mock_schedule], [mock_service], [mock_special_hours])
    )

    # Mock submit_to_queue
    scraper.submit_to_queue = AsyncMock(return_value="test-job-id")

    await scraper.process_batch(coordinates)

    assert scraper.total_locations == 1
    assert len(scraper.unique_locations) == 1
    assert "123" in scraper.unique_locations


@pytest.mark.asyncio
async def test_scrape(scraper: Vivery_ApiScraper) -> None:
    """Test full scrape process."""
    # Mock grid points
    with patch("app.scraper.utils.ScraperUtils.get_us_grid_points") as mock_grid:
        mock_grid.return_value = [
            GridPoint(name="test", latitude=37.7749, longitude=-122.4194)
        ]

        # Mock process_batch
        scraper.process_batch = AsyncMock()

        result = await scraper.scrape()
        data = json.loads(result)

        assert data["total_coordinates"] == 1
        assert "source" in data
        assert scraper.process_batch.called


@pytest.mark.asyncio
async def test_empty_response_handling(scraper: Vivery_ApiScraper) -> None:
    """Test handling of empty API responses."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"item1": []}
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        results = await scraper.search_locations(37.7749, -122.4194)
        assert len(results) == 0


@pytest.mark.asyncio
async def test_error_handling(scraper: Vivery_ApiScraper) -> None:
    """Test error handling during batch processing."""
    coordinates = [GridPoint(name="test", latitude=37.7749, longitude=-122.4194)]

    # Mock search_locations to raise an exception
    scraper.search_locations = AsyncMock(side_effect=Exception("API Error"))

    # This should not raise an exception
    await scraper.process_batch(coordinates)

    # Verify the batch was processed without adding locations
    assert scraper.total_locations == 0
    assert len(scraper.unique_locations) == 0


@pytest.mark.asyncio
async def test_duplicate_location_handling(
    scraper: Vivery_ApiScraper,
    mock_location: dict[str, Any],
    mock_schedule: ScheduleData,
    mock_service: ServiceData,
    mock_special_hours: SpecialHoursData,
) -> None:
    """Test handling of duplicate locations."""
    coordinates = [
        GridPoint(name="test1", latitude=37.7749, longitude=-122.4194),
        GridPoint(name="test2", latitude=37.7750, longitude=-122.4195),
    ]

    # Mock search_locations to return the same location for both coordinates
    scraper.search_locations = AsyncMock(return_value=[mock_location])

    # Mock fetch_additional_data to return properly structured data
    scraper.fetch_additional_data = AsyncMock(
        return_value=([mock_schedule], [mock_service], [mock_special_hours])
    )

    # Mock submit_to_queue
    scraper.submit_to_queue = AsyncMock(return_value="test-job-id")

    await scraper.process_batch(coordinates)

    # Verify the location was only processed once
    assert scraper.total_locations == 1
    assert len(scraper.unique_locations) == 1
