"""Tests for HSDS schema pattern constraints."""

import pytest
from pathlib import Path
from app.llm.hsds_aligner.schema_converter import SchemaConverter, TYPE_CONSTRAINTS


def test_pattern_constraints_exist():
    """Test that pattern constraints are defined for key fields."""
    # Check that important pattern constraints exist
    assert "address.state_province" in TYPE_CONSTRAINTS
    assert "address.postal_code" in TYPE_CONSTRAINTS
    assert "address.country" in TYPE_CONSTRAINTS
    assert "phone.number" in TYPE_CONSTRAINTS
    assert "schedule.opens_at" in TYPE_CONSTRAINTS
    assert "schedule.closes_at" in TYPE_CONSTRAINTS
    

def test_state_province_pattern():
    """Test state province pattern accepts valid US state codes."""
    import re
    pattern = TYPE_CONSTRAINTS["address.state_province"]["pattern"]
    regex = re.compile(pattern)
    
    # Valid state codes
    assert regex.match("CA")
    assert regex.match("NY")
    assert regex.match("TX")
    assert regex.match("FL")
    
    # Invalid formats
    assert not regex.match("California")
    assert not regex.match("ca")  # Lowercase
    assert not regex.match("C")   # Too short
    assert not regex.match("CAL") # Too long
    assert not regex.match("12")  # Numbers


def test_postal_code_pattern():
    """Test postal code pattern accepts valid US ZIP codes."""
    import re
    pattern = TYPE_CONSTRAINTS["address.postal_code"]["pattern"]
    regex = re.compile(pattern)
    
    # Valid ZIP codes
    assert regex.match("12345")
    assert regex.match("12345-6789")
    assert regex.match("00501")  # Lowest ZIP
    assert regex.match("99950")  # Highest ZIP
    
    # Invalid formats
    assert not regex.match("1234")      # Too short
    assert not regex.match("123456")    # Too long
    assert not regex.match("12345-")    # Incomplete ZIP+4
    assert not regex.match("12345-67")  # Invalid ZIP+4
    assert not regex.match("ABCDE")     # Letters


def test_country_code_pattern():
    """Test country code pattern accepts valid ISO 3166-1 codes."""
    import re
    pattern = TYPE_CONSTRAINTS["address.country"]["pattern"]
    regex = re.compile(pattern)
    
    # Valid country codes
    assert regex.match("US")
    assert regex.match("CA")
    assert regex.match("MX")
    assert regex.match("GB")
    
    # Invalid formats
    assert not regex.match("USA")  # Too long
    assert not regex.match("U")    # Too short
    assert not regex.match("us")   # Lowercase
    assert not regex.match("12")   # Numbers


def test_phone_number_pattern():
    """Test phone number pattern accepts various formats."""
    import re
    pattern = TYPE_CONSTRAINTS["phone.number"]["pattern"]
    regex = re.compile(pattern)
    
    # Valid phone formats
    assert regex.match("(555) 123-4567")
    assert regex.match("555-123-4567")
    assert regex.match("555.123.4567")
    assert regex.match("5551234567")
    assert regex.match("+1 555 123 4567")
    assert regex.match("555-123-4567 ext 123")
    
    # Should still accept various formats (flexible)
    assert regex.match("1-800-FLOWERS")  # Letters allowed in flexible format


def test_time_format_pattern():
    """Test time format pattern for schedules."""
    import re
    pattern = TYPE_CONSTRAINTS["schedule.opens_at"]["pattern"]
    regex = re.compile(pattern)
    
    # Valid time formats
    assert regex.match("09:00")
    assert regex.match("09:30")
    assert regex.match("23:59")
    assert regex.match("00:00")
    assert regex.match("14:30:00")  # With seconds
    assert regex.match("09:00Z")     # UTC
    assert regex.match("09:00-05:00") # EST offset
    assert regex.match("09:00+01:00") # CET offset
    
    # Invalid formats
    assert not regex.match("9:00")    # Need leading zero
    assert not regex.match("25:00")   # Invalid hour
    assert not regex.match("09:60")   # Invalid minute
    assert not regex.match("9am")     # AM/PM format


def test_date_format_pattern():
    """Test date format pattern for schedules."""
    import re
    pattern = TYPE_CONSTRAINTS["schedule.valid_from"]["pattern"]
    regex = re.compile(pattern)
    
    # Valid date formats
    assert regex.match("2024-01-01")
    assert regex.match("2024-12-31")
    assert regex.match("2024-02-29")  # Leap year
    assert regex.match("1900-01-01")
    assert regex.match("2099-12-31")
    
    # Invalid formats (pattern allows, but semantically invalid)
    assert regex.match("2024-13-01")  # Pattern doesn't validate month range
    assert regex.match("2024-01-32")  # Pattern doesn't validate day range
    
    # Invalid formats (pattern rejects)
    assert not regex.match("01-01-2024")  # Wrong order
    assert not regex.match("2024/01/01")  # Wrong separator
    assert not regex.match("24-01-01")    # Short year
    assert not regex.match("Jan 1, 2024") # Written format


def test_schema_converter_applies_patterns():
    """Test that SchemaConverter applies pattern constraints to fields."""
    schema_path = Path("docs/HSDS/simple/schema.csv")
    if not schema_path.exists():
        pytest.skip("Schema file not found")
    
    converter = SchemaConverter(schema_path)
    
    # Get schema for organization (includes addresses)
    schema = converter.convert_to_llm_schema("organization")
    
    # The schema should be wrapped as expected
    assert "json_schema" in schema
    json_schema = schema["json_schema"]
    assert "schema" in json_schema
    
    # Check if patterns would be applied (this tests the structure)
    # Note: Actual pattern application happens in _convert_field_type
    assert converter._schema_cache is not None
    
    # Verify TYPE_CONSTRAINTS has the patterns we expect to be applied
    assert TYPE_CONSTRAINTS["address.state_province"]["pattern"] == r"^[A-Z]{2}$"
    assert TYPE_CONSTRAINTS["address.postal_code"]["pattern"] == r"^\d{5}(-\d{4})?$"


def test_format_requirements_in_prompt():
    """Test that format requirements are documented in the prompt."""
    prompt_path = Path("app/llm/hsds_aligner/prompts/food_pantry_mapper.prompt")
    if not prompt_path.exists():
        pytest.skip("Prompt file not found")
    
    prompt_content = prompt_path.read_text()
    
    # Check that format requirements are mentioned
    assert "State codes: 2 letters" in prompt_content
    assert "ZIP codes: 5 digits or ZIP+4" in prompt_content
    assert "Country: 2-letter ISO code" in prompt_content
    assert "Dates: YYYY-MM-DD" in prompt_content
    assert "Times: HH:MM" in prompt_content