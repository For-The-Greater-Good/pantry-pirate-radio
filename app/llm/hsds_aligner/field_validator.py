"""HSDS field validation utilities.

This module provides functionality for validating required fields and relationships
in HSDS data structures, including geographic coordinate validation.
"""

from typing import Any, Dict, List, Optional
from app.llm.hsds_aligner.type_defs import (
    HSDSDataDict,
    KnownFieldsDict,
    LocationDict,
    PhoneDict,
)
from app.llm.utils.geocoding_validator import GeocodingValidator


class FieldValidator:
    """Validates required fields and relationships in HSDS data."""

    def __init__(self):
        """Initialize the field validator with geocoding support."""
        self.geocoding_validator = GeocodingValidator()

    # Field deduction amounts
    DEDUCTIONS = {
        "top_level": 0.15,  # Missing top-level field
        "organization": 0.10,  # Missing organization field
        "service": 0.10,  # Missing service field
        "location": 0.10,  # Missing location field
        "other": 0.05,  # Missing other field
        # Higher deductions for known fields
        "known_top_level": 0.25,  # Missing known top-level field
        "known_organization": 0.20,  # Missing known organization field
        "known_service": 0.20,  # Missing known service field
        "known_location": 0.20,  # Missing known location field
        "known_other": 0.15,  # Missing known other field
        # Reduced deductions for commonly inferrable fields
        "inferrable_address": 0.03,  # City, state, zip - often inferrable
        "inferrable_defaults": 0.02,  # Country, phone type, languages - standard defaults
        "inferrable_status": 0.02,  # Service status, location type - usually standard
    }

    # Required fields by entity type
    REQUIRED_FIELDS = {
        "top_level": ["organization", "service", "location"],
        "organization": [
            "name",
            "description",
            "services",
            "phones",
            "organization_identifiers",
            "contacts",
            "metadata",
        ],
        "service": [
            "name",
            "description",
            "status",
            "phones",
            "schedules",
        ],
        "location": [
            "name",
            "location_type",
            "addresses",
            "phones",
            "accessibility",
            "contacts",
            "schedules",
            "languages",
            "metadata",
        ],
        "phone": [
            "number",
            "type",
            "languages",
        ],
    }

    def validate_required_fields(
        self,
        hsds_data: HSDSDataDict,
        known_fields: KnownFieldsDict | None = None,
    ) -> list[str]:
        """Validate presence of all required fields in HSDS data.

        Args:
            hsds_data: HSDS data to validate

        Returns:
            list[str]: List of missing required field paths
        """
        missing_fields: list[str] = []

        # Check top-level required fields
        for field in self.REQUIRED_FIELDS["top_level"]:
            if field not in hsds_data:
                missing_fields.append(field)

        # Check organization fields
        if "organization" in hsds_data:
            for org in hsds_data["organization"]:
                for field in self.REQUIRED_FIELDS["organization"]:
                    if field not in org:
                        missing_fields.append(f"organization.{field}")

        # Check service fields
        if "service" in hsds_data:
            for service in hsds_data["service"]:
                for field in self.REQUIRED_FIELDS["service"]:
                    if field not in service:
                        missing_fields.append(f"service.{field}")

        # Check location fields
        if "location" in hsds_data:
            for location in hsds_data["location"]:
                for field in self.REQUIRED_FIELDS["location"]:
                    if field not in location:
                        missing_fields.append(f"location.{field}")

        # Check phone fields in all entities
        self._validate_phone_fields(hsds_data, missing_fields)

        return missing_fields

    def _validate_phone_fields(
        self, data: HSDSDataDict, missing_fields: list[str]
    ) -> None:
        """Validate phone fields across all entities.

        Args:
            data: Data structure containing phone objects
            missing_fields: List to append missing fields to
        """

        # Helper to check phone object fields
        def check_phone(phone: PhoneDict, prefix: str) -> None:
            for field in self.REQUIRED_FIELDS["phone"]:
                if field not in phone:
                    missing_fields.append(f"{prefix}.{field}")

        # Check organization phones
        if "organization" in data:
            for org_idx, org in enumerate(data["organization"]):
                org_phones = org.get("phones")
                if org_phones:
                    for phone_idx, phone in enumerate(org_phones):
                        prefix = f"organization[{org_idx}].phones[{phone_idx}]"
                        check_phone(phone, prefix)

        # Check service phones
        if "service" in data:
            for svc_idx, svc in enumerate(data["service"]):
                svc_phones = svc.get("phones")
                if svc_phones:
                    for phone_idx, phone in enumerate(svc_phones):
                        prefix = f"service[{svc_idx}].phones[{phone_idx}]"
                        check_phone(phone, prefix)

        # Check location phones
        if "location" in data:
            for loc_idx, loc in enumerate(data["location"]):
                loc_phones = loc.get("phones")
                if loc_phones:
                    for phone_idx, phone in enumerate(loc_phones):
                        prefix = f"location[{loc_idx}].phones[{phone_idx}]"
                        check_phone(phone, prefix)

    def calculate_confidence(
        self,
        missing_fields: list[str],
        known_fields: KnownFieldsDict | None = None,
    ) -> float:
        """Calculate confidence score based on missing fields.

        Args:
            missing_fields: List of missing required fields
            known_fields: Optional dict of fields known to exist in input

        Returns:
            float: Confidence score between 0.0 and 1.0
        """
        if not missing_fields:
            return 1.0

        # Start with base confidence
        confidence = 1.0

        # Apply deductions for missing fields
        for field in missing_fields:
            # Check if field is in known fields
            is_known = False
            if known_fields:
                if field in self.REQUIRED_FIELDS["top_level"]:
                    is_known = field in known_fields.get("organization_fields", [])
                elif field.startswith("organization."):
                    is_known = field.split(".")[1] in known_fields.get(
                        "organization_fields", []
                    )
                elif field.startswith("service."):
                    is_known = field.split(".")[1] in known_fields.get(
                        "service_fields", []
                    )
                elif field.startswith("location."):
                    is_known = field.split(".")[1] in known_fields.get(
                        "location_fields", []
                    )
                elif "phones" in field:
                    is_known = field.split(".")[-1] in known_fields.get(
                        "phone_fields", []
                    )
                elif "addresses" in field:
                    is_known = field.split(".")[-1] in known_fields.get(
                        "address_fields", []
                    )
                elif "schedules" in field:
                    is_known = field.split(".")[-1] in known_fields.get(
                        "schedule_fields", []
                    )

            # Check if field is commonly inferrable
            is_inferrable_address = any(
                addr_field in field
                for addr_field in ["city", "state_province", "postal_code"]
            )
            is_inferrable_default = any(
                default_field in field
                for default_field in [
                    "country",
                    "phone.type",
                    "languages",
                    "address_type",
                ]
            )
            is_inferrable_status = any(
                status_field in field
                for status_field in ["status", "location_type", "freq", "wkst"]
            )

            # Apply appropriate deduction
            if is_inferrable_address:
                deduction = self.DEDUCTIONS["inferrable_address"]
            elif is_inferrable_default:
                deduction = self.DEDUCTIONS["inferrable_defaults"]
            elif is_inferrable_status:
                deduction = self.DEDUCTIONS["inferrable_status"]
            elif field in self.REQUIRED_FIELDS["top_level"]:
                deduction = (
                    self.DEDUCTIONS["known_top_level"]
                    if is_known
                    else self.DEDUCTIONS["top_level"]
                )
            elif field.startswith("organization."):
                deduction = (
                    self.DEDUCTIONS["known_organization"]
                    if is_known
                    else self.DEDUCTIONS["organization"]
                )
            elif field.startswith("service."):
                deduction = (
                    self.DEDUCTIONS["known_service"]
                    if is_known
                    else self.DEDUCTIONS["service"]
                )
            elif field.startswith("location."):
                deduction = (
                    self.DEDUCTIONS["known_location"]
                    if is_known
                    else self.DEDUCTIONS["location"]
                )
            else:
                deduction = (
                    self.DEDUCTIONS["known_other"]
                    if is_known
                    else self.DEDUCTIONS["other"]
                )

            confidence -= deduction

        return max(0.0, min(1.0, confidence))

    def generate_feedback(self, missing_fields: list[str]) -> str:
        """Generate feedback message for missing fields.

        Args:
            missing_fields: List of missing required fields

        Returns:
            str: Formatted feedback message
        """
        if not missing_fields:
            return ""

        feedback_parts = ["Missing required fields:"]

        # Group fields by entity type for clearer feedback
        entity_groups: dict[str, list[str]] = {
            "top_level": [],
            "organization": [],
            "service": [],
            "location": [],
            "phone": [],
        }

        for field in missing_fields:
            if field in self.REQUIRED_FIELDS["top_level"]:
                entity_groups["top_level"].append(field)
            elif field.startswith("organization."):
                entity_groups["organization"].append(field.split(".", 1)[1])
            elif field.startswith("service."):
                entity_groups["service"].append(field.split(".", 1)[1])
            elif field.startswith("location."):
                entity_groups["location"].append(field.split(".", 1)[1])
            elif "phones" in field:
                entity_groups["phone"].append(field)

        # Add feedback for each entity type
        for entity, fields in entity_groups.items():
            if fields:
                if entity == "top_level":
                    feedback_parts.append(f"Top-level fields: {', '.join(fields)}")
                else:
                    feedback_parts.append(
                        f"{entity.title()} fields: {', '.join(fields)}"
                    )

        return "\n".join(feedback_parts)

    def validate_location_coordinates(self, location: LocationDict) -> List[str]:
        """Validate location coordinates.

        Args:
            location: Location data to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if "latitude" not in location or "longitude" not in location:
            errors.append("Missing latitude or longitude coordinates")
            return errors

        lat = location["latitude"]
        lon = location["longitude"]

        # Check if coordinates are valid lat/long
        if not self.geocoding_validator.is_valid_lat_long(lat, lon):
            if self.geocoding_validator.is_projected_coordinate(
                lat
            ) or self.geocoding_validator.is_projected_coordinate(lon):
                errors.append("Coordinates appear to be in projected coordinate system")
            else:
                errors.append(f"Invalid coordinates: lat={lat}, lon={lon}")

        # Check against state bounds if address is available
        if location.get("addresses"):
            address = location["addresses"][0]
            if "state_province" in address:
                state = address["state_province"]
                if not self.geocoding_validator.is_within_state_bounds(lat, lon, state):
                    errors.append(f"Coordinates are outside {state} bounds")

        # Check if within US bounds
        if not self.geocoding_validator.is_within_us_bounds(lat, lon):
            # Special handling for HI and AK
            if location.get("addresses"):
                address = location["addresses"][0]
                state = address.get("state_province", "")
                if state not in ["HI", "AK"]:
                    errors.append("Coordinates are outside US bounds")

        return errors

    def correct_location_coordinates(
        self, location: LocationDict
    ) -> Optional[Dict[str, Any]]:
        """Attempt to correct invalid location coordinates.

        Args:
            location: Location data with potentially invalid coordinates

        Returns:
            Corrected location data or None if unable to correct
        """
        if "latitude" not in location or "longitude" not in location:
            return None

        lat = location["latitude"]
        lon = location["longitude"]

        # Extract address information
        state = None
        city = None
        address_str = None

        if location.get("addresses"):
            address = location["addresses"][0]
            state = address.get("state_province")
            city = address.get("city")
            address_str = address.get("address_1")

        # Attempt correction
        corrected_lat, corrected_lon, note = (
            self.geocoding_validator.validate_and_correct_coordinates(
                lat, lon, state, city, address_str
            )
        )

        # Create corrected location
        corrected_location = dict(location)
        corrected_location["latitude"] = corrected_lat
        corrected_location["longitude"] = corrected_lon
        corrected_location["coordinate_correction_note"] = note

        return corrected_location

    def validate_geographic_data(self, hsds_data: HSDSDataDict) -> Dict[str, Any]:
        """Validate all geographic data in HSDS structure.

        Args:
            hsds_data: Complete HSDS data structure

        Returns:
            Validation results with location errors
        """
        result: Dict[str, Any] = {
            "location_errors": [],
            "total_locations": 0,
            "valid_locations": 0,
            "correctable_locations": 0,
        }

        if "location" not in hsds_data:
            return result

        for location in hsds_data["location"]:
            result["total_locations"] += 1
            errors = self.validate_location_coordinates(location)

            if errors:
                result["location_errors"].append(
                    {"location_name": location.get("name", "Unknown"), "errors": errors}
                )

                # Check if correctable
                corrected = self.correct_location_coordinates(location)
                if corrected:
                    # Cast back to LocationDict for validation
                    corrected_location = LocationDict(**corrected)  # type: ignore
                    corrected_errors = self.validate_location_coordinates(
                        corrected_location
                    )
                    if not corrected_errors:
                        result["correctable_locations"] += 1
            else:
                result["valid_locations"] += 1

        return result

    def calculate_location_confidence(self, location: LocationDict) -> float:
        """Calculate confidence score for location data.

        Args:
            location: Location data to score

        Returns:
            Confidence score between 0 and 1
        """
        confidence = 1.0

        # Check for missing required fields
        if "name" not in location:
            confidence -= 0.1
        if "location_type" not in location:
            confidence -= 0.05
        if "addresses" not in location or not location["addresses"]:
            confidence -= 0.15

        # Validate coordinates
        errors = self.validate_location_coordinates(location)
        if errors:
            # Deduct based on error severity
            for error in errors:
                if "projected" in error.lower():
                    confidence -= 0.2  # Projected coordinates are fixable
                elif "outside" in error.lower() and "bounds" in error.lower():
                    confidence -= 0.3  # Wrong location is serious
                else:
                    confidence -= 0.25  # Other coordinate errors

        return max(0.0, min(1.0, confidence))

    def generate_geographic_feedback(
        self, location_errors: List[Dict[str, Any]]
    ) -> str:
        """Generate feedback for geographic validation errors.

        Args:
            location_errors: List of location error dictionaries

        Returns:
            Formatted feedback message
        """
        if not location_errors:
            return "All location coordinates are valid."

        feedback_parts = ["Geographic validation issues found:"]

        for loc_error in location_errors:
            name = loc_error["location_name"]
            errors = loc_error["errors"]

            feedback_parts.append(f"\n{name}:")
            for error in errors:
                feedback_parts.append(f"  - {error}")

        feedback_parts.append("\nSuggestions:")
        feedback_parts.append(
            "- Check if coordinates are in the correct format (decimal degrees)"
        )
        feedback_parts.append("- Verify coordinates match the state in the address")
        feedback_parts.append(
            "- Consider re-geocoding addresses with incorrect coordinates"
        )

        return "\n".join(feedback_parts)

    def correct_location_with_geocoding(self, location: LocationDict) -> LocationDict:
        """Correct location using geocoding integration.

        Args:
            location: Location to correct

        Returns:
            Corrected location
        """
        corrected = self.correct_location_coordinates(location)
        if corrected:
            return LocationDict(**corrected)  # type: ignore
        return location
