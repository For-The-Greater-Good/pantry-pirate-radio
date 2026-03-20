"""Tests for schedule entity attachment — location_id must be set on SAL schedules."""

import uuid

from sqlalchemy import text

from app.reconciler.location_creator import LocationCreator
from app.reconciler.organization_creator import OrganizationCreator
from app.reconciler.service_creator import ServiceCreator


class TestScheduleSALLocationId:
    """Schedules created through the SAL path must carry location_id."""

    def _create_entities(self, db_session):
        """Create org → service → location → SAL for test reuse."""
        org_creator = OrganizationCreator(db_session)
        svc_creator = ServiceCreator(db_session)
        loc_creator = LocationCreator(db_session)

        org_id = org_creator.create_organization(
            name="Schedule Attach Org",
            description="Test",
            metadata={"source": "test"},
        )
        service_id = svc_creator.create_service(
            name="Schedule Attach Service",
            description="Test",
            organization_id=org_id,
            metadata={"source": "test"},
        )
        location_id = loc_creator.create_location(
            name="Schedule Attach Location",
            description="Test",
            latitude=40.7128,
            longitude=-74.0060,
            metadata={"source": "test"},
        )
        sal_id = svc_creator.create_service_at_location(
            service_id=service_id,
            location_id=location_id,
            description="Service at location",
            metadata={"source": "test"},
        )
        return org_id, service_id, location_id, sal_id, svc_creator

    def test_create_schedule_via_sal_sets_location_id(self, db_session):
        """New schedule created with SAL should also have location_id populated."""
        _, _, location_id, sal_id, svc = self._create_entities(db_session)

        schedule_id, was_updated = svc.update_or_create_schedule(
            freq="WEEKLY",
            wkst="MO",
            opens_at="09:00",
            closes_at="17:00",
            service_at_location_id=sal_id,
            location_id=location_id,
            metadata={"source": "test"},
            byday="MO,TU,WE,TH,FR",
            description="Weekdays 9-5",
        )

        assert schedule_id is not None
        assert was_updated is False  # Newly created

        row = db_session.execute(
            text(
                "SELECT location_id, service_at_location_id FROM schedule WHERE id = :id"
            ),
            {"id": str(schedule_id)},
        ).first()

        assert str(row.service_at_location_id) == str(sal_id)
        assert row.location_id is not None, "location_id must be set on SAL schedules"
        assert str(row.location_id) == str(location_id)

    def test_update_schedule_populates_null_location_id(self, db_session):
        """Existing schedule with NULL location_id should get it populated on update."""
        _, _, location_id, sal_id, svc = self._create_entities(db_session)

        # Create schedule WITHOUT location_id (simulates pre-fix data)
        schedule_id, _ = svc.update_or_create_schedule(
            freq="WEEKLY",
            wkst="MO",
            opens_at="09:00",
            closes_at="17:00",
            service_at_location_id=sal_id,
            metadata={"source": "test"},
            byday="MO,WE,FR",
            description="MWF 9-5",
        )

        # Verify location_id is NULL initially
        row = db_session.execute(
            text("SELECT location_id FROM schedule WHERE id = :id"),
            {"id": str(schedule_id)},
        ).first()
        assert row.location_id is None, "Precondition: location_id should be NULL"

        # Call again WITH location_id — should trigger update to set it
        updated_id, was_updated = svc.update_or_create_schedule(
            freq="WEEKLY",
            wkst="MO",
            opens_at="09:00",
            closes_at="17:00",
            service_at_location_id=sal_id,
            location_id=location_id,
            metadata={"source": "test"},
            byday="MO,WE,FR",
            description="MWF 9-5",
        )

        assert updated_id == schedule_id  # Same record
        assert was_updated is True, "Should trigger update to populate location_id"

        row = db_session.execute(
            text("SELECT location_id FROM schedule WHERE id = :id"),
            {"id": str(updated_id)},
        ).first()
        assert row.location_id is not None, "location_id must be populated after update"
        assert str(row.location_id) == str(location_id)
