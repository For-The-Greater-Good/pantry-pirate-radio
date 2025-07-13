from typing import TypedDict


class LocationDict(TypedDict):
    name: str
    address: dict[str, str]


class ServiceDict(TypedDict):
    name: str
    organization_id: str


class OrganizationDict(TypedDict):
    name: str
    services: list[ServiceDict]


class HSDSDataDict(TypedDict):
    organization: list[OrganizationDict]
    service: list[ServiceDict]
    location: list[LocationDict]


class AlignmentAttemptDict(TypedDict):
    attempt: int
    prompt: str
    response: str
    cleaned_response: str
    is_valid: bool
    feedback: str | None
    score: float


class FieldRelationship(TypedDict):
    parent: str
    target: str | None
    description: str
