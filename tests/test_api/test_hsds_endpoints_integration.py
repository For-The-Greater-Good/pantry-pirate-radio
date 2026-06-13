"""End-to-end integration tests for HSDS detail/relation endpoints.

These tests previously regressed in prod with HTTP 500 ValidationError because
the handlers called `ResponseModel.model_validate(orm_object, from_attributes=True)`
on SQLAlchemy rows, triggering lazy-load on nested relationships outside the
async session. The handlers now build a dict explicitly from the ORM and
validate that dict.

Following the pattern in `tests/test_ptf_locations_integration.py`, these tests
drive the handler functions directly with a real `db_session` rather than going
through `fastapi.TestClient` — the sync TestClient runs on a different event
loop than `pytest-asyncio`'s `db_session`, which causes "Future attached to a
different loop" errors.

The seed graph: one organization → one service → one location → one
service_at_location row linking them. The bug would only fire when those inner
relationships exist (otherwise Pydantic never tries to recurse into them).
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def hsds_graph(db_session: AsyncSession):
    """Seed a minimal org → service → location → service_at_location graph."""
    org_id = str(uuid.uuid4())
    service_id = str(uuid.uuid4())
    location_id = str(uuid.uuid4())
    sal_id = str(uuid.uuid4())

    await db_session.execute(
        text(
            """
            INSERT INTO organization (id, name, description, email, website)
            VALUES (:id, :name, :desc, :email, :website)
            """
        ),
        {
            "id": org_id,
            "name": "HSDS Integration Org",
            "desc": "Seeded by test_hsds_endpoints_integration",
            "email": "ints@example.org",
            "website": "https://example.org",
        },
    )

    await db_session.execute(
        text(
            """
            INSERT INTO service (id, organization_id, name, description, status)
            VALUES (:id, :org_id, :name, :desc, 'active')
            """
        ),
        {
            "id": service_id,
            "org_id": org_id,
            "name": "Food Pantry",
            "desc": "Walk-in food assistance",
        },
    )

    await db_session.execute(
        text(
            """
            INSERT INTO location (
                id, organization_id, name, description, url,
                latitude, longitude, location_type,
                validation_status, confidence_score, is_canonical
            )
            VALUES (
                :id, :org_id, :name, :desc, :url,
                40.7128, -74.0060, 'physical',
                'verified', 75, true
            )
            """
        ),
        {
            "id": location_id,
            "org_id": org_id,
            "name": "Manhattan Pantry",
            "desc": "Pantry location",
            "url": "https://example.org/manhattan-pantry",
        },
    )

    await db_session.execute(
        text(
            """
            INSERT INTO service_at_location (id, service_id, location_id, description)
            VALUES (:id, :svc, :loc, :desc)
            """
        ),
        {
            "id": sal_id,
            "svc": service_id,
            "loc": location_id,
            "desc": "Service offered at this location",
        },
    )

    address_id = str(uuid.uuid4())
    await db_session.execute(
        text(
            """
            INSERT INTO address (
                id, location_id, attention, address_1, address_2, city,
                region, state_province, postal_code, country, address_type
            )
            VALUES (
                :id, :loc, :attention, :address_1, :address_2, :city,
                :region, :state_province, :postal_code, :country, :address_type
            )
            """
        ),
        {
            "id": address_id,
            "loc": location_id,
            "attention": "Front Desk",
            "address_1": "123 Main St",
            "address_2": "Suite 100",
            "city": "New York",
            "region": "Manhattan",
            "state_province": "NY",
            "postal_code": "10001",
            "country": "US",
            "address_type": "physical",
        },
    )

    await db_session.flush()

    return {
        "org_id": uuid.UUID(org_id),
        "service_id": uuid.UUID(service_id),
        "location_id": uuid.UUID(location_id),
        "sal_id": uuid.UUID(sal_id),
        "address_id": uuid.UUID(address_id),
    }


@pytest.mark.asyncio
async def test_get_organization_returns_200(hsds_graph, db_session: AsyncSession):
    """Regression: GET /api/v1/organizations/{id} used to 500 on all orgs that
    had at least one service."""
    from app.api.v1.organizations import get_organization

    result = await get_organization(
        organization_id=hsds_graph["org_id"],
        include_services=False,
        session=db_session,
    )

    assert str(result.id) == str(hsds_graph["org_id"])
    assert result.name == "HSDS Integration Org"


@pytest.mark.asyncio
async def test_get_organization_with_services(hsds_graph, db_session: AsyncSession):
    """`?include_services=true` must populate services without lazy-loading
    nested location relationships."""
    from app.api.v1.organizations import get_organization

    result = await get_organization(
        organization_id=hsds_graph["org_id"],
        include_services=True,
        session=db_session,
    )

    assert result.services is not None
    assert len(result.services) >= 1
    assert any(s.name == "Food Pantry" for s in result.services)


@pytest.mark.asyncio
async def test_get_service_returns_200(hsds_graph, db_session: AsyncSession):
    """Regression: GET /api/v1/services/{id} used to 500 when the service had
    locations (Pydantic recursed into location.services)."""
    from app.api.v1.services import get_service

    result = await get_service(
        service_id=hsds_graph["service_id"],
        include_locations=False,
        session=db_session,
    )

    assert str(result.id) == str(hsds_graph["service_id"])
    assert result.name == "Food Pantry"


@pytest.mark.asyncio
async def test_get_service_with_locations(hsds_graph, db_session: AsyncSession):
    from app.api.v1.services import get_service

    result = await get_service(
        service_id=hsds_graph["service_id"],
        include_locations=True,
        session=db_session,
    )

    assert result.locations is not None
    assert len(result.locations) >= 1
    assert any(loc.name == "Manhattan Pantry" for loc in result.locations)


@pytest.mark.asyncio
async def test_search_services_returns_200(hsds_graph, db_session: AsyncSession):
    """Regression: GET /api/v1/services/search?q=... used to 500 on any query."""
    from fastapi import Request
    from app.api.v1.services import search_services

    # The handler needs a Request object for pagination link building. Build a
    # minimal stub: only request.url is read by create_pagination_links.
    class _StubURL:
        def __init__(self, url: str):
            self._url = url

        def __str__(self) -> str:
            return self._url

        def include_query_params(self, **kwargs):
            return self

        def remove_query_params(self, key):
            return self

    class _StubRequest:
        url = _StubURL("http://test/api/v1/services/search")

    page = await search_services(
        request=_StubRequest(),  # type: ignore[arg-type]
        q="Pantry",
        page=1,
        per_page=10,
        status=None,
        include_locations=False,
        session=db_session,
    )

    assert page.count >= 1
    assert any(s.name == "Food Pantry" for s in page.data)


@pytest.mark.asyncio
async def test_get_location_with_services(hsds_graph, db_session: AsyncSession):
    """Regression: `?include_services=true` used to 500 because
    ServiceResponse.model_validate(sal.service) recursed into service.locations."""
    from app.api.v1.locations import get_location

    result = await get_location(
        location_id=hsds_graph["location_id"],
        include_services=True,
        session=db_session,
    )

    assert result.services is not None
    assert len(result.services) >= 1
    assert any(s.name == "Food Pantry" for s in result.services)


@pytest.mark.asyncio
async def test_get_location_includes_url_and_organization_id(
    hsds_graph, db_session: AsyncSession
):
    """L1 (issue #597): LocationResponse must surface the HSDS-core `url` and
    `organization_id` scalars that the DB already stores on `location`."""
    from app.api.v1.locations import get_location

    result = await get_location(
        location_id=hsds_graph["location_id"],
        include_services=False,
        session=db_session,
    )

    assert result.url == "https://example.org/manhattan-pantry"
    assert result.organization_id == hsds_graph["org_id"]


@pytest.mark.asyncio
async def test_list_locations_includes_url_and_organization_id(
    hsds_graph, db_session: AsyncSession
):
    """Same as above, but via the list endpoint's loc_dict fallback path."""
    from fastapi import Request
    from app.api.v1.locations import list_locations

    class _StubURL:
        def __init__(self, url: str):
            self._url = url

        def __str__(self) -> str:
            return self._url

        def include_query_params(self, **kwargs):
            return self

        def remove_query_params(self, key):
            return self

    class _StubRequest:
        url = _StubURL("http://test/api/v1/locations")

    page = await list_locations(
        request=_StubRequest(),  # type: ignore[arg-type]
        page=1,
        per_page=10,
        organization_id=None,
        include_services=False,
        session=db_session,
    )

    target = next(
        loc for loc in page.data if str(loc.id) == str(hsds_graph["location_id"])
    )
    assert target.url == "https://example.org/manhattan-pantry"
    assert target.organization_id == hsds_graph["org_id"]


@pytest.mark.asyncio
async def test_get_location_includes_addresses(hsds_graph, db_session: AsyncSession):
    """L2 (issue #599): GET /locations/{id} must nest the structured
    `addresses[]` from the `address` table."""
    from app.api.v1.locations import get_location

    result = await get_location(
        location_id=hsds_graph["location_id"],
        include_services=False,
        session=db_session,
    )

    assert result.addresses is not None
    assert len(result.addresses) == 1
    address = result.addresses[0]
    assert address.id == hsds_graph["address_id"]
    assert address.attention == "Front Desk"
    assert address.address_1 == "123 Main St"
    assert address.address_2 == "Suite 100"
    assert address.city == "New York"
    assert address.region == "Manhattan"
    assert address.state_province == "NY"
    assert address.postal_code == "10001"
    assert address.country == "US"
    assert address.address_type == "physical"


@pytest.mark.asyncio
async def test_list_locations_includes_addresses(hsds_graph, db_session: AsyncSession):
    """Same as above, but via the list endpoint."""
    from fastapi import Request
    from app.api.v1.locations import list_locations

    class _StubURL:
        def __init__(self, url: str):
            self._url = url

        def __str__(self) -> str:
            return self._url

        def include_query_params(self, **kwargs):
            return self

        def remove_query_params(self, key):
            return self

    class _StubRequest:
        url = _StubURL("http://test/api/v1/locations")

    page = await list_locations(
        request=_StubRequest(),  # type: ignore[arg-type]
        page=1,
        per_page=10,
        organization_id=None,
        include_services=False,
        session=db_session,
    )

    target = next(
        loc for loc in page.data if str(loc.id) == str(hsds_graph["location_id"])
    )
    assert target.addresses is not None
    assert len(target.addresses) == 1
    assert target.addresses[0].address_1 == "123 Main St"


@pytest.mark.asyncio
async def test_get_service_at_location_with_details(
    hsds_graph, db_session: AsyncSession
):
    from app.api.v1.service_at_location import get_service_at_location

    result = await get_service_at_location(
        service_at_location_id=hsds_graph["sal_id"],
        include_details=True,
        session=db_session,
    )

    assert result.service is not None
    assert result.service.name == "Food Pantry"
    assert result.location is not None
    assert result.location.name == "Manhattan Pantry"


@pytest.mark.asyncio
async def test_get_locations_for_service_returns_200(
    hsds_graph, db_session: AsyncSession
):
    """Regression: GET /api/v1/service-at-location/service/{id}/locations used to
    500 because the repo eager-loaded `location` but not `service`, and
    model_validate(sal) tried to access sal.service."""
    from fastapi import Request
    from app.api.v1.service_at_location import get_locations_for_service

    class _StubURL:
        def __init__(self, url: str):
            self._url = url

        def __str__(self) -> str:
            return self._url

        def include_query_params(self, **kwargs):
            return self

        def remove_query_params(self, key):
            return self

    class _StubRequest:
        url = _StubURL("http://test/api/v1/service-at-location/service/x/locations")

    page = await get_locations_for_service(
        request=_StubRequest(),  # type: ignore[arg-type]
        service_id=hsds_graph["service_id"],
        page=1,
        per_page=10,
        include_details=True,
        session=db_session,
    )

    assert page.count >= 1
    assert any(sal.location_id == hsds_graph["location_id"] for sal in page.data)


@pytest.mark.asyncio
async def test_get_services_at_location_returns_200(
    hsds_graph, db_session: AsyncSession
):
    """Regression: mirror of the above, repo eager-loads `service.schedules`
    but not `location`, so accessing sal.location would lazy-load."""
    from fastapi import Request
    from app.api.v1.service_at_location import get_services_at_location

    class _StubURL:
        def __init__(self, url: str):
            self._url = url

        def __str__(self) -> str:
            return self._url

        def include_query_params(self, **kwargs):
            return self

        def remove_query_params(self, key):
            return self

    class _StubRequest:
        url = _StubURL("http://test/api/v1/service-at-location/location/x/services")

    page = await get_services_at_location(
        request=_StubRequest(),  # type: ignore[arg-type]
        location_id=hsds_graph["location_id"],
        page=1,
        per_page=10,
        include_details=True,
        session=db_session,
    )

    assert page.count >= 1
    assert any(sal.service_id == hsds_graph["service_id"] for sal in page.data)
