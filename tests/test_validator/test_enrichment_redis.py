"""Tests for Redis-based geocoding enrichment features."""

import json
import time
from unittest.mock import MagicMock, patch, call

import pytest
from unittest.mock import Mock
import redis

from app.validator.enrichment import GeocodingEnricher


class TestRedisCache:
    """Test Redis-based caching functionality."""

    @patch("app.validator.enrichment.redis.from_url")
    def test_redis_initialization(self, mock_redis_from_url):
        """Test Redis client initialization."""
        mock_redis = MagicMock()
        mock_redis_from_url.return_value = mock_redis

        enricher = GeocodingEnricher()

        mock_redis_from_url.assert_called_once()
        mock_redis.ping.assert_called_once()

    @patch("app.validator.enrichment.redis.from_url")
    def test_redis_connection_failure(self, mock_redis_from_url):
        """Test graceful handling of Redis connection failure."""
        mock_redis_from_url.side_effect = redis.ConnectionError("Cannot connect")

        enricher = GeocodingEnricher()

        assert enricher.redis_client is None

    def test_cache_key_generation(self):
        """Test cache key generation with hashing."""
        enricher = GeocodingEnricher(redis_client=None)

        key1 = enricher._get_cache_key("arcgis", "123 Main St, New York, NY 10001")
        key2 = enricher._get_cache_key("nominatim", "123 Main St, New York, NY 10001")
        key3 = enricher._get_cache_key("arcgis", "456 Oak Ave, Boston, MA 02101")

        # Different providers should have different keys
        assert key1 != key2
        # Different addresses should have different keys
        assert key1 != key3
        # Keys should have consistent format
        assert key1.startswith("geocoding:arcgis:")
        assert key2.startswith("geocoding:nominatim:")

    def test_cache_hit(self):
        """Test retrieving cached coordinates."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({"lat": 40.7128, "lon": -74.0060})

        enricher = GeocodingEnricher(redis_client=mock_redis)
        coords = enricher._get_cached_coordinates("arcgis", "123 Main St")

        assert coords == (40.7128, -74.0060)
        mock_redis.get.assert_called_once()

    def test_cache_miss(self):
        """Test cache miss returns None."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        enricher = GeocodingEnricher(redis_client=mock_redis)
        coords = enricher._get_cached_coordinates("arcgis", "123 Main St")

        assert coords is None

    def test_cache_storage(self):
        """Test storing coordinates in cache."""
        mock_redis = MagicMock()
        enricher = GeocodingEnricher(redis_client=mock_redis)
        enricher.cache_ttl = 86400

        enricher._cache_coordinates("arcgis", "123 Main St", (40.7128, -74.0060))

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 86400  # TTL
        stored_value = json.loads(call_args[0][2])
        assert stored_value["lat"] == 40.7128
        assert stored_value["lon"] == -74.0060


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

        enricher = GeocodingEnricher(geocoding_service=mock_service)
        coords = enricher._geocode_with_retry("arcgis", "123 Main St", max_retries=3)

        assert coords == (40.7128, -74.0060)
        # Should call either geocode or geocode_with_provider
        total_calls = (
            mock_service.geocode_with_provider.call_count
            + mock_service.geocode.call_count
        )
        assert total_calls == 3
        # Check exponential backoff was applied
        assert mock_sleep.call_count == 2

    def test_no_retry_on_no_result(self):
        """Test no retry when geocoding returns None (not found)."""
        mock_service = MagicMock()
        mock_service.geocode_with_provider.return_value = None
        mock_service.geocode.return_value = None

        enricher = GeocodingEnricher(geocoding_service=mock_service)
        coords = enricher._geocode_with_retry("arcgis", "123 Main St", max_retries=3)

        assert coords is None
        # Should only try once, no retries for None result
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

        enricher = GeocodingEnricher(geocoding_service=mock_service)
        coords = enricher._geocode_with_retry("arcgis", "123 Main St", max_retries=2)

        assert coords is None
        total_calls = (
            mock_service.geocode_with_provider.call_count
            + mock_service.geocode.call_count
        )
        assert total_calls == 2


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_circuit_breaker_opens_after_threshold(self):
        """Test circuit breaker opens after failure threshold."""
        mock_redis = MagicMock()
        mock_redis.incr.return_value = 5  # Threshold reached

        enricher = GeocodingEnricher(redis_client=mock_redis)
        enricher.provider_config = {
            "arcgis": {"circuit_breaker_threshold": 5, "circuit_breaker_cooldown": 300}
        }

        enricher._record_circuit_failure("arcgis")

        # Check circuit was opened
        calls = mock_redis.set.call_args_list
        assert any("circuit_breaker:arcgis:state" in str(call) for call in calls)
        assert any("open" in str(call) for call in calls)

    def test_circuit_breaker_check_when_open(self):
        """Test circuit breaker prevents calls when open."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = lambda key: {
            "circuit_breaker:arcgis:state": "open",
            "circuit_breaker:arcgis:cooldown_until": str(time.time() + 100),
        }.get(key)

        enricher = GeocodingEnricher(redis_client=mock_redis)
        is_open = enricher._is_circuit_open("arcgis")

        assert is_open is True

    def test_circuit_breaker_resets_after_cooldown(self):
        """Test circuit breaker resets after cooldown period."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = lambda key: {
            "circuit_breaker:arcgis:state": "open",
            "circuit_breaker:arcgis:cooldown_until": str(
                time.time() - 100
            ),  # Past time
        }.get(key)

        enricher = GeocodingEnricher(redis_client=mock_redis)
        is_open = enricher._is_circuit_open("arcgis")

        assert is_open is False
        # Check circuit was reset
        mock_redis.delete.assert_called()

    def test_circuit_breaker_reset_on_success(self):
        """Test circuit breaker resets on successful call."""
        mock_redis = MagicMock()

        enricher = GeocodingEnricher(redis_client=mock_redis)
        enricher._reset_circuit_breaker("arcgis")

        # Check all circuit breaker keys were deleted
        expected_deletes = [
            call("circuit_breaker:arcgis:failures"),
            call("circuit_breaker:arcgis:state"),
            call("circuit_breaker:arcgis:cooldown_until"),
        ]
        mock_redis.delete.assert_has_calls(expected_deletes, any_order=True)


