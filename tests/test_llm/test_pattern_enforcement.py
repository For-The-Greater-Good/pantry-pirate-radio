"""Integration test to verify pattern constraints are enforced in structured output."""

import os
import pytest
from app.llm.providers.openai import OpenAIConfig, OpenAIProvider
from app.llm.providers.types import GenerateConfig


@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"), reason="OpenRouter API key not available"
)
@pytest.mark.asyncio
async def test_pattern_enforcement_in_structured_output():
    """Test that pattern constraints are enforced when generating with real API."""

    provider = OpenAIProvider(
        OpenAIConfig(model_name="openai/gpt-4o-mini", temperature=0.1, max_tokens=300)
    )

    # Create a schema with our pattern constraints
    schema_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "test_address",
            "description": "Test address with pattern constraints",
            "schema": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "object",
                        "properties": {
                            "address_1": {"type": "string"},
                            "city": {"type": "string"},
                            "state_province": {
                                "type": "string",
                                "pattern": "^[A-Z]{2}$",  # Must be 2 uppercase letters
                                "description": "US state code (2 letters)",
                            },
                            "postal_code": {
                                "type": "string",
                                "pattern": "^\\d{5}(-\\d{4})?$",  # 5 digits or ZIP+4
                                "description": "US ZIP code",
                            },
                            "country": {
                                "type": "string",
                                "pattern": "^[A-Z]{2}$",  # 2-letter country code
                                "description": "ISO country code",
                            },
                        },
                        "required": [
                            "address_1",
                            "city",
                            "state_province",
                            "postal_code",
                            "country",
                        ],
                        "additionalProperties": False,
                    },
                    "phone": {
                        "type": "object",
                        "properties": {
                            "number": {
                                "type": "string",
                                "pattern": "^[\\d\\s\\(\\)\\-\\+\\.extA-Z]+$",
                                "description": "Phone number",
                            }
                        },
                        "required": ["number"],
                        "additionalProperties": False,
                    },
                    "schedule": {
                        "type": "object",
                        "properties": {
                            "opens_at": {
                                "type": "string",
                                "pattern": "^([01]\\d|2[0-3]):([0-5]\\d)(:[0-5]\\d)?(Z|[+-]\\d{2}:\\d{2})?$",
                                "description": "Opening time in HH:MM format",
                            },
                            "closes_at": {
                                "type": "string",
                                "pattern": "^([01]\\d|2[0-3]):([0-5]\\d)(:[0-5]\\d)?(Z|[+-]\\d{2}:\\d{2})?$",
                                "description": "Closing time in HH:MM format",
                            },
                            "date": {
                                "type": "string",
                                "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                                "description": "Date in YYYY-MM-DD format",
                            },
                        },
                        "required": ["opens_at", "closes_at", "date"],
                        "additionalProperties": False,
                    },
                },
                "required": ["address", "phone", "schedule"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }

    config = GenerateConfig(format=schema_format, temperature=0.1)

    # Prompt that should result in properly formatted data
    prompt = """Extract the following information from this text and ensure all formats are correct:

    The Maryland Food Bank is located at 2200 Halethorpe Farms Road, Baltimore, Maryland 21227.
    Phone: (410) 737-8282
    Open Monday through Friday from 9am to 5pm.
    Today's date is January 15, 2024.

    Important:
    - State must be 2-letter code (Maryland = MD)
    - ZIP code must be 5 digits
    - Country should be US
    - Times must be in 24-hour HH:MM format
    - Date must be YYYY-MM-DD format
    """

    response = await provider.generate(prompt, config=config)

    # Verify we got a valid response
    assert response is not None
    assert response.parsed is not None

    # Check the parsed data follows our patterns
    parsed = response.parsed

    # Address validations
    assert "address" in parsed
    address = parsed["address"]
    assert len(address["state_province"]) == 2  # 2-letter state code
    assert address["state_province"].isupper()  # Uppercase
    assert address["state_province"] == "MD"  # Should be Maryland's code

    assert len(address["postal_code"]) == 5  # 5-digit ZIP
    assert address["postal_code"].isdigit()  # All digits
    assert address["postal_code"] == "21227"  # Correct ZIP for that address

    assert len(address["country"]) == 2  # 2-letter country code
    assert address["country"] == "US"  # Should be US

    # Phone validation
    assert "phone" in parsed
    phone = parsed["phone"]
    assert (
        "410" in phone["number"]
        or "737" in phone["number"]
        or "8282" in phone["number"]
    )

    # Schedule validation
    assert "schedule" in parsed
    schedule = parsed["schedule"]

    # Check time format (should be 24-hour)
    import re

    time_pattern = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)")
    assert time_pattern.match(schedule["opens_at"])
    assert time_pattern.match(schedule["closes_at"])
    assert schedule["opens_at"] == "09:00"  # 9am in 24-hour
    assert schedule["closes_at"] == "17:00"  # 5pm in 24-hour

    # Check date format
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    assert date_pattern.match(schedule["date"])
    assert schedule["date"] == "2024-01-15"  # Should match the date in prompt

    print("\n✅ Pattern enforcement successful!")
    print(f"State: {address['state_province']} (2-letter code)")
    print(f"ZIP: {address['postal_code']} (5 digits)")
    print(f"Country: {address['country']} (ISO code)")
    print(f"Phone: {phone['number']}")
    print(f"Hours: {schedule['opens_at']} - {schedule['closes_at']} (24-hour format)")
    print(f"Date: {schedule['date']} (YYYY-MM-DD)")


@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"), reason="OpenRouter API key not available"
)
@pytest.mark.asyncio
async def test_pattern_rejection_of_invalid_formats():
    """Test that the LLM correctly formats data to match patterns, not that it rejects."""

    provider = OpenAIProvider(
        OpenAIConfig(model_name="openai/gpt-4o-mini", temperature=0.1, max_tokens=200)
    )

    # Simple schema with strict state code pattern
    schema_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "test_state",
            "description": "Test state code validation",
            "schema": {
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "pattern": "^[A-Z]{2}$",
                        "description": "Must be exactly 2 uppercase letters",
                    }
                },
                "required": ["state"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }

    config = GenerateConfig(format=schema_format, temperature=0.1)

    # Prompt with full state name that should be converted to code
    prompt = """Convert this state to a 2-letter code: California

    Remember: State codes must be exactly 2 uppercase letters (e.g., CA for California)"""

    response = await provider.generate(prompt, config=config)

    # The LLM should convert "California" to "CA" to match the pattern
    assert response is not None
    assert response.parsed is not None
    assert response.parsed["state"] == "CA"  # Should be converted to 2-letter code

    print(
        f"\n✅ LLM correctly converted 'California' to '{response.parsed['state']}' to match pattern!"
    )
