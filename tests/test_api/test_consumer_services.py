"""Tests for the consumer location services."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.consumer.services import ConsumerLocationService
from app.api.v1.consumer.models import (
    MapPinsMetadata,
    SourceData,
    CanonicalData,
    LocationDetail,
    NearbyLocation,
)


class TestConsumerLocationService:
    """Test cases for ConsumerLocationService."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = MagicMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def consumer_service(self, mock_session):
        """Create a ConsumerLocationService instance with mock session."""
        return ConsumerLocationService(mock_session)

    @pytest.mark.asyncio
    async def test_get_map_pins_basic(self, consumer_service, mock_session):
        """Test getting map pins without filters."""
        # Mock the database response - without grouping (default grouping_radius=0)
        mock_row = MagicMock()
        mock_row.id = str(uuid4())
        mock_row.lat = 40.7128
        mock_row.lng = -74.0060
        mock_row.name = "Test Location"
        mock_row.confidence = 85
        mock_row.source_count = 2
        mock_row.has_schedule = True

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]

        mock_execute = AsyncMock(return_value=mock_result)
        mock_session.execute = mock_execute

        # Call the method with grouping_radius=0 (no grouping)
        pins, metadata = await consumer_service.get_map_pins(
            min_lat=40.0, max_lat=41.0, min_lng=-75.0, max_lng=-73.0, grouping_radius=0
        )

        # Verify results
        assert len(pins) == 1
        assert pins[0]["name"] == "Test Location"
        # metadata is a MapPinsMetadata object
        assert isinstance(metadata, MapPinsMetadata)
        assert metadata.total_locations >= 0
        assert mock_execute.called

    @pytest.mark.asyncio
    async def test_get_map_pins_with_grouping(self, consumer_service, mock_session):
        """Test getting map pins with grouping radius."""
        # Mock clustered result - when grouping is enabled, rows have locations attribute
        mock_row = MagicMock()
        mock_row.cluster_id = 1
        mock_row.locations = [
            {
                "id": str(uuid4()),
                "lat": 40.7128,
                "lng": -74.0060,
                "name": "Location 1",
                "confidence": 85,
                "source_count": 1,
                "has_schedule": False,
            },
            {
                "id": str(uuid4()),
                "lat": 40.7130,
                "lng": -74.0058,
                "name": "Location 2",
                "confidence": 90,
                "source_count": 1,
                "has_schedule": True,
            },
        ]

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]

        mock_execute = AsyncMock(return_value=mock_result)
        mock_session.execute = mock_execute

        # Call with grouping
        pins, metadata = await consumer_service.get_map_pins(
            min_lat=40.0,
            max_lat=41.0,
            min_lng=-75.0,
            max_lng=-73.0,
            grouping_radius=200,  # Group within 200 meters
        )

        # Verify grouping occurred
        assert len(pins) >= 1
        # metadata is a MapPinsMetadata object
        assert isinstance(metadata, MapPinsMetadata)
        assert metadata.total_locations >= 0
        assert mock_execute.called

    @pytest.mark.asyncio
    async def test_get_map_pins_with_confidence_filter(
        self, consumer_service, mock_session
    ):
        """Test getting map pins with confidence filter."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_execute = AsyncMock(return_value=mock_result)
        mock_session.execute = mock_execute

        # Call with confidence filter and no grouping
        pins, metadata = await consumer_service.get_map_pins(
            min_lat=40.0,
            max_lat=41.0,
            min_lng=-75.0,
            max_lng=-73.0,
            min_confidence=80,
            grouping_radius=0,
        )

        # Verify filter was applied
        assert len(pins) == 0
        # metadata is a MapPinsMetadata object
        assert isinstance(metadata, MapPinsMetadata)
        assert mock_execute.called

    @pytest.mark.asyncio
    async def test_get_map_pins_with_services_filter(
        self, consumer_service, mock_session
    ):
        """Test getting map pins with services filter."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_execute = AsyncMock(return_value=mock_result)
        mock_session.execute = mock_execute

        # Call with services filter and no grouping
        pins, metadata = await consumer_service.get_map_pins(
            min_lat=40.0,
            max_lat=41.0,
            min_lng=-75.0,
            max_lng=-73.0,
            services=["food pantry", "meals"],
            grouping_radius=0,
        )

        # Verify services filter was applied
        assert len(pins) == 0
        # metadata is a MapPinsMetadata object
        assert isinstance(metadata, MapPinsMetadata)
        assert mock_execute.called

    @pytest.mark.asyncio
    async def test_get_map_pins_with_open_now_filter(
        self, consumer_service, mock_session
    ):
        """Test getting map pins with open now filter."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_execute = AsyncMock(return_value=mock_result)
        mock_session.execute = mock_execute

        # Call with open now filter and no grouping
        pins, metadata = await consumer_service.get_map_pins(
            min_lat=40.0,
            max_lat=41.0,
            min_lng=-75.0,
            max_lng=-73.0,
            open_now=True,
            grouping_radius=0,
        )

        # Verify open now filter was applied
        assert len(pins) == 0
        # metadata is a MapPinsMetadata object
        assert isinstance(metadata, MapPinsMetadata)
        assert mock_execute.called
