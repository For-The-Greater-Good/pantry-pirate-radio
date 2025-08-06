"""Tests for HSDS validation functionality."""

import json
from typing import Any, Dict, Optional, cast
from unittest.mock import AsyncMock

import pytest
from pytest_mock import MockerFixture

from app.llm.config import LLMConfig
from app.llm.hsds_aligner.type_defs import (
    AddressDict,
    HSDSDataDict,
    LocationDict,
    OrganizationDict,
    ServiceDict,
)
from app.llm.hsds_aligner.validation import ValidationConfig, ValidationResult
from app.llm.hsds_aligner.validator import ValidationProvider
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import GenerateConfig, LLMResponse


def create_test_service(name: str = "Food Bank Services") -> ServiceDict:
    """Create a test service with minimal required fields."""
    return {
        "name": name,
        "description": "Food assistance",
        "status": "active",
        "phones": [],  # Required empty list
        "schedules": [  # Required at least one schedule
            {
                "freq": "WEEKLY",
                "wkst": "MO",
                "opens_at": "09:00",
                "closes_at": "17:00",
            }
        ],
    }


def create_test_organization(
    name: str = "Test Food Bank", service: Optional[ServiceDict] = None
) -> OrganizationDict:
    """Create a test organization with minimal required fields."""
    if service is None:
        service = create_test_service()
    return {
        "name": name,
        "description": "Food bank",
        "services": [service],
        "phones": [],  # Required empty list
        "organization_identifiers": [],  # Required empty list
        "contacts": [],  # Required empty list
        "metadata": [  # Required at least one metadata
            {
                "resource_id": "test",
                "resource_type": "organization",
                "last_action_date": "2024-01-01",
                "last_action_type": "create",
            }
        ],
    }


def create_test_location() -> LocationDict:
    """Create a test location with minimal required fields."""
    address: AddressDict = {
        "address_1": "123 Main St",
        "city": "Test City",
        "state_province": "ST",
        "postal_code": "12345",
        "country": "US",
        "address_type": "physical",
    }
    return {
        "name": "Main Location",
        "location_type": "physical",
        "addresses": [address],
        "phones": [],  # Required empty list
        "accessibility": [],  # Required empty list
        "contacts": [],  # Required empty list
        "schedules": [  # Required at least one schedule
            {
                "freq": "WEEKLY",
                "wkst": "MO",
                "opens_at": "09:00",
                "closes_at": "17:00",
            }
        ],
        "languages": [],  # Required empty list
        "metadata": [  # Required at least one metadata
            {
                "resource_id": "test",
                "resource_type": "location",
                "last_action_date": "2024-01-01",
                "last_action_type": "create",
            }
        ],
        "latitude": 0.0,  # Required
        "longitude": 0.0,  # Required
    }


@pytest.fixture
def mock_provider(mocker: MockerFixture) -> BaseLLMProvider[Any, LLMConfig]:
    """Create a mock LLM provider."""
    mock = mocker.Mock(spec=BaseLLMProvider)
    mock.generate = AsyncMock()
    return mock


@pytest.fixture
def validation_result() -> Dict[str, Any]:
    """Create sample validation result data."""
    return {
        "confidence": 0.98,
        "feedback": "Minor formatting issues",
        "hallucination_detected": False,
        "mismatched_fields": ["organization[0].description"],
        "suggested_corrections": {"organization[0].description": "Updated description"},
    }


def test_validation_result_model(validation_result: Dict[str, Any]) -> None:
    """Test ValidationResult model."""
    result = ValidationResult.model_validate(validation_result)
    assert result.confidence == 0.98
    assert result.feedback == "Minor formatting issues"
    assert result.hallucination_detected is False
    assert result.mismatched_fields == ["organization[0].description"]
    assert result.suggested_corrections == {
        "organization[0].description": "Updated description"
    }


def test_validation_config_defaults() -> None:
    """Test ValidationConfig default values."""
    config = ValidationConfig()
    assert config.min_confidence == 0.82  # Lowered to allow smart inference
    assert config.retry_threshold == 0.65  # Updated for better efficiency
    assert config.max_retries == 5
    assert config.validation_model is None


def test_validation_config_custom() -> None:
    """Test ValidationConfig with custom values."""
    config = ValidationConfig(
        min_confidence=0.9,
        retry_threshold=0.7,
        max_retries=5,
        validation_model="google/gemini-2.0-flash-001",
    )
    assert config.min_confidence == 0.9
    assert config.retry_threshold == 0.7
    assert config.max_retries == 5
    assert config.validation_model == "google/gemini-2.0-flash-001"


