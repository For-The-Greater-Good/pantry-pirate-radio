"""Schema converter for HSDS data structures.

This module handles conversion of HSDS schemas into structured formats
suitable for LLM processing.
"""

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

# Schema-specific type definitions
JsonValue = Union[str, int, float, bool, None, list[Any], dict[str, Any]]
SchemaDict = dict[str, JsonValue]

# LLM-specific types
LLMSchemaConfig = dict[str, str | bool | int | float]
LLMSchemaContent = dict[str, str | bool | int | float | SchemaDict]
LLMJsonSchema = dict[str, str | dict[str, str | bool | int | float | SchemaDict]]

# Known format handlers
FORMAT_HANDLERS = {
    # URI and Email
    "uri": {"type": "string", "format": "uri"},
    "email": {"type": "string", "format": "email"},
    # Date and Time
    "%Y": {"type": "string", "pattern": r"^\d{4}$"},  # Year format
    # Time with timezone
    "HH:MM": {
        "type": "string",
        "pattern": r"^([01]\d|2[0-3]):([0-5]\d)(Z|[+-]\d{2}:00)$",
    },
    # Standards
    "ISO639": {"type": "string", "pattern": r"^[a-z]{2,3}$"},  # Language codes
    "ISO3361": {"type": "string", "pattern": r"^[A-Z]{2}$"},  # Country codes
    # 3-letter currency codes
    "currency_code": {"type": "string", "pattern": r"^[A-Z]{3}$"},
}

# Known field type constraints
TYPE_CONSTRAINTS: dict[str, SchemaDict] = {
    # Geographic coordinates - US bounds including Alaska and Hawaii
    "latitude": {
        "type": "number",
        "minimum": 18.91,  # Hawaii southern bound
        "maximum": 71.54,  # Alaska northern bound
        "description": "US latitude including all states (18.91-71.54°N for Hawaii to Alaska)",
    },
    "longitude": {
        "type": "number",
        "minimum": -179.15,  # Alaska/Aleutian western bound
        "maximum": -67,  # Eastern US bound
        "description": "US longitude including all states (-179.15 to -67°W for Alaska to Eastern US)",
    },
    "location.latitude": {
        "type": "number",
        "minimum": 18.91,  # Hawaii southern bound
        "maximum": 71.54,  # Alaska northern bound
        "description": "Location latitude in decimal degrees (US bounds: 18.91-71.54°N)",
    },
    "location.longitude": {
        "type": "number",
        "minimum": -179.15,  # Alaska/Aleutian western bound
        "maximum": -67,  # Eastern US bound
        "description": "Location longitude in decimal degrees (US bounds: -179.15 to -67°W)",
    },
    # Address constraints
    "address.state_province": {
        "type": "string",
        "pattern": r"^[A-Z]{2}$",  # US state codes (2 letters)
        "enum": [
            "AL",
            "AK",
            "AZ",
            "AR",
            "CA",
            "CO",
            "CT",
            "DE",
            "DC",
            "FL",
            "GA",
            "HI",
            "ID",
            "IL",
            "IN",
            "IA",
            "KS",
            "KY",
            "LA",
            "ME",
            "MD",
            "MA",
            "MI",
            "MN",
            "MS",
            "MO",
            "MT",
            "NE",
            "NV",
            "NH",
            "NJ",
            "NM",
            "NY",
            "NC",
            "ND",
            "OH",
            "OK",
            "OR",
            "PA",
            "RI",
            "SC",
            "SD",
            "TN",
            "TX",
            "UT",
            "VT",
            "VA",
            "WA",
            "WV",
            "WI",
            "WY",
        ],
        "description": "US state code (2 letters, must be valid US state)",
    },
    "state_province": {  # For top-level state_province fields
        "type": "string",
        "pattern": r"^[A-Z]{2}$",
        "enum": [
            "AL",
            "AK",
            "AZ",
            "AR",
            "CA",
            "CO",
            "CT",
            "DE",
            "DC",
            "FL",
            "GA",
            "HI",
            "ID",
            "IL",
            "IN",
            "IA",
            "KS",
            "KY",
            "LA",
            "ME",
            "MD",
            "MA",
            "MI",
            "MN",
            "MS",
            "MO",
            "MT",
            "NE",
            "NV",
            "NH",
            "NJ",
            "NM",
            "NY",
            "NC",
            "ND",
            "OH",
            "OK",
            "OR",
            "PA",
            "RI",
            "SC",
            "SD",
            "TN",
            "TX",
            "UT",
            "VT",
            "VA",
            "WA",
            "WV",
            "WI",
            "WY",
        ],
        "description": "US state code (2 letters, must be valid US state)",
    },
    "address.postal_code": {
        "type": "string",
        "pattern": r"^\d{5}(-\d{4})?$",  # US ZIP codes (12345 or 12345-6789)
        "description": "US ZIP code (5 digits or ZIP+4 format)",
    },
    "address.country": {
        "type": "string",
        "pattern": r"^[A-Z]{2}$",  # ISO 3166-1 country codes
        "default": "US",
        "const": "US",  # For US-only food pantries
        "description": "ISO 3166-1 country code (2 letters, defaults to US)",
    },
    # Phone constraints
    "phone.number": {
        "type": "string",
        "pattern": r"^[\d\s\(\)\-\+\.extA-Z]+$",  # Flexible phone format (includes letters for vanity numbers)
        "description": "Phone number (various formats accepted, including vanity numbers)",
    },
    # Schedule constraints
    "schedule.opens_at": {
        "type": "string",
        "pattern": r"^([01]\d|2[0-3]):([0-5]\d)(:[0-5]\d)?(Z|[+-]\d{2}:\d{2})?$",
        "description": "Opening time in HH:MM format with optional timezone",
    },
    "schedule.closes_at": {
        "type": "string",
        "pattern": r"^([01]\d|2[0-3]):([0-5]\d)(:[0-5]\d)?(Z|[+-]\d{2}:\d{2})?$",
        "description": "Closing time in HH:MM format with optional timezone",
    },
    "schedule.valid_from": {
        "type": "string",
        "pattern": r"^\d{4}-\d{2}-\d{2}$",  # YYYY-MM-DD
        "description": "Date in ISO 8601 format (YYYY-MM-DD)",
    },
    "schedule.valid_to": {
        "type": "string",
        "pattern": r"^\d{4}-\d{2}-\d{2}$",  # YYYY-MM-DD
        "description": "Date in ISO 8601 format (YYYY-MM-DD)",
    },
    "schedule.dtstart": {
        "type": "string",
        "pattern": r"^\d{4}-\d{2}-\d{2}$",  # YYYY-MM-DD
        "description": "Start date in ISO 8601 format (YYYY-MM-DD)",
    },
    # UTC offsets
    "timezone": {"type": "number", "minimum": -12, "maximum": 14},
    "bymonthday": {"type": "number", "minimum": -31, "maximum": 31},
    "byyearday": {"type": "number", "minimum": -366, "maximum": 366},
    "interval": {"type": "number", "minimum": 1},
    # Age constraints
    "minimum_age": {"type": "number", "minimum": 0},
    "maximum_age": {"type": "number", "minimum": 0},
    # Financial
    "amount": {"type": "number", "minimum": 0},  # Non-negative amounts
    # Extensions
    "phone.extension": {"type": "integer", "minimum": 0, "maximum": 99999},
    # Text field length constraints
    "organization.name": {
        "type": "string",
        "minLength": 1,
        "maxLength": 255,
        "description": "Organization name (required, max 255 characters)",
    },
    "organization.description": {
        "type": "string",
        "maxLength": 5000,
        "description": "Organization description (max 5000 characters)",
    },
    "organization.alternate_name": {
        "type": "string",
        "maxLength": 255,
        "description": "Alternate organization name (max 255 characters)",
    },
    "service.name": {
        "type": "string",
        "minLength": 1,
        "maxLength": 255,
        "description": "Service name (required, max 255 characters)",
    },
    "service.description": {
        "type": "string",
        "maxLength": 5000,
        "description": "Service description (max 5000 characters)",
    },
    "location.name": {
        "type": "string",
        "minLength": 1,
        "maxLength": 255,
        "description": "Location name (required, max 255 characters)",
    },
    "location.description": {
        "type": "string",
        "maxLength": 5000,
        "description": "Location description (max 5000 characters)",
    },
    # URL and Email validation
    "organization.website": {
        "type": "string",
        "format": "uri",
        "pattern": r"^https?://",
        "description": "Organization website URL (must start with http:// or https://)",
    },
    "organization.email": {
        "type": "string",
        "format": "email",
        "description": "Organization email address",
    },
    "service.email": {
        "type": "string",
        "format": "email",
        "description": "Service-specific email address",
    },
    # Schedule day validation
    "schedule.byday": {
        "type": "string",
        "pattern": r"^(MO|TU|WE|TH|FR|SA|SU)(,(MO|TU|WE|TH|FR|SA|SU))*$",
        "description": "Days of week in RRULE format (e.g., MO,WE,FR)",
    },
    # Address field flexibility
    "address.city": {
        "type": "string",
        "maxLength": 100,
        "description": "City name (can be geocoded if missing)",
    },
}

