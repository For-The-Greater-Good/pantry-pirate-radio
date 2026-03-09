"""Geocoding provider initialization and provider-specific logic.

This module contains the individual geocoding provider implementations
(ArcGIS, Nominatim, Amazon Location Service, Census) extracted from the
main GeocodingService to keep file sizes manageable.
"""

import os
from typing import Any, Optional, Tuple

import requests
import structlog
from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import ArcGIS, Nominatim

logger = structlog.get_logger(__name__)


def init_arcgis(
    timeout: int, max_retries: int
) -> Tuple[
    Optional[ArcGIS], Optional[RateLimiter], Optional[RateLimiter], Optional[str]
]:
    """Initialize ArcGIS geocoder with optional API key authentication.

    Args:
        timeout: Request timeout in seconds
        max_retries: Maximum number of retries

    Returns:
        Tuple of (geocoder, geocode_limiter, reverse_limiter, api_key)
    """
    arcgis_api_key = os.getenv("ARCGIS_API_KEY")
    arcgis_rate_limit = float(os.getenv("GEOCODING_RATE_LIMIT", "0.5"))

    try:
        geocoder = ArcGIS(timeout=timeout)

        if arcgis_api_key:
            logger.info(
                "ArcGIS API key configured (may need custom implementation for token support)"
            )
        else:
            logger.info(
                "Initializing ArcGIS geocoder (unauthenticated - 20K/month limit)"
            )
            logger.info("Set ARCGIS_API_KEY in .env for higher limits")

        geocode_limiter = RateLimiter(
            geocoder.geocode,
            min_delay_seconds=arcgis_rate_limit,
            max_retries=max_retries,
            error_wait_seconds=5,
            return_value_on_exception=None,
        )

        reverse_limiter = RateLimiter(
            geocoder.reverse,
            min_delay_seconds=arcgis_rate_limit,
            max_retries=max_retries,
            error_wait_seconds=5,
            return_value_on_exception=None,
        )

        logger.info(
            "ArcGIS geocoder initialized",
            rate_limit=arcgis_rate_limit,
        )

        return geocoder, geocode_limiter, reverse_limiter, arcgis_api_key

    except Exception as e:
        logger.error("Failed to initialize ArcGIS geocoder", error=str(e))
        return None, None, None, None


def init_nominatim(
    timeout: int, max_retries: int
) -> Tuple[Optional[Nominatim], Optional[RateLimiter], Optional[RateLimiter]]:
    """Initialize Nominatim geocoder as fallback.

    Args:
        timeout: Request timeout in seconds
        max_retries: Maximum number of retries

    Returns:
        Tuple of (geocoder, geocode_limiter, reverse_limiter)
    """
    nominatim_rate_limit = float(os.getenv("NOMINATIM_RATE_LIMIT", "1.1"))
    user_agent = os.getenv("NOMINATIM_USER_AGENT", "pantry-pirate-radio")

    try:
        geocoder = Nominatim(user_agent=user_agent, timeout=timeout)

        geocode_limiter = RateLimiter(
            geocoder.geocode,
            min_delay_seconds=nominatim_rate_limit,
            max_retries=max_retries,
            error_wait_seconds=5,
            return_value_on_exception=None,
        )

        reverse_limiter = RateLimiter(
            geocoder.reverse,
            min_delay_seconds=nominatim_rate_limit,
            max_retries=max_retries,
            error_wait_seconds=5,
            return_value_on_exception=None,
        )

        logger.info(
            "Nominatim geocoder initialized",
            rate_limit=nominatim_rate_limit,
        )

        return geocoder, geocode_limiter, reverse_limiter

    except Exception as e:
        logger.error("Failed to initialize Nominatim geocoder", error=str(e))
        return None, None, None


def init_amazon_location() -> Tuple[object, Optional[str]]:
    """Initialize Amazon Location Service geocoder (AWS only).

    Requires AMAZON_LOCATION_INDEX env var. Skipped gracefully when not set
    (local development) or when boto3 is not available.

    Returns:
        Tuple of (client, index_name)
    """
    amazon_location_index = os.getenv("AMAZON_LOCATION_INDEX")
    if amazon_location_index:
        try:
            import boto3

            client = boto3.client("location")
            logger.info(
                "Amazon Location Service enabled",
                index=amazon_location_index,
            )
            return client, amazon_location_index
        except Exception as e:
            logger.debug("Amazon Location Service not available", error=str(e))

    return None, amazon_location_index


