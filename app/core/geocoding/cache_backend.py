"""Geocoding cache backend abstraction.

Provides a pluggable cache backend following Principle XV (Dual Environment
Compatibility). A factory selects the appropriate implementation based on
environment: GEOCODING_CACHE_TABLE -> DynamoDB, REDIS_URL -> Redis, else None.
"""

import hashlib
import json
import logging
import os
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class GeocodingCacheBackend(Protocol):
    """Protocol for geocoding cache backends."""

    def get(self, cache_key: str) -> Optional[dict]:
        """Retrieve a cached geocoding result.

        Args:
            cache_key: Cache key (from make_geocoding_cache_key or
                make_reverse_geocoding_cache_key)

        Returns:
            Dict with at least 'lat' and 'lon' keys, or None if not cached
        """
        ...

    def set(self, cache_key: str, data: dict, ttl: int) -> None:
        """Store a geocoding result in the cache.

        Args:
            cache_key: Cache key
            data: Dict with at least 'lat' and 'lon' keys
            ttl: Time-to-live in seconds
        """
        ...


class RedisGeocodingCache:
    """Redis-backed geocoding cache."""

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    def get(self, cache_key: str) -> Optional[dict]:
        try:
            raw = self._redis.get(cache_key)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning(f"Geocoding cache get error: {e}")
        return None

    def set(self, cache_key: str, data: dict, ttl: int) -> None:
        try:
            self._redis.setex(cache_key, ttl, json.dumps(data))
        except Exception as e:
            logger.warning(f"Geocoding cache set error: {e}")


def make_geocoding_cache_key(provider: str, address: str) -> str:
    """Generate a canonical cache key for a forward geocoding request.

    Uses SHA-256 of the lowercased address for consistency.

    Args:
        provider: Geocoding provider name (e.g. 'arcgis', 'nominatim')
        address: Raw address string

    Returns:
        Cache key in format ``geocode:{provider}:{sha256_hex}``
    """
    address_hash = hashlib.sha256(address.lower().encode()).hexdigest()
    return f"geocode:{provider}:{address_hash}"


def make_reverse_geocoding_cache_key(lat: float, lon: float) -> str:
    """Generate a canonical cache key for a reverse geocoding request.

    Args:
        lat: Latitude coordinate
        lon: Longitude coordinate

    Returns:
        Cache key in format ``reverse:{lat:.6f},{lon:.6f}``
    """
    return f"reverse:{lat:.6f},{lon:.6f}"


def get_geocoding_cache_backend() -> Optional[GeocodingCacheBackend]:
    """Factory: select the correct cache backend for the current environment.

    Priority:
      1. GEOCODING_CACHE_TABLE env var -> DynamoDB
      2. REDIS_URL env var -> Redis
      3. Neither -> None (caching disabled)

    Returns:
        A GeocodingCacheBackend instance, or None if no backend is available.
    """
    # DynamoDB (AWS)
    table_name = os.getenv("GEOCODING_CACHE_TABLE")
    if table_name:
        try:
            from app.core.geocoding.cache_dynamodb import DynamoDBGeocodingCache

            backend = DynamoDBGeocodingCache(table_name=table_name)
            logger.info("Geocoding cache: DynamoDB (%s)", table_name)
            return backend
        except Exception as e:
            logger.warning(f"DynamoDB geocoding cache init failed: {e}")

    # Redis (local Docker)
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            from redis import Redis

            client = Redis.from_url(redis_url, decode_responses=True)
            client.ping()
            logger.info("Geocoding cache: Redis")
            return RedisGeocodingCache(client)
        except Exception as e:
            logger.warning(f"Redis geocoding cache init failed: {e}")

    logger.info("Geocoding cache: disabled (no backend configured)")
    return None