# Known enum values from schema
KNOWN_ENUMS = {
    # Service enums
    "service.status": ["active", "inactive", "defunct", "temporarily closed"],
    # Location enums
    "location.location_type": ["physical", "postal", "virtual"],
    "address.address_type": ["physical", "postal", "virtual"],
    # State codes enum
    "address.state_province": [
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
    ],
    "state_province": [
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
    ],
    # Schedule enums
    "schedule.freq": ["WEEKLY", "MONTHLY"],
    # Override schema.csv which uses 3 letters
    "schedule.wkst": ["MO", "TU", "WE", "TH", "FR", "SA", "SU"],
    # Phone enums
    "phone.type": ["text", "voice", "fax", "cell", "video", "pager", "textphone"],
    # Service area enums
    "service_area.extent_type": ["geojson", "topojson", "kml", "text"],
    # Metadata enums
    "metadata.last_action_type": ["create", "update", "delete"],
}


@dataclass
class SchemaField:
    """Represents a field in the HSDS schema."""

    name: str
    type: str
    # Added to track field's table for enum validation
    table_name: str | None = None
    description: str | None = None
    constraints_unique: bool = False
    constraints_required: bool = False
    constraints_tabular_required: bool = False
    format: str | None = None
    one_to_many: str | None = None
    one_to_one: str | None = None
    enum: str | None = None

    @property
    def enum_values(self) -> list[str] | None:
        """Get enum values as a list if they exist."""
        if not self.enum:
            return None
        return [v.strip() for v in self.enum.split(",")]

    @property
    def is_required(self) -> bool:
        """Check if field is required by any constraint."""
        return (
            self.constraints_required
            or self.constraints_tabular_required
            or self.constraints_unique
        )