def geocode_with_arcgis(
    arcgis_geocode: Optional[RateLimiter], address: str
) -> Optional[Tuple[float, float]]:
    """Geocode using ArcGIS.

    Args:
        arcgis_geocode: Rate-limited ArcGIS geocode function
        address: Address to geocode

    Returns:
        Tuple of (latitude, longitude) or None if failed
    """
    if not arcgis_geocode:
        return None

    try:
        location = arcgis_geocode(address)
        if location:
            return (location.latitude, location.longitude)
    except (GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError) as e:
        logger.warning("ArcGIS geocoding failed", address=address[:50], error=str(e))
    except Exception as e:
        logger.error("Unexpected ArcGIS error", address=address[:50], error=str(e))

    return None


def geocode_with_nominatim(
    nominatim_geocode: Optional[RateLimiter], address: str
) -> Optional[Tuple[float, float]]:
    """Geocode using Nominatim.

    Args:
        nominatim_geocode: Rate-limited Nominatim geocode function
        address: Address to geocode

    Returns:
        Tuple of (latitude, longitude) or None if failed
    """
    if not nominatim_geocode:
        return None

    try:
        location = nominatim_geocode(address)
        if location:
            return (location.latitude, location.longitude)
    except (GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError) as e:
        logger.warning("Nominatim geocoding failed", address=address[:50], error=str(e))
    except Exception as e:
        logger.error("Unexpected Nominatim error", address=address[:50], error=str(e))

    return None


def geocode_with_amazon_location(
    client: Any,
    index_name: Optional[str],
    address: str,
) -> Optional[Tuple[float, float]]:
    """Geocode using Amazon Location Service (boto3).

    Args:
        client: boto3 location client
        index_name: Amazon Location index name
        address: Address to geocode

    Returns:
        Tuple of (latitude, longitude) or None if failed
    """
    if not client or not index_name:
        return None

    try:
        response = client.search_place_index_for_text(
            IndexName=index_name,
            Text=address,
            MaxResults=1,
        )
        results = response.get("Results", [])
        if results:
            point = results[0]["Place"]["Geometry"]["Point"]
            # Point is [longitude, latitude]
            return (point[1], point[0])
        return None
    except Exception as e:
        logger.debug("Amazon Location geocoding failed", error=str(e))
        return None


def reverse_geocode_with_amazon_location(
    client: Any,
    index_name: Optional[str],
    lat: float,
    lon: float,
) -> Optional[dict]:
    """Reverse geocode using Amazon Location Service.

    Args:
        client: boto3 location client
        index_name: Amazon Location index name
        lat: Latitude coordinate
        lon: Longitude coordinate

    Returns:
        Dict with address components or None if failed
    """
    if not client or not index_name:
        return None

    try:
        response = client.search_place_index_for_position(
            IndexName=index_name,
            Position=[lon, lat],
            MaxResults=1,
        )
        results = response.get("Results", [])
        if results:
            place = results[0]["Place"]
            return {
                "postal_code": place.get("PostalCode"),
                "city": place.get("Municipality"),
                "state": place.get("Region"),
                "country": place.get("Country"),
            }
        return None
    except Exception as e:
        logger.debug("Amazon Location reverse geocoding failed", error=str(e))
        return None


def geocode_with_census(address: str) -> Optional[Tuple[float, float]]:
    """Geocode using US Census Geocoding API.

    Args:
        address: Address string to geocode

    Returns:
        Tuple of (latitude, longitude) or None if geocoding fails
    """
    try:
        base_url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

        params = {"address": address, "benchmark": "2020", "format": "json"}

        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        if data.get("result") and data["result"].get("addressMatches"):
            matches = data["result"]["addressMatches"]
            if matches:
                match = matches[0]
                coords = match.get("coordinates")
                if coords:
                    # Census returns x (longitude), y (latitude)
                    longitude = coords.get("x")
                    latitude = coords.get("y")
                    if latitude is not None and longitude is not None:
                        logger.debug(
                            "Census geocoded address",
                            address=address[:50],
                            latitude=latitude,
                            longitude=longitude,
                        )
                        return (float(latitude), float(longitude))

        logger.debug("Census geocoding found no matches", address=address[:50])
        return None

    except requests.Timeout as e:
        logger.debug("Census geocoding timeout", error=str(e))
        return None
    except requests.RequestException as e:
        logger.debug("Census geocoding request failed", error=str(e))
        return None
    except (ValueError, KeyError) as e:
        logger.debug("Census geocoding data parsing error", error=str(e))
        return None
    except Exception as e:
        logger.warning("Unexpected Census geocoding error", error=str(e))
        return None
