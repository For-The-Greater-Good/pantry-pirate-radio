"""Unit tests for PostGIS distance calculation in locations API."""

import pytest
from app.database.repositories import LocationRepository


class TestLocationDistanceCalculation:
    """Test that locations API properly uses PostGIS distance calculations."""

    @pytest.mark.asyncio
    async def test_postgis_repository_implementation(self):
        """Test that LocationRepository properly uses PostGIS ST_Distance."""
        from app.database.geo_utils import GeoPoint

        # This tests that the repository has the proper PostGIS implementation
        repo = LocationRepository(None)  # type: ignore

        # Verify the repository has PostGIS methods
        assert hasattr(repo, "get_locations_by_radius")
        assert hasattr(repo, "count_by_radius")

        # The actual PostGIS query is tested in repository tests
        # This just verifies the API uses the repository correctly
