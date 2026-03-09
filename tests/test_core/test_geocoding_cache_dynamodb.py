"""Tests for DynamoDB geocoding cache backend."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from app.core.geocoding.cache_backend import GeocodingCacheBackend
from app.core.geocoding.cache_dynamodb import DynamoDBGeocodingCache


class TestDynamoDBGeocodingCache:
    """Tests for DynamoDBGeocodingCache."""

    @pytest.fixture
    def mock_client(self):
        return MagicMock()

    @pytest.fixture
    def cache(self, mock_client):
        c = DynamoDBGeocodingCache(table_name="test-table")
        c._client = mock_client
        return c

    def test_implements_protocol(self, cache):
        assert isinstance(cache, GeocodingCacheBackend)

    def test_get_hit(self, cache, mock_client):
        future_ttl = str(int(time.time()) + 3600)
        mock_client.get_item.return_value = {
            "Item": {
                "address": {"S": "geocode:arcgis:abc123"},
                "latitude": {"N": "40.7128"},
                "longitude": {"N": "-74.006"},
                "ttl": {"N": future_ttl},
            }
        }

        result = cache.get("geocode:arcgis:abc123")

        assert result == {"lat": 40.7128, "lon": -74.006}
        mock_client.get_item.assert_called_once_with(
            TableName="test-table",
            Key={"address": {"S": "geocode:arcgis:abc123"}},
        )

    def test_get_miss(self, cache, mock_client):
        mock_client.get_item.return_value = {}

        result = cache.get("geocode:arcgis:abc123")
        assert result is None

    def test_get_expired_ttl(self, cache, mock_client):
        past_ttl = str(int(time.time()) - 100)
        mock_client.get_item.return_value = {
            "Item": {
                "address": {"S": "geocode:arcgis:abc123"},
                "latitude": {"N": "40.7128"},
                "longitude": {"N": "-74.006"},
                "ttl": {"N": past_ttl},
            }
        }

        result = cache.get("geocode:arcgis:abc123")
        assert result is None

    def test_get_with_extra_data(self, cache, mock_client):
        future_ttl = str(int(time.time()) + 3600)
        mock_client.get_item.return_value = {
            "Item": {
                "address": {"S": "reverse:40.712800,-74.006000"},
                "latitude": {"N": "40.7128"},
                "longitude": {"N": "-74.006"},
                "ttl": {"N": future_ttl},
                "data": {"S": json.dumps({"postal_code": "10001", "city": "New York"})},
            }
        }

        result = cache.get("reverse:40.712800,-74.006000")

        assert result["lat"] == 40.7128
        assert result["lon"] == -74.006
        assert result["postal_code"] == "10001"
        assert result["city"] == "New York"

    def test_get_error_returns_none(self, cache, mock_client):
        mock_client.get_item.side_effect = Exception("DynamoDB error")

        result = cache.get("geocode:arcgis:abc123")
        assert result is None

    def test_set_basic(self, cache, mock_client):
        cache.set("geocode:arcgis:abc123", {"lat": 40.7128, "lon": -74.006}, 3600)

        mock_client.put_item.assert_called_once()
        call_kwargs = mock_client.put_item.call_args[1]
        item = call_kwargs["Item"]

        assert item["address"] == {"S": "geocode:arcgis:abc123"}
        assert item["latitude"] == {"N": "40.7128"}
        assert item["longitude"] == {"N": "-74.006"}
        assert item["provider"] == {"S": "arcgis"}
        assert "ttl" in item
        assert "cached_at" in item
        # TTL should be in the future
        assert int(item["ttl"]["N"]) > int(time.time())

    def test_set_with_extra_data(self, cache, mock_client):
        cache.set(
            "reverse:40.712800,-74.006000",
            {"lat": 40.7128, "lon": -74.006, "postal_code": "10001"},
            3600,
        )

        mock_client.put_item.assert_called_once()
        item = mock_client.put_item.call_args[1]["Item"]

        # Extra data stored as JSON in 'data' field
        assert "data" in item
        extra = json.loads(item["data"]["S"])
        assert extra["postal_code"] == "10001"

    def test_set_error_is_swallowed(self, cache, mock_client):
        mock_client.put_item.side_effect = Exception("DynamoDB error")

        # Should not raise
        cache.set("geocode:arcgis:abc123", {"lat": 40.7128, "lon": -74.006}, 3600)

    @patch("boto3.client")
    def test_lazy_client_init(self, mock_boto3_client):
        mock_client = MagicMock()
        mock_boto3_client.return_value = mock_client

        cache = DynamoDBGeocodingCache(table_name="test-table", region_name="us-east-1")

        # Client should not be created yet
        mock_boto3_client.assert_not_called()

        # First call triggers init
        mock_client.get_item.return_value = {}
        cache.get("test-key")

        mock_boto3_client.assert_called_once_with("dynamodb", region_name="us-east-1")
