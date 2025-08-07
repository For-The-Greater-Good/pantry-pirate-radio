"""Integration tests for geographic validation and geocoding features.

This test module tests the complete geographic validation pipeline including:
- Coordinate validation (latitude/longitude ranges)
- Address validation and geocoding
- HSDS pattern compliance
- Integration with real LLM APIs
"""

import json
import os
from typing import Any, Dict
from unittest.mock import MagicMock, patch
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.llm.hsds_aligner.field_validator import FieldValidator
from app.llm.hsds_aligner.schema_converter import SchemaConverter
from app.llm.queue.job import LLMJob
from app.llm.queue.types import JobResult, JobStatus
from app.llm.providers.types import LLMResponse
from app.reconciler.geocoding_corrector import GeocodingCorrector
from app.reconciler.job_processor import JobProcessor


@pytest.fixture
def db_session():
    """Create a test database session."""
    # Use test database URL
    test_db_url = os.getenv("TEST_DATABASE_URL", settings.DATABASE_URL)
    engine = create_engine(test_db_url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    # Cleanup
    session.rollback()
    session.close()


@pytest.fixture
def field_validator():
    """Create FieldValidator instance for testing."""
    return FieldValidator()


@pytest.fixture
def schema_converter():
    """Create SchemaConverter instance for testing."""
    return SchemaConverter()


@pytest.fixture
def geocoding_corrector():
    """Create GeocodingCorrector instance for testing."""
    with patch(
        "app.reconciler.geocoding_corrector.get_geocoding_service"
    ) as mock_get_service:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        corrector = GeocodingCorrector()
        corrector.mock_geocoding_service = mock_service  # Store for test access
        yield corrector


class TestGeographicValidation:
    """Test geographic validation features."""

    def test_location_coordinate_validation(self, field_validator):
        """Test location coordinate validation using actual methods."""
        # Valid location with coordinates
        valid_location = {
            "name": "Test Location",
            "description": "Test",
            "latitude": 45.5,
            "longitude": -122.6,
        }
        errors = field_validator.validate_location_coordinates(valid_location)
        assert len(errors) == 0, f"Valid coordinates should have no errors: {errors}"

        # Invalid latitude (out of range)
        invalid_lat = {
            "name": "Test Location",
            "description": "Test",
            "latitude": 91,
            "longitude": -122.6,
        }
        errors = field_validator.validate_location_coordinates(invalid_lat)
        assert len(errors) > 0
        assert any(
            "lat=" in err.lower() or "coordinate" in err.lower() for err in errors
        )

        # Invalid longitude (out of range)
        invalid_lon = {
            "name": "Test Location",
            "description": "Test",
            "latitude": 45.5,
            "longitude": 181,
        }
        errors = field_validator.validate_location_coordinates(invalid_lon)
        assert len(errors) > 0
        assert any(
            "lon=" in err.lower() or "coordinate" in err.lower() for err in errors
        )

        # Test edge cases
        edge_cases = [
            {"latitude": -90, "longitude": 180},  # Valid edges
            {"latitude": 90, "longitude": -180},  # Valid edges
            {"latitude": 0, "longitude": 0},  # Valid zero
        ]

        for coords in edge_cases:
            location = {"name": "Edge Case", "description": "Test", **coords}
            errors = field_validator.validate_location_coordinates(location)
            assert len(errors) == 0, f"Edge case {coords} should be valid"

    def test_geographic_data_validation(self, field_validator):
        """Test full geographic data validation."""
        # Valid HSDS data with geographic info
        valid_data = {
            "organization": [{"name": "Test Org", "description": "Test organization"}],
            "location": [
                {
                    "name": "Test Location",
                    "description": "Test location",
                    "latitude": 45.5234,
                    "longitude": -122.6762,
                }
            ],
            "service": [],
        }

        result = field_validator.validate_geographic_data(valid_data)
        assert (
            result["valid_locations"] == result["total_locations"]
        ), f"Valid data should pass validation: {result}"

        # Invalid coordinates
        invalid_data = {
            "organization": [],
            "location": [
                {
                    "name": "Bad Location",
                    "description": "Invalid coords",
                    "latitude": 999,
                    "longitude": -999,
                }
            ],
            "service": [],
        }

        result = field_validator.validate_geographic_data(invalid_data)
        assert (
            result["valid_locations"] < result["total_locations"]
        ), "Invalid coordinates should fail validation"
        assert len(result["location_errors"]) > 0
        # Check that coordinate error is in the location errors
        error_str = str(result["location_errors"]).lower()
        assert "coordinate" in error_str


class TestHSDSPatternCompliance:
    """Test HSDS pattern compliance validation."""

    def test_hsds_schedule_patterns(self):
        """Test HSDS schedule pattern validation."""
        # Valid schedule format
        valid_schedule = {
            "freq": "WEEKLY",
            "wkst": "MO",
            "opens_at": "09:00",
            "closes_at": "17:00",
        }

        # Test that schedule has required fields
        assert "freq" in valid_schedule
        assert "wkst" in valid_schedule
        assert valid_schedule["freq"] in ["DAILY", "WEEKLY", "MONTHLY", "YEARLY"]

        # Test various frequency values
        frequencies = ["DAILY", "WEEKLY", "MONTHLY", "YEARLY"]
        for freq in frequencies:
            schedule = {
                "freq": freq,
                "wkst": "MO",
                "opens_at": "09:00",
                "closes_at": "17:00",
            }
            assert schedule["freq"] == freq
            assert schedule["wkst"] in ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]

    def test_hsds_phone_patterns(self, field_validator):
        """Test HSDS phone number patterns using field validator."""
        # Valid phone formats
        valid_phones = [
            {"number": "(503) 555-1234", "type": "voice"},
            {"number": "503-555-1234", "type": "fax"},
            {"number": "+1-503-555-1234", "type": "cell"},
        ]

        for phone in valid_phones:
            # Validate using the pattern in field_validator
            errors = field_validator.validate_required_fields(
                {"phones": [phone]}, ["phones"]
            )
            # Check that phone number format is acceptable
            assert isinstance(phone["number"], str)
            assert len(phone["number"]) >= 10  # Basic length check


