"""API-5 regression guard: one corrupt schedule row must not 500 a page.

`ScheduleInfo`'s byday/bymonthday field validators RAISE on a value the RFC 5545
normalizer can't parse (response.py). `get_location_schedules` builds a
`ScheduleInfo` per DB row, so a single un-normalizable byday/bymonthday stored by
any write path that bypassed normalization would raise and 500 the entire
/locations list (and the /locations/{id} detail) for that area.

The handler now fails soft: the bad row is logged and skipped, good rows still
render.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.locations import get_location_schedules

pytestmark = pytest.mark.integration


def test_scheduleinfo_raises_on_unnormalizable_byday():
    """Precondition: constructing ScheduleInfo with a bad byday raises."""
    from app.models.hsds.response import ScheduleInfo

    with pytest.raises(Exception):
        ScheduleInfo(
            opens_at="09:00", closes_at="17:00", freq="WEEKLY", byday="NOTADAY"
        )


@pytest_asyncio.fixture
async def location_with_corrupt_schedule(db_session: AsyncSession):
    org_id = str(uuid.uuid4())
    loc_id = str(uuid.uuid4())

    await db_session.execute(
        text(
            "INSERT INTO organization (id, name, description) "
            "VALUES (:id, :name, :desc)"
        ),
        {"id": org_id, "name": "Schedule Failsoft Org", "desc": "API-5 seed"},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO location (
                id, organization_id, name, latitude, longitude,
                location_type, validation_status, confidence_score, is_canonical
            )
            VALUES (:id, :org, 'Failsoft Pantry', 40.0, -75.0,
                    'physical', 'needs_review', 70, TRUE)
            """
        ),
        {"id": loc_id, "org": org_id},
    )
    # One valid schedule row, one corrupt byday inserted via raw SQL (bypasses
    # the Pydantic normalizer the write API would otherwise enforce).
    for byday in ("MO", "TOTALLY-INVALID-BYDAY"):
        await db_session.execute(
            text(
                """
                INSERT INTO schedule (
                    id, location_id, freq, wkst, opens_at, closes_at, byday
                )
                VALUES (:id, :loc, 'WEEKLY', 'MO', '09:00', '17:00', :byday)
                """
            ),
            {"id": str(uuid.uuid4()), "loc": loc_id, "byday": byday},
        )
    await db_session.flush()
    return loc_id


@pytest.mark.asyncio
async def test_corrupt_schedule_row_is_skipped_not_500(
    db_session, location_with_corrupt_schedule
):
    # Must NOT raise — the corrupt row is dropped, the valid one survives.
    schedules = await get_location_schedules(location_with_corrupt_schedule, db_session)
    assert len(schedules) == 1
    assert schedules[0].byday == "MO"
