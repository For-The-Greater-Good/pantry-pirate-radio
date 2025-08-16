"""Geocoding enrichment for validator service."""

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.core.geocoding.service import GeocodingService

logger = logging.getLogger(__name__)


class GeocodingEnricher:
    """Enriches location data with geocoding and reverse geocoding."""

    def __init__(
        self,
        geocoding_service: Optional[GeocodingService] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize the geocoding enricher.

        Args:
            geocoding_service: Optional geocoding service instance
            config: Optional configuration dictionary
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
        self.cache_size = self.config.get("cache_size", settings.ENRICHMENT_CACHE_SIZE)

        # Track enrichment details for reporting
        self._enrichment_details: Dict[str, Any] = {}
        self._cache: Dict[str, Tuple[float, float]] = {}

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
            # Check cache with provider-specific key to avoid collisions
            cache_key = f"{provider}:{address_str}"
            if cache_key in self._cache:
                return self._cache[cache_key], provider

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
                    # Cache with provider-specific key
                    self._cache[cache_key] = coords
                    # Limit cache size
                    if len(self._cache) > self.cache_size:
                        # Remove oldest entry (FIFO)
                        self._cache.pop(next(iter(self._cache)))
                    return coords, provider

            except (TimeoutError, Exception) as e:
                logger.debug(f"Provider {provider} failed: {e}")
                continue

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

        Args:
            address: Address dictionary

        Returns:
            Formatted address string
        """
        parts = []
        if address.get("address_1"):
            parts.append(address["address_1"])
        if address.get("city"):
            parts.append(address["city"])

        # Combine state and postal code without comma between them
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

    def get_enrichment_details(self) -> Dict[str, Any]:
        """Get details about the last enrichment operation.

        Returns:
            Dictionary with enrichment statistics and sources
        """
        return self._enrichment_details