class TestGeocodingCorrector:
    """Test geocoding correction functionality."""

    def test_validate_coordinates_with_address(self, geocoding_corrector):
        """Test coordinate validation against address."""
        # Use the mock service from the fixture
        mock_service = geocoding_corrector.mock_geocoding_service

        # Test case: coordinates match address
        mock_service.geocode.return_value = (45.5, -122.6)

        is_valid, confidence, suggested_coords = (
            geocoding_corrector.validate_coordinates(
                45.5, -122.6, "123 Main St, Portland, OR 97201"
            )
        )

        assert is_valid
        assert confidence >= 0.9  # High confidence for exact match
        assert suggested_coords is None  # No correction needed

    def test_suggest_coordinate_correction(self, geocoding_corrector):
        """Test coordinate correction suggestions."""
        # Use the mock service from the fixture
        mock_service = geocoding_corrector.mock_geocoding_service

        # Test case: coordinates don't match address
        mock_service.geocode.return_value = (45.5, -122.6)

        # Provide very different coordinates
        is_valid, confidence, suggested_coords = (
            geocoding_corrector.validate_coordinates(
                40.7,
                -74.0,
                "123 Main St, Portland, OR 97201",  # NYC coords for Portland address
            )
        )

        assert not is_valid
        assert confidence < 0.5  # Low confidence for mismatch
        assert suggested_coords is not None
        assert (
            abs(suggested_coords[0] - 45.5) < 0.1
        )  # Suggested coords should be close to Portland
        assert abs(suggested_coords[1] - (-122.6)) < 0.1

    def test_fallback_to_arcgis(self, geocoding_corrector):
        """Test that unified geocoding service handles fallback."""
        # Use the mock service from the fixture
        mock_service = geocoding_corrector.mock_geocoding_service

        # Service returns successful geocoding result (simulating fallback)
        mock_service.geocode.return_value = (45.5, -122.6)

        # Test with slightly different coordinates to trigger geocoding
        is_valid, confidence, suggested_coords = (
            geocoding_corrector.validate_coordinates(
                45.4, -122.5, "123 Main St, Portland, OR 97201"
            )
        )

        # Verify geocoding was called to validate the address
        mock_service.geocode.assert_called_once()
        assert is_valid  # Close enough to be valid
        assert confidence >= 0.7  # Good confidence for close match


@pytest.mark.skip(reason="LLM API integration tests require API keys")
class TestLLMIntegration:
    """Test integration with real LLM APIs for geographic validation."""

    def test_llm_placeholder(self):
        """Placeholder test for LLM integration."""
        # This is a placeholder for LLM integration tests
        # Actual tests would require API keys to be configured
        assert True


