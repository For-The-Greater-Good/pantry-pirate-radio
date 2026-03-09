"""Unified geocoding service for the application.

This module provides a centralized geocoding service that:
- Supports multiple geocoding providers (ArcGIS, Nominatim)
- Implements caching to reduce API calls
- Enforces rate limiting to respect API quotas
- Provides fallback mechanisms for reliability
- Maintains backward compatibility with existing scrapers
"""

import os
import random
import re
import time
from typing import Optional, Tuple

import structlog

from app.core.geocoding.cache_backend import (
    GeocodingCacheBackend,
    get_geocoding_cache_backend,
    make_geocoding_cache_key,
    make_reverse_geocoding_cache_key,
)
from app.core.geocoding.providers import (
    geocode_with_amazon_location,
    geocode_with_arcgis,
    geocode_with_census,
    geocode_with_nominatim,
    init_amazon_location,
    init_arcgis,
    init_nominatim,
    reverse_geocode_with_amazon_location,
)
from app.core.state_mapping import normalize_state_to_code

logger = structlog.get_logger(__name__)


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
        self._cache: Optional[GeocodingCacheBackend] = get_geocoding_cache_backend()

        # Rate limiting configuration
        self.max_retries = int(os.getenv("GEOCODING_MAX_RETRIES", "3"))
        self.timeout = int(os.getenv("GEOCODING_TIMEOUT", "10"))

        # Initialize geocoders via provider module
        (
            self.arcgis,
            self.arcgis_geocode,
            self.arcgis_reverse,
            self.arcgis_api_key,
        ) = init_arcgis(self.timeout, self.max_retries)

        (
            self.nominatim,
            self.nominatim_geocode,
            self.nominatim_reverse,
        ) = init_nominatim(self.timeout, self.max_retries)

        (
            self.amazon_location_client,
            self.amazon_location_index,
        ) = init_amazon_location()

    def _geocode_with_amazon_location(
        self, address: str
    ) -> Optional[Tuple[float, float]]:
        """Geocode using Amazon Location Service (boto3)."""
        return geocode_with_amazon_location(
            self.amazon_location_client, self.amazon_location_index, address
        )

    def _reverse_geocode_with_amazon_location(
        self, lat: float, lon: float
    ) -> Optional[dict]:
        """Reverse geocode using Amazon Location Service."""
        return reverse_geocode_with_amazon_location(
            self.amazon_location_client, self.amazon_location_index, lat, lon
        )

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
        if not self._cache:
            return None

        cache_key = make_geocoding_cache_key(provider, address)
        result = self._cache.get(cache_key)
        if result and "lat" in result and "lon" in result:
            logger.debug("Cache hit for address", address=address[:50])
            return (result["lat"], result["lon"])
        return None

    def _cache_result(
        self,
        address: str,
        provider: str,
        lat: float,
        lon: float,
        extra_data: dict = None,
    ):
        """Cache geocoding result.

        Args:
            address: Address string that was geocoded
            provider: Geocoding provider used
            lat: Latitude result
            lon: Longitude result
            extra_data: Optional extra data to cache (for reverse geocoding)
        """
        if not self._cache:
            return

        cache_key = make_geocoding_cache_key(provider, address)
        cache_value = {"lat": lat, "lon": lon}
        if extra_data:
            cache_value.update(extra_data)
        self._cache.set(cache_key, cache_value, self.cache_ttl)
        logger.debug("Cached result for address", address=address[:50])

    def _geocode_with_arcgis(self, address: str) -> Optional[Tuple[float, float]]:
        """Geocode using ArcGIS."""
        return geocode_with_arcgis(self.arcgis_geocode, address)

    def _geocode_with_nominatim(self, address: str) -> Optional[Tuple[float, float]]:
        """Geocode using Nominatim."""
        return geocode_with_nominatim(self.nominatim_geocode, address)

    def _geocode_with_census(self, address: str) -> Optional[Tuple[float, float]]:
        """Geocode using US Census Geocoding API."""
        return geocode_with_census(address)

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
        if provider == "amazon-location":
            result = self._geocode_with_amazon_location(address)
            if result:
                self._cache_result(address, "amazon-location", result[0], result[1])
                return result
        elif provider == "arcgis":
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
            logger.info("Primary provider failed, trying fallback", provider=provider)

            # amazon-location falls back to arcgis, then nominatim
            if provider == "amazon-location":
                result = self._geocode_with_arcgis(address)
                if result:
                    self._cache_result(address, "arcgis", result[0], result[1])
                    return result
                time.sleep(1)
                result = self._geocode_with_nominatim(address)
                if result:
                    self._cache_result(address, "nominatim", result[0], result[1])
                    return result
            elif provider == "arcgis" and self.nominatim_geocode:
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

        logger.warning("Failed to geocode address", address=address[:100])
        return None

    def reverse_geocode(
        self, latitude: float, longitude: float, provider: Optional[str] = None
    ) -> Optional[dict]:
        """Reverse geocode coordinates to get address components.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            provider: Optional provider to use ('arcgis' or 'nominatim')

        Returns:
            Dict with address components including postal_code, or None if failed
        """
        if latitude is None or longitude is None:
            return None

        # Try cache first
        cache_key = make_reverse_geocoding_cache_key(latitude, longitude)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached and "postal_code" in cached:
                logger.debug(
                    "Cache hit for reverse geocoding",
                    latitude=latitude,
                    longitude=longitude,
                )
                return cached

        try:
            point = f"{latitude}, {longitude}"
            location = None

            # Determine which provider to use
            use_provider = provider or self.primary_provider

            # Try Amazon Location Service first if configured
            if use_provider == "amazon-location":
                al_result = self._reverse_geocode_with_amazon_location(
                    latitude, longitude
                )
                if al_result:
                    if al_result.get("postal_code") and self._cache:
                        self._cache.set(cache_key, al_result, self.cache_ttl)
                    return al_result
                # Fallback to arcgis
                if self.enable_fallback:
                    use_provider = "arcgis"

            if (
                use_provider == "arcgis"
                and hasattr(self, "arcgis_reverse")
                and self.arcgis_reverse
            ):
                try:
                    location = self.arcgis_reverse(point)
                except Exception as e:
                    logger.debug("ArcGIS reverse geocoding failed", error=str(e))
                    if (
                        self.enable_fallback
                        and hasattr(self, "nominatim_reverse")
                        and self.nominatim_reverse
                    ):
                        location = self.nominatim_reverse(point)

            elif hasattr(self, "nominatim_reverse") and self.nominatim_reverse:
                location = self.nominatim_reverse(point)

            if location and location.raw:
                # Extract address components
                result = {}
                raw = location.raw

                # Handle different response formats
                if "address" in raw:  # Nominatim format
                    addr = raw["address"]
                    result["postal_code"] = addr.get("postcode", "")
                    result["city"] = (
                        addr.get("city") or addr.get("town") or addr.get("village", "")
                    )
                    # Normalize state to 2-letter code
                    state_value = addr.get("state", "")
                    result["state"] = (
                        normalize_state_to_code(state_value) or state_value
                    )
                    result["country"] = addr.get("country_code", "").upper()
                elif "attributes" in raw:  # ArcGIS format
                    attrs = raw["attributes"]
                    result["postal_code"] = attrs.get("Postal", "")
                    result["city"] = attrs.get("City", "")
                    # Normalize state to 2-letter code
                    state_value = attrs.get("Region", "")
                    result["state"] = (
                        normalize_state_to_code(state_value) or state_value
                    )
                    result["country"] = attrs.get("Country", "")
                else:
                    # Try to extract from address string
                    address_str = str(location.address) if location.address else ""
                    # Look for ZIP code pattern
                    zip_match = re.search(r"\b(\d{5}(?:-\d{4})?)\b", address_str)
                    if zip_match:
                        result["postal_code"] = zip_match.group(1)
                    result["address_string"] = address_str

                # Cache the result directly
                if result.get("postal_code") and self._cache:
                    self._cache.set(cache_key, result, self.cache_ttl)
                    logger.debug(
                        "Cached reverse geocoding result",
                        latitude=latitude,
                        longitude=longitude,
                    )

                return result

        except Exception as e:
            logger.warning(
                "Reverse geocoding failed",
                latitude=latitude,
                longitude=longitude,
                error=str(e),
            )

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

    def geocode_with_provider(
        self, address: str, provider: str
    ) -> Optional[Tuple[float, float]]:
        """Geocode an address using a specific provider.

        Args:
            address: Address string to geocode
            provider: Provider to use ('arcgis', 'nominatim', or 'census')

        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails
        """
        if not address or not address.strip():
            logger.warning("Empty address provided for geocoding")
            return None

        # Check cache first
        cached_result = self._get_cached_result(address, provider)
        if cached_result:
            return cached_result

        result = None

        if provider == "amazon-location":
            result = self._geocode_with_amazon_location(address)
        elif provider == "arcgis":
            result = self._geocode_with_arcgis(address)
        elif provider == "nominatim":
            result = self._geocode_with_nominatim(address)
        elif provider == "census":
            result = self._geocode_with_census(address)
        else:
            logger.warning("Unknown geocoding provider", provider=provider)
            return None

        if result:
            self._cache_result(address, provider, result[0], result[1])

        return result

    def get_default_coordinates(
        self,
        location: str = "US",
        with_offset: bool = True,
        offset_range: float = 0.01,
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
