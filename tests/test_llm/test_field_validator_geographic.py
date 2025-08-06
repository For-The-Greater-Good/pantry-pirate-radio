"""Tests for geographic validation in field validator."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from app.llm.hsds_aligner.field_validator import FieldValidator
from app.llm.hsds_aligner.type_defs import HSDSDataDict, LocationDict


class TestFieldValidatorGeographic:
    """Test suite for geographic validation in FieldValidator."""

    @pytest.fixture
    def validator(self):
        """Create a FieldValidator instance for testing."""
        return FieldValidator()

    def test_validate_location_coordinates(self, validator):
        """Test validation of location coordinates."""
        # Valid location with good coordinates
        valid_location: LocationDict = {
            "name": "Test Location",
            "location_type": "physical",
            "latitude": 35.7596,
            "longitude": -79.0193,
            "addresses": [
                {
                    "address_1": "123 Main St",
                    "city": "Raleigh",
                    "state_province": "NC",
                    "postal_code": "27601",
                    "country": "US",
                    "address_type": "physical",
                }
            ],
            "phones": [],
            "accessibility": [],
            "contacts": [],
            "schedules": [],
            "languages": [],
            "metadata": [],
        }

        errors = validator.validate_location_coordinates(valid_location)
        assert len(errors) == 0

        # Location with projected coordinates
        projected_location: LocationDict = {
            "name": "Test Location",
            "location_type": "physical",
            "latitude": 4716694.4390345,
            "longitude": -8553893.75627903,
            "addresses": [
                {
                    "address_1": "123 Main St",
                    "city": "Lanham",
                    "state_province": "MD",
                    "postal_code": "20706",
                    "country": "US",
                    "address_type": "physical",
                }
            ],
            "phones": [],
            "accessibility": [],
            "contacts": [],
            "schedules": [],
            "languages": [],
            "metadata": [],
        }

        errors = validator.validate_location_coordinates(projected_location)
        assert len(errors) > 0
        assert any("projected" in error.lower() for error in errors)

        # Location with coordinates outside state bounds
        wrong_state_location: LocationDict = {
            "name": "Test Location",
            "location_type": "physical",
            "latitude": 52.5024461,  # UK coordinates
            "longitude": -1.9009857,
            "addresses": [
                {
                    "address_1": "123 Main St",
                    "city": "Thomasville",
                    "state_province": "NC",
                    "postal_code": "27360",
                    "country": "US",
                    "address_type": "physical",
                }
            ],
            "phones": [],
            "accessibility": [],
            "contacts": [],
            "schedules": [],
            "languages": [],
            "metadata": [],
        }

        errors = validator.validate_location_coordinates(wrong_state_location)
        assert len(errors) > 0
        assert any(
            "outside" in error.lower() or "bounds" in error.lower() for error in errors
        )

    def test_validate_and_correct_location(self, validator):
        """Test automatic correction of location coordinates."""
        # Location with projected coordinates that can be corrected
        location_with_projection: LocationDict = {
            "name": "Test Location",
            "location_type": "physical",
            "latitude": 4711637.75015076,
            "longitude": -8555931.90483597,
            "addresses": [
                {
                    "address_1": "123 Main St",
                    "city": "Lanham",
                    "state_province": "MD",
                    "postal_code": "20706",
                    "country": "US",
                    "address_type": "physical",
                }
            ],
            "phones": [],
            "accessibility": [],
            "contacts": [],
            "schedules": [],
            "languages": [],
            "metadata": [],
        }

        corrected = validator.correct_location_coordinates(location_with_projection)
        assert corrected is not None
        assert -90 <= corrected["latitude"] <= 90
        assert -180 <= corrected["longitude"] <= 180
        assert corrected.get("coordinate_correction_note") is not None

    def test_validate_hsds_data_with_locations(self, validator):
        """Test validation of complete HSDS data with location coordinates."""
        hsds_data: HSDSDataDict = {
            "organization": [
                {
                    "name": "Test Org",
                    "description": "Test organization",
                    "services": [],
                    "phones": [],
                    "organization_identifiers": [],
                    "contacts": [],
                    "metadata": [],
                }
            ],
            "service": [
                {
                    "name": "Test Service",
                    "description": "Test service",
                    "status": "active",
                    "phones": [],
                    "schedules": [],
                }
            ],
            "location": [
                {
                    "name": "Good Location",
                    "location_type": "physical",
                    "latitude": 35.7596,
                    "longitude": -79.0193,
                    "addresses": [
                        {
                            "address_1": "123 Main St",
                            "city": "Raleigh",
                            "state_province": "NC",
                            "postal_code": "27601",
                            "country": "US",
                            "address_type": "physical",
                        }
                    ],
                    "phones": [],
                    "accessibility": [],
                    "contacts": [],
                    "schedules": [],
                    "languages": [],
                    "metadata": [],
                },
                {
                    "name": "Bad Location",
                    "location_type": "physical",
                    "latitude": 52.5024461,  # Wrong coordinates
                    "longitude": -1.9009857,
                    "addresses": [
                        {
                            "address_1": "456 Oak St",
                            "city": "Charlotte",
                            "state_province": "NC",
                            "postal_code": "28202",
                            "country": "US",
                            "address_type": "physical",
                        }
                    ],
                    "phones": [],
                    "accessibility": [],
                    "contacts": [],
                    "schedules": [],
                    "languages": [],
                    "metadata": [],
                },
            ],
        }

        validation_result = validator.validate_geographic_data(hsds_data)
        assert "location_errors" in validation_result
        assert (
            len(validation_result["location_errors"]) == 1
        )  # Only bad location has errors
        assert (
            validation_result["location_errors"][0]["location_name"] == "Bad Location"
        )
        assert len(validation_result["location_errors"][0]["errors"]) > 0

    def test_calculate_geographic_confidence(self, validator):
        """Test confidence scoring with geographic validation."""
        # Good location data
        good_location: LocationDict = {
            "name": "Test Location",
            "location_type": "physical",
            "latitude": 35.7596,
            "longitude": -79.0193,
            "addresses": [
                {
                    "address_1": "123 Main St",
                    "city": "Raleigh",
                    "state_province": "NC",
                    "postal_code": "27601",
                    "country": "US",
                    "address_type": "physical",
                }
            ],
            "phones": [],
            "accessibility": [],
            "contacts": [],
            "schedules": [],
            "languages": [],
            "metadata": [],
        }

        confidence = validator.calculate_location_confidence(good_location)
        assert confidence >= 0.9  # High confidence for valid coordinates

        # Bad location data
        bad_location: LocationDict = {
            "name": "Test Location",
            "location_type": "physical",
            "latitude": 52.5024461,  # Wrong coordinates
            "longitude": -1.9009857,
            "addresses": [
                {
                    "address_1": "123 Main St",
                    "city": "Charlotte",
                    "state_province": "NC",
                    "postal_code": "28202",
                    "country": "US",
                    "address_type": "physical",
                }
            ],
            "phones": [],
            "accessibility": [],
            "contacts": [],
            "schedules": [],
            "languages": [],
            "metadata": [],
        }

        confidence = validator.calculate_location_confidence(bad_location)
        assert confidence < 0.7  # Lower confidence for invalid coordinates

    def test_generate_geographic_feedback(self, validator):
        """Test generation of feedback for geographic issues."""
        location_errors = [
            {
                "location_name": "Test Location",
                "errors": [
                    "Coordinates appear to be in projected coordinate system",
                    "Coordinates are outside NC bounds",
                ],
            }
        ]

        feedback = validator.generate_geographic_feedback(location_errors)
        assert feedback is not None
        assert "Test Location" in feedback
        assert "projected" in feedback.lower()
        assert "bounds" in feedback.lower()

    def test_integration_with_geocoding_validator(self, validator):
        """Test integration with GeocodingValidator."""
        # Mock the geocoding validator instance method
        with patch.object(
            validator.geocoding_validator, "validate_and_correct_coordinates"
        ) as mock_validate:
            mock_validate.return_value = (
                35.7596,
                -79.0193,
                "Corrected from projection",
            )

            location: LocationDict = {
                "name": "Test Location",
                "location_type": "physical",
                "latitude": 4711637.75015076,
                "longitude": -8555931.90483597,
                "addresses": [
                    {
                        "address_1": "123 Main St",
                        "city": "Raleigh",
                        "state_province": "NC",
                        "postal_code": "27601",
                        "country": "US",
                        "address_type": "physical",
                    }
                ],
                "phones": [],
                "accessibility": [],
                "contacts": [],
                "schedules": [],
                "languages": [],
                "metadata": [],
            }

            corrected = validator.correct_location_with_geocoding(location)
            assert corrected["latitude"] == 35.7596
            assert corrected["longitude"] == -79.0193
            mock_validate.assert_called_once()
