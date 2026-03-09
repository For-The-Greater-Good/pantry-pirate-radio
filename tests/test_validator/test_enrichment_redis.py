"""Tests for geocoding enrichment caching, circuit breaker, and metrics."""

import json
import time
from unittest.mock import MagicMock, patch, call

import pytest
from unittest.mock import Mock

from app.validator.enrichment import GeocodingEnricher


class TestCacheBackend:
    """Test cache backend integration in GeocodingEnricher."""

    @patch("app.validator.enrichment.get_geocoding_cache_backend")
    def test_auto_detects_cache_backend(self, mock_factory):
        """Test cache backend is auto-detected when not provided."""
        mock_backend = MagicMock()
        mock_factory.return_value = mock_backend

        enricher = GeocodingEnricher()

        mock_factory.assert_called_once()
        assert enricher._cache is mock_backend

    def test_explicit_cache_backend(self):
        """Test explicit cache backend skips auto-detection."""
        mock_backend = MagicMock()

        enricher = GeocodingEnricher(cache_backend=mock_backend)

        assert enricher._cache is mock_backend

    @patch("app.validator.enrichment.get_geocoding_cache_backend")
    def test_no_cache_backend_available(self, mock_factory):
        """Test graceful handling when no cache backend is available."""
        mock_factory.return_value = None

        enricher = GeocodingEnricher()

        assert enricher._cache is None

    def test_cache_hit(self):
        """Test retrieving cached coordinates."""
        mock_backend = MagicMock()
        mock_backend.get.return_value = {"lat": 40.7128, "lon": -74.0060}

        enricher = GeocodingEnricher(cache_backend=mock_backend)
        coords = enricher._get_cached_coordinates("arcgis", "123 Main St")

        assert coords == (40.7128, -74.0060)
        mock_backend.get.assert_called_once()

    def test_cache_miss(self):
        """Test cache miss returns None."""
        mock_backend = MagicMock()
        mock_backend.get.return_value = None

        enricher = GeocodingEnricher(cache_backend=mock_backend)
        coords = enricher._get_cached_coordinates("arcgis", "123 Main St")

        assert coords is None

    def test_cache_storage(self):
        """Test storing coordinates in cache."""
        mock_backend = MagicMock()
        enricher = GeocodingEnricher(cache_backend=mock_backend)
        enricher.cache_ttl = 86400

        enricher._cache_coordinates("arcgis", "123 Main St", (40.7128, -74.0060))

        mock_backend.set.assert_called_once()
        call_args = mock_backend.set.call_args[0]
        assert call_args[1] == {"lat": 40.7128, "lon": -74.0060}
        assert call_args[2] == 86400

    def test_cache_disabled_get(self):
        """Test _get_cached_coordinates returns None when cache is None."""
        enricher = GeocodingEnricher(cache_backend=None)
        # Ensure _cache is actually None (factory may try to set it)
        enricher._cache = None

        coords = enricher._get_cached_coordinates("arcgis", "123 Main St")
        assert coords is None

    def test_cache_disabled_set(self):
        """Test _cache_coordinates is no-op when cache is None."""
        enricher = GeocodingEnricher(cache_backend=None)
        enricher._cache = None

        # Should not raise
        enricher._cache_coordinates("arcgis", "123 Main St", (40.7128, -74.0060))


