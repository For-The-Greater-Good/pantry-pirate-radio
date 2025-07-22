"""Unit tests for GetFull.app browser scraper geo search functionality."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, Response

from app.scraper.getfull_app_browser_scraper import Getfull_App_BrowserScraper


class TestGetfullAppBrowserScraperGeoSearch:
    """Test suite for GetFull.app browser scraper geo search functionality."""

    @pytest.fixture
    def scraper(self):
        """Create a scraper instance for testing."""
        return Getfull_App_BrowserScraper()

    @pytest.fixture
    def mock_pantry_response(self):
        """Mock pantry response from API."""
        return {
            "_id": "test-123",
            "_source": {
                "name": "Test Geo Pantry",
                "address": {
                    "street": "456 Geo St",
                    "city": "Boston",
                    "state": "MA",
                    "zip": "02101",
                },
                "latitude": 42.3601,
                "longitude": -71.0589,
                "phone": "617-555-0123",
                "hours": [{"day": "Wednesday", "open": "8:00 AM", "close": "4:00 PM"}],
            },
        }

    @pytest.mark.asyncio
    async def test_should_search_pantries_by_location_with_valid_auth(
        self, scraper, mock_pantry_response
    ):
        """Test searching pantries by location with valid authentication."""
        # Arrange
        scraper.auth_token = "valid-token"
        lat, lng, radius = 42.3601, -71.0589, 50

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"hits": {"hits": [mock_pantry_response]}}
        mock_response.raise_for_status = MagicMock()

        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.post = AsyncMock(return_value=mock_response)

            # Act
            pantries = await scraper.search_pantries_by_location(lat, lng, radius)

            # Assert
            assert len(pantries) == 1
            assert pantries[0]["id"] == "test-123"
            # Verify bounding box calculation
            mock_client.return_value.post.assert_called_once()
            call_args = mock_client.return_value.post.call_args
            payload = call_args.kwargs["json"]
            assert "top_left" in payload
            assert "bottom_right" in payload

    @pytest.mark.asyncio
    async def test_should_handle_auth_failure_in_geo_search(self, scraper):
        """Test handling of authentication failure in geo search."""
        # Arrange
        scraper.auth_token = "invalid-token"

        mock_response_401 = MagicMock(spec=Response)
        mock_response_401.status_code = 401
        mock_response_401.raise_for_status = MagicMock(
            side_effect=Exception("401 Unauthorized")
        )

        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.post = AsyncMock(return_value=mock_response_401)

            # Act
            pantries = await scraper.search_pantries_by_location(40.7128, -74.0060, 50)

            # Assert
            assert pantries == []  # Should return empty list on auth failure

    @pytest.mark.asyncio
    async def test_should_return_empty_list_on_search_error(self, scraper):
        """Test returning empty list when search encounters error."""
        # Arrange
        scraper.auth_token = "token"

        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.post = AsyncMock(
                side_effect=Exception("Network error")
            )

            # Act
            pantries = await scraper.search_pantries_by_location(40.7128, -74.0060, 50)

            # Assert
            assert pantries == []

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_no_auth_token(self, scraper):
        """Test returning empty list when no auth token available."""
        # Arrange
        scraper.auth_token = None

        # Act
        pantries = await scraper.search_pantries_by_location(40.7128, -74.0060, 50)

        # Assert
        assert pantries == []

    def test_should_have_configuration_constants(self, scraper):
        """Test that scraper has proper configuration constants."""
        # Assert
        assert hasattr(scraper, "DEFAULT_SEARCH_RADIUS_MILES")
        assert hasattr(scraper, "DEFAULT_OVERLAP_FACTOR")
        assert hasattr(scraper, "EARTH_RADIUS_MILES")
        assert hasattr(scraper, "REQUEST_TIMEOUT")
        assert scraper.DEFAULT_SEARCH_RADIUS_MILES == 50.0
        assert scraper.DEFAULT_OVERLAP_FACTOR == 0.30

    @pytest.mark.asyncio
    async def test_should_calculate_bounding_box_correctly(self, scraper):
        """Test correct bounding box calculation for different coordinates."""
        # Arrange
        scraper.auth_token = "test-token"
        lat, lng, radius = 40.7128, -74.0060, 50

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.post = AsyncMock(return_value=mock_response)

            # Act
            await scraper.search_pantries_by_location(lat, lng, radius)

            # Assert
            call_args = mock_client.return_value.post.call_args
            payload = call_args.kwargs["json"]

            # Check bounding box calculation
            expected_lat_offset = radius / scraper.EARTH_RADIUS_MILES
            assert abs((payload["top_left"][0] - lat) - expected_lat_offset) < 0.01
            assert abs((lat - payload["bottom_right"][0]) - expected_lat_offset) < 0.01

    @pytest.mark.asyncio
    async def test_should_handle_different_response_formats(self, scraper):
        """Test handling of different API response formats."""
        # Arrange
        scraper.auth_token = "token"

        # Test with list response
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"_id": "1", "_source": {"name": "Pantry 1"}}
        ]
        mock_response.raise_for_status = MagicMock()

        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.post = AsyncMock(return_value=mock_response)

            # Act
            pantries = await scraper.search_pantries_by_location(40.7128, -74.0060, 50)

            # Assert
            assert len(pantries) == 1
