"""Tests for geocoding cache backend protocol, Redis impl, factory, and key helpers."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.core.geocoding.cache_backend import (
    GeocodingCacheBackend,
    RedisGeocodingCache,
    get_geocoding_cache_backend,
    make_geocoding_cache_key,
    make_reverse_geocoding_cache_key,
)


class TestMakeGeocodingCacheKey:
    """Tests for make_geocoding_cache_key helper."""

    def test_canonical_format(self):
        key = make_geocoding_cache_key("arcgis", "123 Main St")
        assert key.startswith("geocode:arcgis:")
        # SHA-256 hex digest is 64 chars
        assert len(key.split(":")[-1]) == 64

    def test_case_insensitive(self):
        key1 = make_geocoding_cache_key("arcgis", "123 Main St")
        key2 = make_geocoding_cache_key("arcgis", "123 MAIN ST")
        assert key1 == key2

    def test_different_providers(self):
        key1 = make_geocoding_cache_key("arcgis", "123 Main St")
        key2 = make_geocoding_cache_key("nominatim", "123 Main St")
        assert key1 != key2

    def test_different_addresses(self):
        key1 = make_geocoding_cache_key("arcgis", "123 Main St")
        key2 = make_geocoding_cache_key("arcgis", "456 Oak Ave")
        assert key1 != key2


class TestMakeReverseGeocodingCacheKey:
    """Tests for make_reverse_geocoding_cache_key helper."""

    def test_canonical_format(self):
        key = make_reverse_geocoding_cache_key(40.712800, -74.006000)
        assert key == "reverse:40.712800,-74.006000"

    def test_precision(self):
        key = make_reverse_geocoding_cache_key(40.7128001, -74.00600099)
        assert key == "reverse:40.712800,-74.006001"


class TestRedisGeocodingCache:
    """Tests for RedisGeocodingCache."""

    def test_get_hit(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({"lat": 40.7128, "lon": -74.006})
        cache = RedisGeocodingCache(mock_redis)

        result = cache.get("geocode:arcgis:abc123")
        assert result == {"lat": 40.7128, "lon": -74.006}
        mock_redis.get.assert_called_once_with("geocode:arcgis:abc123")

    def test_get_miss(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        cache = RedisGeocodingCache(mock_redis)

        result = cache.get("geocode:arcgis:abc123")
        assert result is None

    def test_get_error_returns_none(self):
        mock_redis = MagicMock()
        mock_redis.get.side_effect = ConnectionError("lost connection")
        cache = RedisGeocodingCache(mock_redis)

        result = cache.get("geocode:arcgis:abc123")
        assert result is None

    def test_set_calls_setex(self):
        mock_redis = MagicMock()
        cache = RedisGeocodingCache(mock_redis)

        cache.set("geocode:arcgis:abc123", {"lat": 40.7128, "lon": -74.006}, 3600)

        mock_redis.setex.assert_called_once()
        args = mock_redis.setex.call_args[0]
        assert args[0] == "geocode:arcgis:abc123"
        assert args[1] == 3600
        assert json.loads(args[2]) == {"lat": 40.7128, "lon": -74.006}

    def test_set_error_is_swallowed(self):
        mock_redis = MagicMock()
        mock_redis.setex.side_effect = ConnectionError("lost connection")
        cache = RedisGeocodingCache(mock_redis)

        # Should not raise
        cache.set("geocode:arcgis:abc123", {"lat": 40.7128, "lon": -74.006}, 3600)

    def test_implements_protocol(self):
        mock_redis = MagicMock()
        cache = RedisGeocodingCache(mock_redis)
        assert isinstance(cache, GeocodingCacheBackend)


class TestGetGeocodingCacheBackend:
    """Tests for factory function."""

    @patch.dict("os.environ", {}, clear=True)
    def test_no_env_returns_none(self):
        result = get_geocoding_cache_backend()
        assert result is None

    @patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379/0"}, clear=True)
    @patch("redis.Redis.from_url")
    def test_redis_url_returns_redis_backend(self, mock_from_url):
        mock_client = MagicMock()
        mock_from_url.return_value = mock_client

        result = get_geocoding_cache_backend()

        assert isinstance(result, RedisGeocodingCache)
        mock_from_url.assert_called_once_with(
            "redis://localhost:6379/0", decode_responses=True
        )
        mock_client.ping.assert_called_once()

    @patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379/0"}, clear=True)
    @patch("redis.Redis.from_url")
    def test_redis_connection_failure_returns_none(self, mock_from_url):
        mock_from_url.side_effect = ConnectionError("refused")

        result = get_geocoding_cache_backend()
        assert result is None

    @patch.dict(
        "os.environ",
        {"GEOCODING_CACHE_TABLE": "geocoding-cache-dev"},
        clear=True,
    )
    @patch("app.core.geocoding.cache_dynamodb.DynamoDBGeocodingCache")
    def test_dynamodb_table_returns_dynamodb_backend(self, mock_dynamo_class):
        mock_instance = MagicMock()
        mock_dynamo_class.return_value = mock_instance

        result = get_geocoding_cache_backend()

        assert result is mock_instance
        mock_dynamo_class.assert_called_once_with(table_name="geocoding-cache-dev")

    @patch.dict(
        "os.environ",
        {
            "GEOCODING_CACHE_TABLE": "geocoding-cache-dev",
            "REDIS_URL": "redis://localhost:6379/0",
        },
        clear=True,
    )
    @patch("app.core.geocoding.cache_dynamodb.DynamoDBGeocodingCache")
    def test_dynamodb_takes_priority_over_redis(self, mock_dynamo_class):
        mock_instance = MagicMock()
        mock_dynamo_class.return_value = mock_instance

        result = get_geocoding_cache_backend()

        # DynamoDB should win even if REDIS_URL is set
        assert result is mock_instance