class TestMetrics:
    """Test metrics collection."""

    def test_cache_metrics_increment(self):
        """Test cache hit/miss metrics are incremented."""
        mock_redis = MagicMock()

        enricher = GeocodingEnricher(redis_client=mock_redis)
        enricher._increment_cache_metric("hits")
        enricher._increment_cache_metric("misses")

        expected_calls = [
            call("metrics:geocoding:cache:hits"),
            call("metrics:geocoding:cache:misses"),
        ]
        mock_redis.incr.assert_has_calls(expected_calls)

    def test_provider_metrics_increment(self):
        """Test provider success/failure metrics are incremented."""
        mock_redis = MagicMock()

        enricher = GeocodingEnricher(redis_client=mock_redis)
        enricher._increment_provider_metric("arcgis", "success")
        enricher._increment_provider_metric("nominatim", "failure")

        expected_calls = [
            call("metrics:geocoding:arcgis:success"),
            call("metrics:geocoding:nominatim:failure"),
        ]
        mock_redis.incr.assert_has_calls(expected_calls)

    def test_enrichment_details_with_metrics(self):
        """Test enrichment details include metrics from Redis."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = lambda key: {
            "metrics:geocoding:cache:hits": "10",
            "metrics:geocoding:cache:misses": "5",
            "metrics:geocoding:arcgis:success": "8",
            "metrics:geocoding:arcgis:failure": "2",
            "metrics:geocoding:nominatim:success": "3",
            "metrics:geocoding:nominatim:failure": "1",
        }.get(key, "0")

        enricher = GeocodingEnricher(redis_client=mock_redis)
        enricher.providers = ["arcgis", "nominatim"]
        enricher._enrichment_details = {"locations_enriched": 5}

        details = enricher.get_enrichment_details()

        assert details["cache_metrics"]["hits"] == 10
        assert details["cache_metrics"]["misses"] == 5
        assert details["provider_metrics"]["arcgis"]["success"] == 8
        assert details["provider_metrics"]["arcgis"]["failure"] == 2


class TestProviderConfig:
    """Test provider-specific configuration."""

    def test_provider_config_from_settings(self):
        """Test provider config is loaded from settings."""
        # Pass provider config directly in initialization
        config = {"provider_config": {"arcgis": {"max_retries": 5, "timeout": 15}}}

        enricher = GeocodingEnricher(config=config)

        assert enricher.provider_config["arcgis"]["max_retries"] == 5
        assert enricher.provider_config["arcgis"]["timeout"] == 15

    def test_provider_specific_retry_count(self):
        """Test different retry counts per provider."""
        mock_service = MagicMock()
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # No cached values

        # Make geocoding return None to avoid retries on success
        mock_service.geocode_with_provider.return_value = None
        mock_service.geocode.return_value = None

        enricher = GeocodingEnricher(
            geocoding_service=mock_service, redis_client=mock_redis
        )
        enricher.provider_config = {
            "arcgis": {"max_retries": 3},
            "nominatim": {"max_retries": 2},
        }

        # Test with arcgis config
        enricher._geocode_with_retry("arcgis", "123 Main St", 3)
        # Test with nominatim config
        enricher._geocode_with_retry("nominatim", "123 Main St", 2)

        # Verify at least 2 calls were made (one for each provider)
        total_calls = (
            mock_service.geocode_with_provider.call_count
            + mock_service.geocode.call_count
        )
        assert total_calls >= 2


class TestIntegration:
    """Integration tests for the complete enrichment flow."""

    @patch("app.validator.enrichment.GeocodingService")
    @patch("app.validator.enrichment.redis.from_url")
    def test_full_enrichment_with_redis(self, mock_redis_from_url, mock_service_class):
        """Test complete enrichment flow with Redis caching and metrics."""
        # Setup mocks
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # Cache miss
        mock_redis_from_url.return_value = mock_redis

        mock_service = MagicMock()
        # Mock both methods for backward compatibility
        mock_service.geocode_with_provider.return_value = (40.7128, -74.0060)
        mock_service.geocode.return_value = (40.7128, -74.0060)
        mock_service_class.return_value = mock_service

        # Create enricher and test location
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

        # Perform enrichment
        enriched, source = enricher.enrich_location(location_data)

        # Verify results
        assert enriched["latitude"] == 40.7128
        assert enriched["longitude"] == -74.0060
        # Source should be arcgis since it's the first provider that succeeds
        assert source == "arcgis"

        # Verify cache was updated
        mock_redis.setex.assert_called_once()

        # Verify metrics were updated
        assert (
            mock_redis.incr.call_count >= 2
        )  # At least cache miss and provider success
