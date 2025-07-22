"""Unit tests for GetFull.app API scraper."""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, Response

from app.scraper.getfull_app_api_scraper import Getfull_App_ApiScraper


class TestGetfullAppApiScraper:
    """Test suite for GetFull.app API scraper."""

    @pytest.fixture
    def scraper(self):
        """Create a scraper instance for testing."""
        return Getfull_App_ApiScraper()

    @pytest.fixture
    def mock_grid_points(self):
        """Mock grid points for testing."""
        mock_point = MagicMock()
        mock_point.name = "Test Location"
        mock_point.latitude = 40.7128
        mock_point.longitude = -74.0060
        return [mock_point]

    @pytest.fixture
    def mock_pantry_data(self):
        """Mock pantry data from API."""
        return {
            "id": "123",
            "name": "Test Food Pantry",
            "description": "A test pantry",
            "address": {
                "street": "123 Main St",
                "city": "New York",
                "state": "NY",
                "zip": "10001",
            },
            "phone": "555-1234",
            "website": "https://example.com",
            "email": "test@example.com",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "hours": [{"day": "Monday", "open": "9:00 AM", "close": "5:00 PM"}],
            "services": ["Food Pantry", "Meals"],
        }

    @pytest.mark.asyncio
    async def test_should_authenticate_successfully_when_valid_token_available(
        self, scraper
    ):
        """Test successful authentication token retrieval."""
        # Arrange
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "valid_token"}

        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.get = AsyncMock(return_value=mock_response)

            # Act
            token = await scraper.get_auth_token()

            # Assert
            assert token == "valid_token"

    @pytest.mark.asyncio
    async def test_should_return_none_when_auth_fails(self, scraper):
        """Test returning None when authentication fails."""
        # Arrange
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 401

        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.post = AsyncMock(return_value=mock_response)

            # Act
            token = await scraper.get_auth_token()

            # Assert
            assert token is None

    @pytest.mark.asyncio
    async def test_should_handle_auth_exception_gracefully(self, scraper):
        """Test graceful handling of authentication exceptions."""
        # Arrange
        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.get = AsyncMock(
                side_effect=Exception("Network error")
            )

            # Act
            token = await scraper.get_auth_token()

            # Assert
            assert token is None  # Returns None on error

    def test_should_create_proper_grid_when_search_radius_provided(
        self, scraper, mock_grid_points
    ):
        """Test grid creation with proper bounding boxes."""
        # Arrange
        with patch.object(
            scraper.utils, "get_us_grid_points", return_value=mock_grid_points
        ):

            # Act
            search_areas = scraper.create_search_grid()

            # Assert
            assert len(search_areas) == 1
            area = search_areas[0]
            assert area["name"] == "Test Location"
            assert area["center"] == [40.7128, -74.0060]
            assert "top_left" in area
            assert "bottom_right" in area
            # Verify bounding box calculation (50 miles radius)
            assert area["top_left"][0] > area["center"][0]  # North of center
            assert area["top_left"][1] < area["center"][1]  # West of center
            assert area["bottom_right"][0] < area["center"][0]  # South of center
            assert area["bottom_right"][1] > area["center"][1]  # East of center

    @pytest.mark.asyncio
    async def test_should_search_pantries_successfully_when_valid_bbox(
        self, scraper, mock_pantry_data
    ):
        """Test successful pantry search with bounding box."""
        # Arrange
        top_left = [40.8, -74.1]
        bottom_right = [40.6, -73.9]
        auth_token = "test_token"

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = [mock_pantry_data]
        mock_response.raise_for_status = MagicMock()

        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.post = AsyncMock(return_value=mock_response)

            # Act
            pantries = await scraper.search_pantries_by_bbox(
                top_left, bottom_right, auth_token
            )

            # Assert
            assert len(pantries) == 1
            assert pantries[0] == mock_pantry_data

    @pytest.mark.asyncio
    async def test_should_retry_without_auth_when_401_error(
        self, scraper, mock_pantry_data
    ):
        """Test retry without authentication on 401 error."""
        # Arrange
        top_left = [40.8, -74.1]
        bottom_right = [40.6, -73.9]
        auth_token = "invalid_token"

        mock_response_401 = MagicMock(spec=Response)
        mock_response_401.status_code = 401

        mock_response_success = MagicMock(spec=Response)
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = [mock_pantry_data]
        mock_response_success.raise_for_status = MagicMock()

        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.post = AsyncMock(
                side_effect=[mock_response_401, mock_response_success]
            )

            # Act
            pantries = await scraper.search_pantries_by_bbox(
                top_left, bottom_right, auth_token
            )

            # Assert
            assert len(pantries) == 1
            assert mock_client.return_value.post.call_count == 2

    @pytest.mark.asyncio
    async def test_should_handle_elasticsearch_response_format(
        self, scraper, mock_pantry_data
    ):
        """Test handling of Elasticsearch response format."""
        # Arrange
        es_response = {"hits": {"hits": [{"_id": "123", "_source": mock_pantry_data}]}}

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = es_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.post = AsyncMock(return_value=mock_response)

            # Act
            pantries = await scraper.search_pantries_by_bbox(
                [40.8, -74.1], [40.6, -73.9], "token"
            )

            # Assert
            assert len(pantries) == 1

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_search_fails(self, scraper):
        """Test returning empty list when search fails."""
        # Arrange
        with patch.object(AsyncClient, "__aenter__") as mock_client:
            mock_client.return_value.post = AsyncMock(
                side_effect=Exception("Network error")
            )

            # Act
            pantries = await scraper.search_pantries_by_bbox(
                [40.8, -74.1], [40.6, -73.9], "token"
            )

            # Assert
            assert pantries == []

    def test_should_transform_to_hsds_when_valid_pantry_data(
        self, scraper, mock_pantry_data
    ):
        """Test transformation of pantry data to HSDS format."""
        # Act
        hsds_data = scraper.transform_to_hsds(mock_pantry_data)

        # Assert
        assert hsds_data["id"] == "123"
        assert hsds_data["name"] == "Test Food Pantry"
        assert hsds_data["description"] == "A test pantry"
        assert hsds_data["email"] == "test@example.com"
        assert hsds_data["url"] == "https://example.com"
        assert hsds_data["status"] == "active"

        # Check address
        assert hsds_data["address"]["address_1"] == "123 Main St"
        assert hsds_data["address"]["city"] == "New York"
        assert hsds_data["address"]["state_province"] == "NY"
        assert hsds_data["address"]["postal_code"] == "10001"
        assert hsds_data["address"]["country"] == "US"

        # Check phone
        assert len(hsds_data["phones"]) == 1
        assert hsds_data["phones"][0]["number"] == "555-1234"
        assert hsds_data["phones"][0]["type"] == "voice"

        # Check location
        assert hsds_data["location"]["latitude"] == 40.7128
        assert hsds_data["location"]["longitude"] == -74.0060

        # Check schedule
        assert len(hsds_data["regular_schedule"]) == 1
        assert hsds_data["regular_schedule"][0]["weekday"] == "Monday"
        assert hsds_data["regular_schedule"][0]["opens_at"] == "9:00 AM"
        assert hsds_data["regular_schedule"][0]["closes_at"] == "5:00 PM"

    def test_should_handle_string_address_when_transforming(self, scraper):
        """Test handling string address format."""
        # Arrange
        pantry_data = {
            "id": "456",
            "name": "Test Pantry",
            "address": "789 Broadway, Brooklyn, NY 11211",
        }

        # Act
        hsds_data = scraper.transform_to_hsds(pantry_data)

        # Assert
        assert hsds_data["address"]["address_1"] == "789 Broadway"
        assert hsds_data["address"]["city"] == "Brooklyn"
        assert hsds_data["address"]["state_province"] == "NY"
        assert hsds_data["address"]["postal_code"] == "11211"

    def test_should_handle_missing_fields_gracefully(self, scraper):
        """Test graceful handling of missing fields."""
        # Arrange
        minimal_pantry = {"id": "789", "name": "Minimal Pantry"}

        # Act
        hsds_data = scraper.transform_to_hsds(minimal_pantry)

        # Assert
        assert hsds_data["id"] == "789"
        assert hsds_data["name"] == "Minimal Pantry"
        assert hsds_data["description"] == ""
        assert hsds_data["phones"] == []
        assert hsds_data["location"] == {}
        assert hsds_data["regular_schedule"] == []

    def test_should_handle_closed_pantry_status(self, scraper):
        """Test handling of closed pantry status."""
        # Arrange
        pantry_data = {"id": "999", "name": "Closed Pantry", "isClosed": True}

        # Act
        hsds_data = scraper.transform_to_hsds(pantry_data)

        # Assert
        assert hsds_data["status"] == "inactive"

    def test_should_convert_services_to_attributes(self, scraper):
        """Test conversion of services to service attributes."""
        # Arrange
        pantry_data = {
            "id": "111",
            "name": "Service Pantry",
            "services": ["Food Pantry", "Meals", "Groceries"],
        }

        # Act
        hsds_data = scraper.transform_to_hsds(pantry_data)

        # Assert
        assert "service_attributes" in hsds_data
        assert len(hsds_data["service_attributes"]) == 3
        for i, service in enumerate(["Food Pantry", "Meals", "Groceries"]):
            assert hsds_data["service_attributes"][i]["attribute_key"] == "service_type"
            assert hsds_data["service_attributes"][i]["attribute_value"] == service

    @pytest.mark.asyncio
    async def test_should_deduplicate_pantries_across_search_areas(
        self, scraper, mock_pantry_data
    ):
        """Test deduplication of pantries across multiple search areas."""
        # Arrange
        # Mock two search areas that return the same pantry
        mock_grid_points = []
        for i in range(2):
            point = MagicMock()
            point.name = f"Location {i}"
            point.latitude = 40.7128 + i * 0.1
            point.longitude = -74.0060
            mock_grid_points.append(point)

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = [mock_pantry_data]
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            scraper.utils, "get_us_grid_points", return_value=mock_grid_points
        ):
            with patch.object(scraper, "get_auth_token", return_value="test_token"):
                with patch.object(AsyncClient, "__aenter__") as mock_client:
                    mock_client.return_value.post = AsyncMock(
                        return_value=mock_response
                    )
                    with patch.object(
                        scraper, "submit_to_queue", return_value="job_123"
                    ) as mock_submit:

                        # Act
                        result = await scraper.scrape()

                        # Assert
                        # Should only submit one job despite two search areas returning same pantry
                        assert mock_submit.call_count == 1
                        summary = json.loads(result)
                        assert summary["unique_pantries"] == 1

    @pytest.mark.asyncio
    async def test_should_handle_invalid_coordinates_gracefully(self, scraper):
        """Test graceful handling of invalid coordinates."""
        # Arrange
        pantry_data = {
            "id": "bad-coords",
            "name": "Bad Coords Pantry",
            "latitude": "not-a-number",
            "longitude": None,
        }

        # Act
        hsds_data = scraper.transform_to_hsds(pantry_data)

        # Assert
        assert hsds_data["location"] == {}  # Empty location when coordinates invalid

    @pytest.mark.asyncio
    async def test_should_raise_error_when_no_auth_token_available(self, scraper):
        """Test that scraper raises error when no auth token is available."""
        # Arrange
        with patch.object(scraper, "get_auth_token", return_value=None):
            with patch.object(os, "getenv", return_value=None):

                # Act & Assert
                with pytest.raises(
                    RuntimeError, match="Could not obtain authentication token"
                ):
                    await scraper.scrape()

    def test_should_handle_alternative_hour_field_names(self, scraper):
        """Test handling of alternative field names for hours."""
        # Arrange
        pantry_data = {
            "id": "alt-hours",
            "name": "Alt Hours Pantry",
            "hours": [
                {"day": "Tuesday", "opens_at": "10:00 AM", "closes_at": "6:00 PM"}
            ],
        }

        # Act
        hsds_data = scraper.transform_to_hsds(pantry_data)

        # Assert
        assert len(hsds_data["regular_schedule"]) == 1
        assert hsds_data["regular_schedule"][0]["opens_at"] == "10:00 AM"
        assert hsds_data["regular_schedule"][0]["closes_at"] == "6:00 PM"
