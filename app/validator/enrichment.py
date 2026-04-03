"""Geocoding enrichment for validator service."""

import logging
import random
import time
from collections import defaultdict
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Tuple

from app.core.geocoding.cache_backend import (
    GeocodingCacheBackend,
    get_geocoding_cache_backend,
    make_geocoding_cache_key,
)
from app.core.geocoding.service import GeocodingService
from app.core.state_mapping import normalize_state_to_code
from app.core.zip_state_mapping import (
    get_state_from_zip,
    get_state_from_city,
    resolve_state_conflict,
)
from app.validator.scraper_context import (
    enhance_address_with_context,
    format_address_for_geocoding,
    get_scraper_context,
)

logger = logging.getLogger(__name__)


class GeocodingEnricher:
    """Enriches location data with geocoding and reverse geocoding."""

    def __init__(
        self,
        geocoding_service: Optional[GeocodingService] = None,
        config: Optional[Dict[str, Any]] = None,
        cache_backend: Optional[GeocodingCacheBackend] = None,
    ):
        """Initialize the geocoding enricher.

        Args:
            geocoding_service: Optional geocoding service instance
            config: Optional configuration dictionary
            cache_backend: Optional cache backend (auto-detected if None)
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

        # Cache backend (pluggable: Redis local, DynamoDB on AWS)
        self._cache: Optional[GeocodingCacheBackend] = (
            cache_backend
            if cache_backend is not None
            else get_geocoding_cache_backend()
        )

        # In-memory circuit breaker state (process-local, fine for single-container)
        self._circuit_state: Dict[str, Dict[str, Any]] = {}
        # In-memory metrics counters
        self._metrics: Dict[str, int] = defaultdict(int)

        # Track enrichment details for reporting
        self._enrichment_details: Dict[str, Any] = {
            "locations_enriched": 0,
            "coordinates_added": 0,
            "addresses_added": 0,
            "postal_codes_added": 0,
            "sources": {},
            "geocoding_calls": 0,
            "cache_hits": 0,
            "provider_failures": {},
        }

    def enrich_location(
        self, location_data: Dict[str, Any], scraper_id: Optional[str] = None
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Enrich a single location with geocoding data.

        Args:
            location_data: Location dictionary with addresses and coordinates
            scraper_id: Optional scraper identifier for context

        Returns:
            Tuple of (enriched location data, geocoding source used)
        """
        location_name = location_data.get("name", "Unknown Location")
        location_type = location_data.get("location_type", "physical")
        logger.info(f"🌟 ENRICHER: Starting enrichment for location: {location_name}")
        logger.info(f"🌟 ENRICHER: Location type: {location_type}")
        logger.info(f"🌟 ENRICHER: Enabled: {self.enabled}")
        logger.info(f"🌟 ENRICHER: Location data: {location_data}")

        if not self.enabled:
            logger.info("🌟 ENRICHER: Enrichment disabled, returning original data")
            return location_data, None

        # Skip enrichment for virtual locations
        if location_type == "virtual":
            logger.info(
                f"🌟 ENRICHER: Skipping enrichment for virtual location: {location_name}"
            )
            return location_data, None

        # Check if location needs enrichment
        needs_geocoding = (
            location_data.get("latitude") is None
            or location_data.get("longitude") is None
        )
        # Check for both "address" and "addresses" keys
        addresses = location_data.get("addresses") or location_data.get("address") or []

        needs_reverse_geocoding = not needs_geocoding and addresses == []
        needs_postal_enrichment = False

        if addresses:
            for address in addresses:
                if not address.get("postal_code"):
                    needs_postal_enrichment = True
                    break

        logger.info(f"📍 ENRICHER: Needs geocoding: {needs_geocoding}")
        logger.info(f"📍 ENRICHER: Needs reverse geocoding: {needs_reverse_geocoding}")
        logger.info(f"📍 ENRICHER: Needs postal enrichment: {needs_postal_enrichment}")

        # If location has complete data, no enrichment needed
        if (
            not needs_geocoding
            and not needs_reverse_geocoding
            and not needs_postal_enrichment
        ):
            logger.info(
                f"✅ ENRICHER: Location '{location_name}' has complete data, no enrichment needed"
            )
            return location_data, None

        enriched = location_data.copy()
        source = None

        try:
            # Geocode missing coordinates
            if needs_geocoding:
                # Check for both "address" and "addresses" keys
                has_addresses = enriched.get("addresses") or enriched.get("address")

                # If no addresses array, try to create one from the name
                if not has_addresses and location_name:
                    logger.info(
                        f"🔍 ENRICHER: No address array found, attempting to extract from name: '{location_name}'"
                    )
                    # Create a temporary address from the name
                    # Many NYC locations have addresses in the name like "58-25 LITTLE NECK PKWY (LITTLE NECK)"
                    enriched["addresses"] = [
                        {
                            "address_1": location_name,
                            "city": "",
                            "state_province": "",
                            "postal_code": "",
                            "country": "US",
                            "address_type": "physical",
                        }
                    ]
                    logger.info(
                        "🔍 ENRICHER: Created temporary address from name for geocoding"
                    )

                # Normalize to "addresses" if we have "address"
                if enriched.get("address") and not enriched.get("addresses"):
                    enriched["addresses"] = enriched["address"]

                if enriched.get("addresses"):
                    logger.info(
                        f"🔍 ENRICHER: Geocoding missing coordinates for '{location_name}'"
                    )
                    result = self._geocode_missing_coordinates(enriched, scraper_id)
                    if result:
                        coords, source = result
                        # Check if we got valid coordinates (not None, None)
                        if coords and coords[0] is not None and coords[1] is not None:
                            logger.info(
                                f"✅ ENRICHER: Successfully geocoded '{location_name}' to {coords} using {source}"
                            )
                            enriched["latitude"], enriched["longitude"] = coords
                            enriched["geocoding_source"] = source  # Track the source
                            self._enrichment_details["coordinates_added"] += 1

                            # Backfill missing address fields via reverse geocoding
                            if enriched.get("addresses"):
                                addr = enriched["addresses"][0]
                                if not addr.get("city") or not addr.get(
                                    "state_province"
                                ):
                                    logger.info(
                                        f"🔍 ENRICHER: Reverse geocoding to fill missing address fields for '{location_name}'"
                                    )
                                    reverse_result = (
                                        self._reverse_geocode_missing_address(enriched)
                                    )
                                    if reverse_result:
                                        reverse_addr, reverse_source = reverse_result
                                        if reverse_addr:
                                            if not addr.get(
                                                "city"
                                            ) and reverse_addr.get("city"):
                                                addr["city"] = reverse_addr["city"]
                                            if not addr.get(
                                                "state_province"
                                            ) and reverse_addr.get("state"):
                                                state_value = (
                                                    reverse_addr["state"] or ""
                                                )
                                                normalized = normalize_state_to_code(
                                                    state_value
                                                )
                                                if normalized:
                                                    addr["state_province"] = normalized
                                                elif (
                                                    len(state_value) == 2
                                                    and state_value.isalpha()
                                                ):
                                                    addr["state_province"] = (
                                                        state_value.upper()
                                                    )
                                            if not addr.get(
                                                "postal_code"
                                            ) and reverse_addr.get("postal_code"):
                                                addr["postal_code"] = reverse_addr[
                                                    "postal_code"
                                                ]
                                            self._enrichment_details[
                                                "addresses_added"
                                            ] += 1
                        else:
                            logger.warning(
                                f"❌ ENRICHER: Geocoding returned invalid coordinates for '{location_name}': {coords}"
                            )
                    else:
                        logger.warning(
                            f"❌ ENRICHER: All geocoding attempts failed for '{location_name}'"
                        )
                else:
                    logger.warning(
                        f"❌ ENRICHER: Cannot geocode '{location_name}' - no address information available"
                    )

            # Reverse geocode missing address
            elif needs_reverse_geocoding:
                logger.info(
                    f"🔍 ENRICHER: Reverse geocoding missing address for '{location_name}'"
                )
                logger.info(
                    f"🔍 ENRICHER: Using coordinates: {enriched.get('latitude')}, {enriched.get('longitude')}"
                )
                reverse_result = self._reverse_geocode_missing_address(enriched)
                if reverse_result:
                    address_data, source = reverse_result
                    if address_data:
                        logger.info(
                            f"✅ ENRICHER: Successfully reverse geocoded '{location_name}' using {source}"
                        )
                        logger.info(f"✅ ENRICHER: Address data: {address_data}")
                        # Normalize state to 2-letter code
                        state_value = address_data.get("state") or ""
                        normalized_state = normalize_state_to_code(state_value)
                        if not normalized_state and state_value:
                            logger.warning(
                                f"Could not normalize state '{state_value}' to 2-letter code"
                            )
                            # Prevent corrupted state data - only use if it's 2 chars
                            if len(state_value) == 2 and state_value.isalpha():
                                normalized_state = state_value.upper()
                            else:
                                logger.error(
                                    f"Rejecting invalid state value with length {len(state_value)}: '{state_value[:50]}...'"
                                )
                                normalized_state = (
                                    ""  # Use empty string rather than corrupted data
                                )

                        enriched["addresses"] = [
                            {
                                "address_1": address_data.get("address", ""),
                                "city": address_data.get("city", ""),
                                "state_province": normalized_state or "",
                                "postal_code": address_data.get("postal_code", ""),
                                "country": "US",
                                "address_type": "physical",
                            }
                        ]
                    else:
                        logger.warning(
                            f"❌ ENRICHER: Reverse geocoding returned empty address data for '{location_name}'"
                        )
                else:
                    logger.warning(
                        f"❌ ENRICHER: Reverse geocoding failed for '{location_name}'"
                    )

            # Enrich postal code if missing
            # Check for both "address" and "addresses" keys
            addresses_for_postal = enriched.get("addresses") or enriched.get("address")
            if needs_postal_enrichment and addresses_for_postal:
                logger.info(f"🔍 ENRICHER: Enriching postal code for '{location_name}'")
                postal_result = self._enrich_postal_code(enriched)
                if postal_result:
                    enriched, postal_source = postal_result
                    if postal_source and not source:
                        source = postal_source
                        logger.info(
                            f"✅ ENRICHER: Successfully enriched postal code for '{location_name}' using {postal_source}"
                        )

            # Auto-correct state mismatches before returning
            enriched = self._correct_state_mismatches(enriched, source)

        except Exception as e:
            logger.error(
                f"❌ ENRICHER: Failed to enrich location '{location_name}': {e}",
                exc_info=True,
            )

        logger.info(
            f"🎯 ENRICHER: Finished enriching '{location_name}', source: {source}"
        )
        return enriched, source

    def _correct_state_mismatches(
        self, location_data: Dict[str, Any], geocoding_source: Optional[str]
    ) -> Dict[str, Any]:
        """Automatically correct state mismatches using ZIP and city data.

        Args:
            location_data: Location data to check and correct
            geocoding_source: Source of geocoding if any

        Returns:
            Location data with corrected state if needed
        """
        if not location_data.get("addresses"):
            return location_data

        lat = location_data.get("latitude")
        lng = location_data.get("longitude")

        for address in location_data["addresses"]:
            claimed_state = address.get("state_province", "")
            postal_code = address.get("postal_code", "")
            city = address.get("city", "")

            if not claimed_state and not postal_code:
                continue

            # Get state from multiple sources
            zip_state = get_state_from_zip(postal_code) if postal_code else None
            city_state = get_state_from_city(city) if city else None

            # Determine if coordinates are in the claimed state
            coord_state = None
            if lat and lng and claimed_state:
                # Check if coordinates match claimed state
                from app.llm.utils.geocoding_validator import GeocodingValidator

                validator = GeocodingValidator()
                if not validator.is_within_state_bounds(lat, lng, claimed_state):
                    # Coordinates don't match claimed state
                    # Try to find which state they're actually in
                    for state in (
                        [zip_state, city_state] if zip_state or city_state else []
                    ):
                        if state and validator.is_within_state_bounds(lat, lng, state):
                            coord_state = state
                            break

            # Resolve conflicts
            resolved_state, reason = resolve_state_conflict(
                claimed_state, postal_code, city, coord_state
            )

            # If state needs correction
            if resolved_state and resolved_state != claimed_state:
                logger.warning(
                    f"🔧 ENRICHER: Correcting state from '{claimed_state}' to '{resolved_state}' "
                    f"(reason: {reason}) for {city}, {postal_code}"
                )

                address["state_province"] = resolved_state

                # Add note about correction
                if "validation_notes" not in location_data:
                    location_data["validation_notes"] = {}

                if "corrections" not in location_data["validation_notes"]:
                    location_data["validation_notes"]["corrections"] = []

                location_data["validation_notes"]["corrections"].append(
                    {
                        "field": "state_province",
                        "old_value": claimed_state,
                        "new_value": resolved_state,
                        "reason": reason,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )

                # Flag if coordinates might be wrong
                if zip_state and city_state and zip_state == city_state:
                    if coord_state and coord_state != zip_state:
                        location_data["validation_notes"]["coordinates_suspect"] = True
                        logger.warning(
                            f"⚠️ ENRICHER: Coordinates may be wrong - "
                            f"ZIP/city indicate {zip_state} but coords point to {coord_state}"
                        )

        return location_data

    def _geocode_missing_coordinates(
        self, location_data: Dict[str, Any], scraper_id: Optional[str] = None
    ) -> Tuple[Optional[Tuple[float, float]], Optional[str]]:
        """Geocode address to get coordinates.

        Args:
            location_data: Location data with address
            scraper_id: Optional scraper identifier for context

        Returns:
            Tuple of (coordinates, provider source) or (None, None) if all attempts fail
        """
        if not location_data.get("addresses"):
            return None, None

        address = location_data["addresses"][0]

        # Enhance address with scraper context if available
        if scraper_id:
            address = enhance_address_with_context(address, scraper_id)
            address_str = format_address_for_geocoding(address, scraper_id)
        else:
            address_str = self._format_address(address)

        logger.debug(f"Attempting to geocode: {address_str}")

        # Ensure we try ALL configured providers including census
        all_providers = ["amazon-location", "arcgis", "nominatim", "census"]

        # Try each provider in order
        for provider in all_providers:
            # Skip if not in configured providers list
            if provider not in self.providers and provider != "census":
                continue

            # Check Redis cache if available
            cached_coords = self._get_cached_coordinates(provider, address_str)
            if cached_coords:
                self._increment_cache_metric("hits")
                self._enrichment_details["cache_hits"] += 1
                # Validate cached coordinates are not None
                if cached_coords[0] is not None and cached_coords[1] is not None:
                    return cached_coords, provider
                else:
                    logger.debug(
                        f"Cached coordinates invalid for {provider}: {cached_coords}"
                    )

            self._increment_cache_metric("misses")

            # Check if provider is in circuit breaker open state
            if self._is_circuit_open(provider):
                logger.debug(f"Circuit breaker open for {provider}, skipping")
                continue

            # Try with minimal retry logic for provider fallback
            # Each provider gets one attempt in the fallback chain
            # Only retry on specific network/timeout errors, not general failures
            logger.info(f"Trying {provider} for: {address_str[:50]}...")
            coords = self._geocode_with_retry(provider, address_str, max_retries=2)
            self._enrichment_details["geocoding_calls"] += 1

            if coords and coords[0] is not None and coords[1] is not None:
                # Cache the result in Redis
                self._cache_coordinates(provider, address_str, coords)
                self._increment_provider_metric(provider, "success")
                self._reset_circuit_breaker(provider)
                logger.info(f"✅ Successfully geocoded with {provider}: {coords}")
                return coords, provider
            else:
                self._increment_provider_metric(provider, "failure")
                self._record_circuit_failure(provider)
                logger.debug(f"Failed to geocode with {provider}")

        logger.error(f"All geocoding providers failed for address: {address_str}")
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
            logger.warning(f"Reverse geocoding failed: {e}")

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

    def enrich_job_data(
        self, job_data: Dict[str, Any], scraper_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Enrich all locations in job data.

        Args:
            job_data: Job data with organization, service, and location arrays
            scraper_id: Optional scraper identifier for context

        Returns:
            Enriched job data
        """
        logger.info("🌟 ENRICHER: Starting enrichment process")
        logger.info(f"🌟 ENRICHER: Enabled: {self.enabled}")
        logger.info(f"🌟 ENRICHER: Providers: {self.providers}")
        if scraper_id:
            logger.info(f"🌟 ENRICHER: Using scraper context: {scraper_id}")

        if not self.enabled:
            logger.info("🌟 ENRICHER: Enrichment disabled, returning original data")
            return job_data

        logger.info(f"🌟 ENRICHER: Input data keys: {list(job_data.keys())}")

        enriched_data = job_data.copy()
        self._enrichment_details = {
            "locations_enriched": 0,
            "coordinates_added": 0,
            "addresses_added": 0,
            "postal_codes_added": 0,
            "sources": {},
            "geocoding_calls": 0,
            "cache_hits": 0,
            "provider_failures": {},
        }

        # Check for locations in different possible keys
        location_key = None
        location_count = 0

        if "location" in enriched_data and isinstance(enriched_data["location"], list):
            location_key = "location"
            location_count = len(enriched_data["location"])
        elif "locations" in enriched_data and isinstance(
            enriched_data["locations"], list
        ):
            location_key = "locations"
            location_count = len(enriched_data["locations"])

        logger.info(
            f"🌟 ENRICHER: Found {location_count} locations in key '{location_key}'"
        )

        if location_key and location_count > 0:
            # Enrich each location
            for i, location in enumerate(enriched_data[location_key]):
                logger.info(f"📍 ENRICHER: Processing location {i+1}/{location_count}")
                logger.info(f"📍 ENRICHER: Location data: {location}")

                enriched_location, source = self.enrich_location(location, scraper_id)
                enriched_data[location_key][i] = enriched_location

                if source:
                    self._enrichment_details["locations_enriched"] += 1
                    location_name = location.get("name", f"Location {i+1}")
                    self._enrichment_details["sources"][location_name] = source
                    logger.info(
                        f"✨ ENRICHER: Location '{location_name}' enriched using {source}"
                    )
                else:
                    logger.info(
                        f"📍 ENRICHER: Location {i+1} did not require enrichment"
                    )

        logger.info(
            f"🎯 ENRICHER: Enrichment complete - {self._enrichment_details['locations_enriched']} locations enriched"
        )
        logger.info(
            f"🎯 ENRICHER: Final enrichment details: {self._enrichment_details}"
        )

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
                if provider == "amazon-location":
                    if hasattr(self.geocoding_service, "geocode_with_provider"):
                        coords = self.geocoding_service.geocode_with_provider(
                            address_str, provider="amazon-location"
                        )
                elif provider == "arcgis" and hasattr(
                    self.geocoding_service, "geocode"
                ):
                    # Try regular geocode for arcgis (backward compatibility)
                    coords = self.geocoding_service.geocode(address_str)
                elif provider == "census":
                    # Use geocode_with_provider for census
                    if hasattr(self.geocoding_service, "geocode_with_provider"):
                        coords = self.geocoding_service.geocode_with_provider(
                            address_str, provider="census"
                        )
                elif hasattr(self.geocoding_service, "geocode_with_provider"):
                    coords = self.geocoding_service.geocode_with_provider(
                        address_str, provider=provider
                    )

                if coords:
                    return coords

                # If no result but no exception, don't retry for "not found" results
                # Only retry on actual errors (timeouts, network issues, etc.)
                return None

            except Exception as e:
                logger.warning(
                    f"Provider {provider} attempt {attempt + 1}/{max_retries} failed: {e}"
                )

                if attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    base_delay = 2**attempt  # 1s, 2s, 4s
                    # Using random for jitter is safe here - not cryptographic use
                    jitter = random.uniform(0, 0.5)  # nosec B311 - Add 0-0.5s jitter
                    delay = base_delay + jitter
                    logger.debug(f"Retrying {provider} after {delay:.2f}s")
                    time.sleep(delay)
                else:
                    logger.debug(
                        f"Provider {provider} failed after {max_retries} attempts"
                    )

        return None

    def _is_circuit_open(self, provider: str) -> bool:
        """Check if circuit breaker is open for a provider (in-memory).

        Args:
            provider: Provider name

        Returns:
            True if circuit is open (provider should be skipped)
        """
        state = self._circuit_state.get(provider)
        if not state or state.get("state") != "open":
            return False

        cooldown_until = state.get("cooldown_until", 0)
        if cooldown_until > time.time():
            return True

        # Cooldown expired, reset
        self._circuit_state.pop(provider, None)
        logger.info(f"Circuit breaker for {provider} reset after cooldown")
        return False

    def _record_circuit_failure(self, provider: str) -> None:
        """Record a failure for circuit breaker (in-memory).

        Args:
            provider: Provider name
        """
        provider_cfg = self.provider_config.get(provider, {})
        threshold = provider_cfg.get("circuit_breaker_threshold", 5)
        cooldown = provider_cfg.get("circuit_breaker_cooldown", 300)

        state = self._circuit_state.setdefault(provider, {"failures": 0})
        state["failures"] = state.get("failures", 0) + 1

        if state["failures"] >= threshold:
            state["state"] = "open"
            state["cooldown_until"] = time.time() + cooldown
            state["failures"] = 0
            logger.warning(
                f"Circuit breaker opened for {provider} after {threshold} failures"
            )

    def _reset_circuit_breaker(self, provider: str) -> None:
        """Reset circuit breaker state on success (in-memory).

        Args:
            provider: Provider name
        """
        self._circuit_state.pop(provider, None)

    def _get_cached_coordinates(
        self, provider: str, address: str
    ) -> Optional[Tuple[float, float]]:
        """Get cached coordinates from cache backend.

        Args:
            provider: Geocoding provider name
            address: Address string

        Returns:
            Cached coordinates or None
        """
        if not self._cache:
            return None

        cache_key = make_geocoding_cache_key(provider, address)
        result = self._cache.get(cache_key)
        if result and "lat" in result and "lon" in result:
            return (result["lat"], result["lon"])
        return None

    def _cache_coordinates(
        self, provider: str, address: str, coords: Tuple[float, float]
    ) -> None:
        """Cache coordinates via cache backend.

        Args:
            provider: Geocoding provider name
            address: Address string
            coords: Tuple of (latitude, longitude)
        """
        if not self._cache:
            return

        cache_key = make_geocoding_cache_key(provider, address)
        self._cache.set(cache_key, {"lat": coords[0], "lon": coords[1]}, self.cache_ttl)

    def _increment_cache_metric(self, metric_type: str) -> None:
        """Increment cache metric counter (in-memory).

        Args:
            metric_type: Type of metric (hits or misses)
        """
        self._metrics[f"cache:{metric_type}"] += 1

    def _increment_provider_metric(self, provider: str, result: str) -> None:
        """Increment provider metric counter (in-memory).

        Args:
            provider: Provider name
            result: Result type (success or failure)
        """
        self._metrics[f"{provider}:{result}"] += 1

    def get_enrichment_details(self) -> Dict[str, Any]:
        """Get details about the last enrichment operation.

        Returns:
            Dictionary with enrichment statistics and sources
        """
        details = self._enrichment_details.copy()

        # Add in-memory cache metrics
        details["cache_metrics"] = {
            "hits": self._metrics.get("cache:hits", 0),
            "misses": self._metrics.get("cache:misses", 0),
        }

        # Add in-memory provider metrics
        details["provider_metrics"] = {}
        for provider in self.providers:
            details["provider_metrics"][provider] = {
                "success": self._metrics.get(f"{provider}:success", 0),
                "failure": self._metrics.get(f"{provider}:failure", 0),
            }

        return details
