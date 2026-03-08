"""Tests for the unified geocoding service."""

import json
import os
from unittest.mock import MagicMock, Mock, patch

import pytest
from geopy.exc import GeocoderServiceError, GeocoderTimedOut

from app.core.geocoding import GeocodingService, get_geocoding_service
from app.core.geocoding.cache_backend import make_geocoding_cache_key


class TestGeocodingService:
    """Unit tests for GeocodingService."""

    @pytest.fixture
    def mock_cache(self):
        """Mock GeocodingCacheBackend."""
        with patch(
            "app.core.geocoding.service.get_geocoding_cache_backend"
        ) as mock_factory:
            cache_instance = MagicMock()
            cache_instance.get.return_value = None
            mock_factory.return_value = cache_instance
            yield cache_instance

    @pytest.fixture
    def mock_env(self, monkeypatch):
        """Set up test environment variables."""
        monkeypatch.setenv("GEOCODING_PROVIDER", "arcgis")
        monkeypatch.setenv("GEOCODING_CACHE_TTL", "3600")
        monkeypatch.setenv("GEOCODING_RATE_LIMIT", "0.1")
        monkeypatch.setenv("NOMINATIM_RATE_LIMIT", "0.1")
        monkeypatch.setenv("GEOCODING_ENABLE_FALLBACK", "true")
        monkeypatch.setenv("GEOCODING_MAX_RETRIES", "2")
        monkeypatch.setenv("GEOCODING_TIMEOUT", "5")

    def test_initialization_with_defaults(self, mock_env, mock_cache):
        """Test service initialization with default configuration."""
        service = GeocodingService()

        assert service.primary_provider == "arcgis"
        assert service.enable_fallback is True
        assert service.cache_ttl == 3600
        assert service.max_retries == 2
        assert service.timeout == 5
        assert service._cache is not None

    def test_initialization_with_arcgis_api_key(
        self, mock_env, mock_cache, monkeypatch
    ):
        """Test service initialization with ArcGIS API key."""
        monkeypatch.setenv("ARCGIS_API_KEY", "test_api_key_123")

        with patch("app.core.geocoding.providers.ArcGIS") as mock_arcgis:
            service = GeocodingService()

            # Verify ArcGIS was initialized
            mock_arcgis.assert_called_once_with(timeout=5)
            # Verify API key was stored
            assert service.arcgis_api_key == "test_api_key_123"

    def test_initialization_without_cache(self, mock_env):
        """Test service initialization when no cache backend is available."""
        with patch(
            "app.core.geocoding.service.get_geocoding_cache_backend"
        ) as mock_factory:
            mock_factory.return_value = None
            service = GeocodingService()
            assert service._cache is None

    def test_cache_key_generation(self, mock_env, mock_cache):
        """Test cache key generation via module-level helpers."""
        key1 = make_geocoding_cache_key("arcgis", "123 Main St")
        key2 = make_geocoding_cache_key("arcgis", "123 MAIN ST")
        key3 = make_geocoding_cache_key("nominatim", "123 Main St")

        # Same address (case insensitive) with same provider should give same key
        assert key1 == key2
        # Different provider should give different key
        assert key1 != key3
        # Key should start with expected prefix
        assert key1.startswith("geocode:arcgis:")

    def test_get_cached_result_hit(self, mock_env, mock_cache):
        """Test retrieving cached geocoding result."""
        service = GeocodingService()

        # Mock cache hit
        mock_cache.get.return_value = {"lat": 40.7128, "lon": -74.0060}

        result = service._get_cached_result("123 Main St", "arcgis")

        assert result == (40.7128, -74.0060)
        mock_cache.get.assert_called_once()

    def test_get_cached_result_miss(self, mock_env, mock_cache):
        """Test cache miss."""
        service = GeocodingService()

        # Mock cache miss
        mock_cache.get.return_value = None

        result = service._get_cached_result("123 Main St", "arcgis")

        assert result is None
        mock_cache.get.assert_called_once()

    def test_cache_result(self, mock_env, mock_cache):
        """Test caching geocoding result."""
        service = GeocodingService()

        service._cache_result("123 Main St", "arcgis", 40.7128, -74.0060)

        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args[0]
        assert call_args[1] == {"lat": 40.7128, "lon": -74.0060}
        assert call_args[2] == 3600  # TTL

    @patch("app.core.geocoding.providers.RateLimiter")
    def test_geocode_with_arcgis_success(self, mock_rate_limiter, mock_env, mock_cache):
        """Test successful geocoding with ArcGIS."""
        service = GeocodingService()

        # Mock successful geocoding
        mock_location = Mock()
        mock_location.latitude = 40.7128
        mock_location.longitude = -74.0060

        mock_geocoder = Mock(return_value=mock_location)
        mock_rate_limiter.return_value = mock_geocoder
        service.arcgis_geocode = mock_geocoder

        result = service._geocode_with_arcgis("123 Main St")

        assert result == (40.7128, -74.0060)
        mock_geocoder.assert_called_once_with("123 Main St")

    @patch("app.core.geocoding.providers.RateLimiter")
    def test_geocode_with_arcgis_failure(self, mock_rate_limiter, mock_env, mock_cache):
        """Test ArcGIS geocoding failure."""
        service = GeocodingService()

        # Mock geocoding failure
        mock_geocoder = Mock(side_effect=GeocoderTimedOut("Timeout"))
        mock_rate_limiter.return_value = mock_geocoder
        service.arcgis_geocode = mock_geocoder

        result = service._geocode_with_arcgis("123 Main St")

        assert result is None
        mock_geocoder.assert_called_once()

    @patch("app.core.geocoding.providers.RateLimiter")
    def test_geocode_with_nominatim_success(
        self, mock_rate_limiter, mock_env, mock_cache
    ):
        """Test successful geocoding with Nominatim."""
        service = GeocodingService()

        # Mock successful geocoding
        mock_location = Mock()
        mock_location.latitude = 40.7128
        mock_location.longitude = -74.0060

        mock_geocoder = Mock(return_value=mock_location)
        mock_rate_limiter.return_value = mock_geocoder
        service.nominatim_geocode = mock_geocoder

        result = service._geocode_with_nominatim("123 Main St")

        assert result == (40.7128, -74.0060)
        mock_geocoder.assert_called_once_with("123 Main St")

    def test_geocode_with_cache_hit(self, mock_env, mock_cache):
        """Test geocoding with cache hit (no API call)."""
        service = GeocodingService()

        # Mock cache hit (backend returns dict, not JSON string)
        mock_cache.get.return_value = {"lat": 40.7128, "lon": -74.0060}

        with patch.object(service, "_geocode_with_arcgis") as mock_arcgis:
            result = service.geocode("123 Main St")

            assert result == (40.7128, -74.0060)
            # Should not call geocoding API when cache hit
            mock_arcgis.assert_not_called()

    def test_geocode_with_fallback(self, mock_env, mock_cache):
        """Test geocoding with fallback to secondary provider."""
        service = GeocodingService()

        # Mock cache miss
        mock_cache.get.return_value = None

        with patch.object(service, "_geocode_with_arcgis") as mock_arcgis:
            with patch.object(service, "_geocode_with_nominatim") as mock_nominatim:
                # ArcGIS fails, Nominatim succeeds
                mock_arcgis.return_value = None
                mock_nominatim.return_value = (40.7128, -74.0060)

                result = service.geocode("123 Main St")

                assert result == (40.7128, -74.0060)
                mock_arcgis.assert_called_once()
                mock_nominatim.assert_called_once()

    def test_geocode_empty_address(self, mock_env, mock_cache):
        """Test geocoding with empty address."""
        service = GeocodingService()

        result = service.geocode("")
        assert result is None

        result = service.geocode("   ")
        assert result is None

    def test_geocode_force_provider(self, mock_env, mock_cache):
        """Test forcing specific provider."""
        service = GeocodingService()

        # Mock cache miss
        mock_cache.get.return_value = None

        with patch.object(service, "_geocode_with_nominatim") as mock_nominatim:
            mock_nominatim.return_value = (40.7128, -74.0060)

            # Force Nominatim even though ArcGIS is primary
            result = service.geocode("123 Main St", force_provider="nominatim")

            assert result == (40.7128, -74.0060)
            mock_nominatim.assert_called_once()

    def test_batch_geocode(self, mock_env, mock_cache):
        """Test batch geocoding."""
        service = GeocodingService()

        addresses = ["123 Main St", "456 Oak Ave", "", "789 Pine Rd"]  # Empty address

        with patch.object(service, "geocode") as mock_geocode:
            mock_geocode.side_effect = [
                (40.7128, -74.0060),
                (41.8781, -87.6298),
                None,
                (34.0522, -118.2437),
            ]

            results = service.batch_geocode(addresses)

            assert len(results) == 4
            assert results[0] == (40.7128, -74.0060)
            assert results[1] == (41.8781, -87.6298)
            assert results[2] is None
            assert results[3] == (34.0522, -118.2437)
            assert mock_geocode.call_count == 4

    def test_singleton_pattern(self, mock_env, mock_cache):
        """Test that get_geocoding_service returns singleton."""
        service1 = get_geocoding_service()
        service2 = get_geocoding_service()

        assert service1 is service2

    def test_geocode_address_backward_compatibility(self, mock_env, mock_cache):
        """Test geocode_address method for backward compatibility with scrapers."""
        service = GeocodingService()

        # Mock cache miss
        mock_cache.get.return_value = None

        with patch.object(service, "geocode") as mock_geocode:
            # Test with successful geocoding
            mock_geocode.return_value = (40.7128, -74.0060)

            result = service.geocode_address(
                "123 Main St", county="New York", state="NY"
            )

            assert result == (40.7128, -74.0060)
            # Should try variations
            assert mock_geocode.call_count >= 1

            # Test with failed geocoding
            mock_geocode.reset_mock()
            mock_geocode.return_value = None

            with pytest.raises(ValueError) as exc_info:
                service.geocode_address("Invalid Address", county="Fake", state="ZZ")

            assert "Could not geocode address" in str(exc_info.value)

    def test_geocode_address_with_landmarks(self, mock_env, mock_cache):
        """Test geocode_address handling of addresses with landmarks."""
        service = GeocodingService()

        with patch.object(service, "geocode") as mock_geocode:
            mock_geocode.return_value = (40.7128, -74.0060)

            # Test with parking lot address
            result = service.geocode_address(
                "123 Main Street parking lot", county="New York", state="NY"
            )

            assert result == (40.7128, -74.0060)
            # Should extract street address and try multiple variations
            calls = [call[0][0] for call in mock_geocode.call_args_list]
            assert any("123 Main Street" in call for call in calls)

    def test_get_default_coordinates_backward_compatibility(self, mock_env, mock_cache):
        """Test get_default_coordinates for backward compatibility."""
        service = GeocodingService()

        # Test US default
        lat, lon = service.get_default_coordinates("US", with_offset=False)
        assert lat == 39.8283
        assert lon == -98.5795

        # Test with offset (default offset_range is 0.01)
        lat_off, lon_off = service.get_default_coordinates("US", with_offset=True)
        # The offset is random.uniform(-0.01, 0.01), so the bounds should be:
        # lat: 39.8283 +/- 0.01 = [39.8183, 39.8383]
        # lon: -98.5795 +/- 0.01 = [-98.5895, -98.5695]
        assert 39.8183 <= lat_off <= 39.8383  # Within offset range (inclusive)
        assert -98.5895 <= lon_off <= -98.5695  # Within offset range (inclusive)

        # Test unknown location defaults to US
        lat, lon = service.get_default_coordinates("UNKNOWN", with_offset=False)
        assert lat == 39.8283
        assert lon == -98.5795


