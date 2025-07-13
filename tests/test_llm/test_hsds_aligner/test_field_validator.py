"""Tests for HSDS field validation."""

import pytest

from app.llm.hsds_aligner.field_validator import FieldValidator
from app.llm.hsds_aligner.type_defs import (
    AddressDict,
    HSDSDataDict,
    KnownFieldsDict,
    LocationDict,
    OrganizationDict,
    PhoneDict,
    ServiceDict,
)


@pytest.fixture
def validator() -> FieldValidator:
    """Create a field validator instance."""
    return FieldValidator()


@pytest.fixture
def valid_phone() -> PhoneDict:
    """Create a valid phone object."""
    return {
        "number": "123-456-7890",
        "type": "voice",
        "languages": [{"name": "English"}],
    }


@pytest.fixture
def valid_address() -> AddressDict:
    """Create a valid address object."""
    return {
        "address_1": "123 Test St",
        "city": "Test City",
        "state_province": "TS",
        "postal_code": "12345",
        "country": "US",
        "address_type": "physical",
    }


@pytest.fixture
def valid_hsds_data(valid_phone: PhoneDict, valid_address: AddressDict) -> HSDSDataDict:
    """Create valid HSDS data for testing."""
    return {
        "organization": [
            {
                "name": "Test Org",
                "description": "A test organization",
                "services": [],  # Empty but valid
                "phones": [valid_phone],
                "organization_identifiers": [
                    {"identifier_type": "test", "identifier": "123"}
                ],
                "contacts": [],
                "metadata": [
                    {
                        "resource_id": "test",
                        "resource_type": "organization",
                        "last_action_date": "2024-01-01",
                        "last_action_type": "create",
                    }
                ],
            }
        ],
        "service": [
            {
                "name": "Test Service",
                "description": "A test service",
                "status": "active",
                "phones": [valid_phone],
                "schedules": [
                    {
                        "freq": "WEEKLY",
                        "wkst": "MO",
                        "opens_at": "09:00",
                        "closes_at": "17:00",
                    }
                ],
            }
        ],
        "location": [
            {
                "name": "Test Location",
                "location_type": "physical",
                "addresses": [valid_address],
                "phones": [valid_phone],
                "accessibility": [],
                "contacts": [],
                "schedules": [
                    {
                        "freq": "WEEKLY",
                        "wkst": "MO",
                        "opens_at": "09:00",
                        "closes_at": "17:00",
                    }
                ],
                "languages": [],
                "metadata": [
                    {
                        "resource_id": "test",
                        "resource_type": "location",
                        "last_action_date": "2024-01-01",
                        "last_action_type": "create",
                    }
                ],
                "latitude": 42.0,
                "longitude": -73.0,
            }
        ],
    }


def test_validate_required_fields_valid(
    validator: FieldValidator, valid_hsds_data: HSDSDataDict
) -> None:
    """Test validation of valid HSDS data."""
    missing_fields = validator.validate_required_fields(valid_hsds_data)
    assert not missing_fields, "Expected no missing fields"


def test_validate_required_fields_missing_top_level(validator: FieldValidator) -> None:
    """Test validation when top-level fields are missing."""
    data: HSDSDataDict = {
        "organization": [],
        "service": [],  # Empty but present
        "location": [],  # Empty but present
    }
    missing_fields = validator.validate_required_fields(data)
    assert not missing_fields, "Expected no missing fields for empty arrays"


def test_validate_required_fields_missing_organization_fields(
    validator: FieldValidator,
) -> None:
    """Test validation when organization fields are missing."""
    org: OrganizationDict = {
        "name": "Test Org",
        "description": "",  # Empty but present
        "services": [],  # Empty but present
        "phones": [],  # Empty but present
        "organization_identifiers": [],  # Empty but present
        "contacts": [],  # Empty but present
        "metadata": [],  # Empty but present
    }
    data: HSDSDataDict = {
        "organization": [org],
        "service": [],
        "location": [],
    }
    missing_fields = validator.validate_required_fields(data)
    assert not missing_fields, "Expected no missing fields for empty required fields"