class SchemaConverter:
    """Converts HSDS schemas to LLM-compatible structured output format."""

    def __init__(self, schema_path: Path) -> None:
        """Initialize schema converter.

        Args:
            schema_path: Path to the schema.csv file
        """
        self.schema_path = schema_path
        self._schema_cache: dict[str, list[SchemaField]] = {}
        self._processed_tables: set[str] = set()
        self.max_depth = 5
        self.max_properties = 100
        self.max_string_length = 15000
        self.max_enum_values = 500
        self.max_enum_chars = 7500
        self._load_schema()

    def _load_schema(self) -> None:
        """Load and parse the schema CSV file."""
        with open(self.schema_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                table = row["table_name"]
                if table not in self._schema_cache:
                    self._schema_cache[table] = []

                field = SchemaField(
                    name=row["name"],
                    type=row["type"],
                    table_name=table,
                    description=row["description"] or None,
                    constraints_unique=row["constraints_unique"].lower() == "true",
                    constraints_required=row["constraints_required"].lower() == "true",
                    constraints_tabular_required=row[
                        "constraints_tablular_required"
                    ].lower()
                    == "true",
                    format=row["format"] or None,
                    one_to_many=row["one_to_many"] or None,
                    one_to_one=row["one_to_one"] or None,
                    enum=row["enum"] or None,
                )
                self._schema_cache[table].append(field)

    def _validate_field(self, field: SchemaField) -> None:
        """Validate field constraints.

        Args:
            field: SchemaField to validate

        Raises:
            ValueError: If field violates constraints
        """
        if field.description and len(field.description) > self.max_string_length:
            raise ValueError(
                f"Field {field.name} description exceeds max length of {self.max_string_length}"
            )

        # Special case: override schema.csv enum values with KNOWN_ENUMS
        if field.table_name and field.enum:
            enum_key = f"{field.table_name}.{field.name}"
            if enum_key in KNOWN_ENUMS:
                # Use KNOWN_ENUMS values instead of schema.csv values
                field.enum = ",".join(KNOWN_ENUMS[enum_key])

        # Validate enum values if present
        enum_values = field.enum_values
        if enum_values is not None:
            if len(enum_values) > self.max_enum_values:
                raise ValueError(
                    f"Field {field.name} has too many enum values: {len(enum_values)}"
                )
            total_chars = sum(len(v) for v in enum_values)
            if total_chars > self.max_enum_chars:
                raise ValueError(
                    f"Field {field.name} enum values exceed total character limit"
                )

    def _handle_relationship(self, field: SchemaField) -> SchemaDict | None:
        """Handle relationship field types.

        Args:
            field: SchemaField to convert

        Returns:
            Schema dict for relationship or None if not a relationship
        """
        # Enhanced descriptions for critical HSDS relationships
        relationship_descriptions = {
            "organization.locations": (
                "Array of location objects where this organization provides services. "
                "IMPORTANT: Create a separate location entity for EACH unique physical address, "
                "including event sites, distribution points, and mobile locations. "
                "Each location must have its own entry in the locations array."
            ),
            "organization.services": (
                "Array of service objects provided by this organization. "
                "Services should be linked to their delivery locations via service_at_location."
            ),
            "service.service_at_location": (
                "Array linking this service to the locations where it's provided. "
                "Use this to connect services to multiple delivery sites."
            ),
            "location.addresses": (
                "Array of address objects for this location. "
                "Each unique physical address should have its own location entity."
            ),
        }

        if field.one_to_many:
            ref_name = field.one_to_many.replace(".json", "")
            field_key = f"{field.table_name}.{field.name}"

            # Use enhanced description if available
            description = relationship_descriptions.get(
                field_key,
                (
                    f"Array of {ref_name} objects. These must be included both here "
                    f"and in the top-level {ref_name} array. Each {ref_name} must "
                    f"reference back to this {field.table_name} via {ref_name}_id."
                ),
            )

            return {
                "type": "array",
                "description": description,
                "items": {"$ref": f"#/definitions/{ref_name}"},
                "additionalProperties": False,
            }
        elif field.one_to_one:
            ref_name = field.one_to_one.replace(".json", "")
            return {
                "$ref": f"#/definitions/{ref_name}",
                "description": (
                    f"Reference to a {ref_name} object that must exist in the "
                    f"top-level {ref_name} array."
                ),
            }
        elif field.name.endswith("_id"):
            parent_name = field.name[:-3]  # Remove _id suffix
            return {
                "type": "string",
                "description": (
                    f"ID linking to a {parent_name} object. This {field.table_name} must be "
                    f"included in the {parent_name}.{field.table_name}s array of the referenced {parent_name}."
                ),
                "additionalProperties": False,
            }
        return None

    def _convert_field_type(self, field: SchemaField) -> dict[str, Any]:
        """Convert field type to JSON schema type definition.

        Args:
            field: SchemaField to convert

        Returns:
            Dict containing JSON schema type definition
        """
        # Check for relationship first
        relationship_schema = self._handle_relationship(field)
        if relationship_schema is not None:
            return relationship_schema

        # Initialize default schema
        type_map = {
            "string": "string",
            "number": "number",
            "array": "array",
            "": "object",  # For relationship fields
        }

        # Build base schema
        schema: SchemaDict = {
            "type": type_map[field.type] if field.type else "object",
            "description": field.description or "",
            "additionalProperties": False,
        }

        # Handle formats
        if field.format and field.format in FORMAT_HANDLERS:
            schema.update(FORMAT_HANDLERS[field.format])

        # Handle type-specific constraints
        if field.table_name:
            field_key = f"{field.table_name}.{field.name}"
            if field_key in TYPE_CONSTRAINTS:
                schema.update(TYPE_CONSTRAINTS[field_key])

        # Handle enums
        if field.enum_values:
            schema["enum"] = field.enum_values

        return schema

    def _validate_table_depth(self, depth: int) -> None:
        """Validate the schema depth doesn't exceed maximum.

        Args:
            depth: Current recursion depth

        Raises:
            ValueError: If maximum depth is exceeded
        """
        if depth > self.max_depth:
            raise ValueError(f"Maximum schema depth of {self.max_depth} exceeded")

    def _validate_table_size(self, table_name: str, fields: list[SchemaField]) -> None:
        """Validate the table doesn't exceed maximum field count.

        Args:
            table_name: Name of the table being validated
            fields: List of fields in the table

        Raises:
            ValueError: If maximum field count is exceeded
        """
        if len(fields) > self.max_properties:
            raise ValueError(
                f"Table {table_name} has too many properties: {len(fields)}"
            )

    def _build_properties(self, fields: list[SchemaField]) -> dict[str, SchemaDict]:
        """Build the properties section of the schema.

        Args:
            fields: List of fields to convert

        Returns:
            Dict of field names to their schema definitions
        """
        properties: dict[str, SchemaDict] = {}
        for field in fields:
            self._validate_field(field)
            properties[field.name] = self._convert_field_type(field)
        return properties

    def _collect_required_fields(self, fields: list[SchemaField]) -> list[str]:
        """Collect all required field names including relationships.

        Args:
            fields: List of fields to check

        Returns:
            List of required field names
        """
        required: list[str] = []

        # Add directly required fields
        for field in fields:
            if field.is_required:
                required.append(field.name)

        # Add relationship requirements
        for field in fields:
            if field.one_to_many:
                ref_name = field.one_to_many.replace(".json", "")
                if ref_name not in required:
                    required.append(ref_name)
            elif field.one_to_one:
                ref_name = field.one_to_one.replace(".json", "")
                if ref_name not in required:
                    required.append(ref_name)

        return required

    def convert_table_schema(self, table_name: str, depth: int = 0) -> SchemaDict:
        """Convert a table schema to JSON schema format.

        Args:
            table_name: Name of the table to convert
            depth: Current recursion depth

        Returns:
            Dict containing converted JSON schema

        Raises:
            ValueError: If schema violates constraints
        """
        self._validate_table_depth(depth)

        if table_name in self._processed_tables:
            return {"$ref": f"#/definitions/{table_name}"}

        self._processed_tables.add(table_name)
        fields = self._schema_cache.get(table_name, [])

        self._validate_table_size(table_name, fields)

        properties = self._build_properties(fields)
        required = self._collect_required_fields(fields)

        # Enhanced table descriptions with HSDS guidance
        table_descriptions = {
            "organization": (
                "The agency or entity providing services. Must include ALL locations where services are delivered as separate location objects in the locations array."
            ),
            "service": (
                "A program or assistance offered by the organization. Link to delivery locations via service_at_location."
            ),
            "location": (
                "A physical place where services are delivered. Create one location for EACH unique address, including event sites and mobile distribution points."
            ),
            "address": (
                "Physical or mailing address details. Each unique street address should have its own parent location entity."
            ),
            "service_at_location": (
                "Links services to their delivery locations with location-specific details like schedules."
            ),
            "schedule": (
                "Operating hours and recurring patterns. Use RRULE format for recurring schedules (e.g., freq: WEEKLY, byday: MO,TU)."
            ),
        }

        description = table_descriptions.get(
            table_name, f"Schema for {table_name} data in HSDS format"
        )

        schema: SchemaDict = {
            "type": "object",
            "title": f"HSDS {table_name.title()}",
            "description": description,
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

        return schema

    def convert_to_llm_schema(self, table_name: str) -> LLMJsonSchema:
        """Convert table schema to LLM-compatible format.

        Args:
            table_name: Name of the table to convert

        Returns:
            Dict containing LLM-compatible schema definition
        """
        self._processed_tables.clear()

        # First pass: collect all referenced tables
        referenced_tables: set[str] = set()

        def collect_refs(fields: list[SchemaField]) -> None:
            for field in fields:
                if field.one_to_many:
                    ref = field.one_to_many.replace(".json", "")
                    referenced_tables.add(ref)
                if field.one_to_one:
                    ref = field.one_to_one.replace(".json", "")
                    referenced_tables.add(ref)

        # Start with main table
        collect_refs(self._schema_cache.get(table_name, []))

        # Then collect from referenced tables
        processed = referenced_tables.copy()
        for ref_table in processed:
            collect_refs(self._schema_cache.get(ref_table, []))

        # Now convert schemas with all references known
        self._processed_tables.clear()
        schema = self.convert_table_schema(table_name)

        # Convert referenced tables
        definitions: dict[str, SchemaDict] = {}
        for ref_table in referenced_tables:
            if ref_table != table_name:
                definitions[ref_table] = self.convert_table_schema(ref_table)

        # Add common definitions
        common_defs: dict[str, SchemaDict] = {
            "phone": {
                "type": "object",
                "properties": {
                    "number": {"type": "string"},
                    "type": {"type": "string", "enum": KNOWN_ENUMS["phone.type"]},
                    "languages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                            "required": ["name"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "number",
                    "type",
                ],  # Languages made optional - scrapers rarely have this data
                "additionalProperties": False,
            },
            "metadata": {
                "type": "object",
                "properties": {
                    "resource_id": {"type": "string"},
                    "resource_type": {"type": "string"},
                    "last_action_date": {"type": "string"},
                    "last_action_type": {
                        "type": "string",
                        "enum": KNOWN_ENUMS["metadata.last_action_type"],
                    },
                },
                "required": [
                    "resource_id",
                    "resource_type",
                    "last_action_date",
                    "last_action_type",
                ],
                "additionalProperties": False,
            },
            "schedule": {
                "type": "object",
                "properties": {
                    "freq": {"type": "string", "enum": KNOWN_ENUMS["schedule.freq"]},
                    "wkst": {"type": "string", "enum": KNOWN_ENUMS["schedule.wkst"]},
                    "opens_at": {"type": "string"},
                    "closes_at": {"type": "string"},
                    "byday": {
                        "type": "string",
                        "pattern": r"^(MO|TU|WE|TH|FR|SA|SU)(,(MO|TU|WE|TH|FR|SA|SU))*$",
                        "description": "Days of week in RRULE format (e.g., MO,WE,FR for Monday, Wednesday, Friday)",
                    },
                    "bymonthday": {"type": "string"},
                    "byweekno": {"type": "string"},
                    "byyearday": {"type": "string"},
                    "interval": {"type": "number"},
                    "count": {"type": "number"},
                    "until": {"type": "string"},
                    "dtstart": {"type": "string"},
                    "valid_from": {"type": "string"},
                    "valid_to": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["freq", "wkst", "opens_at", "closes_at"],
                "additionalProperties": False,
            },
        }

        # Add all definitions
        schema["definitions"] = {**definitions, **common_defs}

        # Add schema metadata
        schema["$schema"] = "http://json-schema.org/draft-07/schema#"
        schema["title"] = f"HSDS {table_name.title()} Schema"
        schema["description"] = f"JSON Schema for HSDS {table_name} data"

        # Add required fields based on schema.csv constraints
        required_fields: list[str] = []

        # Add fields marked as required in schema.csv
        for field in self._schema_cache.get(table_name, []):
            if field.constraints_required or field.constraints_unique:
                required_fields.append(field.name)

            # Handle array fields that are required
            if field.type == "array" and field.one_to_many:
                ref_name = field.one_to_many.replace(".json", "")
                required_fields.append(ref_name)

        # Add additional required fields for specific tables
        if table_name == "organization":
            required_fields.extend(
                [
                    "name",
                    "description",
                    "services",
                    "phones",
                    "organization_identifiers",
                    "contacts",
                    "metadata",
                ]
            )
        elif table_name == "service":
            required_fields.extend(
                ["name", "description", "status", "phones", "schedules"]
            )
        elif table_name == "location":
            required_fields.extend(
                [
                    "name",
                    "location_type",
                    "addresses",
                    "phones",
                    "accessibility",
                    "contacts",
                    "schedules",
                    "languages",
                    "metadata",
                ]
            )
        elif table_name == "address":
            required_fields.extend(
                [
                    "address_1",
                    "state_province",
                    "address_type",
                ]
                # Only address_1 and state_province are truly required
                # city, postal_code, and country can be geocoded if missing
            )
        elif table_name == "phone":
            required_fields.extend(["number", "type"])  # Languages made optional
        elif table_name == "schedule":
            required_fields.extend(["freq", "wkst", "opens_at", "closes_at"])
        elif table_name == "metadata":
            required_fields.extend(
                [
                    "resource_id",
                    "resource_type",
                    "last_action_date",
                    "last_action_type",
                    "field_name",
                    "previous_value",
                    "replacement_value",
                    "updated_by",
                ]
            )

        # Get existing required fields and merge with new ones
        existing_required = schema.get("required", [])
        if isinstance(existing_required, list):
            required_fields.extend(existing_required)

        # Update schema with combined required fields
        schema["required"] = list(set(required_fields))  # Deduplicate

        # TODO: Remove this double wrapper once downstream services (queues, content_store)
        # are updated to handle native structured output format directly.
        # Currently returns {"type": "json_schema", "json_schema": {...}} for compatibility.
        # OpenAI provider unwraps this to use native response_format parameter.
        # Enhanced schema description with HSDS relationship guidance
        schema_description = (
            f"Structured output schema for HSDS {table_name} data following Human Services Data Specification v3.1.1. "
            "CRITICAL REQUIREMENTS: "
            "1. Create separate location entities for EACH unique physical address (including event sites, distribution points, mobile locations). "
            "2. Services and locations have a many-to-many relationship via service_at_location. "
            "3. Each organization must have its locations array populated with location objects for every address where services are provided. "
            "4. Location entities are NOT hierarchical - each unique address needs its own location object. "
            "5. When input data contains events or distributions at different addresses, create a separate location entity for each address. "
            "6. Arrays like 'locations', 'services', 'addresses' must contain actual objects, not be empty when data exists. "
            "7. Use RRULE format for recurring schedules (freq: WEEKLY/MONTHLY, byday: MO,TU,WE,TH,FR,SA,SU). "
            "8. Convert date/time strings to ISO format (YYYY-MM-DD for dates, HH:MM for times). "
            "9. State codes must be 2-letter US state codes (e.g., OH, CA, NY). "
            "10. Never hallucinate data - only include fields present in or directly derivable from the input."
        )

        return {
            "type": "json_schema",
            "json_schema": {
                "name": f"hsds_{table_name}",
                "description": schema_description,
                "schema": schema,
                "strict": True,
                "temperature": 0.4,  # Ensure deterministic outputs
                "max_tokens": 64768,  # Maximum tokens for structured output
            },
        }

    def load_hsds_core_schema(self) -> LLMJsonSchema:
        """Load and combine core HSDS schemas from JSON files.

        This method loads only the essential HSDS schemas needed for food pantry data:
        - Core tables: organization, service, location, service_at_location
        - Supporting tables: address, phone, schedule
        - Additional tables: required_document, service_area

        Returns:
            Dict containing LLM-compatible schema for core HSDS structure
        """
        # Define paths to core schema files
        schema_base_path = (
            Path(__file__).parent.parent.parent.parent / "docs" / "HSDS" / "schema"
        )

        # Core entity schemas to load
        core_schemas = {
            "organization": schema_base_path / "organization.json",
            "service": schema_base_path / "service.json",
            "location": schema_base_path / "location.json",
            "service_at_location": schema_base_path / "service_at_location.json",
            "address": schema_base_path / "address.json",
            "phone": schema_base_path / "phone.json",
            "schedule": schema_base_path / "schedule.json",
            "required_document": schema_base_path / "required_document.json",
            "service_area": schema_base_path / "service_area.json",
        }

        # Load each schema file
        definitions = {}
        for name, path in core_schemas.items():
            if path.exists():
                with open(path) as f:
                    schema_data = json.load(f)
                    # Extract only core fields if marked
                    if "properties" in schema_data:
                        core_properties = {}
                        required_fields = []
                        for field_name, field_def in schema_data["properties"].items():
                            # Include all fields for now, but prioritize core fields
                            # Core fields are marked with "core": "Y"
                            # Phone, address, and schedule need all fields included to avoid schema errors
                            if field_def.get("core") == "Y" or name in [
                                "service_at_location",
                                "required_document",
                                "service_area",
                                "phone",
                                "address",
                                "schedule",
                            ]:
                                core_properties[field_name] = {
                                    "type": field_def.get("type", "string"),
                                    "description": field_def.get("description", ""),
                                }
                                if field_def.get("format"):
                                    core_properties[field_name]["format"] = field_def[
                                        "format"
                                    ]
                                if field_def.get("constraints", {}).get("unique"):
                                    required_fields.append(field_name)

                        # For non-core tables, include all fields
                        if not core_properties:
                            core_properties = {
                                field_name: {
                                    "type": field_def.get("type", "string"),
                                    "description": field_def.get("description", ""),
                                }
                                for field_name, field_def in schema_data[
                                    "properties"
                                ].items()
                            }

                        # Define required fields based on entity type for proper data tracking
                        if name == "organization":
                            # Critical fields for organizations
                            required_fields = [
                                "id",
                                "name",
                                "description",
                                "email",
                                "website",
                            ]
                        elif name == "service":
                            # Critical fields for services
                            required_fields = [
                                "id",
                                "name",
                                "description",
                                "status",
                                "email",
                                "eligibility_description",
                            ]
                        elif name == "location":
                            # Critical fields for locations
                            required_fields = [
                                "id",
                                "name",
                                "description",
                                "latitude",
                                "longitude",
                                "location_type",
                            ]
                        elif name == "address":
                            # Critical fields for addresses
                            required_fields = [
                                "id",
                                "address_1",
                                "city",
                                "state_province",
                                "postal_code",
                                "country",
                            ]
                        elif name == "phone":
                            # Keep existing phone requirements
                            required_fields = ["id", "number", "type"]
                        elif name == "schedule":
                            # Only id is required, other fields are optional
                            required_fields = ["id"]
                        else:
                            # Default to id only for other entities
                            required_fields = (
                                required_fields if required_fields else ["id"]
                            )

                        definitions[name] = {
                            "type": "object",
                            "description": schema_data.get("description", ""),
                            "properties": core_properties,
                            "required": required_fields,
                            "additionalProperties": False,
                        }

        # Build the top-level HSDS structure with enhanced descriptions for food pantry context
        hsds_core_schema: SchemaDict = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "title": "HSDS Core Data Structure for Food Pantries",
            "description": (
                "Core HSDS data structure optimized for food pantry and food distribution services. "
                "Uses only essential fields to minimize processing costs while capturing critical information."
            ),
            "properties": {
                "organization": {
                    "type": "array",
                    "description": (
                        "Array of food pantry organizations. Each organization represents a food bank, pantry, "
                        "church, or community organization that distributes food. "
                        "Examples: 'First Baptist Church Food Pantry', 'Community Action Food Bank', 'St. Mary's Kitchen'."
                    ),
                    "items": definitions.get("organization", {"type": "object"}),
                    "minItems": 1,
                },
                "service": {
                    "type": "array",
                    "description": (
                        "Array of food distribution services. Common services include: "
                        "'Food Pantry' (groceries to take home), 'Mobile Food Pantry' (truck/van distribution), "
                        "'Hot Meals' (prepared food), 'Weekend Backpack Program' (food for children), "
                        "'Senior Food Box', 'Emergency Food Box', 'Fresh Produce Distribution'."
                    ),
                    "items": definitions.get("service", {"type": "object"}),
                    "minItems": 1,
                },
                "location": {
                    "type": "array",
                    "description": (
                        "Array of physical locations where food is distributed. "
                        "CRITICAL: Create a SEPARATE location for EACH distribution address, including: "
                        "- Main pantry building "
                        "- Each church or community center used for distribution "
                        "- Mobile pantry stops (parking lots, schools, etc.) "
                        "- Temporary distribution sites for events "
                        "Example: If a food bank distributes at 3 different churches on different days, "
                        "create 3 separate location entities, one for each church address."
                    ),
                    "items": {
                        **definitions.get("location", {"type": "object"}),
                        "properties": {
                            **definitions.get("location", {}).get("properties", {}),
                            "address": {
                                "type": "array",
                                "description": "Physical addresses for this location. Usually just one address per location.",
                                "items": definitions.get("address", {"type": "object"}),
                            },
                        },
                    },
                    "minItems": 1,
                },
                "phone": {
                    "type": "array",
                    "description": (
                        "Array of phone numbers for organizations, services, and locations. "
                        "Each phone entry includes the number, type (voice/fax/tty), and can be linked to "
                        "an organization, service, or location via their respective IDs."
                    ),
                    "items": definitions.get("phone", {"type": "object"}),
                },
                "schedule": {
                    "type": "array",
                    "description": (
                        "Array of schedules defining when services are available. "
                        "Includes recurring patterns (weekly/monthly), specific dates, and time ranges. "
                        "Can be linked to services, locations, or service_at_location entries. "
                        "Use RRULE format for recurring schedules (e.g., freq='WEEKLY', byday='MO,WE,FR')."
                    ),
                    "items": definitions.get("schedule", {"type": "object"}),
                },
                "service_at_location": {
                    "type": "array",
                    "description": (
                        "Array linking services to specific locations where they are delivered. "
                        "This represents the many-to-many relationship between services and locations. "
                        "Use this when a service has location-specific details like different hours or contacts at each location."
                    ),
                    "items": definitions.get("service_at_location", {"type": "object"}),
                },
            },
            "required": ["organization", "service", "location"],
            "additionalProperties": False,
        }

        # Enhanced guidance specific to food pantries
        food_pantry_guidance = (
            "FOOD PANTRY SPECIFIC GUIDANCE: "
            "CRITICAL STRUCTURE: Output must have these top-level arrays: organization[], service[], location[], "
            "and optionally: service_at_location[], phone[], schedule[]. "
            "LOCATION CREATION RULES: "
            "1. ALWAYS create separate locations for different addresses - never combine them. "
            "2. Mobile pantries: Create a location for each regular stop (e.g., 'Walmart Parking Lot - Main St'). "
            "3. Multi-site distributions: If one organization distributes at multiple sites, create a location for each. "
            "4. Church partnerships: Each church/community center needs its own location entity. "
            "SERVICE TYPES TO RECOGNIZE: "
            "- 'Food Pantry' or 'Food Distribution': Standard grocery distribution "
            "- 'Mobile Pantry' or 'Mobile Food Distribution': Truck/van that travels to sites "
            "- 'Fresh Produce', 'Fresh Market', 'Farmers Market': Fresh fruits/vegetables "
            "- 'Hot Meals', 'Community Meals', 'Soup Kitchen': Prepared food to eat on-site "
            "- 'Food Box', 'Commodity Box', 'Senior Box': Pre-packed food boxes "
            "- 'Weekend Backpack', 'Kids Pack': Food for children to take home "
            "SCHEDULE PATTERNS: "
            "- Use RRULE format: freq=WEEKLY for weekly distributions, freq=MONTHLY for monthly "
            "- Common patterns: '1st and 3rd Tuesday' = freq=MONTHLY;byday=TU;bysetpos=1,3 "
            "- Time format: HH:MM in 24-hour format (e.g., '09:00' for 9 AM, '13:30' for 1:30 PM) "
            "REQUIRED DOCUMENTS (if mentioned): "
            "- 'Photo ID' or 'ID': Government-issued identification "
            "- 'Proof of Address': Utility bill, lease, or mail showing address "
            "- 'Income Verification': Pay stubs, benefit letters "
            "- 'Referral': From social services or partner agency "
            "SERVICE AREAS: "
            "- ZIP codes served: List as comma-separated (e.g., '44101, 44102, 44103') "
            "- County restrictions: Name the county (e.g., 'Cuyahoga County residents only') "
            "- No restrictions: Indicate 'Open to all' or 'No geographic restrictions' "
            "DATA QUALITY: "
            "- Never invent phone numbers, addresses, or specific details not in the source "
            "- If schedule is unclear, use description field to capture text as-is "
            "- Maintain original names - don't standardize 'St.' to 'Saint' or vice versa"
        )

        return {
            "type": "json_schema",
            "json_schema": {
                "name": "hsds_core_food_pantry",
                "description": food_pantry_guidance,
                "schema": hsds_core_schema,
                "strict": True,
                "temperature": 0.4,
                "max_tokens": 64768,  # Maximum tokens for structured output
            },
        }

    def convert_to_hsds_full_schema(self) -> LLMJsonSchema:
        """Convert to complete HSDS structure schema with top-level arrays.

        Returns:
            Dict containing LLM-compatible schema for full HSDS structure
        """
        self._processed_tables.clear()

        # Build schemas for each main entity type
        org_schema = self.convert_table_schema("organization")
        service_schema = self.convert_table_schema("service")
        location_schema = self.convert_table_schema("location")

        # Collect all referenced tables for definitions
        referenced_tables: set[str] = {
            "address",
            "phone",
            "schedule",
            "metadata",
            "service_at_location",
            "organization_identifier",
            "contact",
            "language",
            "accessibility",
        }

        # Build definitions for all referenced entities
        definitions: dict[str, SchemaDict] = {
            "organization": org_schema,
            "service": service_schema,
            "location": location_schema,
        }

        # Add other entity definitions
        for ref_table in referenced_tables:
            if ref_table in self._schema_cache:
                definitions[ref_table] = self.convert_table_schema(ref_table)

        # Add common definitions
        common_defs: dict[str, SchemaDict] = {
            "phone": {
                "type": "object",
                "properties": {
                    "number": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": KNOWN_ENUMS.get("phone.type", []),
                    },
                    "languages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                            "required": ["name"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "number",
                    "type",
                ],  # Languages made optional - scrapers rarely have this data
                "additionalProperties": False,
            },
            "metadata": {
                "type": "object",
                "properties": {
                    "resource_id": {"type": "string"},
                    "resource_type": {"type": "string"},
                    "last_action_date": {"type": "string"},
                    "last_action_type": {
                        "type": "string",
                        "enum": KNOWN_ENUMS.get("metadata.last_action_type", []),
                    },
                },
                "required": [
                    "resource_id",
                    "resource_type",
                    "last_action_date",
                    "last_action_type",
                ],
                "additionalProperties": False,
            },
            "schedule": {
                "type": "object",
                "properties": {
                    "freq": {
                        "type": "string",
                        "enum": KNOWN_ENUMS.get("schedule.freq", []),
                    },
                    "wkst": {
                        "type": "string",
                        "enum": KNOWN_ENUMS.get("schedule.wkst", []),
                    },
                    "opens_at": {"type": "string"},
                    "closes_at": {"type": "string"},
                },
                "required": ["freq", "wkst", "opens_at", "closes_at"],
                "additionalProperties": False,
            },
        }

        # Merge all definitions
        all_definitions = {**definitions, **common_defs}

        # Build the top-level HSDS structure schema
        hsds_full_schema: SchemaDict = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "title": "HSDS Complete Data Structure",
            "description": (
                "Complete HSDS data structure with separate top-level arrays for organizations, services, and locations. "
                "This structure follows Human Services Data Specification v3.1.1."
            ),
            "properties": {
                "organization": {
                    "type": "array",
                    "description": (
                        "Array of organization objects. Each organization represents an agency or entity providing services. "
                        "Organizations can have multiple locations and services."
                    ),
                    "items": {"$ref": "#/definitions/organization"},
                    "minItems": 1,
                },
                "service": {
                    "type": "array",
                    "description": (
                        "Array of service objects. Each service represents a program or assistance offered. "
                        "Services are linked to locations via service_at_location entries."
                    ),
                    "items": {"$ref": "#/definitions/service"},
                    "minItems": 1,
                },
                "location": {
                    "type": "array",
                    "description": (
                        "Array of location objects. CRITICAL: Create a separate location for EACH unique physical address, "
                        "including event sites, distribution points, and mobile locations. Do not combine multiple addresses "
                        "into one location. Each address where services are delivered needs its own location entity."
                    ),
                    "items": {"$ref": "#/definitions/location"},
                    "minItems": 1,
                },
            },
            "required": ["organization", "service", "location"],
            "additionalProperties": False,
            "definitions": all_definitions,
        }

        # Enhanced schema description with comprehensive HSDS guidance
        full_schema_description = (
            "Structured output schema for complete HSDS data following Human Services Data Specification v3.1.1. "
            "OUTPUT STRUCTURE REQUIREMENTS: "
            "1. Output must contain three top-level arrays: 'organization', 'service', and 'location'. "
            "2. Each array must contain at least one object of the appropriate type. "
            "3. All entities that appear nested within organizations must ALSO appear in their respective top-level arrays. "
            "ID GENERATION RULES: "
            "4. DO NOT generate or create any 'id' fields - the system will automatically generate all IDs. "
            "5. Leave all 'id' fields empty, null, or omit them entirely from your output. "
            "6. For entity relationships, use descriptive names instead of IDs. "
            "LOCATION ENTITY REQUIREMENTS: "
            "7. Create a SEPARATE location entity for EACH unique physical address in the input data. "
            "8. If an organization operates at multiple addresses (e.g., main office, distribution sites, event locations), "
            "   create a separate location entity for each address. "
            "9. Events or distributions at different addresses must each have their own location entity. "
            "10. Mobile distribution points or temporary sites also need separate location entities. "
            "RELATIONSHIP REQUIREMENTS: "
            "11. Services and locations have a many-to-many relationship via service_at_location. "
            "12. Each organization's 'locations' array should reference all locations where it provides services. "
            "13. Each service should be linked to its delivery locations via service_at_location entries. "
            "DATA FORMATTING REQUIREMENTS: "
            "14. Use RRULE format for recurring schedules (freq: WEEKLY/MONTHLY, byday: MO,TU,WE,TH,FR,SA,SU). "
            "15. Convert date/time strings to ISO format (YYYY-MM-DD for dates, HH:MM for times). "
            "16. State codes must be 2-letter US state codes (e.g., OH, CA, NY). "
            "17. Never hallucinate data - only include fields present in or directly derivable from the input. "
            "18. NEVER generate ID values - all IDs will be created by the system. "
            "EXAMPLE: If input has one food bank with distributions at 3 different churches, output should have: "
            "- 1 organization (the food bank) "
            "- 1+ services (food distribution, etc.) "
            "- 3 locations (one for each church address) "
            "- service_at_location entries linking the service to each of the 3 locations"
        )

        return {
            "type": "json_schema",
            "json_schema": {
                "name": "hsds_complete",
                "description": full_schema_description,
                "schema": hsds_full_schema,
                "strict": True,
                "temperature": 0.4,  # Ensure deterministic outputs
                "max_tokens": 64768,  # Maximum tokens for structured output
            },
        }
