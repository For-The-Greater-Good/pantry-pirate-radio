"""Validation rules for post-enrichment location data."""

import logging
import re
from typing import Any, Dict, Tuple, Optional

from app.core.geocoding.validator import GeocodingValidator
from app.core.geocoding.constants import STATE_BOUNDS

logger = logging.getLogger(__name__)


class ValidationRules:
    """Apply validation rules to location data after enrichment."""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize validation rules.

        Args:
            config: Optional configuration dictionary
        """
        from app.core.config import settings

        self.config = config or {}
        self.geocoding_validator = GeocodingValidator()

        # Test data patterns
        self.test_patterns = self.config.get(
            "test_patterns",
            getattr(
                settings,
                "VALIDATION_TEST_DATA_PATTERNS",
                [
                    "test",
                    "demo",
                    "example",
                    "sample",
                    "dummy",
                    "fake",
                    "anytown",
                    "unknown",
                ],
            ),
        )

        # Placeholder address patterns
        self.placeholder_patterns = self.config.get(
            "placeholder_patterns",
            getattr(
                settings,
                "VALIDATION_PLACEHOLDER_PATTERNS",
                [
                    r"^\d{1,3}\s+(main|first|second|third|test|example)\s+(st|street|ave|avenue|rd|road)",
                    r"^1\s+.+\s+(street|avenue|road|lane|way|drive|court|place)$",
                ],
            ),
        )

        # Test postal codes
        self.test_postal_codes = {"00000", "99999", "12345", "11111", "22222"}

    def check_coordinates_present(
        self, location: Dict[str, Any]
    ) -> Tuple[bool, int, str]:
        """Check if coordinates are present after enrichment.

        Args:
            location: Location data dictionary

        Returns:
            Tuple of (is_valid, confidence_impact, reason)
        """
        lat = location.get("latitude")
        lon = location.get("longitude")

        if lat is None or lon is None:
            return (False, -100, "Missing coordinates after enrichment")

        return (True, 0, "Coordinates present")

    def check_zero_coordinates(self, location: Dict[str, Any]) -> Tuple[bool, int, str]:
        """Check for 0,0 or near-zero coordinates.

        Args:
            location: Location data dictionary

        Returns:
            Tuple of (is_valid, confidence_impact, reason)
        """
        lat = location.get("latitude")
        lon = location.get("longitude")

        if lat is None or lon is None:
            return (
                True,
                0,
                "Valid coordinates",
            )  # Will be caught by check_coordinates_present

        # Check for exact 0,0
        if lat == 0.0 and lon == 0.0:
            return (False, -100, "Invalid 0,0 coordinates")

        # Check for near-zero (within 0.001 degrees of 0,0)
        if abs(lat) < 0.001 and abs(lon) < 0.001:
            return (False, -100, "Near-zero coordinates detected")

        return (True, 0, "Valid coordinates")

    def check_us_bounds(self, location: Dict[str, Any]) -> Tuple[bool, int, str]:
        """Check if coordinates are within US bounds (including AK and HI).

        Args:
            location: Location data dictionary

        Returns:
            Tuple of (is_valid, confidence_impact, reason)
        """
        lat = location.get("latitude")
        lon = location.get("longitude")

        if lat is None or lon is None:
            return (False, -95, "Missing coordinates")

        state = location.get("state", "").upper()

        # Special handling for Alaska and Hawaii
        if state == "AK":
            # Check Alaska bounds
            if self.geocoding_validator.is_within_state_bounds(lat, lon, "AK"):
                return (True, 0, "Within US bounds")
        elif state == "HI":
            # Check Hawaii bounds
            if self.geocoding_validator.is_within_state_bounds(lat, lon, "HI"):
                return (True, 0, "Within US bounds")
        else:
            # Check continental US bounds
            if self.geocoding_validator.is_within_us_bounds(lat, lon):
                return (True, 0, "Within US bounds")

        return (False, -95, "Outside US bounds")

    def verify_state_match(self, location: Dict[str, Any]) -> Tuple[bool, int, str]:
        """Verify coordinates match the claimed state.

        Args:
            location: Location data dictionary

        Returns:
            Tuple of (is_valid, confidence_impact, reason)
        """
        lat = location.get("latitude")
        lon = location.get("longitude")
        state = location.get("state", "").upper() if location.get("state") else None

        if lat is None or lon is None:
            return (True, 0, "Coordinates not available for verification")

        if not state:
            return (True, -5, "No state specified")

        # Check if state code is valid
        if state not in STATE_BOUNDS:
            return (False, -10, f"Invalid state code: {state}")

        # Check if coordinates are within state bounds
        if self.geocoding_validator.is_within_state_bounds(lat, lon, state):
            return (True, 0, "Coordinates match state")

        return (False, -20, f"Coordinates outside claimed state: {state}")

    def detect_test_data(self, location: Dict[str, Any]) -> Tuple[bool, int, str]:
        """Detect test/demo data patterns in location.

        Args:
            location: Location data dictionary

        Returns:
            Tuple of (is_valid, confidence_impact, reason)
        """
        # Check name for test patterns
        name = (location.get("name") or "").lower()
        for pattern in self.test_patterns:
            if pattern in name:
                return (False, -95, "Test data detected in name")

        # Check city for test patterns
        city = (location.get("city") or "").lower()
        for pattern in self.test_patterns:
            if pattern in city:
                return (False, -95, "Test data detected in city")

        # Check address for test patterns
        address = (location.get("address") or "").lower()
        for pattern in self.test_patterns:
            if pattern in address:
                return (False, -95, "Test data detected in address")

        # Check for test postal codes
        postal = location.get("postal_code", "")
        if postal in self.test_postal_codes:
            return (False, -95, f"Test postal code: {postal}")

        return (True, 0, "No test data indicators")

    def detect_placeholder_addresses(
        self, location: Dict[str, Any]
    ) -> Tuple[bool, int, str]:
        """Detect generic/placeholder addresses.

        Args:
            location: Location data dictionary

        Returns:
            Tuple of (is_valid, confidence_impact, reason)
        """
        address = location.get("address", "")

        if not address:
            return (True, -10, "No address provided")

        address_lower = address.lower().strip()

        # Check for exact matches to common placeholders
        exact_placeholders = [
            "123 main street",
            "123 main st",
            "1 main street",
            "1 main st",
            "123 first street",
            "123 first st",
            "1 test avenue",
            "123 example road",
        ]

        if address_lower in exact_placeholders:
            return (False, -75, "Placeholder address detected")

        # Check regex patterns
        for pattern in self.placeholder_patterns:
            if re.match(pattern, address_lower):
                # Exception: 4+ digit street numbers are probably real
                if re.match(r"^\d{4,}", address_lower):
                    continue
                return (False, -75, "Placeholder address detected")

        return (True, 0, "Valid address")

    def assess_geocoding_confidence(
        self, location: Dict[str, Any]
    ) -> Tuple[bool, int, str]:
        """Assess confidence based on geocoding source.

        Args:
            location: Location data dictionary

        Returns:
            Tuple of (is_valid, confidence_impact, reason)
        """
        source = location.get("geocoding_source") or ""
        source = source.lower() if source else ""

        if not source:
            return (False, -20, "No geocoding source")

        # High confidence sources
        if source in ["arcgis", "google"]:
            return (True, 0, f"High confidence geocoding: {source}")

        # Medium confidence sources
        if source == "nominatim":
            return (True, -5, f"Medium confidence geocoding: {source}")

        # Lower confidence sources
        if source == "census":
            return (True, -10, f"Lower confidence geocoding: {source}")

        # Fallback sources
        if source in ["state_centroid", "fallback"]:
            return (False, -15, f"Fallback geocoding: {source}")

        # Unknown source
        return (True, -5, f"Unknown geocoding source: {source}")

    def check_missing_fields(self, location: Dict[str, Any]) -> Dict[str, Any]:
        """Check for missing important fields after enrichment.

        Args:
            location: Location data dictionary

        Returns:
            Dictionary with missing field indicators
        """
        results: Dict[str, Any] = {
            "missing_postal": not bool(location.get("postal_code")),
            "missing_city": not bool(location.get("city")),
            "missing_address": not bool(location.get("address")),
        }

        # Calculate field completeness score
        important_fields = [
            "name",
            "address",
            "city",
            "state",
            "postal_code",
            "latitude",
            "longitude",
        ]
        present_fields = sum(1 for field in important_fields if location.get(field))
        field_completeness = present_fields / len(important_fields)
        results["field_completeness"] = field_completeness

        return results

    def validate_location(self, location: Dict[str, Any]) -> Dict[str, Any]:
        """Perform complete validation of a location.

        Args:
            location: Location data dictionary

        Returns:
            Dictionary with all validation results
        """
        results: Dict[str, Any] = {}

        # Check coordinates presence
        has_coords, _, _ = self.check_coordinates_present(location)
        results["has_coordinates"] = has_coords

        # Check for zero coordinates
        not_zero, _, _ = self.check_zero_coordinates(location)
        results["is_zero_coordinates"] = not not_zero

        # Check US bounds
        in_us, _, _ = self.check_us_bounds(location)
        results["within_us_bounds"] = in_us

        # Check state match
        state_match, _, _ = self.verify_state_match(location)
        results["within_state_bounds"] = state_match

        # Check for test data
        not_test, _, _ = self.detect_test_data(location)
        results["is_test_data"] = not not_test

        # Check for placeholder addresses
        not_placeholder, _, _ = self.detect_placeholder_addresses(location)
        results["has_placeholder_address"] = not not_placeholder

        # Assess geocoding confidence
        _, _, geocoding_msg = self.assess_geocoding_confidence(location)
        geocoding_confidence = "low"  # Default
        if "high" in geocoding_msg.lower():
            geocoding_confidence = "high"
        elif "medium" in geocoding_msg.lower():
            geocoding_confidence = "medium"
        elif "fallback" in geocoding_msg.lower():
            geocoding_confidence = "fallback"
        results["geocoding_confidence"] = geocoding_confidence

        # Check missing fields
        missing_fields = self.check_missing_fields(location)
        results.update(missing_fields)

        # Overall validation pass/fail
        critical_failures = [
            not results["has_coordinates"],
            results["is_zero_coordinates"],
            not results["within_us_bounds"],
            results["is_test_data"],
        ]

        results["validation_passed"] = not any(critical_failures)

        return results

    def validate_job_data(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate complete job data including organization and locations.

        Args:
            job_data: Complete job data dictionary

        Returns:
            Dictionary with validation results for all entities
        """
        results = {}

        # Validate organization if present
        if "organization" in job_data:
            org = job_data["organization"]
            results["organization_validation"] = {
                "has_name": bool(org.get("name")),
                "has_description": bool(org.get("description")),
            }

        # Validate locations
        if "locations" in job_data:
            location_validations = []
            for location in job_data["locations"]:
                validation = self.validate_location(location)
                location_validations.append(validation)
            results["location_validations"] = location_validations  # type: ignore[assignment]

        # Validate services if present
        if "services" in job_data:
            service_validations = []
            for service in job_data["services"]:
                validation = {
                    "has_name": bool(service.get("name")),
                    "has_description": bool(service.get("description")),
                }
                service_validations.append(validation)
            results["service_validations"] = service_validations  # type: ignore[assignment]

        return results
