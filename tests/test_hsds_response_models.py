"""Tests for HSDS response models."""

from typing import Any, Dict
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.hsds.response import (
    Address,
    LocationResponse,
    MetadataResponse,
    OrganizationResponse,
    Page,
    ScheduleInfo,
    ServiceAtLocationResponse,
    ServiceResponse,
)


def test_page_model():
    """Test Page model validation."""
    data: Dict[str, Any] = {
        "count": 25,
        "total": 123,
        "per_page": 25,
        "current_page": 1,
        "page": 1,  # Add required page field
        "total_pages": 5,
        "links": {
            "first": "http://example.com/api/v1/services?page=1",
            "last": "http://example.com/api/v1/services?page=5",
            "next": "http://example.com/api/v1/services?page=2",
            "prev": None,
        },
        "data": [],
    }
    page = Page[ServiceResponse](**data)
    assert page.count == 25
    assert page.total == 123
    assert page.current_page == 1
    assert page.total_pages == 5
    assert page.links["next"] is not None
    assert page.links["prev"] is None

    # Test invalid values
    with pytest.raises(ValidationError) as exc_info:
        Page[ServiceResponse](
            count=-1,  # Invalid: must be >= 0
            total=123,
            per_page=25,
            current_page=1,
            page=1,
            total_pages=5,
            links={},
            data=[],
        )
    assert "Input should be greater than or equal to 0" in str(exc_info.value)


def test_metadata_response():
    """Test MetadataResponse model validation."""
    data: Dict[str, Any] = {
        "last_updated": "2024-02-06T20:46:26Z",
        "coverage_area": "San Francisco Bay Area",
        "data_source": "Community Food Bank API",
        "license": "CC BY-SA 4.0",
    }
    metadata = MetadataResponse(**data)
    assert metadata.last_updated == "2024-02-06T20:46:26Z"
    assert metadata.coverage_area == "San Francisco Bay Area"
    assert metadata.data_source == "Community Food Bank API"
    assert metadata.license == "CC BY-SA 4.0"


def test_service_response():
    """Test ServiceResponse model validation."""
    service_id = uuid4()
    org_id = uuid4()
    data: Dict[str, Any] = {
        "id": service_id,
        "organization_id": org_id,
        "name": "Food Pantry Service",
        "description": "Weekly food distribution",
        "url": "http://example.com/food-pantry",
        "email": "pantry@example.com",
        "status": "active",
        "metadata": {
            "last_updated": "2024-02-06T20:46:26Z",
            "data_source": "Direct Input",
        },
    }
    service = ServiceResponse(**data)
    assert service.id == service_id
    assert service.organization_id == org_id
    assert service.name == "Food Pantry Service"
    assert service.status == "active"
    assert service.metadata is not None
    assert service.metadata.last_updated == "2024-02-06T20:46:26Z"


def test_organization_response():
    """Test OrganizationResponse model validation."""
    org_id = uuid4()
    data: Dict[str, Any] = {
        "id": org_id,
        "name": "Community Food Bank",
        "description": "Local food bank serving the community",
        "url": "http://example.com/food-bank",
        "email": "info@example.com",
        "metadata": {
            "last_updated": "2024-02-06T20:46:26Z",
            "data_source": "Direct Input",
        },
    }
    org = OrganizationResponse(**data)
    assert org.id == org_id
    assert org.name == "Community Food Bank"
    assert org.metadata is not None
    assert org.metadata.last_updated == "2024-02-06T20:46:26Z"


def test_location_response():
    """Test LocationResponse model validation."""
    location_id = uuid4()
    data: Dict[str, Any] = {
        "id": location_id,
        "name": "Downtown Food Pantry",
        "description": "Main distribution center",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "metadata": {
            "last_updated": "2024-02-06T20:46:26Z",
            "data_source": "Direct Input",
        },
    }
    location = LocationResponse(**data)
    assert location.id == location_id
    assert location.name == "Downtown Food Pantry"
    assert location.latitude == 37.7749
    assert location.longitude == -122.4194
    assert location.metadata is not None
    assert location.metadata.last_updated == "2024-02-06T20:46:26Z"


def test_location_response_url_and_organization_id():
    """L1 (issue #597): `url` and `organization_id` are optional HSDS-core
    location scalars, default to None, and `url` stays a plain string (no
    HttpUrl trailing-slash normalization that would mutate served values and
    break the Tier-B byte round-trip)."""
    location_id = uuid4()
    org_id = uuid4()

    # Defaults: both None when not supplied.
    bare = LocationResponse(id=location_id, name="Bare Location")
    assert bare.url is None
    assert bare.organization_id is None

    # Accepted when supplied, and url is NOT mutated (no trailing slash added).
    location = LocationResponse(
        id=location_id,
        name="Downtown Food Pantry",
        url="http://example.com",
        organization_id=org_id,
    )
    assert location.url == "http://example.com"
    assert isinstance(location.url, str)
    assert location.organization_id == org_id


