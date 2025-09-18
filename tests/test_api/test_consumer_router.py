"""Tests for consumer router API endpoints."""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.consumer.router import get_location_detail
from app.api.v1.consumer.models import SingleLocationResponse


class TestConsumerRouterAPI:
    """Test cases for consumer router API endpoints."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        return MagicMock(spec=Request)

    @pytest.mark.asyncio
    async def test_get_location_detail_not_found(self, mock_request, mock_session):
        """Test get location detail returns 404 when location not found."""
        location_id = uuid4()

        with patch(
            "app.api.v1.consumer.router.ConsumerLocationService"
        ) as mock_service_class:
            # Mock the service to return None (location not found)
            mock_service = MagicMock()
            mock_service.get_single_location = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            # Should raise HTTPException with 404
            with pytest.raises(HTTPException) as exc_info:
                await get_location_detail(
                    location_id=location_id,
                    request=mock_request,
                    include_nearby=False,
                    nearby_radius=500,
                    include_history=False,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == "Location not found"

            # Verify the service was called with correct parameters
            mock_service.get_single_location.assert_called_once_with(
                location_id=location_id,
                include_nearby=False,
                nearby_radius=500,
                include_history=False,
            )

    @pytest.mark.asyncio
    async def test_get_location_detail_success(self, mock_request, mock_session):
        """Test get location detail returns data when location found."""
        location_id = uuid4()

        # Mock location data that matches SingleLocationResponse model
        mock_location_data = {
            "location": {
                "id": str(location_id),
                "canonical": {
                    "name": "Test Location",
                    "coordinates": {
                        "lat": 40.7128,
                        "lng": -74.0060,
                        "geocoding_source": "google",
                        "confidence": 95,
                    },
                    "confidence": 85,
                },
                "sources": [],
            },
            "nearby_locations": [],
            "version_history": None,
        }

        with patch(
            "app.api.v1.consumer.router.ConsumerLocationService"
        ) as mock_service_class:
            # Mock the service to return location data
            mock_service = MagicMock()
            mock_service.get_single_location = AsyncMock(
                return_value=mock_location_data
            )
            mock_service_class.return_value = mock_service

            # Call the endpoint
            result = await get_location_detail(
                location_id=location_id,
                request=mock_request,
                include_nearby=True,
                nearby_radius=800,
                include_history=False,
                session=mock_session,
            )

            # Should return SingleLocationResponse
            assert isinstance(result, SingleLocationResponse)
            assert result.location.id == str(location_id)
            assert result.location.canonical.name == "Test Location"

    @pytest.mark.asyncio
    async def test_get_location_detail_with_custom_params(
        self, mock_request, mock_session
    ):
        """Test get location detail with custom parameters."""
        location_id = uuid4()

        with patch(
            "app.api.v1.consumer.router.ConsumerLocationService"
        ) as mock_service_class:
            # Mock the service
            mock_service = MagicMock()
            mock_service.get_single_location = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            # Should raise 404
            with pytest.raises(HTTPException):
                await get_location_detail(
                    location_id=location_id,
                    request=mock_request,
                    include_nearby=True,
                    nearby_radius=2000,
                    include_history=True,
                    session=mock_session,
                )

            # Verify the service was called with custom parameters
            mock_service.get_single_location.assert_called_once_with(
                location_id=location_id,
                include_nearby=True,
                nearby_radius=2000,
                include_history=True,
            )