class TestGeocodingIntegration:
    """Integration tests for geocoding with real services (requires network)."""

    @pytest.mark.integration
    def test_real_arcgis_geocoding(self):
        """Test real ArcGIS geocoding (requires network)."""
        service = GeocodingService()

        # Well-known address
        result = service.geocode("1600 Pennsylvania Avenue NW, Washington, DC 20500")

        assert result is not None
        lat, lon = result
        # White House coordinates
        assert 38.8 < lat < 38.9
        assert -77.1 < lon < -77.0

    @pytest.mark.integration
    def test_real_nominatim_geocoding(self):
        """Test real Nominatim geocoding (requires network)."""
        import time

        service = GeocodingService()

        # Force Nominatim - this can fail due to rate limiting or network issues
        try:
            result = service.geocode(
                "350 Fifth Avenue, New York, NY 10118", force_provider="nominatim"
            )

            if result is None:
                # Skip test if Nominatim is unavailable rather than fail
                pytest.skip("Nominatim service unavailable or rate limited")

            lat, lon = result
            # Empire State Building coordinates - be flexible as different providers may have slight variations
            assert 40.7 < lat < 41.0  # Wider range for Nominatim
            assert -74.0 < lon < -73.8  # Wider range for Nominatim
        except Exception as e:
            # For network integration tests, skip rather than fail on service issues
            if "rate limit" in str(e).lower() or "connection" in str(e).lower():
                pytest.skip(f"Nominatim service issue: {e}")
            raise

    @pytest.mark.integration
    def test_real_fallback_behavior(self):
        """Test fallback from invalid provider to working one."""
        service = GeocodingService()

        # Temporarily break ArcGIS
        original_arcgis = service.arcgis_geocode
        service.arcgis_geocode = None

        try:
            # Should fallback to Nominatim
            result = service.geocode("1 Infinite Loop, Cupertino, CA 95014")

            assert result is not None
            lat, lon = result
            # Apple HQ coordinates
            assert 37.3 < lat < 37.4
            assert -122.1 < lon < -122.0
        finally:
            service.arcgis_geocode = original_arcgis