def test_validate_required_fields_missing_service_fields(
    validator: FieldValidator,
) -> None:
    """Test validation when service fields are missing."""
    service: ServiceDict = {
        "name": "Test Service",
        "description": "",  # Empty but present
        "status": "active",
        "phones": [],  # Empty but present
        "schedules": [],  # Empty but present
    }
    data: HSDSDataDict = {
        "organization": [],
        "service": [service],
        "location": [],
    }
    missing_fields = validator.validate_required_fields(data)
    assert not missing_fields, "Expected no missing fields for empty required fields"


def test_validate_required_fields_missing_location_fields(
    validator: FieldValidator,
) -> None:
    """Test validation when location fields are missing."""
    location: LocationDict = {
        "name": "Test Location",
        "location_type": "physical",
        "addresses": [],  # Empty but present
        "phones": [],  # Empty but present
        "accessibility": [],  # Empty but present
        "contacts": [],  # Empty but present
        "schedules": [],  # Empty but present
        "languages": [],  # Empty but present
        "metadata": [],  # Empty but present
        "latitude": 0.0,
        "longitude": 0.0,
    }
    data: HSDSDataDict = {
        "organization": [],
        "service": [],
        "location": [location],
    }
    missing_fields = validator.validate_required_fields(data)
    assert not missing_fields, "Expected no missing fields for empty required fields"


def test_validate_phone_fields(
    validator: FieldValidator, valid_phone: PhoneDict
) -> None:
    """Test validation of phone fields."""
    org: OrganizationDict = {
        "name": "Test Org",
        "description": "Test",
        "services": [],
        "phones": [valid_phone],  # Valid phone
        "organization_identifiers": [],
        "contacts": [],
        "metadata": [],
    }
    data: HSDSDataDict = {
        "organization": [org],
        "service": [],
        "location": [],
    }
    missing_fields = validator.validate_required_fields(data)
    assert not missing_fields, "Expected no missing fields for valid phone"

    # Test with invalid phone
    invalid_phone: PhoneDict = {
        "number": "",  # Empty but present
        "type": "voice",
        "languages": [],  # Empty but present
    }
    org["phones"] = [invalid_phone]
    missing_fields = validator.validate_required_fields(data)
    assert not missing_fields, "Expected no missing fields for empty phone fields"


def test_calculate_confidence(validator: FieldValidator) -> None:
    """Test confidence score calculation."""
    # No missing fields
    assert validator.calculate_confidence([]) == 1.0

    # Missing top-level field (0.15 deduction)
    assert validator.calculate_confidence(["organization"]) == 0.85

    # Missing organization field (0.10 deduction)
    assert validator.calculate_confidence(["organization.name"]) == 0.90

    # Missing service field (0.10 deduction)
    assert validator.calculate_confidence(["service.name"]) == 0.90

    # Missing location field (0.10 deduction)
    assert validator.calculate_confidence(["location.name"]) == 0.90

    # Missing other field (0.05 deduction)
    assert validator.calculate_confidence(["some.other.field"]) == 0.95

    # Multiple missing fields (additive deductions)
    assert (
        validator.calculate_confidence(["organization", "service.name"]) == 0.75
    )  # 0.15 + 0.10 deduction

    # Test with known fields (higher deductions)
    known_fields: KnownFieldsDict = {
        "organization_fields": ["name"],
        "service_fields": ["name"],
    }  # All fields are NotRequired, so we only need to specify the ones we use

    # Missing known organization field (0.20 deduction)
    assert validator.calculate_confidence(["organization.name"], known_fields) == 0.80

    # Missing known service field (0.20 deduction)
    assert validator.calculate_confidence(["service.name"], known_fields) == 0.80

    # Multiple missing known fields (additive deductions)
    result = validator.calculate_confidence(
        ["organization.name", "service.name"], known_fields
    )
    assert abs(result - 0.60) < 0.0001  # Use floating point comparison


def test_generate_feedback(validator: FieldValidator) -> None:
    """Test feedback message generation."""
    missing_fields = [
        "organization",  # Top-level
        "service.name",  # Service field
        "service.description",
        "location.addresses",  # Location field
        "organization[0].phones[0].number",  # Phone field
    ]

    feedback = validator.generate_feedback(missing_fields)
    assert "Missing required fields:" in feedback
    assert "Top-level fields: organization" in feedback
    assert "Service fields: name, description" in feedback
    assert "Location fields: addresses" in feedback
    assert "organization[0].phones[0].number" in feedback

    # Test empty missing fields
    assert validator.generate_feedback([]) == ""
