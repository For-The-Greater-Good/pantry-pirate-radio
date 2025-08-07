"""Test GeocoderUtils integration with GeocodingService."""

import pytest
from unittest.mock import patch, MagicMock

from app.scraper.utils import GeocoderUtils


class TestGeocoderUtilsIntegration:
    """Test GeocoderUtils backward compatibility wrapper."""

    @patch("app.core.geocoding.get_geocoding_service")
    def test_geocoder_utils_uses_unified_service(self, mock_get_service):
        """Test that GeocoderUtils delegates to unified GeocodingService."""
        # Mock the geocoding service
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        # Create GeocoderUtils instance
        geocoder = GeocoderUtils(
            timeout=15,  # These params should be ignored
            max_retries=5,
        )

        # Verify it got the singleton service
        mock_get_service.assert_called_once()
        assert geocoder.geocoding_service == mock_service

    @patch("app.core.geocoding.get_geocoding_service")
    def test_geocode_address_delegation(self, mock_get_service):
        """Test geocode_address method delegates to service."""
        # Mock the geocoding service
        mock_service = MagicMock()
        mock_service.geocode_address.return_value = (40.7128, -74.0060)
        mock_get_service.return_value = mock_service

        # Create GeocoderUtils and geocode address
        geocoder = GeocoderUtils()
        result = geocoder.geocode_address("123 Main St", county="New York", state="NY")

        # Verify delegation
        assert result == (40.7128, -74.0060)
        mock_service.geocode_address.assert_called_once_with(
            "123 Main St", "New York", "NY"
        )

    @patch("app.core.geocoding.get_geocoding_service")
    def test_get_default_coordinates_with_custom(self, mock_get_service):
        """Test get_default_coordinates with custom coordinates."""
        # Mock the geocoding service
        mock_service = MagicMock()
        mock_service.get_default_coordinates.return_value = (39.8283, -98.5795)
        mock_get_service.return_value = mock_service

        # Create GeocoderUtils with custom defaults
        custom_coords = {"TEST": (50.0, -100.0)}
        geocoder = GeocoderUtils(default_coordinates=custom_coords)

        # Test custom location (without offset)
        result = geocoder.get_default_coordinates("TEST", with_offset=False)
        assert result == (50.0, -100.0)

        # Test custom location with offset
        result_with_offset = geocoder.get_default_coordinates("TEST", with_offset=True)
        # Should be close to original but with small offset
        assert 49.99 < result_with_offset[0] < 50.01
        assert -100.01 < result_with_offset[1] < -99.99

        # Test fallback to service for unknown location
        result_fallback = geocoder.get_default_coordinates("UNKNOWN", with_offset=False)
        assert result_fallback == (39.8283, -98.5795)
        mock_service.get_default_coordinates.assert_called_once_with(
            "UNKNOWN", False, 0.01
        )

    @patch("app.core.geocoding.get_geocoding_service")
    def test_get_default_coordinates_without_custom(self, mock_get_service):
        """Test get_default_coordinates without custom coordinates."""
        # Mock the geocoding service
        mock_service = MagicMock()
        mock_service.get_default_coordinates.return_value = (39.8283, -98.5795)
        mock_get_service.return_value = mock_service

        # Create GeocoderUtils without custom defaults
        geocoder = GeocoderUtils()

        # Should always delegate to service
        result = geocoder.get_default_coordinates("US", with_offset=True)
        assert result == (39.8283, -98.5795)
        mock_service.get_default_coordinates.assert_called_once_with("US", True, 0.01)
