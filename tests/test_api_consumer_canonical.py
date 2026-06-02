"""API-4 regression guard: consumer /locations endpoints hide hidden rows.

`ConsumerLocationService.get_map_pins` already filtered `is_canonical`, but
`get_multiple_locations` (POST /locations/multi) and `get_single_location`
(GET /locations/{id}, which delegates to get_multiple_locations) fetched rows by
id with no canonical/validation filter, so a soft-deleted duplicate or a
rejected location could be served by id.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.consumer.services import ConsumerLocationService

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def consumer_visibility(db_session: AsyncSession):
    org_id = str(uuid.uuid4())
    visible_id = str(uuid.uuid4())
    duplicate_id = str(uuid.uuid4())
    rejected_id = str(uuid.uuid4())

    await db_session.execute(
        text(
            "INSERT INTO organization (id, name, description) "
            "VALUES (:id, :name, :desc)"
        ),
        {"id": org_id, "name": "Consumer Vis Org", "desc": "API-4 seed"},
    )
    seed = [
        (visible_id, "Visible Pantry", "needs_review", True),
        (duplicate_id, "Soft-deleted Dup", "needs_review", False),
        (rejected_id, "Rejected Pantry", "rejected", True),
    ]
    for loc_id, name, status, canonical in seed:
        await db_session.execute(
            text(
                """
                INSERT INTO location (
                    id, organization_id, name, latitude, longitude,
                    location_type, validation_status, confidence_score,
                    is_canonical
                )
                VALUES (
                    :id, :org, :name, 39.0, -77.0,
                    'physical', :status, 70, :canonical
                )
                """
            ),
            {
                "id": loc_id,
                "org": org_id,
                "name": name,
                "status": status,
                "canonical": canonical,
            },
        )
    await db_session.flush()
    return {
        "visible_id": visible_id,
        "duplicate_id": duplicate_id,
        "rejected_id": rejected_id,
    }


@pytest.mark.asyncio
async def test_get_multiple_locations_excludes_hidden(db_session, consumer_visibility):
    service = ConsumerLocationService(db_session)
    result = await service.get_multiple_locations(
        [
            consumer_visibility["visible_id"],
            consumer_visibility["duplicate_id"],
            consumer_visibility["rejected_id"],
        ],
        include_sources=False,
        include_schedule=False,
    )
    ids = {loc.id for loc in result}
    assert consumer_visibility["visible_id"] in ids
    assert consumer_visibility["duplicate_id"] not in ids
    assert consumer_visibility["rejected_id"] not in ids


@pytest.mark.asyncio
async def test_get_single_location_404s_for_hidden(db_session, consumer_visibility):
    service = ConsumerLocationService(db_session)

    visible = await service.get_single_location(
        uuid.UUID(consumer_visibility["visible_id"])
    )
    assert visible.get("location") is not None

    # Soft-deleted duplicate and rejected row resolve to {} (router → 404).
    assert (
        await service.get_single_location(
            uuid.UUID(consumer_visibility["duplicate_id"])
        )
        == {}
    )
    assert (
        await service.get_single_location(uuid.UUID(consumer_visibility["rejected_id"]))
        == {}
    )
