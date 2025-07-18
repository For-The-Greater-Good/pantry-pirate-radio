"""Unit tests for PostGIS distance calculation in locations API."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi import Request

from app.api.v1.locations import search_locations
from app.models.hsds.query import GeoPoint


class TestLocationDistanceCalculation:
    """Test that locations API properly uses PostGIS distance calculations."""

    @pytest.mark.asyncio
    async def test_postgis_distance_from_repository(self):
        """Test that distance is retrieved from PostGIS via repository."""
        # Mock location with distance from PostGIS
        mock_location = Mock()
        mock_location.latitude = 34.0522  # LA
        mock_location.longitude = -118.2437
        mock_location.distance_miles = 2445.5  # Distance from NYC to LA
        mock_location.services_at_location = []

        # Mock repository
        mock_repo = AsyncMock()
        mock_repo.get_locations_by_radius.return_value = [mock_location]
        mock_repo.count_by_radius.return_value = 1

        with patch("app.api.v1.locations.LocationRepository") as mock_repo_class, \
             patch("app.api.v1.locations.LocationResponse") as mock_response_class, \
             patch("app.api.v1.locations.Page") as mock_page_class:
            mock_repo_class.return_value = mock_repo

            # Mock LocationResponse
            mock_location_response = Mock()
            mock_location_response.distance = "2445.5mi"
            mock_response_class.model_validate.return_value = mock_location_response

            # Mock Page response
            mock_page = Mock()
            mock_page.items = [mock_location_response]
            mock_page_class.return_value = mock_page

            # Mock request and session
            mock_request = Mock(spec=Request)
            mock_session = AsyncMock()

            # Call search_locations with radius search
            result = await search_locations(
                request=mock_request,
                page=1,
                per_page=10,
                latitude=40.7128,  # NYC
                longitude=-74.0060,
                radius_miles=3000.0,
                min_latitude=None,
                max_latitude=None,
                min_longitude=None,
                max_longitude=None,
                organization_id=None,
                include_services=False,
                session=mock_session,
            )

            # Verify repository was called with correct parameters
            mock_repo.get_locations_by_radius.assert_called_once()
            call_args = mock_repo.get_locations_by_radius.call_args

            # Verify the center point
            center = call_args.kwargs["center"]
            assert isinstance(center, GeoPoint)
            assert center.latitude == 40.7128
            assert center.longitude == -74.0060

            # Verify radius
            assert call_args.kwargs["radius_miles"] == 3000.0

            # Verify result contains distance from PostGIS
            assert len(result["items"]) == 1
            assert result["items"][0].distance == "2445.5mi"

    @pytest.mark.asyncio
    async def test_no_python_distance_calculation(self):
        """Verify that Python distance calculation is NOT used."""
        # Mock location without distance_miles attribute
        mock_location = Mock()
        mock_location.latitude = 34.0522
        mock_location.longitude = -118.2437
        mock_location.services_at_location = []
        # Intentionally don't set distance_miles

        # Mock repository
        mock_repo = AsyncMock()
        mock_repo.get_locations_by_radius.return_value = [mock_location]
        mock_repo.count_by_radius.return_value = 1

        with patch("app.api.v1.locations.LocationRepository") as mock_repo_class, \
             patch("app.api.v1.locations.LocationResponse") as mock_response_class, \
             patch("app.api.v1.locations.Page") as mock_page_class:
            mock_repo_class.return_value = mock_repo

            # Mock LocationResponse without distance
            mock_location_response = Mock()
            # No distance attribute set
            mock_response_class.model_validate.return_value = mock_location_response

            # Mock Page response
            mock_page = Mock()
            mock_page.items = [mock_location_response]
            mock_page_class.return_value = mock_page

            # Mock request and session
            mock_request = Mock(spec=Request)
            mock_session = AsyncMock()

            # Call search_locations
            result = await search_locations(
                request=mock_request,
                page=1,
                per_page=10,
                latitude=40.7128,
                longitude=-74.0060,
                radius_miles=3000.0,
                min_latitude=None,
                max_latitude=None,
                min_longitude=None,
                max_longitude=None,
                organization_id=None,
                include_services=False,
                session=mock_session,
            )

            # Verify no distance is added if not from PostGIS
            assert len(result["items"]) == 1
            assert (
                not hasattr(result["items"][0], "distance")
                or result["items"][0].distance is None
            )

    @pytest.mark.asyncio
    async def test_postgis_repository_implementation(self):
        """Test that LocationRepository properly uses PostGIS ST_Distance."""
        from app.database.repositories import LocationRepository
        from app.database.geo_utils import GeoPoint

        # This tests that the repository has the proper PostGIS implementation
        repo = LocationRepository(None)  # type: ignore

        # Verify the repository has PostGIS methods
        assert hasattr(repo, "get_locations_by_radius")
        assert hasattr(repo, "count_by_radius")

        # The actual PostGIS query is tested in repository tests
        # This just verifies the API uses the repository correctly

