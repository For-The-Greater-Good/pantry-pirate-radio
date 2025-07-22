"""Simple unit tests for GetFull.app browser scraper to improve coverage."""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime
import asyncio

import pytest
from httpx import AsyncClient, Response

from app.scraper.getfull_app_browser_scraper import (
    Getfull_App_BrowserScraper,
    BrowserWorker,
    ProgressFilter,
)
from app.models.geographic import GridPoint


class TestBrowserScraperMethods:
    """Test individual methods of the browser scraper."""

    @pytest.fixture
    def scraper(self):
        """Create a scraper instance for testing."""
        return Getfull_App_BrowserScraper()

    def test_should_initialize_with_default_values(self, scraper):
        """Test scraper initialization with default values."""
        assert scraper.scraper_id == "getfull_app_browser"
        assert scraper.DEFAULT_SEARCH_RADIUS_MILES == 50.0
        assert scraper.DEFAULT_OVERLAP_FACTOR == 0.30
        assert scraper.auth_token is None
        assert scraper.unique_pantries == set()
        assert scraper.pantry_data == {}

    def test_progress_filter_allows_specific_messages(self):
        """Test ProgressFilter allows specific message types."""
        filter_obj = ProgressFilter()

        # Test error messages
        record = MagicMock()
        record.levelno = 40  # ERROR
        assert filter_obj.filter(record) is True

        # Test progress messages
        record.levelno = 20  # INFO
        record.getMessage.return_value = "OVERALL PROGRESS: 50%"
        assert filter_obj.filter(record) is True

        # Test worker progress
        record.getMessage.return_value = "Worker 1: 50% complete"
        assert filter_obj.filter(record) is True

        # Test other info messages
        record.getMessage.return_value = "Random info"
        assert filter_obj.filter(record) is False

        # Test debug messages
        record.levelno = 10  # DEBUG
        assert filter_obj.filter(record) is False

    def test_transform_to_hsds_with_complete_data(self, scraper):
        """Test HSDS transformation with complete pantry data."""
        pantry = {
            "id": "test-123",
            "name": "Test Pantry",
            "address": {
                "street": "123 Main St",
                "city": "New York",
                "state": "NY",
                "zip": "10001",
            },
            "phone": "(212) 555-0123",
            "email": "test@pantry.org",
            "website": "https://pantry.org",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "hours": [
                {"day": "Monday", "open": "9:00 AM", "close": "5:00 PM"},
                {"day": "Tuesday", "open": "9:00 AM", "close": "5:00 PM"},
            ],
            "lastUpdated": "2024-01-01T00:00:00Z",
            "notes": "Test notes",
            "requirements": "Test requirements",
            "services": ["Food distribution", "Clothing"],
            "eligibility": "Low income",
            "languages": ["English", "Spanish"],
            "accessibility": ["Wheelchair accessible"],
        }

        result = scraper.transform_to_hsds(pantry)

        assert result["id"] == "test-123"
        assert result["name"] == "Test Pantry"
        assert result["address"]["address_1"] == "123 Main St"
        assert result["address"]["city"] == "New York"
        assert result["address"]["state_province"] == "NY"
        assert result["address"]["postal_code"] == "10001"
        assert result["location"]["latitude"] == 40.7128
        assert result["location"]["longitude"] == -74.0060
        assert len(result["phones"]) == 1
        assert result["phones"][0]["number"] == "(212) 555-0123"
        assert result["email"] == "test@pantry.org"
        assert result["url"] == "https://pantry.org"

    def test_transform_to_hsds_with_minimal_data(self, scraper):
        """Test HSDS transformation with minimal pantry data."""
        pantry = {"id": "minimal-123", "name": "Minimal Pantry"}

        result = scraper.transform_to_hsds(pantry)

        assert result["id"] == "minimal-123"
        assert result["name"] == "Minimal Pantry"
        assert result["address"]["address_1"] == ""
        assert result["address"]["city"] == ""
        assert result["address"]["state_province"] == ""
        assert result["address"]["postal_code"] == ""
        # location should be empty dict when no coordinates provided
        assert result["location"] == {}

    def test_transform_to_hsds_handles_invalid_data(self, scraper):
        """Test HSDS transformation handles invalid data gracefully."""
        pantry = {
            "id": "invalid-123",
            "name": "Invalid Data Pantry",
            "latitude": "not-a-number",
            "longitude": None,
            "phone": None,
            "hours": "invalid-hours-format",
        }

        result = scraper.transform_to_hsds(pantry)

        assert result["id"] == "invalid-123"
        assert result["name"] == "Invalid Data Pantry"
        # location should be empty when coordinates are invalid
        assert result["location"] == {}
        assert result["phones"] == []  # No phone since it was None
        assert result["regular_schedule"] == []  # Hours was invalid format

    def test_is_pantry_processed(self, scraper):
        """Test checking if pantry is already processed."""
        # Initially no pantries processed
        assert scraper.is_pantry_processed("pantry-1") is False
        # After first check, it should be marked as processed
        assert scraper.is_pantry_processed("pantry-1") is True

        # Different pantry should not be processed
        assert scraper.is_pantry_processed("pantry-2") is False
        # After check, it's now processed
        assert scraper.is_pantry_processed("pantry-2") is True

    def test_create_general_grid(self, scraper):
        """Test general grid creation."""
        # Provide base coordinates
        base_coords = [
            GridPoint(latitude=40.7, longitude=-74.0, name="NYC"),
            GridPoint(latitude=34.0, longitude=-118.2, name="LA"),
        ]
        grid = scraper._create_general_grid(base_coords)

        assert len(grid) > 0
        # Check first few points are within US bounds
        for point in grid[:5]:
            assert 25.0 <= point.latitude <= 49.0
            assert -125.0 <= point.longitude <= -67.0
            assert isinstance(point.name, str)

    def test_create_region_grid(self, scraper):
        """Test regional grid creation."""
        base_points = [GridPoint(latitude=40.7, longitude=-74.0, name="NYC")]
        grid = scraper._create_region_grid(
            base_points=base_points, radius_miles=10.0, high_density=False
        )

        assert len(grid) > 0
        # Points should be around the base point (NYC) within radius
        for point in grid:
            # Check points are within reasonable bounds of NYC
            assert 39.0 <= point.latitude <= 42.0
            assert -75.0 <= point.longitude <= -73.0

    def test_distribute_coordinates(self, scraper):
        """Test coordinate distribution among workers."""
        # Use region names that the method expects
        regional_coordinates = {
            "east_coast_major": [
                GridPoint(
                    latitude=40.7 + i * 0.1, longitude=-74.0 + i * 0.1, name=f"ec_{i}"
                )
                for i in range(20)
            ],
            "west_coast_major": [
                GridPoint(
                    latitude=34.0 + i * 0.1, longitude=-118.2 + i * 0.1, name=f"wc_{i}"
                )
                for i in range(20)
            ],
        }

        distribution = scraper._distribute_coordinates(regional_coordinates)

        assert isinstance(distribution, list)
        assert len(distribution) == scraper.num_workers
        total = sum(len(coords) for coords in distribution)
        assert total == 40

        # Check balance - with enough points, should be well balanced
        non_empty = [len(coords) for coords in distribution if len(coords) > 0]
        if non_empty:
            assert max(non_empty) - min(non_empty) <= 2

    def test_balance_worker_loads(self, scraper):
        """Test worker load balancing."""
        distribution = [
            [GridPoint(latitude=i, longitude=i, name=f"p{i}") for i in range(10)],
            [GridPoint(latitude=i, longitude=i, name=f"p{i}") for i in range(10, 12)],
            [GridPoint(latitude=i, longitude=i, name=f"p{i}") for i in range(12, 15)],
        ]

        total_before = sum(len(coords) for coords in distribution)

        # balance_worker_loads modifies in place and returns None
        scraper._balance_worker_loads(distribution)

        sizes = [len(coords) for coords in distribution]
        assert max(sizes) - min(sizes) <= 1

        # Verify no coordinates lost
        total_after = sum(len(coords) for coords in distribution)
        assert total_before == total_after

    def test_prepare_regional_coordinate_sets(self, scraper):
        """Test regional coordinate set preparation."""
        # The method uses predefined coordinates, not grid_points attribute
        result = scraper._prepare_regional_coordinate_sets()

        # Should have various regions
        assert isinstance(result, dict)
        assert len(result) > 0

        # Check for some expected regions (based on the actual implementation)
        expected_regions = ["east_coast_major", "west_coast_major", "colorado_major"]
        for region in expected_regions:
            assert region in result
            assert isinstance(result[region], list)
            assert len(result[region]) > 0

    @pytest.mark.asyncio
    async def test_search_pantries_by_location_success(self, scraper):
        """Test successful pantry search by location."""
        scraper.auth_token = "test-token"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "hits": {
                "hits": [
                    {
                        "_id": "pantry-1",
                        "_source": {
                            "name": "Test Pantry 1",
                            "address": {"street": "123 Main St"},
                            "latitude": 40.7128,
                            "longitude": -74.0060,
                        },
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.post = AsyncMock(return_value=mock_response)

            result = await scraper.search_pantries_by_location(40.7128, -74.0060, 50)

            assert len(result) == 1
            assert result[0]["id"] == "pantry-1"
            assert result[0]["name"] == "Test Pantry 1"

    @pytest.mark.asyncio
    async def test_search_pantries_handles_errors(self, scraper):
        """Test pantry search handles errors gracefully."""
        scraper.auth_token = "test-token"

        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.post = AsyncMock(
                side_effect=Exception("Network error")
            )

            result = await scraper.search_pantries_by_location(40.7128, -74.0060, 50)

            assert result == []

    @pytest.mark.asyncio
    async def test_get_pantry_details_api_success(self, scraper):
        """Test getting pantry details via API."""
        scraper.auth_token = "test-token"
        pantry = {"id": "pantry-123", "name": "Test Pantry"}  # Include name field

        mock_response = MagicMock()
        mock_response.status_code = 200
        # API returns pantry details directly
        mock_response.json.return_value = {
            "name": "Detailed Pantry",
            "address": {
                "street": "456 Oak St",
                "city": "Brooklyn",
                "state": "NY",
                "zip": "11201",
            },
            "phone": "718-555-0123",
            "latitude": 40.6892,
            "longitude": -73.9902,
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.get = AsyncMock(return_value=mock_response)

            result = await scraper.get_pantry_details_api(pantry)

            # The method merges API response with original pantry data
            assert result["id"] == "pantry-123"  # Original ID preserved
            assert result["name"] == "Detailed Pantry"  # Updated from API
            assert result["address"]["city"] == "Brooklyn"  # From API
            assert result["phone"] == "718-555-0123"  # From API

    @pytest.mark.asyncio
    async def test_get_pantry_details_api_error_returns_original(self, scraper):
        """Test pantry details API returns original on error."""
        scraper.auth_token = "test-token"
        pantry = {"id": "pantry-123", "name": "Original Pantry"}

        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.get = AsyncMock(side_effect=Exception("API Error"))

            result = await scraper.get_pantry_details_api(pantry)

            assert result == pantry

    @pytest.mark.asyncio
    async def test_scrape_with_auth_token_from_env(self, scraper):
        """Test scraping with auth token from environment."""
        # Mock the entire flow - auth token is set during navigate_to_map
        with patch.object(scraper, "geo_search_scrape") as mock_geo:
            mock_geo.return_value = {
                "summary": {
                    "total_unique_pantries": 100,
                    "total_coordinates_processed": 50,
                }
            }

            result = await scraper.scrape()

            # Result is JSON string of the summary

            result_data = json.loads(result)
            assert result_data["summary"]["total_unique_pantries"] == 100
            mock_geo.assert_called_once()

    @pytest.mark.asyncio
    async def test_scrape_without_auth_token_handles_gracefully(self, scraper):
        """Test scraping without auth token handles gracefully."""
        # Mock geo_search_scrape to return error when no auth token
        with patch.object(scraper, "geo_search_scrape") as mock_geo:
            mock_geo.return_value = {
                "error": "Authentication failed",
                "total_pantries_found": 0,
                "unique_pantries": 0,
            }

            result = await scraper.scrape()

            # Result is JSON string of the error response

            result_data = json.loads(result)
            assert result_data["error"] == "Authentication failed"
            assert result_data["unique_pantries"] == 0
            mock_geo.assert_called_once()


class TestBrowserWorkerSimple:
    """Simple tests for BrowserWorker class."""

    @pytest.fixture
    def mock_scraper(self):
        """Create a mock scraper."""
        scraper = MagicMock()
        scraper.auth_token = "test-token"
        scraper.DEFAULT_REQUEST_DELAY = 0.05
        scraper.unique_pantries = {}
        scraper.pantries_lock = MagicMock()
        scraper.default_zoom_level = 11
        return scraper

    @pytest.fixture
    def worker(self, mock_scraper):
        """Create a browser worker."""
        return BrowserWorker(worker_id=1, scraper=mock_scraper)

    def test_browser_worker_initialization(self, worker):
        """Test browser worker initialization."""
        assert worker.worker_id == 1
        assert worker.pantries_found == 0
        assert worker.unique_pantries == {}
        assert worker.page is None
        assert worker.browser is None

    @pytest.mark.asyncio
    async def test_cleanup_with_no_resources(self, worker):
        """Test cleanup when no resources initialized."""
        # Should not raise exception
        await worker.cleanup()

        assert worker.page is None
        assert worker.browser is None

    @pytest.mark.asyncio
    async def test_cleanup_with_resources(self, worker):
        """Test cleanup with initialized resources."""
        # Mock resources
        worker.page = AsyncMock()
        worker.browser = AsyncMock()
        worker.playwright = AsyncMock()

        await worker.cleanup()

        # Cleanup only closes browser and playwright, not page
        worker.browser.close.assert_called_once()
        worker.playwright.stop.assert_called_once()
