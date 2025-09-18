"""Tests for the map search service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.map.search_service import MapSearchService, OutputFormat


class TestMapSearchService:
    """Test cases for MapSearchService."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = MagicMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def search_service(self, mock_session):
        """Create a MapSearchService instance with mock session."""
        return MapSearchService(mock_session)

    @pytest.mark.asyncio
    async def test_search_locations_basic(self, search_service, mock_session):
        """Test basic search without filters."""
        # Create a mock row that behaves like a database row with attributes
        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.lat = 40.7128
        mock_row.lng = -74.0060
        mock_row.location_name = "Test Location"
        mock_row.org_name = "Test Org"
        mock_row.website = "https://example.org"
        mock_row.email = "test@example.org"
        mock_row.description = "Test description"
        mock_row.address = "123 Main St, New York, NY 10001"
        mock_row.address_1 = "123 Main St"
        mock_row.address_2 = None
        mock_row.city = "New York"
        mock_row.state = "NY"
        mock_row.zip = "10001"
        mock_row.phone = "555-1234"
        mock_row.services = "Food Pantry"
        mock_row.languages = "English,Spanish"
        mock_row.opens_at = "09:00"
        mock_row.closes_at = "17:00"
        mock_row.byday = "MO,TU,WE,TH,FR"
        mock_row.schedule_description = "Open weekdays"
        mock_row.confidence_score = 85
        mock_row.validation_status = "validated"
        mock_row.geocoding_source = "google"
        mock_row.location_type = "physical"
        mock_row.source_count = 2

        # Mock the database response - ensure fetchall() is properly configured
        mock_result = MagicMock()
        # Make sure fetchall is a method that returns the list
        mock_result.fetchall = MagicMock(return_value=[mock_row])

        # Fix mock_result to return scalar properly for count
        count_result = MagicMock()
        count_result.scalar.return_value = 1

        # Mock for sources query (when in FULL format, it queries sources)
        sources_result = MagicMock()
        sources_result.fetchall.return_value = []  # No sources for simplicity

        # Mock execute to return appropriate results
        mock_session.execute = AsyncMock()
        # Configure execute to return the right result based on call count
        mock_session.execute.side_effect = [count_result, mock_result, sources_result]

        # Call the search method
        locations, metadata, total = await search_service.search_locations(
            limit=10, offset=0
        )

        # Verify results
        assert len(locations) == 1
        assert locations[0]["name"] == "Test Location"
        assert total == 1
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_search_locations_with_query(self, search_service, mock_session):
        """Test search with text query."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        # Fix mock_result to return scalar properly
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        # Mock execute to return different results for count and main query
        async def mock_execute_side_effect(*args, **kwargs):
            if "COUNT" in str(args[0]):
                return count_result
            return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute_side_effect)

        # Search with query
        locations, metadata, total = await search_service.search_locations(
            query="food bank", limit=10, offset=0
        )

        # Verify the query parameter was used
        assert len(locations) == 0
        assert total == 0
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_search_locations_compact_format(self, search_service, mock_session):
        """Test search with compact output format."""
        # Create a mock row
        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.lat = 40.7128
        mock_row.lng = -74.0060
        mock_row.location_name = "Test Location"
        mock_row.org_name = "Test Org"
        mock_row.confidence_score = 85

        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[mock_row])

        # Fix mock_result to return scalar properly
        count_result = MagicMock()
        count_result.scalar.return_value = 1

        # Mock execute to return appropriate results
        mock_session.execute = AsyncMock()
        # Configure execute to return the right result based on call count
        mock_session.execute.side_effect = [count_result, mock_result]

        # Search with compact format
        locations, metadata, total = await search_service.search_locations(
            output_format=OutputFormat.COMPACT, limit=10, offset=0
        )

        assert len(locations) == 1
        assert total == 1
        # Compact format should have fewer fields
        assert "name" in locations[0]
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_search_locations_geojson_format(self, search_service, mock_session):
        """Test search with GeoJSON output format."""
        # Create a mock row
        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.lat = 40.7128
        mock_row.lng = -74.0060
        mock_row.location_name = "Test Location"
        mock_row.org_name = "Test Org"
        mock_row.address = "123 Main St"
        mock_row.city = "New York"
        mock_row.state = "NY"
        mock_row.services = "Food Pantry"
        mock_row.confidence_score = 85

        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[mock_row])

        # Fix mock_result to return scalar properly
        count_result = MagicMock()
        count_result.scalar.return_value = 1

        # Mock execute to return appropriate results
        # GeoJSON format might query for sources too
        sources_result = MagicMock()
        sources_result.fetchall.return_value = []

        mock_session.execute = AsyncMock()
        # Configure execute to return the right result based on call count
        mock_session.execute.side_effect = [count_result, mock_result, sources_result]

        # Search with GeoJSON format
        locations, metadata, total = await search_service.search_locations(
            output_format=OutputFormat.GEOJSON, limit=10, offset=0
        )

        assert len(locations) == 1
        assert total == 1
        # GeoJSON format returns a FeatureCollection with features inside
        assert "type" in locations[0]
        assert locations[0]["type"] == "FeatureCollection"
        assert "features" in locations[0]
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_search_locations_with_filters(self, search_service, mock_session):
        """Test search with various filters."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        # Fix mock_result to return scalar properly
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        # Mock execute to return different results for count and main query
        async def mock_execute_side_effect(*args, **kwargs):
            if "COUNT" in str(args[0]):
                return count_result
            return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute_side_effect)

        # Search with multiple filters
        locations, metadata, total = await search_service.search_locations(
            query="food",
            state="NY",
            services=["pantry"],
            confidence_min=70,
            validation_status="validated",
            has_multiple_sources=True,
            output_format=OutputFormat.COMPACT,
            limit=50,
            offset=0,
        )

        assert len(locations) == 0
        assert total == 0
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_search_locations_with_pagination(self, search_service, mock_session):
        """Test search with pagination."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        # Fix mock_result to return scalar properly
        count_result = MagicMock()
        count_result.scalar.return_value = 100

        # Mock execute to return different results for count and main query
        async def mock_execute_side_effect(*args, **kwargs):
            if "COUNT" in str(args[0]):
                return count_result
            return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute_side_effect)

        # Search with pagination
        locations, metadata, total = await search_service.search_locations(
            limit=20, offset=40
        )

        assert len(locations) == 0
        assert total == 100
        assert mock_session.execute.called

    def test_output_format_enum(self):
        """Test OutputFormat enum values."""
        assert OutputFormat.FULL == "full"
        assert OutputFormat.COMPACT == "compact"
        assert OutputFormat.GEOJSON == "geojson"
        assert OutputFormat.FULL.value == "full"