@pytest.mark.asyncio
async def test_validation_provider_validate(
    mock_provider: BaseLLMProvider[Any, LLMConfig]
) -> None:
    """Test ValidationProvider.validate method."""
    # Setup mock response with new confidence threshold
    validation_data: Dict[str, Any] = {
        "confidence": 0.85,  # Match new threshold
        "feedback": "Minor formatting issues",
        "hallucination_detected": False,
        "missing_required_fields": [],  # Required by schema
        "mismatched_fields": ["organization[0].description"],
        "suggested_corrections": {"organization[0].description": "Updated description"},
    }
    mock_response = LLMResponse(
        text=json.dumps(validation_data),
        model="test-model",
        usage={"total_tokens": 100},
        parsed=validation_data,
    )
    mock_provider.generate = AsyncMock(return_value=mock_response)

    # Create test input data
    raw_data = """
    Name: Test Food Bank
    Address: 123 Main St
    Phone: (555) 123-4567
    """

    # Create test data
    service = create_test_service()
    org = create_test_organization(service=service)
    location = create_test_location()

    hsds_data: HSDSDataDict = {
        "organization": [org],
        "service": [service],
        "location": [location],
    }

    # Create validator and validate
    validator = ValidationProvider[Any, LLMConfig](mock_provider)
    result = await validator.validate(raw_data, hsds_data)

    # Verify results
    assert isinstance(result, ValidationResult)
    assert result.confidence == 0.85  # Match new threshold
    assert result.feedback == "Minor formatting issues"
    assert result.hallucination_detected is False

    # Verify LLM was called correctly
    assert mock_provider.generate.call_count == 1
    call_args = mock_provider.generate.call_args
    config = cast(GenerateConfig, call_args.kwargs["config"])
    assert "format" in config.__dict__


@pytest.mark.asyncio
async def test_validation_provider_hallucination(
    mock_provider: BaseLLMProvider[Any, LLMConfig]
) -> None:
    """Test ValidationProvider hallucination detection."""
    # Setup mock response with hallucination detected
    validation_data: Dict[str, Any] = {
        "confidence": 0.0,  # Zero confidence for hallucination
        "feedback": "Found hallucinated data: email, phones, languages, metadata",
        "hallucination_detected": True,
        "missing_required_fields": [],  # Required by schema
        "mismatched_fields": [
            "organization[0].email",
            "organization[0].phones",
            "organization[0].languages",
            "organization[0].metadata",
        ],
        "suggested_corrections": None,
    }
    mock_response = LLMResponse(
        text=json.dumps(validation_data),
        model="test-model",
        usage={"total_tokens": 100},
        parsed=validation_data,
    )
    mock_provider.generate = AsyncMock(return_value=mock_response)

    # Create test input data
    raw_data = "Name: Test Organization"

    # Create test data with hallucination
    service = create_test_service("Test Service")
    org = create_test_organization(name="Test Organization", service=service)
    # Add hallucinated email - using cast to bypass type checking since we're testing invalid data
    org_dict = cast(Dict[str, Any], org)
    org_dict["email"] = "fake@email.com"

    hsds_data: HSDSDataDict = {
        "organization": [org],
        "service": [service],
        "location": [],
    }

    # Create validator and validate
    validator = ValidationProvider[Any, LLMConfig](mock_provider)
    result = await validator.validate(raw_data, hsds_data)

    # Verify hallucination was detected
    assert result.confidence == 0.0
    assert result.hallucination_detected is True
    assert (
        result.mismatched_fields is not None and "email" in result.mismatched_fields[0]
    )


@pytest.mark.asyncio
async def test_validation_provider_invalid_response(
    mock_provider: BaseLLMProvider[Any, LLMConfig]
) -> None:
    """Test ValidationProvider handling of invalid responses."""
    # Setup mock response with invalid data
    mock_response = LLMResponse(
        text="Invalid JSON", model="test-model", usage={"total_tokens": 100}
    )
    mock_provider.generate = AsyncMock(return_value=mock_response)

    # Create test input data
    raw_data = "Test data"

    # Create test data
    service = create_test_service("Test Service")
    org = create_test_organization(name="Test", service=service)

    hsds_data: HSDSDataDict = {
        "organization": [org],
        "service": [service],
        "location": [],
    }

    # Create validator
    validator = ValidationProvider[Any, LLMConfig](mock_provider)

    # Verify invalid response handling
    with pytest.raises(ValueError, match="Invalid JSON in validation response"):
        await validator.validate(raw_data, hsds_data)