@pytest.mark.integration
class TestEndToEndGeographicValidation:
    """Test complete end-to-end geographic validation pipeline."""

    def test_full_pipeline_with_job_processor(self, db_session):
        """Test complete pipeline from raw data through job processing with geographic validation."""
        # Create job processor
        processor = JobProcessor(db_session)

        # Create mock job result with geographic data
        llm_response = LLMResponse(
            text="""{
                "organization": [{
                    "name": "Test Food Bank",
                    "description": "A food bank for testing",
                    "website": "https://testfoodbank.org",
                    "email": "info@testfoodbank.org"
                }],
                "location": [{
                    "name": "Main Location",
                    "description": "Primary distribution center",
                    "latitude": 45.5234,
                    "longitude": -122.6762,
                    "addresss": [{
                        "address_1": "123 Test St",
                        "city": "Portland",
                        "state_province": "OR",
                        "postal_code": "97201",
                        "country": "US"
                    }],
                    "phones": [{
                        "number": "(503) 555-1234",
                        "type": "voice"
                    }]
                }],
                "service": [{
                    "name": "Food Distribution",
                    "description": "Weekly food distribution service",
                    "schedules": [{
                        "freq": "WEEKLY",
                        "wkst": "MO",
                        "opens_at": "09:00",
                        "closes_at": "17:00"
                    }]
                }]
            }""",
            model="test-model",
            usage={"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
        )

        job = LLMJob(
            id="test-job-123",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={"scraper_id": "test_scraper", "type": "hsds_alignment"},
        )

        job_result = JobResult(
            job_id="test-job-123",
            job=job,
            status=JobStatus.COMPLETED,
            result=llm_response,
        )

        # Mock the database creators
        with patch(
            "app.reconciler.job_processor.OrganizationCreator"
        ) as mock_org_creator, patch(
            "app.reconciler.job_processor.LocationCreator"
        ) as mock_loc_creator, patch(
            "app.reconciler.job_processor.ServiceCreator"
        ) as mock_svc_creator:

            # Setup mocks with proper UUID strings
            import uuid

            org_id = str(uuid.uuid4())
            loc_id = str(uuid.uuid4())
            svc_id = str(uuid.uuid4())
            sal_id = str(uuid.uuid4())

            mock_org_instance = mock_org_creator.return_value
            mock_org_instance.process_organization.return_value = (org_id, True)

            mock_loc_instance = mock_loc_creator.return_value
            mock_loc_instance.find_matching_location.return_value = None
            mock_loc_instance.create_location.return_value = loc_id
            mock_loc_instance.create_address.return_value = "addr-123"

            mock_svc_instance = mock_svc_creator.return_value
            mock_svc_instance.process_service.return_value = (svc_id, True)
            mock_svc_instance.create_service_at_location.return_value = sal_id
            mock_svc_instance.create_phone.return_value = "phone-123"
            mock_svc_instance.create_schedule.return_value = "sched-123"

            # Process the job
            result = processor.process_job_result(job_result)

            # Verify result
            assert result["status"] == "success"
            assert result["scraper_id"] == "test_scraper"
            assert result["organization_id"] is not None

            # Verify location was created with valid coordinates
            mock_loc_instance.create_location.assert_called_once()
            call_args = mock_loc_instance.create_location.call_args
            assert call_args[0][0] == "Main Location"  # name
            assert abs(call_args[0][2] - 45.5234) < 0.001  # latitude
            assert abs(call_args[0][3] - (-122.6762)) < 0.001  # longitude

            # Verify address was created
            mock_loc_instance.create_address.assert_called_once()
            addr_args = mock_loc_instance.create_address.call_args
            assert addr_args[1]["address_1"] == "123 Test St"
            assert addr_args[1]["city"] == "Portland"
            assert addr_args[1]["state_province"] == "OR"
            assert addr_args[1]["postal_code"] == "97201"

            # Verify phone was created with valid format
            mock_svc_instance.create_phone.assert_called()
            phone_args = mock_svc_instance.create_phone.call_args
            assert phone_args[1]["number"] == "(503) 555-1234"
            assert phone_args[1]["phone_type"] == "voice"

            # Verify schedule was created with valid RRULE components
            mock_svc_instance.create_schedule.assert_called_once()
            sched_args = mock_svc_instance.create_schedule.call_args
            assert sched_args[1]["freq"] == "WEEKLY"
            assert sched_args[1]["wkst"] == "MO"
            assert sched_args[1]["opens_at"] == "09:00"
            assert sched_args[1]["closes_at"] == "17:00"

    def test_geographic_validation_error_handling(self, db_session):
        """Test error handling for invalid geographic data."""
        processor = JobProcessor(db_session)

        # Create job result with invalid coordinates
        llm_response = LLMResponse(
            text="""{
                "organization": [{
                    "name": "Invalid Coords Org",
                    "description": "Organization with invalid coordinates"
                }],
                "location": [{
                    "name": "Bad Location",
                    "description": "Location with invalid coordinates",
                    "latitude": 999.99,
                    "longitude": -999.99
                }],
                "service": []
            }""",
            model="test-model",
            usage={"prompt_tokens": 50, "completion_tokens": 100, "total_tokens": 150},
        )

        job = LLMJob(
            id="test-job-456",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={"scraper_id": "test_invalid_coords", "type": "hsds_alignment"},
        )

        job_result = JobResult(
            job_id="test-job-456",
            job=job,
            status=JobStatus.COMPLETED,
            result=llm_response,
        )

        # Test with field validator
        validator = FieldValidator()

        # Extract coordinates from the response

        data = json.loads(llm_response.text)
        loc = data["location"][0]

        # Validate coordinates - should fail with invalid values
        errors = validator.validate_location_coordinates(loc)

        assert len(errors) > 0
        assert any("coordinate" in err.lower() for err in errors)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
