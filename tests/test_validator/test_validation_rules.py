"""Tests for validation rules."""

import pytest
from typing import Dict, Any

from app.validator.rules import ValidationRules


class TestValidationRules:
    """Test validation rules for post-enrichment location data."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = ValidationRules()

        # Good location data
        self.valid_location = {
            "name": "Community Food Bank",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "address": "456 Broadway",
            "city": "New York",
            "state": "NY",
            "postal_code": "10013",
            "geocoding_source": "arcgis",
        }

    def test_check_coordinates_present(self):
        """Test detection of missing coordinates."""
        # Valid coordinates
        result = self.validator.check_coordinates_present(self.valid_location)
        assert result == (True, 0, "Coordinates present")

        # Missing latitude
        location = {**self.valid_location, "latitude": None}
        result = self.validator.check_coordinates_present(location)
        assert result == (False, -100, "Missing coordinates after enrichment")

        # Missing longitude
        location = {**self.valid_location, "longitude": None}
        result = self.validator.check_coordinates_present(location)
        assert result == (False, -100, "Missing coordinates after enrichment")

        # Both missing
        location = {**self.valid_location, "latitude": None, "longitude": None}
        result = self.validator.check_coordinates_present(location)
        assert result == (False, -100, "Missing coordinates after enrichment")

    def test_check_zero_coordinates(self):
        """Test detection of 0,0 coordinates."""
        # Valid coordinates
        result = self.validator.check_zero_coordinates(self.valid_location)
        assert result == (True, 0, "Valid coordinates")

        # Exact 0,0
        location = {**self.valid_location, "latitude": 0.0, "longitude": 0.0}
        result = self.validator.check_zero_coordinates(location)
        assert result == (False, -100, "Invalid 0,0 coordinates")

        # Near zero (0.0001, 0.0001)
        location = {**self.valid_location, "latitude": 0.0001, "longitude": 0.0001}
        result = self.validator.check_zero_coordinates(location)
        assert result == (False, -100, "Near-zero coordinates detected")

        # One zero, one valid
        location = {**self.valid_location, "latitude": 0.0, "longitude": -74.0060}
        result = self.validator.check_zero_coordinates(location)
        assert result == (True, 0, "Valid coordinates")  # Only both at 0,0 is invalid

    def test_check_us_bounds(self):
        """Test US bounds checking including Alaska and Hawaii."""
        # Continental US
        result = self.validator.check_us_bounds(self.valid_location)
        assert result == (True, 0, "Within US bounds")

        # Alaska
        location = {
            **self.valid_location,
            "latitude": 61.2181,
            "longitude": -149.9003,
            "state": "AK",
        }
        result = self.validator.check_us_bounds(location)
        assert result == (True, 0, "Within US bounds")

        # Hawaii
        location = {
            **self.valid_location,
            "latitude": 21.3099,
            "longitude": -157.8581,
            "state": "HI",
        }
        result = self.validator.check_us_bounds(location)
        assert result == (True, 0, "Within US bounds")

        # Outside US (London)
        location = {**self.valid_location, "latitude": 51.5074, "longitude": -0.1276}
        result = self.validator.check_us_bounds(location)
        assert result == (False, -95, "Outside US bounds")

    def test_verify_state_match(self):
        """Test state boundary verification."""
        # Correct state
        result = self.validator.verify_state_match(self.valid_location)
        assert result == (True, 0, "Coordinates match state")

        # Wrong state (NY coords but claims CA)
        location = {**self.valid_location, "state": "CA"}
        result = self.validator.verify_state_match(location)
        assert result == (False, -20, "Coordinates outside claimed state: CA")

        # No state provided
        location = {**self.valid_location, "state": None}
        result = self.validator.verify_state_match(location)
        assert result == (True, -5, "No state specified")

        # Invalid state code
        location = {**self.valid_location, "state": "XX"}
        result = self.validator.verify_state_match(location)
        assert result == (False, -10, "Invalid state code: XX")

    def test_detect_test_data(self):
        """Test detection of test/demo data patterns."""
        # Normal location
        result = self.validator.detect_test_data(self.valid_location)
        assert result == (True, 0, "No test data indicators")

        # Test in name
        location = {**self.valid_location, "name": "Test Food Bank"}
        result = self.validator.detect_test_data(location)
        assert result == (False, -95, "Test data detected in name")

        # Demo in name
        location = {**self.valid_location, "name": "Demo Pantry"}
        result = self.validator.detect_test_data(location)
        assert result == (False, -95, "Test data detected in name")

        # Anytown city
        location = {**self.valid_location, "city": "Anytown"}
        result = self.validator.detect_test_data(location)
        assert result == (False, -95, "Test data detected in city")

        # Unknown city
        location = {**self.valid_location, "city": "Unknown"}
        result = self.validator.detect_test_data(location)
        assert result == (False, -95, "Test data detected in city")

        # Test postal code 00000
        location = {**self.valid_location, "postal_code": "00000"}
        result = self.validator.detect_test_data(location)
        assert result == (False, -95, "Test postal code: 00000")

        # Test postal code 99999
        location = {**self.valid_location, "postal_code": "99999"}
        result = self.validator.detect_test_data(location)
        assert result == (False, -95, "Test postal code: 99999")

        # Test in address
        location = {**self.valid_location, "address": "123 Test Street"}
        result = self.validator.detect_test_data(location)
        assert result == (False, -95, "Test data detected in address")

        # Example in name
        location = {**self.valid_location, "name": "Example Food Distribution"}
        result = self.validator.detect_test_data(location)
        assert result == (False, -95, "Test data detected in name")

    def test_detect_placeholder_addresses(self):
        """Test detection of generic/placeholder addresses."""
        # Real address
        result = self.validator.detect_placeholder_addresses(self.valid_location)
        assert result == (True, 0, "Valid address")

        # Classic placeholder: 123 Main St
        location = {**self.valid_location, "address": "123 Main Street"}
        result = self.validator.detect_placeholder_addresses(location)
        assert result == (False, -75, "Placeholder address detected")

        # Variation: 123 Main St
        location = {**self.valid_location, "address": "123 Main St"}
        result = self.validator.detect_placeholder_addresses(location)
        assert result == (False, -75, "Placeholder address detected")

        # 1 Main Street
        location = {**self.valid_location, "address": "1 Main Street"}
        result = self.validator.detect_placeholder_addresses(location)
        assert result == (False, -75, "Placeholder address detected")

        # 123 First Street
        location = {**self.valid_location, "address": "123 First Street"}
        result = self.validator.detect_placeholder_addresses(location)
        assert result == (False, -75, "Placeholder address detected")

        # 1234 Main St (4 digits should be OK)
        location = {**self.valid_location, "address": "1234 Main Street"}
        result = self.validator.detect_placeholder_addresses(location)
        assert result == (True, 0, "Valid address")

        # Test Avenue
        location = {**self.valid_location, "address": "1 Test Avenue"}
        result = self.validator.detect_placeholder_addresses(location)
        assert result == (False, -75, "Placeholder address detected")

        # Example Road
        location = {**self.valid_location, "address": "123 Example Road"}
        result = self.validator.detect_placeholder_addresses(location)
        assert result == (False, -75, "Placeholder address detected")

        # No address
        location = {**self.valid_location, "address": None}
        result = self.validator.detect_placeholder_addresses(location)
        assert result == (True, -10, "No address provided")

        # Empty address
        location = {**self.valid_location, "address": ""}
        result = self.validator.detect_placeholder_addresses(location)
        assert result == (True, -10, "No address provided")

    def test_assess_geocoding_confidence(self):
        """Test assessment of geocoding source quality."""
        # ArcGIS (high confidence)
        location = {**self.valid_location, "geocoding_source": "arcgis"}
        result = self.validator.assess_geocoding_confidence(location)
        assert result == (True, 0, "High confidence geocoding: arcgis")

        # Nominatim (medium confidence)
        location = {**self.valid_location, "geocoding_source": "nominatim"}
        result = self.validator.assess_geocoding_confidence(location)
        assert result == (True, -5, "Medium confidence geocoding: nominatim")

        # Census (lower confidence)
        location = {**self.valid_location, "geocoding_source": "census"}
        result = self.validator.assess_geocoding_confidence(location)
        assert result == (True, -10, "Lower confidence geocoding: census")

        # State centroid fallback
        location = {**self.valid_location, "geocoding_source": "state_centroid"}
        result = self.validator.assess_geocoding_confidence(location)
        assert result == (False, -15, "Fallback geocoding: state_centroid")

        # Fallback
        location = {**self.valid_location, "geocoding_source": "fallback"}
        result = self.validator.assess_geocoding_confidence(location)
        assert result == (False, -15, "Fallback geocoding: fallback")

        # No geocoding source
        location = {**self.valid_location, "geocoding_source": None}
        result = self.validator.assess_geocoding_confidence(location)
        assert result == (False, -20, "No geocoding source")

        # Unknown source
        location = {**self.valid_location, "geocoding_source": "unknown"}
        result = self.validator.assess_geocoding_confidence(location)
        assert result == (True, -5, "Unknown geocoding source: unknown")

    def test_validate_location_complete(self):
        """Test complete location validation."""
        # Perfect location
        results = self.validator.validate_location(self.valid_location)
        assert results["has_coordinates"] is True
        assert results["is_zero_coordinates"] is False
        assert results["within_us_bounds"] is True
        assert results["within_state_bounds"] is True
        assert results["is_test_data"] is False
        assert results["has_placeholder_address"] is False
        assert results["geocoding_confidence"] == "high"
        assert results["validation_passed"] is True

        # Location with multiple issues
        bad_location = {
            "name": "Test Food Bank",
            "latitude": 0.0,
            "longitude": 0.0,
            "address": "123 Main Street",
            "city": "Anytown",
            "state": "XX",
            "postal_code": "00000",
            "geocoding_source": "fallback",
        }
        results = self.validator.validate_location(bad_location)
        assert results["has_coordinates"] is True  # Present but invalid
        assert results["is_zero_coordinates"] is True
        assert results["within_us_bounds"] is False
        assert results["within_state_bounds"] is False
        assert results["is_test_data"] is True
        assert results["has_placeholder_address"] is True
        assert results["geocoding_confidence"] == "fallback"
        assert results["validation_passed"] is False

    def test_check_missing_fields(self):
        """Test detection of missing important fields."""
        # All fields present
        result = self.validator.check_missing_fields(self.valid_location)
        assert result["missing_postal"] is False
        assert result["missing_city"] is False
        assert result["missing_address"] is False
        assert result["field_completeness"] == 1.0

        # Missing postal
        location = {**self.valid_location, "postal_code": None}
        result = self.validator.check_missing_fields(location)
        assert result["missing_postal"] is True
        assert result["missing_city"] is False

        # Missing city
        location = {**self.valid_location, "city": None}
        result = self.validator.check_missing_fields(location)
        assert result["missing_postal"] is False
        assert result["missing_city"] is True

        # Missing address
        location = {**self.valid_location, "address": ""}
        result = self.validator.check_missing_fields(location)
        assert result["missing_address"] is True

        # Multiple missing
        location = {
            **self.valid_location,
            "postal_code": None,
            "city": "",
            "address": None,
        }
        result = self.validator.check_missing_fields(location)
        assert result["missing_postal"] is True
        assert result["missing_city"] is True
        assert result["missing_address"] is True
        assert result["field_completeness"] < 1.0

    def test_validation_with_organizations(self):
        """Test validation of organization-level data."""
        org_data = {
            "organization": {
                "name": "Food Bank Network",
                "description": "Serving the community",
            },
            "locations": [
                self.valid_location,
                {
                    "name": "Test Location",
                    "latitude": 0.0,
                    "longitude": 0.0,
                    "address": "123 Main St",
                    "city": "Anytown",
                    "state": "NY",
                    "postal_code": "00000",
                },
            ],
        }

        # Validate organization data
        results = self.validator.validate_job_data(org_data)
        assert "organization_validation" in results
        assert "location_validations" in results
        assert len(results["location_validations"]) == 2

        # First location should pass
        assert results["location_validations"][0]["validation_passed"] is True

        # Second location should fail (test data)
        assert results["location_validations"][1]["validation_passed"] is False
        assert results["location_validations"][1]["is_test_data"] is True
