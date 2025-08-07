"""Unified geocoding service for the application.

This module provides a centralized geocoding service that:
- Supports multiple geocoding providers (ArcGIS, Nominatim)
- Implements caching to reduce API calls
- Enforces rate limiting to respect API quotas
- Provides fallback mechanisms for reliability
- Maintains backward compatibility with existing scrapers
"""

import hashlib
import json
import logging
import os
import random
import re
import time
from typing import Optional, Tuple

from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import ArcGIS, Nominatim
from redis import Redis

logger = logging.getLogger(__name__)


class GeocodingService:
    """Unified geocoding service with caching and rate limiting."""

    def __init__(self):
        """Initialize the geocoding service with configuration from environment."""
        # Provider configuration
        self.primary_provider = os.getenv("GEOCODING_PROVIDER", "arcgis").lower()
        self.enable_fallback = (
            os.getenv("GEOCODING_ENABLE_FALLBACK", "true").lower() == "true"
        )

        # Caching configuration
        self.cache_ttl = int(os.getenv("GEOCODING_CACHE_TTL", "2592000"))  # 30 days
        self.redis_client = None
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                self.redis_client = Redis.from_url(redis_url, decode_responses=True)
                self.redis_client.ping()
                logger.info("Redis caching enabled for geocoding")
            except Exception as e:
                logger.warning(f"Redis connection failed, caching disabled: {e}")
                self.redis_client = None

        # Rate limiting configuration
        self.max_retries = int(os.getenv("GEOCODING_MAX_RETRIES", "3"))
        self.timeout = int(os.getenv("GEOCODING_TIMEOUT", "10"))

        # Initialize geocoders
        self._init_arcgis()
        self._init_nominatim()

    def _init_arcgis(self):
        """Initialize ArcGIS geocoder with optional API key authentication."""
        arcgis_api_key = os.getenv("ARCGIS_API_KEY")

        # Rate limit: 2 requests per second for free tier (safe margin)
        arcgis_rate_limit = float(os.getenv("GEOCODING_RATE_LIMIT", "0.5"))

        try:
            # Note: The ArcGIS REST API accepts API keys via the 'token' parameter
            # However, geopy's ArcGIS class doesn't directly support API keys
            # We'll need to extend it or pass the key differently

            # For now, use standard ArcGIS geocoder
            # In production, you may want to extend the ArcGIS class to add token support
            self.arcgis = ArcGIS(timeout=self.timeout)
            self.arcgis_api_key = arcgis_api_key  # Store for potential future use

            if arcgis_api_key:
                logger.info(
                    "ArcGIS API key configured (may need custom implementation for token support)"
                )
            else:
                logger.info(
                    "Initializing ArcGIS geocoder (unauthenticated - 20K/month limit)"
                )
                logger.info("Set ARCGIS_API_KEY in .env for higher limits")

            # Apply rate limiting
            self.arcgis_geocode = RateLimiter(
                self.arcgis.geocode,
                min_delay_seconds=arcgis_rate_limit,
                max_retries=self.max_retries,
                error_wait_seconds=5,
                return_value_on_exception=None,
            )

            logger.info(
                f"ArcGIS geocoder initialized with {arcgis_rate_limit}s rate limit"
            )

        except Exception as e:
            logger.error(f"Failed to initialize ArcGIS geocoder: {e}")
            self.arcgis = None
            self.arcgis_geocode = None

    def _init_nominatim(self):
        """Initialize Nominatim geocoder as fallback."""
        # Rate limit: 1 request per second (strict requirement)
        nominatim_rate_limit = float(os.getenv("NOMINATIM_RATE_LIMIT", "1.1"))
        user_agent = os.getenv("NOMINATIM_USER_AGENT", "pantry-pirate-radio")

        try:
            self.nominatim = Nominatim(user_agent=user_agent, timeout=self.timeout)

            # Apply rate limiting
            self.nominatim_geocode = RateLimiter(
                self.nominatim.geocode,
                min_delay_seconds=nominatim_rate_limit,
                max_retries=self.max_retries,
                error_wait_seconds=5,
                return_value_on_exception=None,
            )

            logger.info(
                f"Nominatim geocoder initialized with {nominatim_rate_limit}s rate limit"
            )

        except Exception as e:
            logger.error(f"Failed to initialize Nominatim geocoder: {e}")
            self.nominatim = None
            self.nominatim_geocode = None

    def _get_cache_key(self, address: str, provider: str) -> str:
        """Generate cache key for geocoding result.

        Args:
            address: Address string to geocode
            provider: Geocoding provider name

        Returns:
            Cache key string
        """
        # Use SHA256 instead of MD5 to avoid security warnings
        # Note: This is just for cache keys, not security-critical
        address_hash = hashlib.sha256(address.lower().encode()).hexdigest()
        return f"geocode:{provider}:{address_hash}"

    def _get_cached_result(
        self, address: str, provider: str
    ) -> Optional[Tuple[float, float]]:
        """Get cached geocoding result if available.

        Args:
            address: Address string to geocode
            provider: Geocoding provider name

        Returns:
            Tuple of (latitude, longitude) or None if not cached
        """
        if not self.redis_client:
            return None

        try:
            cache_key = self._get_cache_key(address, provider)
            cached = self.redis_client.get(cache_key)
            if cached:
                result = json.loads(cached)
                logger.debug(f"Cache hit for address: {address[:50]}...")
                return (result["lat"], result["lon"])
        except Exception as e:
            logger.warning(f"Cache retrieval error: {e}")

        return None

    def _cache_result(self, address: str, provider: str, lat: float, lon: float):
        """Cache geocoding result.

        Args:
            address: Address string that was geocoded
            provider: Geocoding provider used
            lat: Latitude result
            lon: Longitude result
        """
        if not self.redis_client:
            return

        try:
            cache_key = self._get_cache_key(address, provider)
            cache_value = json.dumps({"lat": lat, "lon": lon})
            self.redis_client.setex(cache_key, self.cache_ttl, cache_value)
            logger.debug(f"Cached result for address: {address[:50]}...")
        except Exception as e:
            logger.warning(f"Cache storage error: {e}")

    def _geocode_with_arcgis(self, address: str) -> Optional[Tuple[float, float]]:
        """Geocode using ArcGIS.

        Args:
            address: Address to geocode

        Returns:
            Tuple of (latitude, longitude) or None if failed
        """
        if not self.arcgis_geocode:
            return None

        try:
            location = self.arcgis_geocode(address)
            if location:
                return (location.latitude, location.longitude)
        except (GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError) as e:
            logger.warning(f"ArcGIS geocoding failed for '{address[:50]}...': {e}")
        except Exception as e:
            logger.error(f"Unexpected ArcGIS error for '{address[:50]}...': {e}")

        return None

    def _geocode_with_nominatim(self, address: str) -> Optional[Tuple[float, float]]:
        """Geocode using Nominatim.

        Args:
            address: Address to geocode

        Returns:
            Tuple of (latitude, longitude) or None if failed
        """
        if not self.nominatim_geocode:
            return None

        try:
            location = self.nominatim_geocode(address)
            if location:
                return (location.latitude, location.longitude)
        except (GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError) as e:
            logger.warning(f"Nominatim geocoding failed for '{address[:50]}...': {e}")
        except Exception as e:
            logger.error(f"Unexpected Nominatim error for '{address[:50]}...': {e}")

        return None

    def geocode(
        self, address: str, force_provider: Optional[str] = None
    ) -> Optional[Tuple[float, float]]:
        """Geocode an address to coordinates.

        Args:
            address: Address string to geocode
            force_provider: Optional provider to use ('arcgis' or 'nominatim')

        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails
        """
        if not address or not address.strip():
            logger.warning("Empty address provided for geocoding")
            return None

        # Determine which provider to use
        provider = force_provider or self.primary_provider

        # Check cache first
        cached_result = self._get_cached_result(address, provider)
        if cached_result:
            return cached_result

        # Try primary provider
        result = None
        if provider == "arcgis":
            result = self._geocode_with_arcgis(address)
            if result:
                self._cache_result(address, "arcgis", result[0], result[1])
                return result
        elif provider == "nominatim":
            result = self._geocode_with_nominatim(address)
            if result:
                self._cache_result(address, "nominatim", result[0], result[1])
                return result

        # Try fallback if enabled and primary failed
        if self.enable_fallback and not result and not force_provider:
            logger.info(f"Primary provider {provider} failed, trying fallback")

            if provider == "arcgis" and self.nominatim_geocode:
                # Add extra delay before fallback to be respectful
                time.sleep(1)
                result = self._geocode_with_nominatim(address)
                if result:
                    self._cache_result(address, "nominatim", result[0], result[1])
                    return result
            elif provider == "nominatim" and self.arcgis_geocode:
                result = self._geocode_with_arcgis(address)
                if result:
                    self._cache_result(address, "arcgis", result[0], result[1])
                    return result

        logger.warning(f"Failed to geocode address: {address[:100]}...")
        return None

    def batch_geocode(
        self, addresses: list[str]
    ) -> list[Optional[Tuple[float, float]]]:
        """Geocode multiple addresses.

        Args:
            addresses: List of address strings

        Returns:
            List of coordinate tuples or None for failed geocoding
        """
        results = []
        for address in addresses:
            result = self.geocode(address)
            results.append(result)
            # Small delay between batch requests to be respectful
            if result:
                time.sleep(0.1)
        return results

    def geocode_address(
        self, address: str, county: str | None = None, state: str | None = None
    ) -> tuple[float, float]:
        """Geocode address with county/state context (backward compatibility method).

        This method maintains compatibility with existing scrapers that use
        the GeocoderUtils.geocode_address signature.

        Args:
            address: Address to geocode
            county: Optional county name
            state: Optional state code

        Returns:
            Tuple of (latitude, longitude)

        Raises:
            ValueError: If all geocoding attempts fail
        """
        # Prepare address variations to try
        address_variations = []

        # Full address with county and state
        if (
            county
            and state
            and county.lower() not in address.lower()
            and state.lower() not in address.lower()
        ):
            address_variations.append(f"{address}, {county} County, {state}")

        # Address with just state
        if state and state.lower() not in address.lower():
            address_variations.append(f"{address}, {state}")

        # Original address as fallback
        address_variations.append(address)

        # Add specific variations for addresses with landmarks or special formats
        if "parking lot" in address.lower() or "across from" in address.lower():
            # Extract street address if it contains a street number
            street_match = re.search(
                r"\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd)",
                address,
            )
            if street_match:
                street_address = street_match.group(0)
                if county and state:
                    address_variations.append(
                        f"{street_address}, {county} County, {state}"
                    )
                if state:
                    address_variations.append(f"{street_address}, {state}")

        # Try each address variation
        errors = []
        for addr in address_variations:
            result = self.geocode(addr)
            if result:
                return result
            errors.append(f"Failed to geocode: '{addr}'")

        # If we get here, all geocoding attempts failed
        error_msg = "; ".join(errors) if errors else "Unknown geocoding error"
        raise ValueError(f"Could not geocode address: {address}. Errors: {error_msg}")

    def get_default_coordinates(
        self, location: str = "US", with_offset: bool = True, offset_range: float = 0.01
    ) -> tuple[float, float]:
        """Get default coordinates for a location (backward compatibility method).

        This method maintains compatibility with existing scrapers.

        Args:
            location: Location name (US, state code, or county name)
            with_offset: Whether to add a random offset
            offset_range: Range for random offset

        Returns:
            Tuple of (latitude, longitude)
        """
        # Default coordinates
        default_coordinates = {
            # Geographic center of the United States
            "US": (39.8283, -98.5795),
        }

        # Get base coordinates
        if location in default_coordinates:
            lat, lon = default_coordinates[location]
        else:
            # Default to US if location not found
            lat, lon = default_coordinates["US"]

        # Add random offset if requested
        if with_offset:
            lat_offset = random.uniform(-offset_range, offset_range)  # nosec B311
            lon_offset = random.uniform(-offset_range, offset_range)  # nosec B311
            lat += lat_offset
            lon += lon_offset

        return lat, lon


# Singleton instance
_geocoding_service = None


def get_geocoding_service() -> GeocodingService:
    """Get or create the singleton geocoding service instance.

    Returns:
        GeocodingService instance
    """
    global _geocoding_service
    if _geocoding_service is None:
        _geocoding_service = GeocodingService()
    return _geocoding_service