def test_address_model_required_fields():
    """L2 (issue #599): `Address` enforces the HSDS-required scalars
    (address_1, city, state_province, postal_code, country, address_type)."""
    address_id = uuid4()

    address = Address(
        id=address_id,
        address_1="123 Main St",
        city="Anytown",
        state_province="NY",
        postal_code="10001",
        country="US",
        address_type="physical",
    )
    assert address.id == address_id
    assert address.address_1 == "123 Main St"
    assert address.city == "Anytown"
    assert address.state_province == "NY"
    assert address.postal_code == "10001"
    assert address.country == "US"
    assert address.address_type == "physical"

    # Optional fields default to None when not supplied.
    assert address.attention is None
    assert address.address_2 is None
    assert address.region is None
    assert address.location_id is None

    # Missing a required field (address_1) raises.
    with pytest.raises(ValidationError):
        Address(
            id=uuid4(),
            city="Anytown",
            state_province="NY",
            postal_code="10001",
            country="US",
            address_type="physical",
        )


def test_address_model_optional_fields():
    """Optional Address fields (attention, address_2, region, location_id) are
    accepted when supplied."""
    address_id = uuid4()
    location_id = uuid4()

    address = Address(
        id=address_id,
        location_id=location_id,
        attention="A. Persona",
        address_1="1-30 Main Street",
        address_2="MyVillage",
        city="MyCity",
        region="MyRegion",
        state_province="MyState",
        postal_code="ABC 1234",
        country="US",
        address_type="postal",
    )
    assert address.location_id == location_id
    assert address.attention == "A. Persona"
    assert address.address_2 == "MyVillage"
    assert address.region == "MyRegion"


def test_address_model_validates_official_example():
    """The official HSDS `location.json` example's `addresses[0]` dict
    (no `location_id`, no `attributes`/`metadata`) must `model_validate`
    cleanly against `Address` (Tier-A progress on the address sub-shape)."""
    example_address = {
        "id": "74706e55-df26-4b84-80fe-ecc30b5befb4",
        "attention": "A. Persona",
        "address_1": "1-30 Main Street",
        "address_2": "MyVillage",
        "city": "MyCity",
        "region": "MyRegion",
        "state_province": "MyState",
        "postal_code": "ABC 1234",
        "country": "US",
        "address_type": "postal",
    }
    address = Address.model_validate(example_address)
    assert str(address.id) == example_address["id"]
    assert address.attention == "A. Persona"
    assert address.address_1 == "1-30 Main Street"
    assert address.address_2 == "MyVillage"
    assert address.city == "MyCity"
    assert address.region == "MyRegion"
    assert address.state_province == "MyState"
    assert address.postal_code == "ABC 1234"
    assert address.country == "US"
    assert address.address_type == "postal"


def test_address_model_jcs_round_trip_with_official_example():
    """`Address` validated from the official example round-trips byte-equal
    via `app.federation.canonical.jcs_bytes` after `model_dump(mode="json",
    exclude_none=True)` (no location_id/attributes/metadata leak in)."""
    from app.federation.canonical import jcs_bytes

    example_address = {
        "id": "74706e55-df26-4b84-80fe-ecc30b5befb4",
        "attention": "A. Persona",
        "address_1": "1-30 Main Street",
        "address_2": "MyVillage",
        "city": "MyCity",
        "region": "MyRegion",
        "state_province": "MyState",
        "postal_code": "ABC 1234",
        "country": "US",
        "address_type": "postal",
    }
    address = Address.model_validate(example_address)
    dumped = address.model_dump(mode="json", exclude_none=True)
    assert dumped == example_address
    # Byte-for-byte round trip: re-canonicalizing the dump is idempotent.
    assert jcs_bytes(dumped) == jcs_bytes(example_address)


def test_location_response_addresses_field():
    """L2 (issue #599): `LocationResponse.addresses` defaults to None and
    accepts a list of `Address` models."""
    location_id = uuid4()

    bare = LocationResponse(id=location_id, name="Bare Location")
    assert bare.addresses is None

    address = Address(
        id=uuid4(),
        location_id=location_id,
        address_1="123 Main St",
        city="Anytown",
        state_province="NY",
        postal_code="10001",
        country="US",
        address_type="physical",
    )
    location = LocationResponse(
        id=location_id,
        name="Downtown Food Pantry",
        addresses=[address],
    )
    assert location.addresses is not None
    assert len(location.addresses) == 1
    assert location.addresses[0].address_1 == "123 Main St"


def test_service_at_location_response():
    """Test ServiceAtLocationResponse model validation."""
    service_id = uuid4()
    location_id = uuid4()
    data: Dict[str, Any] = {
        "id": uuid4(),
        "service_id": service_id,
        "location_id": location_id,
        "metadata": {
            "last_updated": "2024-02-06T20:46:26Z",
            "data_source": "Direct Input",
        },
    }
    sal = ServiceAtLocationResponse(**data)
    assert sal.service_id == service_id
    assert sal.location_id == location_id
    assert sal.metadata is not None
    assert sal.metadata.last_updated == "2024-02-06T20:46:26Z"


