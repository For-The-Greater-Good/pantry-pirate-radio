"""Geocoding enrichment for validator service."""

import hashlib
import json
import logging
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import redis

from app.core.geocoding.service import GeocodingService

logger = logging.getLogger(__name__)


class GeocodingEnricher:
    """Enriches location data with geocoding and reverse geocoding."""

    def __init__(
        self,
        geocoding_service: Optional[GeocodingService] = None,
        config: Optional[Dict[str, Any]] = None,
        redis_client: Optional[redis.Redis] = None,
    ):
        """Initialize the geocoding enricher.

        Args:
            geocoding_service: Optional geocoding service instance
            config: Optional configuration dictionary
            redis_client: Optional Redis client for caching
        """
        from app.core.config import settings

        self.geocoding_service = geocoding_service or GeocodingService()
        self.config = config or {}

        # Use centralized settings with config overrides
        self.enabled = self.config.get(
            "enrichment_enabled", settings.VALIDATOR_ENRICHMENT_ENABLED
        )
        self.providers = self.config.get(
            "geocoding_providers", settings.ENRICHMENT_GEOCODING_PROVIDERS
        )
        self.timeout = self.config.get(
            "enrichment_timeout", settings.ENRICHMENT_TIMEOUT
        )
        self.cache_ttl = self.config.get(
            "cache_ttl", getattr(settings, "ENRICHMENT_CACHE_TTL", 86400)
        )
        self.provider_config = self.config.get(
            "provider_config", getattr(settings, "ENRICHMENT_PROVIDER_CONFIG", {})
        )

        # Initialize Redis client for caching
        if redis_client:
            self.redis_client = redis_client
        else:
            try:
                self.redis_client = redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                )
                # Test connection
                self.redis_client.ping()
                logger.debug("Redis connection established for geocoding cache")
            except (redis.ConnectionError, redis.TimeoutError) as e:
                logger.warning(f"Redis not available for caching: {e}")
                self.redis_client = None

        # Track enrichment details for reporting
        self._enrichment_details: Dict[str, Any] = {}

    def enrich_location(
        self, location_data: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Enrich a single location with geocoding data.

        Args:
            location_data: Location dictionary with addresses and coordinates

        Returns:
            Tuple of (enriched location data, geocoding source used)
        """
        if not self.enabled:
            return location_data, None

        # Check if location needs enrichment
        needs_geocoding = (
            location_data.get("latitude") is None
            or location_data.get("longitude") is None
        )
        needs_reverse_geocoding = (
            not needs_geocoding and location_data.get("addresses", []) == []
        )
        needs_postal_enrichment = False

        if location_data.get("addresses"):
            for address in location_data["addresses"]:
                if not address.get("postal_code"):
                    needs_postal_enrichment = True
                    break

        # If location has complete data, no enrichment needed
        if (
            not needs_geocoding
            and not needs_reverse_geocoding
            and not needs_postal_enrichment
        ):
            return location_data, None

        enriched = location_data.copy()
        source = None

        try:
            # Geocode missing coordinates
            if needs_geocoding and enriched.get("addresses"):
                result = self._geocode_missing_coordinates(enriched)
                if result:
                    coords, source = result
                    if coords:
                        enriched["latitude"], enriched["longitude"] = coords

            # Reverse geocode missing address
            elif needs_reverse_geocoding:
                reverse_result = self._reverse_geocode_missing_address(enriched)
                if reverse_result:
                    address_data, source = reverse_result
                    if address_data:
                        enriched["addresses"] = [
                            {
                                "address_1": address_data.get("address", ""),
                                "city": address_data.get("city", ""),
                                "state_province": address_data.get("state", ""),
                                "postal_code": address_data.get("postal_code", ""),
                                "country": "US",
                                "address_type": "physical",
                            }
                        ]

            # Enrich postal code if missing
            if needs_postal_enrichment and enriched.get("addresses"):
                postal_result = self._enrich_postal_code(enriched)
                if postal_result:
                    enriched, postal_source = postal_result
                    if postal_source and not source:
                        source = postal_source

        except Exception as e:
            logger.warning(f"Failed to enrich location: {e}")

        return enriched, source

    def _geocode_missing_coordinates(
        self, location_data: Dict[str, Any]
    ) -> Tuple[Optional[Tuple[float, float]], Optional[str]]:
        """Geocode address to get coordinates.

        Args:
            location_data: Location data with address

        Returns:
            Tuple of (coordinates, provider source)
        """
        if not location_data.get("addresses"):
            return None, None

        address = location_data["addresses"][0]
        address_str = self._format_address(address)

        # Try each provider in order
        for provider in self.providers:
            # Check Redis cache if available
            cached_coords = self._get_cached_coordinates(provider, address_str)
            if cached_coords:
                self._increment_cache_metric("hits")
                return cached_coords, provider

            self._increment_cache_metric("misses")

            # Check if provider is in circuit breaker open state
            if self._is_circuit_open(provider):
                logger.debug(f"Circuit breaker open for {provider}, skipping")
                continue

            # Try with retry logic using provider-specific config
            max_retries = self.provider_config.get(provider, {}).get("max_retries", 3)
            coords = self._geocode_with_retry(provider, address_str, max_retries)
            
            if coords:
                # Cache the result in Redis
                self._cache_coordinates(provider, address_str, coords)
                self._increment_provider_metric(provider, "success")
                self._reset_circuit_breaker(provider)
                return coords, provider
            else:
                self._increment_provider_metric(provider, "failure")
                self._record_circuit_failure(provider)

        return None, None

    def _reverse_geocode_missing_address(
        self, location_data: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Reverse geocode coordinates to get address.

        Args:
            location_data: Location data with coordinates

        Returns:
            Tuple of (address data, provider source)
        """
        lat = location_data.get("latitude")
        lon = location_data.get("longitude")

        if lat is None or lon is None:
            return None, None

        try:
            address_data = self.geocoding_service.reverse_geocode(lat, lon)
            if address_data:
                return address_data, "arcgis"
        except Exception as e:
            logger.debug(f"Reverse geocoding failed: {e}")

        return None, None

    def _enrich_postal_code(
        self, location_data: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Enrich missing postal code using geocoding.

        Args:
            location_data: Location data with partial address

        Returns:
            Tuple of (enriched location, provider source)
        """
        enriched = location_data.copy()
        source = None

        # If we don't have coordinates yet, geocode first
        if enriched.get("latitude") is None or enriched.get("longitude") is None:
            result = self._geocode_missing_coordinates(enriched)
            if result:
                coords, source = result
                if coords:
                    enriched["latitude"], enriched["longitude"] = coords

        # Now reverse geocode to get full address with postal code
        if (
            enriched.get("latitude") is not None
            and enriched.get("longitude") is not None
        ):
            reverse_result = self._reverse_geocode_missing_address(enriched)
            if reverse_result:
                address_data, rev_source = reverse_result
                if address_data and address_data.get("postal_code"):
                    # Update postal code in existing addresses
                    for address in enriched.get("addresses", []):
                        if not address.get("postal_code"):
                            address["postal_code"] = address_data["postal_code"]
                    if not source:
                        source = rev_source

        return enriched, source

    def _format_address(self, address: Dict[str, Any]) -> str:
        """Format address dictionary into a string for geocoding.

        The format used is: "street, city, state postal" (no comma between state and postal).
        This format is optimal for geocoding services which expect standard US address format.
        Most geocoding APIs interpret a comma between state and postal code as a separator
        that can cause parsing issues, while space-separated state and postal code is the
        standard USPS format.

        Args:
            address: Address dictionary with keys like address_1, city, state_province, postal_code

        Returns:
            Formatted address string in format: "123 Main St, New York, NY 10001"
        """
        parts = []
        if address.get("address_1"):
            parts.append(address["address_1"])
        if address.get("city"):
            parts.append(address["city"])

        # Combine state and postal code without comma between them (standard USPS format)
        # Example: "NY 10001" not "NY, 10001"
        state_zip = []
        if address.get("state_province"):
            state_zip.append(address["state_province"])
        if address.get("postal_code"):
            state_zip.append(address["postal_code"])

        if state_zip:
            parts.append(" ".join(state_zip))

        return ", ".join(parts)

    def enrich_job_data(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich all locations in job data.

        Args:
            job_data: Job data with organization, service, and location arrays

        Returns:
            Enriched job data
        """
        if not self.enabled:
            return job_data

        enriched_data = job_data.copy()
        self._enrichment_details = {
            "locations_enriched": 0,
            "sources": {},
        }

        # Enrich each location
        for i, location in enumerate(enriched_data.get("location", [])):
            enriched_location, source = self.enrich_location(location)
            enriched_data["location"][i] = enriched_location

            if source:
                self._enrichment_details["locations_enriched"] += 1
                location_name = location.get("name", f"Location {i+1}")
                self._enrichment_details["sources"][location_name] = source

        return enriched_data

    def _geocode_with_retry(
        self, provider: str, address_str: str, max_retries: int = 3
    ) -> Optional[Tuple[float, float]]:
        """Geocode with retry logic and exponential backoff.

        Args:
            provider: Geocoding provider name
            address_str: Address string to geocode
            max_retries: Maximum number of retry attempts

        Returns:
            Coordinates tuple or None
        """
        for attempt in range(max_retries):
            try:
                coords = None
                if provider == "arcgis" and hasattr(self.geocoding_service, "geocode"):
                    # Try regular geocode for arcgis (backward compatibility)
                    coords = self.geocoding_service.geocode(address_str)
                elif hasattr(self.geocoding_service, "geocode_with_provider"):
                    coords = self.geocoding_service.geocode_with_provider(
                        address_str, provider=provider
                    )

                if coords:
                    return coords

                # If no result but no exception, don't retry
                return None

            except (TimeoutError, Exception) as e:
                logger.debug(
                    f"Provider {provider} attempt {attempt + 1}/{max_retries} failed: {e}"
                )

                if attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    base_delay = 2**attempt  # 1s, 2s, 4s
                    jitter = random.uniform(0, 0.5)  # Add 0-0.5s jitter
                    delay = base_delay + jitter
                    logger.debug(f"Retrying {provider} after {delay:.2f}s")
                    time.sleep(delay)
                else:
                    logger.debug(f"Provider {provider} failed after {max_retries} attempts")

        return None

    def _is_circuit_open(self, provider: str) -> bool:
        """Check if circuit breaker is open for a provider.

        Args:
            provider: Provider name

        Returns:
            True if circuit is open (provider should be skipped)
        """
        if not self.redis_client:
            return False

        try:
            circuit_key = f"circuit_breaker:{provider}:state"
            state = self.redis_client.get(circuit_key)
            
            if state == "open":
                # Check if cooldown period has passed
                cooldown_key = f"circuit_breaker:{provider}:cooldown_until"
                cooldown_until = self.redis_client.get(cooldown_key)
                
                if cooldown_until:
                    if float(cooldown_until) > time.time():
                        return True
                    else:
                        # Cooldown expired, reset to closed
                        self.redis_client.delete(circuit_key)
                        self.redis_client.delete(cooldown_key)
                        logger.info(f"Circuit breaker for {provider} reset after cooldown")
                        return False
                
                return True
                
        except (redis.RedisError, ValueError) as e:
            logger.debug(f"Circuit breaker check error: {e}")

        return False

    def _record_circuit_failure(self, provider: str) -> None:
        """Record a failure for circuit breaker.

        Args:
            provider: Provider name
        """
        if not self.redis_client:
            return

        # Get provider-specific config
        provider_cfg = self.provider_config.get(provider, {})
        threshold = provider_cfg.get("circuit_breaker_threshold", 5)
        cooldown = provider_cfg.get("circuit_breaker_cooldown", 300)

        try:
            failure_key = f"circuit_breaker:{provider}:failures"
            failures = self.redis_client.incr(failure_key)
            self.redis_client.expire(failure_key, cooldown)  # Reset counter after cooldown period

            if failures >= threshold:
                # Open the circuit
                circuit_key = f"circuit_breaker:{provider}:state"
                cooldown_key = f"circuit_breaker:{provider}:cooldown_until"
                cooldown_time = time.time() + cooldown

                self.redis_client.set(circuit_key, "open")
                self.redis_client.set(cooldown_key, str(cooldown_time))
                self.redis_client.expire(circuit_key, cooldown + 10)
                self.redis_client.expire(cooldown_key, cooldown + 10)

                logger.warning(
                    f"Circuit breaker opened for {provider} after {failures} failures"
                )
                
                # Reset failure counter
                self.redis_client.delete(failure_key)

        except redis.RedisError as e:
            logger.debug(f"Circuit breaker record error: {e}")

    def _reset_circuit_breaker(self, provider: str) -> None:
        """Reset circuit breaker state on success.

        Args:
            provider: Provider name
        """
        if not self.redis_client:
            return

        try:
            # Clear failure counter and state
            self.redis_client.delete(f"circuit_breaker:{provider}:failures")
            self.redis_client.delete(f"circuit_breaker:{provider}:state")
            self.redis_client.delete(f"circuit_breaker:{provider}:cooldown_until")
        except redis.RedisError as e:
            logger.debug(f"Circuit breaker reset error: {e}")

    def _get_cache_key(self, provider: str, address: str) -> str:
        """Generate a cache key for geocoding results.

        Args:
            provider: Geocoding provider name
            address: Address string

        Returns:
            Cache key string
        """
        # Use SHA256 hash to handle long addresses and special characters
        address_hash = hashlib.sha256(address.encode()).hexdigest()[:16]
        return f"geocoding:{provider}:{address_hash}"

    def _get_cached_coordinates(
        self, provider: str, address: str
    ) -> Optional[Tuple[float, float]]:
        """Get cached coordinates from Redis.

        Args:
            provider: Geocoding provider name
            address: Address string

        Returns:
            Cached coordinates or None
        """
        if not self.redis_client:
            return None

        try:
            cache_key = self._get_cache_key(provider, address)
            cached_value = self.redis_client.get(cache_key)
            if cached_value:
                coords = json.loads(cached_value)
                return (coords["lat"], coords["lon"])
        except (redis.RedisError, json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Cache retrieval error: {e}")

        return None

    def _cache_coordinates(
        self, provider: str, address: str, coords: Tuple[float, float]
    ) -> None:
        """Cache coordinates in Redis.

        Args:
            provider: Geocoding provider name
            address: Address string
            coords: Tuple of (latitude, longitude)
        """
        if not self.redis_client:
            return

        try:
            cache_key = self._get_cache_key(provider, address)
            cache_value = json.dumps({"lat": coords[0], "lon": coords[1]})
            self.redis_client.setex(cache_key, self.cache_ttl, cache_value)
        except redis.RedisError as e:
            logger.debug(f"Cache storage error: {e}")

    def _increment_cache_metric(self, metric_type: str) -> None:
        """Increment cache metric counter.

        Args:
            metric_type: Type of metric (hits or misses)
        """
        if not self.redis_client:
            return

        try:
            metric_key = f"metrics:geocoding:cache:{metric_type}"
            self.redis_client.incr(metric_key)
        except redis.RedisError as e:
            logger.debug(f"Metric increment error: {e}")

    def _increment_provider_metric(self, provider: str, result: str) -> None:
        """Increment provider metric counter.

        Args:
            provider: Provider name
            result: Result type (success or failure)
        """
        if not self.redis_client:
            return

        try:
            metric_key = f"metrics:geocoding:{provider}:{result}"
            self.redis_client.incr(metric_key)
        except redis.RedisError as e:
            logger.debug(f"Metric increment error: {e}")

    def get_enrichment_details(self) -> Dict[str, Any]:
        """Get details about the last enrichment operation.

        Returns:
            Dictionary with enrichment statistics and sources
        """
        details = self._enrichment_details.copy()

        # Add cache metrics if Redis is available
        if self.redis_client:
            try:
                details["cache_metrics"] = {
                    "hits": int(self.redis_client.get("metrics:geocoding:cache:hits") or 0),
                    "misses": int(
                        self.redis_client.get("metrics:geocoding:cache:misses") or 0
                    ),
                }
                # Add provider metrics
                details["provider_metrics"] = {}
                for provider in self.providers:
                    details["provider_metrics"][provider] = {
                        "success": int(
                            self.redis_client.get(f"metrics:geocoding:{provider}:success")
                            or 0
                        ),
                        "failure": int(
                            self.redis_client.get(f"metrics:geocoding:{provider}:failure")
                            or 0
                        ),
                    }
            except redis.RedisError as e:
                logger.debug(f"Error retrieving metrics: {e}")

        return details
