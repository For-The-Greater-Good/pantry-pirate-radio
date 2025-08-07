"""Schema converter for HSDS data structures.

This module handles conversion of HSDS schemas into structured formats
suitable for LLM processing.
"""

import csv
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
    # Geographic coordinates
    "latitude": {
        "type": "number",
        "minimum": -90,
        "maximum": 90,
        "description": "Latitude in decimal degrees (-90 to 90, negative = south)",
    },
    "longitude": {
        "type": "number",
        "minimum": -180,
        "maximum": 180,
        "description": "Longitude in decimal degrees (-180 to 180, negative = west)",
    },
    "location.latitude": {
        "type": "number",
        "minimum": -90,
        "maximum": 90,
        "description": "Location latitude in decimal degrees",
    },
    "location.longitude": {
        "type": "number",
        "minimum": -180,
        "maximum": 180,
        "description": "Location longitude in decimal degrees",
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
        "description": "ISO 3166-1 country code (2 letters, e.g., US)",
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
    "phone.extension": {"type": "number", "minimum": 0},
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
        if field.one_to_many:
            ref_name = field.one_to_many.replace(".json", "")
            return {
                "type": "array",
                "description": (
                    f"Array of {ref_name} objects. These must be included both here "
                    f"and in the top-level {ref_name} array. Each {ref_name} must "
                    f"reference back to this {field.table_name} via {ref_name}_id."
                ),
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

        schema: SchemaDict = {
            "type": "object",
            "title": f"HSDS {table_name.title()}",
            "description": f"Schema for {table_name} data in HSDS format",
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
                "required": ["number", "type", "languages"],
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
                    "city",
                    "state_province",
                    "postal_code",
                    "country",
                    "address_type",
                ]
            )
        elif table_name == "phone":
            required_fields.extend(["number", "type", "languages"])
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
        return {
            "type": "json_schema",
            "json_schema": {
                "name": f"hsds_{table_name}",
                "description": f"Structured output schema for HSDS {table_name} data",
                "schema": schema,
                "strict": True,
                "max_tokens": 64768,
                "temperature": 0.4,  # Ensure deterministic outputs
            },
        }
