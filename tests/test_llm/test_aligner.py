"""Tests for HSDS aligner."""

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest
from pytest_mock import MockerFixture

from app.llm.config import LLMConfig
from app.llm.hsds_aligner.aligner import HSDSAligner
from app.llm.hsds_aligner.type_defs import HSDSDataDict
from app.llm.hsds_aligner.validation import ValidationConfig
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import LLMResponse


@pytest.fixture
def mock_provider(mocker: MockerFixture) -> BaseLLMProvider[Any, LLMConfig]:
    """Create a mock LLM provider."""
    mock = mocker.Mock(spec=BaseLLMProvider)
    mock.generate = AsyncMock()
    return mock


@pytest.fixture
def mock_validation_provider(mocker: MockerFixture) -> BaseLLMProvider[Any, LLMConfig]:
    """Create a mock validation LLM provider."""
    mock = mocker.Mock(spec=BaseLLMProvider)
    mock.generate = AsyncMock()
    return mock


@pytest.fixture
def schema_path(project_root: Path) -> Path:
    """Get schema path."""
    return project_root / "docs" / "HSDS" / "schema" / "simple" / "schema.csv"


@pytest.fixture
def hsds_data() -> HSDSDataDict:
    """Create sample HSDS data."""
    return {
        "organization": [
            {
                "name": "Test Food Bank",
                "description": "A food bank",
                "services": [
                    {
                        "name": "Food Distribution",
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
                ],
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
        ],
        "service": [
            {
                "name": "Food Distribution",
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
        ],
        "location": [
            {
                "name": "Main Location",
                "location_type": "physical",  # Required
                "addresses": [
                    {
                        "address_1": "123 Main St",
                        "city": "Test City",
                        "state_province": "ST",
                        "postal_code": "12345",
                        "country": "US",
                        "address_type": "physical",
                    }
                ],
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
                "latitude": 42.4733363,  # Required
                "longitude": -73.8023108,  # Required
            }
        ],
    }


@pytest.mark.asyncio
async def test_aligner_validation_success(
    mock_provider: BaseLLMProvider[Any, LLMConfig],
    mock_validation_provider: BaseLLMProvider[Any, LLMConfig],
    schema_path: Path,
    hsds_data: HSDSDataDict,
) -> None:
    """Test successful validation with custom validation provider."""
    # Setup mock responses
    mock_provider.generate = AsyncMock(
        return_value=LLMResponse(
            text=json.dumps(hsds_data),
            model="test-model",
            usage={"total_tokens": 100},
            parsed=hsds_data,
        )
    )

    validation_result: Dict[str, Any] = {
        "confidence": 0.82,  # Match new HSDS_MIN_CONFIDENCE default
        "feedback": None,
        "hallucination_detected": False,
        "missing_required_fields": [],  # Required by schema
        "mismatched_fields": None,
        "suggested_corrections": None,
    }
    mock_validation_provider.generate = AsyncMock(
        return_value=LLMResponse(
            text=json.dumps(validation_result),
            model="test-model",
            usage={"total_tokens": 100},
            parsed=validation_result,
        )
    )

    # Create aligner with default validation config and provider
    config = ValidationConfig(
        load_from_env=False
    )  # Uses 0.82 min_confidence by default
    aligner = HSDSAligner(
        mock_provider,
        schema_path,
        validation_config=config,
        validation_provider=mock_validation_provider,
    )

    # Test alignment
    raw_data = "The Pantry at St. Patrick's (Entity_Id 97) is a Food Pantry—categorized under Food Pantries within the Capital District and provided by St. Patrick—that welcomes walk-in visits once a month or accommodates clients in urgent need of food, operating on Tuesday from 10:00–11:00 am, Wednesday from 6:00–7:00 pm, and Friday from 10:00–11:00 am; it is located at 21 Main Street in Ravena, NY (zip code 12143) within Albany County, reached by phone at (518) 756-3145, and can be explored further via its website at https://churchofsaintpatrick.wixsite.com/church-ravena, while its precise location is marked by the coordinates 42.4733363 (latitude) and -73.8023108 (longitude), is associated with Coalition 1 and CFAN 0, was last updated on 03-21-2024, and is highlighted by the icon marker-F42000.. open mondeys 9am-5pm"
    result = await aligner.align(raw_data)

    # Verify results
    assert result["confidence_score"] == 0.82  # Match new HSDS_MIN_CONFIDENCE default
    assert isinstance(result["hsds_data"], dict)
    assert result["hsds_data"]["organization"][0]["name"] == "Test Food Bank"


@pytest.mark.asyncio
async def test_aligner_validation_failure(
    mock_provider: BaseLLMProvider[Any, LLMConfig],
    mock_validation_provider: BaseLLMProvider[Any, LLMConfig],
    schema_path: Path,
    hsds_data: HSDSDataDict,
) -> None:
    """Test validation failure with hallucination detection."""
    # Add hallucinated email to test data
    modified_data = json.loads(json.dumps(hsds_data))
    modified_data["organization"][0]["email"] = "fake@email.com"

    # Setup mock responses
    mock_provider.generate = AsyncMock(
        return_value=LLMResponse(
            text=json.dumps(modified_data),
            model="test-model",
            usage={"total_tokens": 100},
            parsed=modified_data,
        )
    )

    validation_result: Dict[str, Any] = {
        "confidence": 0.0,
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
    mock_validation_provider.generate = AsyncMock(
        return_value=LLMResponse(
            text=json.dumps(validation_result),
            model="test-model",
            usage={"total_tokens": 100},
            parsed=validation_result,
        )
    )

    # Create aligner with default validation config and provider
    config = ValidationConfig(
        load_from_env=False
    )  # Uses 0.82 min_confidence by default
    aligner = HSDSAligner(
        mock_provider,
        schema_path,
        validation_config=config,
        validation_provider=mock_validation_provider,
    )

    # Test alignment
    raw_data = "The Pantry at St. Patrick's (Entity_Id 97) is a Food Pantry—categorized under Food Pantries within the Capital District and provided by St. Patrick—that welcomes walk-in visits once a month or accommodates clients in urgent need of food, operating on Tuesday from 10:00–11:00 am, Wednesday from 6:00–7:00 pm, and Friday from 10:00–11:00 am; it is located at 21 Main Street in Ravena, NY (zip code 12143) within Albany County, reached by phone at (518) 756-3145, and can be explored further via its website at https://churchofsaintpatrick.wixsite.com/church-ravena, while its precise location is marked by the coordinates 42.4733363 (latitude) and -73.8023108 (longitude), is associated with Coalition 1 and CFAN 0, was last updated on 03-21-2024, and is highlighted by the icon marker-F42000.. open money 9am-5pm"
    # Test should raise ValueError with appropriate message
    with pytest.raises(
        ValueError,
        match=r"Failed to achieve minimum confidence score of 0\.82 after 5 attempts\. Final confidence: 0\.0",
    ):
        await aligner.align(raw_data)

    # Verify attempts were made
    assert len(aligner.attempts) == 5  # Should try max retries (5)
    assert (
        aligner.attempts[-1]["feedback"]
        == "Found hallucinated data: email, phones, languages, metadata"
    )
    assert aligner.attempts[-1]["score"] == 0.0


@pytest.mark.asyncio
async def test_aligner_validation_retry_success(
    mock_provider: BaseLLMProvider[Any, LLMConfig],
    mock_validation_provider: BaseLLMProvider[Any, LLMConfig],
    schema_path: Path,
    hsds_data: HSDSDataDict,
) -> None:
    """Test successful retry after validation failure."""
    # First attempt - missing required description field
    first_attempt: HSDSDataDict = {
        "organization": [
            {
                "name": "Test Food Bank",
                "description": "",  # Empty description to trigger validation failure
                "services": [
                    {
                        "name": "Food Distribution",
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
                ],
                "phones": [],  # Required empty list
                "organization_identifiers": [],  # Required empty list
                "contacts": [],  # Required empty list
                "metadata": [],  # Empty metadata to trigger validation failure
            }
        ],
        "service": [
            {
                "name": "Food Distribution",
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
        ],
        "location": [
            {
                "name": "Main Location",
                "location_type": "physical",  # Required
                "addresses": [
                    {
                        "address_1": "123 Main St",
                        "city": "Test City",
                        "state_province": "ST",
                        "postal_code": "12345",
                        "country": "US",
                        "address_type": "physical",
                    }
                ],
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
                "latitude": 42.4733363,  # Required
                "longitude": -73.8023108,  # Required
            }
        ],
    }

    # Second attempt - with required description field
    second_attempt = json.loads(json.dumps(hsds_data))

    # Setup mock responses for main LLM
    mock_provider.generate = AsyncMock()
    first_response = LLMResponse(
        text=json.dumps(first_attempt),
        model="test-model",
        usage={"total_tokens": 100},
        parsed=first_attempt,
    )
    second_response = LLMResponse(
        text=json.dumps(second_attempt),
        model="test-model",
        usage={"total_tokens": 100},
        parsed=second_attempt,
    )
    mock_provider.generate.side_effect = [
        first_response,
        second_response,
        second_response,  # Add third response for potential final attempt
    ]

    # Setup mock responses for validation LLM
    mock_validation_provider.generate = AsyncMock()
    first_validation_data: Dict[str, Any] = {
        "confidence": 0.75,  # Above retry threshold
        # Match the expected feedback in test
        "feedback": "Missing organization description",
        "hallucination_detected": False,
        "missing_required_fields": ["organization[0].description"],
        "mismatched_fields": None,
        "suggested_corrections": {"organization[0].description": "A food bank"},
    }
    first_validation = LLMResponse(
        text=json.dumps(first_validation_data),
        model="test-model",
        usage={"total_tokens": 100},
        parsed=first_validation_data,
    )

    second_validation_data: Dict[str, Any] = {
        "confidence": 0.82,  # Match new threshold (lowered for smart inference)
        "feedback": None,
        "hallucination_detected": False,
        "missing_required_fields": [],  # Required by schema
        "mismatched_fields": None,
        "suggested_corrections": None,
    }
    second_validation = LLMResponse(
        text=json.dumps(second_validation_data),
        model="test-model",
        usage={"total_tokens": 100},
        parsed=second_validation_data,
    )
    mock_validation_provider.generate.side_effect = [
        first_validation,
        second_validation,
        second_validation,  # Add third validation for potential final attempt
    ]

    # Create aligner with default validation config
    config = ValidationConfig(
        load_from_env=False
    )  # Uses 0.82 min_confidence and 0.65 retry_threshold
    aligner = HSDSAligner(
        mock_provider,
        schema_path,
        validation_config=config,
        validation_provider=mock_validation_provider,
    )

    # Test alignment
    raw_data = "The Pantry at St. Patrick's (Entity_Id 97) is a Food Pantry—categorized under Food Pantries within the Capital District and provided by St. Patrick—that welcomes walk-in visits once a month or accommodates clients in urgent need of food, operating on Tuesday from 10:00–11:00 am, Wednesday from 6:00–7:00 pm, and Friday from 10:00–11:00 am; it is located at 21 Main Street in Ravena, NY (zip code 12143) within Albany County, reached by phone at (518) 756-3145, and can be explored further via its website at https://churchofsaintpatrick.wixsite.com/church-ravena, while its precise location is marked by the coordinates 42.4733363 (latitude) and -73.8023108 (longitude), is associated with Coalition 1 and CFAN 0, was last updated on 03-21-2024, and is highlighted by the icon marker-F42000.. open money 9am-5pm"
    result = await aligner.align(raw_data)

    # Verify results
    assert result["confidence_score"] == 0.82  # Match new HSDS_MIN_CONFIDENCE default
    assert isinstance(result["hsds_data"], dict)
    assert len(aligner.attempts) == 2  # Should succeed on second try
    assert aligner.attempts[0]["feedback"] == "Missing organization description"
    assert aligner.attempts[1]["feedback"] is None
