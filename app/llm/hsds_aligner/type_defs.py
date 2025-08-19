"""Type definitions for HSDS data structures.

This module provides TypedDict definitions for HSDS data structures,
used for type hints in the codebase while validation is handled by
JSON Schema via structured outputs.
"""

from typing import Any, NotRequired, Required, TypedDict


class AddressDict(TypedDict):
    """Physical or mailing address information."""

    address_1: Required[str]
    city: Required[str]
    state_province: Required[str]
    postal_code: Required[str]
    country: Required[str]
    address_type: Required[str]
    address_2: NotRequired[str | None]
    region: NotRequired[str | None]
    attention: NotRequired[str | None]


class LanguageDict(TypedDict):
    """Language information."""

    name: Required[str]


class PhoneDict(TypedDict):
    """Phone number information."""

    number: Required[str]
    type: Required[str]
    languages: Required[list[LanguageDict]]
    extension: NotRequired[int | None]
    description: NotRequired[str | None]


class ScheduleDict(TypedDict):
    """Schedule information."""

    freq: Required[str]  # WEEKLY, MONTHLY
    wkst: Required[str]  # MO, TU, WE, TH, FR, SA, SU
    opens_at: Required[str]  # HH:MM format
    closes_at: Required[str]  # HH:MM format
    byday: NotRequired[str | None]  # MO,TU,WE,TH,FR,SA,SU
    bymonthday: NotRequired[str | None]  # Comma-separated day numbers
    byweekno: NotRequired[str | None]  # Comma-separated week numbers
    byyearday: NotRequired[str | None]  # Comma-separated day numbers
    interval: NotRequired[int | None]  # Frequency interval
    count: NotRequired[int | None]  # Number of occurrences
    valid_from: NotRequired[str | None]
    valid_to: NotRequired[str | None]
    dtstart: NotRequired[str | None]
    until: NotRequired[str | None]
    description: NotRequired[str | None]


class MetadataDict(TypedDict):
    """Metadata information."""

    resource_id: Required[str]
    resource_type: Required[str]
    last_action_date: Required[str]
    last_action_type: Required[str]


class LocationDict(TypedDict):
    """Physical location information."""

    name: Required[str]
    location_type: Required[str]  # physical, postal, virtual
    addresses: Required[list[AddressDict]]
    phones: Required[list[PhoneDict]]
    accessibility: Required[list[Any]]  # Any for now since not fully specified
    contacts: Required[list[Any]]  # Any for now since not fully specified
    schedules: Required[list[ScheduleDict]]
    languages: Required[list[LanguageDict]]
    metadata: Required[list[MetadataDict]]
    latitude: Required[float]
    longitude: Required[float]
    alternate_name: NotRequired[str | None]
    description: NotRequired[str | None]
    transportation: NotRequired[str | None]


class ServiceDict(TypedDict):
    """Service information."""

    name: Required[str]
    description: Required[str]
    status: Required[str]  # active, inactive, defunct, temporarily closed
    phones: Required[list[PhoneDict]]
    schedules: Required[list[ScheduleDict]]
    alternate_name: NotRequired[str | None]
    organization_id: NotRequired[str | None]
    url: NotRequired[str | None]
    email: NotRequired[str | None]
    application_process: NotRequired[str | None]
    fees_description: NotRequired[str | None]


class OrganizationIdentifierDict(TypedDict):
    """Organization identifier information."""

    identifier_type: Required[str]
    identifier: Required[str]


class OrganizationDict(TypedDict):
    """Organization information."""

    name: Required[str]
    description: Required[str]
    services: Required[list[ServiceDict]]
    phones: Required[list[PhoneDict]]
    organization_identifiers: Required[list[OrganizationIdentifierDict]]
    contacts: Required[list[Any]]  # Any for now since not fully specified
    metadata: Required[list[MetadataDict]]
    alternate_name: NotRequired[str | None]
    email: NotRequired[str | None]
    website: NotRequired[str | None]
    tax_id: NotRequired[str | None]
    year_incorporated: NotRequired[int | None]
    locations: NotRequired[list[LocationDict] | None]


class ValidationDetailsDict(TypedDict):
    """Validation details from alignment process."""

    hallucination_detected: Required[bool]
    mismatched_fields: Required[list[str]]
    suggested_corrections: Required[dict[str, str | None]]
    feedback: Required[str | None]


class HSDSDataDict(TypedDict):
    """Complete HSDS output structure."""

    organization: Required[list[OrganizationDict]]
    service: Required[list[ServiceDict]]
    location: Required[list[LocationDict]]


class ParsedHSDSDataDict(HSDSDataDict, total=False):
    """HSDS data with optional validation details."""

    validation_details: ValidationDetailsDict


class KnownFieldsDict(TypedDict):
    """Known fields that must be present in output."""

    organization_fields: NotRequired[list[str]]  # e.g. ["name", "description"]
    service_fields: NotRequired[list[str]]
    location_fields: NotRequired[list[str]]
    phone_fields: NotRequired[list[str]]
    address_fields: NotRequired[list[str]]
    schedule_fields: NotRequired[list[str]]


class AlignmentInputDict(TypedDict):
    """Input for HSDS alignment."""

    raw_data: Required[str]
    source_format: NotRequired[str | None]
    # Fields known to exist in input
    known_fields: NotRequired[KnownFieldsDict]


class AlignmentOutputDict(TypedDict):
    """Result of HSDS alignment."""

    hsds_data: Required[HSDSDataDict]
    confidence_score: Required[float]
    validation_details: NotRequired[ValidationDetailsDict]