def test_nested_relationships():
    """Test nested relationship handling in response models."""
    service_id = uuid4()
    org_id = uuid4()
    location_id = uuid4()

    # Create a service with a location
    service_data: Dict[str, Any] = {
        "id": service_id,
        "organization_id": org_id,
        "name": "Food Pantry Service",
        "description": "Weekly food distribution",
        "status": "active",
        "locations": [
            {
                "id": location_id,
                "name": "Downtown Location",
                "latitude": 37.7749,
                "longitude": -122.4194,
            }
        ],
    }
    service = ServiceResponse(**service_data)
    assert service.locations is not None
    assert len(service.locations) == 1
    assert service.locations[0].id == location_id
    assert service.locations[0].latitude == 37.7749

    # Create an organization with services
    org_data: Dict[str, Any] = {
        "id": org_id,
        "name": "Community Food Bank",
        "services": [service_data],
    }
    org = OrganizationResponse(**org_data)
    assert org.services is not None
    assert len(org.services) == 1
    assert org.services[0].id == service_id
    assert org.services[0].locations is not None
    assert len(org.services[0].locations) == 1
    assert org.services[0].locations[0].id == location_id


def test_response_model_defaults():
    """Test default values in response models."""
    service = ServiceResponse(
        id=uuid4(),
        organization_id=uuid4(),
        name="Test Service",
        description="Test Description",
        status="active",
    )
    assert service.url is None
    assert service.email is None
    assert service.locations is None
    assert service.metadata is None

    org = OrganizationResponse(
        id=uuid4(),
        name="Test Organization",
    )
    assert org.description is None
    assert org.url is None
    assert org.email is None
    assert org.services is None
    assert org.metadata is None

    location = LocationResponse(
        id=uuid4(),
        name="Test Location",
    )
    assert location.description is None
    assert location.latitude is None
    assert location.longitude is None
    assert location.services is None
    assert location.metadata is None


class TestScheduleInfoBydayValidation:
    """ScheduleInfo enforces RFC 5545 byday via the shared ical normalizer."""

    @pytest.mark.parametrize(
        "byday,expected",
        [
            ("MO", "MO"),
            ("MO,TU,WE,TH,FR", "MO,TU,WE,TH,FR"),
            ("1FR", "1FR"),
            ("3TU,-1MO", "3TU,-1MO"),
            ("+1WE", "+1WE"),
        ],
    )
    def test_valid_byday_passes(self, byday: str, expected: str) -> None:
        schedule = ScheduleInfo(byday=byday, freq="WEEKLY")
        assert schedule.byday == expected

    @pytest.mark.parametrize(
        "byday,expected",
        [
            ("Third Tuesday", "3TU"),
            ("third tuesday", "3TU"),
            ("LTU", "-1TU"),
            ("2TU,LTU", "2TU,-1TU"),
            ("Monday", "MO"),
            ("−1MO", "-1MO"),  # Unicode minus
        ],
    )
    def test_coerced_byday_normalized(self, byday: str, expected: str) -> None:
        schedule = ScheduleInfo(byday=byday, freq="WEEKLY")
        assert schedule.byday == expected

    @pytest.mark.parametrize(
        "bad_byday",
        ["today", "tomorrow", "3F", "2F,3F", "15", "20,28", "random text"],
    )
    def test_invalid_byday_raises(self, bad_byday: str) -> None:
        with pytest.raises(ValidationError):
            ScheduleInfo(byday=bad_byday, freq="WEEKLY")

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_empty_byday_becomes_none(self, empty: str | None) -> None:
        schedule = ScheduleInfo(byday=empty, freq="WEEKLY")
        assert schedule.byday is None


class TestScheduleInfoBymonthdayValidation:
    """ScheduleInfo enforces RFC 5545 bymonthday via normalize_bymonthday."""

    @pytest.mark.parametrize(
        "bymonthday,expected",
        [
            ("1", "1"),
            ("15", "15"),
            ("31", "31"),
            ("-1", "-1"),
            ("-31", "-31"),
            ("1,15", "1,15"),
            ("1,-1", "1,-1"),
            ("  1 , 15  ", "1,15"),  # whitespace stripped
        ],
    )
    def test_valid_bymonthday_passes(self, bymonthday: str, expected: str) -> None:
        schedule = ScheduleInfo(bymonthday=bymonthday, freq="MONTHLY")
        assert schedule.bymonthday == expected

    @pytest.mark.parametrize(
        "bad_bymonthday",
        ["0", "32", "-32", "100", "MO", "today", "15th", "1,0", "1,MO", "+1"],
    )
    def test_invalid_bymonthday_raises(self, bad_bymonthday: str) -> None:
        with pytest.raises(ValidationError):
            ScheduleInfo(bymonthday=bad_bymonthday, freq="MONTHLY")

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_empty_bymonthday_becomes_none(self, empty: str | None) -> None:
        schedule = ScheduleInfo(bymonthday=empty, freq="MONTHLY")
        assert schedule.bymonthday is None

    def test_bymonthday_and_byday_both_accepted(self) -> None:
        """Pydantic allows both — XOR enforcement is at submarine/reconciler layer."""
        schedule = ScheduleInfo(byday="MO", bymonthday="15", freq="MONTHLY")
        assert schedule.byday == "MO"
        assert schedule.bymonthday == "15"
