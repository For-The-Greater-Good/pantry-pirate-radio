"""Tests for schema converter functionality."""

import json
from pathlib import Path
from typing import Any, Dict, List, cast

import pytest

from app.llm.hsds_aligner.schema_converter import (
    SchemaConverter,
    SchemaDict,
    SchemaField,
)


@pytest.fixture
def test_schema_path(tmp_path: Path) -> Path:
    """Create a test schema CSV file."""
    schema_content = """table_name,name,type,description,constraints_unique,constraints_required,constraints_tablular_required,format,one_to_many,one_to_one,enum
organization,id,string,Organization identifier,true,true,false,,,,
organization,name,string,Organization name,false,true,false,,,,
organization,email,string,Contact email,false,false,false,email,,,
organization,status,string,Organization status,false,true,false,,,,active,inactive
organization,locations,array,Organization locations,false,false,false,,location.json,,
location,id,string,Location identifier,true,true,false,,,,
location,name,string,Location name,false,true,false,,,,
location,organization,,Parent organization,false,false,false,,,organization.json,
"""
    schema_file = tmp_path / "schema.csv"
    schema_file.write_text(schema_content)
    return schema_file


def test_schema_field_creation() -> None:
    """Test SchemaField creation and properties."""
    field = SchemaField(
        name="status",
        type="string",
        table_name="service",  # Service table has status enum
        description="Status field",
        enum="active,inactive,pending",
    )

    assert field.name == "status"
    assert field.type == "string"
    assert field.description == "Status field"
    assert field.enum_values == ["active", "inactive", "pending"]


def test_schema_loading(test_schema_path: Path) -> None:
    """Test schema loading from CSV."""
    converter = SchemaConverter(test_schema_path)

    # Access internal cache for testing purposes only
    schema_cache = converter._schema_cache  # type: ignore
    assert "organization" in schema_cache
    assert "location" in schema_cache

    org_fields = schema_cache["organization"]
    assert len(org_fields) == 5

    id_field = next(f for f in org_fields if f.name == "id")
    assert id_field.constraints_unique
    assert id_field.constraints_required

    email_field = next(f for f in org_fields if f.name == "email")
    assert email_field.format == "email"


def test_field_validation(test_schema_path: Path) -> None:
    """Test field validation constraints."""
    converter = SchemaConverter(test_schema_path)

    # Test valid field
    valid_field = SchemaField(
        name="test",
        type="string",
        table_name="test_table",
        description="Short description",
    )
    converter._validate_field(valid_field)  # type: ignore

    # Test invalid description length
    with pytest.raises(ValueError, match="description exceeds max length"):
        invalid_field = SchemaField(
            name="test",
            type="string",
            table_name="test_table",
            description="x" * (converter.max_string_length + 1),
        )
        converter._validate_field(invalid_field)  # type: ignore

    # Test invalid enum values count
    with pytest.raises(ValueError, match="too many enum values"):
        invalid_field = SchemaField(
            name="test",
            type="string",
            table_name="test_table",
            enum=",".join([f"value{i}" for i in range(converter.max_enum_values + 1)]),
        )
        converter._validate_field(invalid_field)  # type: ignore


def test_convert_table_schema(test_schema_path: Path) -> None:
    """Test table schema conversion."""
    converter = SchemaConverter(test_schema_path)
    schema = converter.convert_table_schema("organization")

    assert schema["type"] == "object"
    assert not schema.get("additionalProperties", True)
    assert "properties" in schema

    properties = cast(Dict[str, SchemaDict], schema.get("properties", {}))
    assert "id" in properties
    assert "email" in properties
    assert "locations" in properties

    # Check required fields
    required = cast(List[str], schema.get("required", []))
    assert all(field in required for field in ["id", "name"])

    # Check email format
    email_props = cast(Dict[str, Any], properties["email"])
    assert email_props.get("format") == "email"

    # Check array reference
    locations_prop = cast(Dict[str, Any], properties["locations"])
    assert locations_prop.get("type") == "array"
    items = cast(Dict[str, str], locations_prop.get("items", {}))
    assert items.get("$ref") == "#/definitions/location"


def test_convert_to_llm_schema(test_schema_path: Path) -> None:
    """Test conversion to LLM schema format."""
    converter = SchemaConverter(test_schema_path)
    llm_schema = converter.convert_to_llm_schema("organization")

    # Display the converted schema in test output
    print("\n=== Converted LLM Schema ===")
    print(json.dumps(llm_schema, indent=2))
    print("===========================\n")

    assert llm_schema["type"] == "json_schema"
    json_schema = cast(Dict[str, Any], llm_schema["json_schema"])
    assert json_schema["name"] == "hsds_organization"
    assert json_schema["strict"] is True
    assert json_schema["max_tokens"] == 64768
    assert json_schema["temperature"] == 0.4

    # Check schema content
    schema = cast(SchemaDict, json_schema["schema"])
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "definitions" in schema
    definitions = cast(Dict[str, SchemaDict], schema.get("definitions", {}))
    assert "location" in definitions


def test_circular_reference_handling(test_schema_path: Path) -> None:
    """Test handling of circular references."""
    converter = SchemaConverter(test_schema_path)
    schema = converter.convert_to_llm_schema("organization")

    # Display the schema with circular references
    print("\n=== Schema with Circular References ===")
    print(json.dumps(schema, indent=2))
    print("=====================================\n")

    # Check that circular references are properly handled
    json_schema = cast(Dict[str, Any], schema["json_schema"])
    schema_obj = cast(SchemaDict, json_schema["schema"])
    properties = cast(Dict[str, SchemaDict], schema_obj["properties"])
    locations = cast(Dict[str, Any], properties["locations"])
    items = cast(Dict[str, str], locations["items"])
    assert items["$ref"] == "#/definitions/location"

    definitions = cast(Dict[str, SchemaDict], schema_obj["definitions"])
    location = cast(Dict[str, Dict[str, Any]], definitions["location"])
    location_props = cast(Dict[str, Dict[str, Any]], location["properties"])
    org_ref = cast(Dict[str, str], location_props["organization"])
    assert org_ref["$ref"] == "#/definitions/organization"


def test_depth_limit(test_schema_path: Path) -> None:
    """Test maximum depth limit enforcement."""
    converter = SchemaConverter(test_schema_path)

    # Force depth limit exceeded
    with pytest.raises(ValueError, match="Maximum schema depth"):
        converter.convert_table_schema("organization", depth=converter.max_depth + 1)
