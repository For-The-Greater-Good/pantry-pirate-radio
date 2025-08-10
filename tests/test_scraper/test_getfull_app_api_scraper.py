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
        mock_response.headers = {"Set-Cookie": "token=test-token-123"}
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

    def test_should_pass_through_pantry_data_unchanged(
        self, scraper, mock_pantry_data
    ):
        """Test that pantry data passes through unchanged for LLM processing."""
        # Act
        result_data = scraper.transform_to_hsds(mock_pantry_data)

        # Assert - data should be unchanged
        assert result_data == mock_pantry_data
        assert result_data["id"] == "123"
        assert result_data["name"] == "Test Food Pantry"
        assert result_data["description"] == "A test pantry"
        assert result_data["email"] == "test@example.com"
        assert result_data["website"] == "https://example.com"
        assert result_data["phone"] == "555-1234"
        assert result_data["latitude"] == 40.7128
        assert result_data["longitude"] == -74.0060

    def test_should_pass_through_any_data_format(self, scraper):
        """Test that any data format passes through unchanged."""
        # Arrange
        pantry_data = {
            "id": "456",
            "name": "Test Pantry",
            "address1": "789 Broadway",
            "city": "Brooklyn",
            "state": "NY",
            "zip": "11211",
        }

        # Act
        result_data = scraper.transform_to_hsds(pantry_data)

        # Assert - data should be unchanged
        assert result_data == pantry_data

    def test_should_handle_minimal_data(self, scraper):
        """Test handling of minimal data."""
        # Arrange
        minimal_pantry = {"id": "789", "name": "Minimal Pantry"}

        # Act
        result_data = scraper.transform_to_hsds(minimal_pantry)

        # Assert - data should be unchanged
        assert result_data == minimal_pantry
        assert result_data["id"] == "789"
        assert result_data["name"] == "Minimal Pantry"

    def test_should_preserve_status_fields(self, scraper):
        """Test preservation of status fields."""
        # Arrange
        pantry_data = {"id": "999", "name": "Active Pantry", "active": True, "claimed": True}

        # Act
        result_data = scraper.transform_to_hsds(pantry_data)

        # Assert - data should be unchanged
        assert result_data == pantry_data
        assert result_data["active"] == True
        assert result_data["claimed"] == True

    def test_should_preserve_all_service_fields(self, scraper):
        """Test preservation of all service-related fields."""
        # Arrange
        pantry_data = {
            "id": "111",
            "name": "Service Pantry",
            "services": ["1-Groceries", "2-Meals"],
            "tags": ["family-friendly", "no-id-required"],
            "online_order": True,
            "delivery": False,
            "pickup": True,
            "walkup": False,
        }

        # Act
        result_data = scraper.transform_to_hsds(pantry_data)

        # Assert - all fields should be preserved
        assert result_data == pantry_data
        assert result_data["services"] == ["1-Groceries", "2-Meals"]
        assert result_data["tags"] == ["family-friendly", "no-id-required"]
        assert result_data["online_order"] == True
        assert result_data["delivery"] == False

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
    async def test_should_preserve_all_coordinate_formats(self, scraper):
        """Test preservation of coordinate data regardless of format."""
        # Arrange
        pantry_data = {
            "id": "coords-test",
            "name": "Coords Test Pantry",
            "lat": 45.5,
            "lng": -122.6,
        }

        # Act
        result_data = scraper.transform_to_hsds(pantry_data)

        # Assert - data should be unchanged
        assert result_data == pantry_data
        assert result_data["lat"] == 45.5
        assert result_data["lng"] == -122.6

    @pytest.mark.asyncio
    async def test_should_continue_without_auth_when_no_token_available(self, scraper):
        """Test that scraper continues without auth when no token is available."""
        # Arrange
        mock_grid_point = MagicMock()
        mock_grid_point.name = "Test Location"
        mock_grid_point.latitude = 40.7128
        mock_grid_point.longitude = -74.0060

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch.object(scraper, "get_auth_token", return_value=None):
            with patch.object(os, "getenv", return_value=None):
                with patch.object(
                    scraper.utils, "get_us_grid_points", return_value=[mock_grid_point]
                ):
                    with patch.object(AsyncClient, "__aenter__") as mock_client:
                        mock_client.return_value.post = AsyncMock(
                            return_value=mock_response
                        )

                        # Act - should not raise error
                        result = await scraper.scrape()

                        # Assert
                        assert result is not None
                        summary = json.loads(result)
                        assert summary["total_search_areas"] == 1
                        assert summary["total_pantries_found"] == 0
                        assert summary["jobs_created"] == 0

    def test_should_preserve_hours_data_format(self, scraper):
        """Test preservation of hours data in API format."""
        # Arrange
        pantry_data = {
            "id": "hours-test",
            "name": "Hours Test Pantry",
            "days": ["Monday", "Friday"],
            "hours": {
                "monday": "09:00 - 17:00",
                "friday": "10:00 - 14:00"
            },
            "availability_notes": "Call ahead for holiday hours",
        }

        # Act
        result_data = scraper.transform_to_hsds(pantry_data)

        # Assert - all fields should be preserved
        assert result_data == pantry_data
        assert result_data["hours"] == {"monday": "09:00 - 17:00", "friday": "10:00 - 14:00"}
        assert result_data["days"] == ["Monday", "Friday"]
        assert result_data["availability_notes"] == "Call ahead for holiday hours"