class TestRetryLogic:
    """Test retry logic with exponential backoff."""

    @patch("app.validator.enrichment.time.sleep")
    def test_retry_on_timeout(self, mock_sleep):
        """Test retry logic on timeout errors."""
        mock_service = MagicMock()
        mock_service.geocode_with_provider.side_effect = [
            TimeoutError("Timeout"),
            TimeoutError("Timeout"),
            (40.7128, -74.0060),  # Success on third try
        ]
        mock_service.geocode.side_effect = [
            TimeoutError("Timeout"),
            TimeoutError("Timeout"),
            (40.7128, -74.0060),  # Success on third try
        ]

        enricher = GeocodingEnricher(
            geocoding_service=mock_service, cache_backend=MagicMock()
        )
        coords = enricher._geocode_with_retry("arcgis", "123 Main St", max_retries=3)

        assert coords == (40.7128, -74.0060)
        total_calls = (
            mock_service.geocode_with_provider.call_count
            + mock_service.geocode.call_count
        )
        assert total_calls == 3
        assert mock_sleep.call_count == 2

    def test_no_retry_on_no_result(self):
        """Test no retry when geocoding returns None (not found)."""
        mock_service = MagicMock()
        mock_service.geocode_with_provider.return_value = None
        mock_service.geocode.return_value = None

        enricher = GeocodingEnricher(
            geocoding_service=mock_service, cache_backend=MagicMock()
        )
        coords = enricher._geocode_with_retry("arcgis", "123 Main St", max_retries=3)

        assert coords is None
        total_calls = (
            mock_service.geocode_with_provider.call_count
            + mock_service.geocode.call_count
        )
        assert total_calls == 1

    @patch("app.validator.enrichment.time.sleep")
    def test_max_retries_exceeded(self, mock_sleep):
        """Test behavior when max retries are exceeded."""
        mock_service = MagicMock()
        mock_service.geocode_with_provider.side_effect = TimeoutError("Timeout")
        mock_service.geocode.side_effect = TimeoutError("Timeout")

        enricher = GeocodingEnricher(
            geocoding_service=mock_service, cache_backend=MagicMock()
        )
        coords = enricher._geocode_with_retry("arcgis", "123 Main St", max_retries=2)

        assert coords is None
        total_calls = (
            mock_service.geocode_with_provider.call_count
            + mock_service.geocode.call_count
        )
        assert total_calls == 2


class TestCircuitBreaker:
    """Test in-memory circuit breaker functionality."""

    def test_circuit_breaker_opens_after_threshold(self):
        """Test circuit breaker opens after failure threshold."""
        enricher = GeocodingEnricher(cache_backend=MagicMock())
        enricher.provider_config = {
            "arcgis": {"circuit_breaker_threshold": 3, "circuit_breaker_cooldown": 300}
        }

        # Record failures up to threshold
        enricher._record_circuit_failure("arcgis")
        enricher._record_circuit_failure("arcgis")
        assert not enricher._is_circuit_open("arcgis")

        enricher._record_circuit_failure("arcgis")
        assert enricher._is_circuit_open("arcgis")

    def test_circuit_breaker_check_when_open(self):
        """Test circuit breaker prevents calls when open."""
        enricher = GeocodingEnricher(cache_backend=MagicMock())

        # Manually open the circuit
        enricher._circuit_state["arcgis"] = {
            "state": "open",
            "cooldown_until": time.time() + 100,
            "failures": 0,
        }

        assert enricher._is_circuit_open("arcgis") is True

    def test_circuit_breaker_resets_after_cooldown(self):
        """Test circuit breaker resets after cooldown period."""
        enricher = GeocodingEnricher(cache_backend=MagicMock())

        # Manually open the circuit with expired cooldown
        enricher._circuit_state["arcgis"] = {
            "state": "open",
            "cooldown_until": time.time() - 100,
            "failures": 0,
        }

        assert enricher._is_circuit_open("arcgis") is False
        assert "arcgis" not in enricher._circuit_state

    def test_circuit_breaker_reset_on_success(self):
        """Test circuit breaker resets on successful call."""
        enricher = GeocodingEnricher(cache_backend=MagicMock())

        # Set some state
        enricher._circuit_state["arcgis"] = {"failures": 3}

        enricher._reset_circuit_breaker("arcgis")

        assert "arcgis" not in enricher._circuit_state

    def test_circuit_closed_by_default(self):
        """Test circuit is closed for unknown providers."""
        enricher = GeocodingEnricher(cache_backend=MagicMock())

        assert enricher._is_circuit_open("unknown_provider") is False


