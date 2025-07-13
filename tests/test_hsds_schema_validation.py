"""Tests for validating HSDS models against JSON schema definitions."""

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Tuple, Type, cast, get_args, get_origin

import pytest
from pydantic import BaseModel

from app.models import (
    Location,
    Organization,
    Service,
    ServiceAtLocation,
)


@pytest.fixture(scope="module")
def schema_dir(project_root: Path) -> Path:
    """Get the path to HSDS schema directory."""
    return project_root / "docs" / "HSDS" / "schema"


def load_schema(filename: str, schema_dir: Path) -> Dict[str, Any]:
    """Load a JSON schema file."""
    schema_path = schema_dir / filename
    with open(schema_path) as f:
        return json.load(f)


def validate_field_presence(model: Type[BaseModel], schema: Dict[str, Any]) -> None:
    """Verify all fields from schema exist in model."""
    schema_fields = set(schema["properties"].keys())
    model_fields = set(model.model_fields.keys())

    # Some fields in schema are relationship arrays that will be implemented
    # later
    relationship_fields = {
        name
        for name, props in schema["properties"].items()
        if props.get("type") == "array" or "$ref" in props
    }
    schema_fields -= relationship_fields

    missing_fields = schema_fields - model_fields
    assert not missing_fields, f"Missing fields in {model.__name__}: {missing_fields}"


def validate_required_fields(model: Type[BaseModel], schema: Dict[str, Any]) -> None:
    """Verify required fields from schema are required in model."""
    required_fields = set(schema.get("required", []))
    model_required = {
        name for name, field in model.model_fields.items() if field.is_required()
    }
    missing_required = required_fields - model_required
    assert (
        not missing_required
    ), f"Missing required fields in {model.__name__}: {missing_required}"


def validate_field_types(model: Type[BaseModel], schema: Dict[str, Any]) -> None:
    """Verify field types match schema types."""
    type_mapping: Dict[str, Tuple[Type[Any], ...]] = {
        # Allow UUID for string fields with format: uuid
        "string": (str, uuid.UUID),
        "number": (float, int),
        "integer": (int,),
        "boolean": (bool,),
        "array": (list, set, tuple),
    }

    for field_name, field_schema in schema["properties"].items():
        if field_name not in model.model_fields:
            continue  # Skip relationship fields not yet implemented

        if "type" not in field_schema:
            continue  # Skip fields with $ref or no explicit type

        field = model.model_fields[field_name]
        schema_type = field_schema["type"]
        expected_types = type_mapping.get(schema_type, ())

        if not expected_types:
            continue

        # Get the field's type, handling Optional/Union types
        field_type = field.annotation
        if get_origin(field_type) is not None:
            args = get_args(field_type)
            # For Optional[T], get the first non-None type
            field_type = cast(
                Type[Any], next((t for t in args if t is not type(None)), args[0])
            )

        # Skip validation for special format fields
        field_format = field_schema.get("format")
        datapackage_type = field_schema.get("datapackage_type")

        if field_format in ("uuid", "email", "uri"):
            continue
        if datapackage_type in ("date", "datetime", "time"):
            if field_type in (date, datetime):
                continue

        assert isinstance(field_type, type) and issubclass(
            field_type, expected_types
        ), f"Field {field_name} in {model.__name__} has wrong type. Expected {expected_types}, got {field_type}"


def test_service_schema(schema_dir: Path) -> None:
    """Test Service model against HSDS schema."""
    schema = load_schema("service.json", schema_dir)
    validate_field_presence(Service, schema)
    validate_required_fields(Service, schema)
    validate_field_types(Service, schema)


def test_organization_schema(schema_dir: Path) -> None:
    """Test Organization model against HSDS schema."""
    schema = load_schema("organization.json", schema_dir)
    validate_field_presence(Organization, schema)
    validate_required_fields(Organization, schema)
    validate_field_types(Organization, schema)


def test_location_schema(schema_dir: Path) -> None:
    """Test Location model against HSDS schema."""
    schema = load_schema("location.json", schema_dir)
    validate_field_presence(Location, schema)
    validate_required_fields(Location, schema)
    validate_field_types(Location, schema)


def test_service_at_location_schema(schema_dir: Path) -> None:
    """Test ServiceAtLocation model against HSDS schema."""
    schema = load_schema("service_at_location.json", schema_dir)
    validate_field_presence(ServiceAtLocation, schema)
    validate_required_fields(ServiceAtLocation, schema)
    validate_field_types(ServiceAtLocation, schema)


# Example Data Validation Tests


def test_service_example_data(schema_dir: Path) -> None:
    """Test Service model with schema example data."""
    schema = load_schema("service.json", schema_dir)
    example_data = {
        "id": schema["properties"]["id"]["example"],
        "organization_id": schema["properties"]["organization_id"]["example"],
        "name": schema["properties"]["name"]["example"],
        "description": schema["properties"]["description"]["example"],
        "url": schema["properties"]["url"]["example"],
        "email": schema["properties"]["email"]["example"],
        "status": schema["properties"]["status"]["example"],
    }
    service = Service(**example_data)
    assert service.id is not None
    assert service.name == example_data["name"]
    assert service.status == "active"


def test_organization_example_data(schema_dir: Path) -> None:
    """Test Organization model with schema example data."""
    schema = load_schema("organization.json", schema_dir)
    example_data = {
        "id": schema["properties"]["id"]["example"],
        "name": schema["properties"]["name"]["example"],
        "description": schema["properties"]["description"]["example"],
    }
    org = Organization(**example_data)
    assert org.id is not None
    assert org.name == example_data["name"]


def test_location_example_data(schema_dir: Path) -> None:
    """Test Location model with schema example data."""
    schema = load_schema("location.json", schema_dir)
    example_data = {
        "id": schema["properties"]["id"]["example"],
        "name": schema["properties"]["name"]["example"],
        "description": schema["properties"]["description"]["example"],
        "location_type": schema["properties"]["location_type"]["example"],
    }
    location = Location(**example_data)
    assert location.id is not None
    assert location.name == example_data["name"]


def test_service_at_location_example_data(schema_dir: Path) -> None:
    """Test ServiceAtLocation model with schema example data."""
    schema = load_schema("service_at_location.json", schema_dir)
    example_data = {
        "id": schema["properties"]["id"]["example"],
        "service_id": schema["properties"]["service_id"]["example"],
        "location_id": schema["properties"]["location_id"]["example"],
    }
    sal = ServiceAtLocation(**example_data)
    assert sal.id is not None
    assert sal.service_id is not None
    assert sal.location_id is not None