class TestMetrics:
    """Test in-memory metrics collection."""

    def test_cache_metrics_increment(self):
        """Test cache hit/miss metrics are incremented."""
        enricher = GeocodingEnricher(cache_backend=MagicMock())

        enricher._increment_cache_metric("hits")
        enricher._increment_cache_metric("hits")
        enricher._increment_cache_metric("misses")

        assert enricher._metrics["cache:hits"] == 2
        assert enricher._metrics["cache:misses"] == 1

    def test_provider_metrics_increment(self):
        """Test provider success/failure metrics are incremented."""
        enricher = GeocodingEnricher(cache_backend=MagicMock())

        enricher._increment_provider_metric("arcgis", "success")
        enricher._increment_provider_metric("arcgis", "success")
        enricher._increment_provider_metric("nominatim", "failure")

        assert enricher._metrics["arcgis:success"] == 2
        assert enricher._metrics["nominatim:failure"] == 1

    def test_enrichment_details_with_metrics(self):
        """Test enrichment details include in-memory metrics."""
        enricher = GeocodingEnricher(cache_backend=MagicMock())
        enricher.providers = ["arcgis", "nominatim"]
        enricher._enrichment_details = {"locations_enriched": 5}

        # Simulate some metrics
        enricher._metrics["cache:hits"] = 10
        enricher._metrics["cache:misses"] = 5
        enricher._metrics["arcgis:success"] = 8
        enricher._metrics["arcgis:failure"] = 2
        enricher._metrics["nominatim:success"] = 3
        enricher._metrics["nominatim:failure"] = 1

        details = enricher.get_enrichment_details()

        assert details["cache_metrics"]["hits"] == 10
        assert details["cache_metrics"]["misses"] == 5
        assert details["provider_metrics"]["arcgis"]["success"] == 8
        assert details["provider_metrics"]["arcgis"]["failure"] == 2
        assert details["provider_metrics"]["nominatim"]["success"] == 3
        assert details["provider_metrics"]["nominatim"]["failure"] == 1


class TestProviderConfig:
    """Test provider-specific configuration."""

    def test_provider_config_from_settings(self):
        """Test provider config is loaded from settings."""
        config = {"provider_config": {"arcgis": {"max_retries": 5, "timeout": 15}}}

        enricher = GeocodingEnricher(config=config, cache_backend=MagicMock())

        assert enricher.provider_config["arcgis"]["max_retries"] == 5
        assert enricher.provider_config["arcgis"]["timeout"] == 15

    def test_provider_specific_retry_count(self):
        """Test different retry counts per provider."""
        mock_service = MagicMock()
        mock_backend = MagicMock()
        mock_backend.get.return_value = None

        mock_service.geocode_with_provider.return_value = None
        mock_service.geocode.return_value = None

        enricher = GeocodingEnricher(
            geocoding_service=mock_service, cache_backend=mock_backend
        )
        enricher.provider_config = {
            "arcgis": {"max_retries": 3},
            "nominatim": {"max_retries": 2},
        }

        enricher._geocode_with_retry("arcgis", "123 Main St", 3)
        enricher._geocode_with_retry("nominatim", "123 Main St", 2)

        total_calls = (
            mock_service.geocode_with_provider.call_count
            + mock_service.geocode.call_count
        )
        assert total_calls >= 2


class TestIntegration:
    """Integration tests for the complete enrichment flow."""

    @patch("app.validator.enrichment.GeocodingService")
    @patch("app.validator.enrichment.get_geocoding_cache_backend")
    def test_full_enrichment_with_cache(self, mock_factory, mock_service_class):
        """Test complete enrichment flow with cache backend and metrics."""
        # Setup mocks
        mock_backend = MagicMock()
        mock_backend.get.return_value = None  # Cache miss
        mock_factory.return_value = mock_backend

        mock_service = MagicMock()
        mock_service.geocode_with_provider.return_value = (40.7128, -74.0060)
        mock_service.geocode.return_value = (40.7128, -74.0060)
        mock_service_class.return_value = mock_service

        enricher = GeocodingEnricher()
        location_data = {
            "name": "Test Location",
            "latitude": None,
            "longitude": None,
            "addresses": [
                {
                    "address_1": "123 Main St",
                    "city": "New York",
                    "state_province": "NY",
                    "postal_code": "10001",
                }
            ],
        }

        enriched, source = enricher.enrich_location(location_data)

        assert enriched["latitude"] == 40.7128
        assert enriched["longitude"] == -74.0060
        assert source == "arcgis"

        # Verify cache was updated
        mock_backend.set.assert_called_once()

        # Verify in-memory metrics were updated
        assert enricher._metrics["cache:misses"] >= 1
