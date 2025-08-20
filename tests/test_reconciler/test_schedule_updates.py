"""Tests for schedule update and versioning functionality."""

from datetime import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app.reconciler.service_creator import ServiceCreator


class TestScheduleUpdateOrCreate:
    """Test the update_or_create_schedule method."""

    @pytest.fixture
    def service_creator(self, db_session):
        """Create a ServiceCreator instance."""
        return ServiceCreator(db_session)

    @pytest.fixture
    def sample_schedule_data(self):
        """Sample schedule data for testing."""
        return {
            "freq": "WEEKLY",
            "wkst": "MO",
            "opens_at": "09:00",
            "closes_at": "17:00",
            "byday": "MO,TU,WE,TH,FR",
            "description": "Open Monday through Friday",
            "metadata": {"source": "test"},
        }

    def test_create_new_schedule(self, service_creator, sample_schedule_data):
        """Test creating a new schedule when none exists."""
        # First create an organization and service that the schedule can reference
        from app.reconciler.organization_creator import OrganizationCreator

        org_creator = OrganizationCreator(service_creator.db)
        org_id = org_creator.create_organization(
            name="Test Organization Create",
            description="Test Description",
            metadata={"source": "test"},
        )

        service_id = service_creator.create_service(
            name="Test Service",
            description="Test Description",
            organization_id=org_id,
            metadata={"source": "test"},
        )

        # Create new schedule
        schedule_id, was_updated = service_creator.update_or_create_schedule(
            freq=sample_schedule_data["freq"],
            wkst=sample_schedule_data["wkst"],
            opens_at=sample_schedule_data["opens_at"],
            closes_at=sample_schedule_data["closes_at"],
            metadata=sample_schedule_data["metadata"],
            service_id=service_id,
            byday=sample_schedule_data["byday"],
            description=sample_schedule_data["description"],
        )

        assert schedule_id is not None
        assert was_updated is False  # New creation, not an update

        # Verify schedule was created
        result = service_creator.db.execute(
            text("SELECT * FROM schedule WHERE id = :id"), {"id": str(schedule_id)}
        ).first()

        assert result is not None
        assert result.byday == "MO,TU,WE,TH,FR"
        assert result.freq == "WEEKLY"

    def test_update_existing_schedule_with_changes(
        self, service_creator, sample_schedule_data
    ):
        """Test updating an existing schedule when data changes."""
        # First create an organization and service that the schedule can reference
        from app.reconciler.organization_creator import OrganizationCreator

        org_creator = OrganizationCreator(service_creator.db)
        org_id = org_creator.create_organization(
            name="Test Organization Update",
            description="Test Description",
            metadata={"source": "test"},
        )

        service_id = service_creator.create_service(
            name="Test Service",
            description="Test Description",
            organization_id=org_id,
            metadata={"source": "test"},
        )

        # Create initial schedule
        initial_id, _ = service_creator.update_or_create_schedule(
            freq=sample_schedule_data["freq"],
            wkst=sample_schedule_data["wkst"],
            opens_at=sample_schedule_data["opens_at"],
            closes_at=sample_schedule_data["closes_at"],
            metadata=sample_schedule_data["metadata"],
            service_id=service_id,
            byday="MO,WE,FR",  # Different days initially
            description="Old description",
        )

        # Update with new data
        updated_id, was_updated = service_creator.update_or_create_schedule(
            freq=sample_schedule_data["freq"],
            wkst=sample_schedule_data["wkst"],
            opens_at=sample_schedule_data["opens_at"],
            closes_at=sample_schedule_data["closes_at"],
            metadata=sample_schedule_data["metadata"],
            service_id=service_id,
            byday=sample_schedule_data["byday"],  # Updated days
            description=sample_schedule_data["description"],  # Updated description
        )

        assert updated_id == initial_id  # Same schedule record
        assert was_updated is True  # Was updated

        # Verify schedule was updated
        result = service_creator.db.execute(
            text("SELECT * FROM schedule WHERE id = :id"), {"id": str(updated_id)}
        ).first()

        assert result.byday == "MO,TU,WE,TH,FR"
        assert result.description == "Open Monday through Friday"

    def test_skip_update_when_no_changes(self, service_creator, sample_schedule_data):
        """Test that schedule is not updated when data is unchanged."""
        # First create an organization and service that the schedule can reference
        from app.reconciler.organization_creator import OrganizationCreator

        org_creator = OrganizationCreator(service_creator.db)
        org_id = org_creator.create_organization(
            name="Test Organization NoChanges",
            description="Test Description",
            metadata={"source": "test"},
        )

        service_id = service_creator.create_service(
            name="Test Service",
            description="Test Description",
            organization_id=org_id,
            metadata={"source": "test"},
        )

        # Create initial schedule
        initial_id, _ = service_creator.update_or_create_schedule(
            freq=sample_schedule_data["freq"],
            wkst=sample_schedule_data["wkst"],
            opens_at=sample_schedule_data["opens_at"],
            closes_at=sample_schedule_data["closes_at"],
            metadata=sample_schedule_data["metadata"],
            service_id=service_id,
            byday=sample_schedule_data["byday"],
            description=sample_schedule_data["description"],
        )

        # Try to update with same data
        updated_id, was_updated = service_creator.update_or_create_schedule(
            freq=sample_schedule_data["freq"],
            wkst=sample_schedule_data["wkst"],
            opens_at=sample_schedule_data["opens_at"],
            closes_at=sample_schedule_data["closes_at"],
            metadata=sample_schedule_data["metadata"],
            service_id=service_id,
            byday=sample_schedule_data["byday"],
            description=sample_schedule_data["description"],
        )

        assert updated_id == initial_id  # Same schedule record
        assert was_updated is False  # Was NOT updated (no changes)

    def test_separate_schedules_for_different_entities(
        self, service_creator, sample_schedule_data
    ):
        """Test that different entities get separate schedules."""
        # Create organization and two services
        from app.reconciler.organization_creator import OrganizationCreator

        org_creator = OrganizationCreator(service_creator.db)
        org_id = org_creator.create_organization(
            name="Test Organization Separate",
            description="Test Description",
            metadata={"source": "test"},
        )

        service_id_1 = service_creator.create_service(
            name="Test Service 1",
            description="Test Description 1",
            organization_id=org_id,
            metadata={"source": "test"},
        )
        service_id_2 = service_creator.create_service(
            name="Test Service 2",
            description="Test Description 2",
            organization_id=org_id,
            metadata={"source": "test"},
        )

        # Create schedule for first service
        schedule_id_1, _ = service_creator.update_or_create_schedule(
            freq=sample_schedule_data["freq"],
            wkst=sample_schedule_data["wkst"],
            opens_at=sample_schedule_data["opens_at"],
            closes_at=sample_schedule_data["closes_at"],
            metadata=sample_schedule_data["metadata"],
            service_id=service_id_1,
            byday=sample_schedule_data["byday"],
            description="Service 1 schedule",
        )

        # Create schedule for second service
        schedule_id_2, _ = service_creator.update_or_create_schedule(
            freq=sample_schedule_data["freq"],
            wkst=sample_schedule_data["wkst"],
            opens_at=sample_schedule_data["opens_at"],
            closes_at=sample_schedule_data["closes_at"],
            metadata=sample_schedule_data["metadata"],
            service_id=service_id_2,
            byday=sample_schedule_data["byday"],
            description="Service 2 schedule",
        )

        assert schedule_id_1 != schedule_id_2  # Different schedules

    def test_version_tracking_on_update(self, service_creator, sample_schedule_data):
        """Test that version records are created on update."""
        # First create an organization and service that the schedule can reference
        from app.reconciler.organization_creator import OrganizationCreator

        org_creator = OrganizationCreator(service_creator.db)
        org_id = org_creator.create_organization(
            name="Test Organization Version",
            description="Test Description",
            metadata={"source": "test"},
        )

        service_id = service_creator.create_service(
            name="Test Service",
            description="Test Description",
            organization_id=org_id,
            metadata={"source": "test"},
        )

        # Create initial schedule
        initial_id, _ = service_creator.update_or_create_schedule(
            freq=sample_schedule_data["freq"],
            wkst=sample_schedule_data["wkst"],
            opens_at=sample_schedule_data["opens_at"],
            closes_at=sample_schedule_data["closes_at"],
            metadata=sample_schedule_data["metadata"],
            service_id=service_id,
            byday="MO",
            description="Initial",
        )

        # Update schedule
        with patch(
            "app.reconciler.version_tracker.VersionTracker.create_version"
        ) as mock_version:
            _, was_updated = service_creator.update_or_create_schedule(
                freq=sample_schedule_data["freq"],
                wkst=sample_schedule_data["wkst"],
                opens_at=sample_schedule_data["opens_at"],
                closes_at=sample_schedule_data["closes_at"],
                metadata=sample_schedule_data["metadata"],
                service_id=service_id,
                byday="MO,TU,WE,TH,FR",
                description="Updated",
            )

            assert was_updated is True
            # Version tracker should be called for the update
            mock_version.assert_called_once()

    def test_service_at_location_schedule_priority(
        self, service_creator, sample_schedule_data
    ):
        """Test that service_at_location takes priority over service or location."""
        # Create the necessary entities
        from app.reconciler.location_creator import LocationCreator

        location_creator = LocationCreator(service_creator.db)

        # Create a location
        location_id = location_creator.create_location(
            name="Test Location",
            description="Test Location Description",
            latitude=40.7128,
            longitude=-74.0060,
            metadata={"source": "test"},
        )

        # Create an organization and service
        from app.reconciler.organization_creator import OrganizationCreator

        org_creator = OrganizationCreator(service_creator.db)
        org_id = org_creator.create_organization(
            name="Test Organization Priority",
            description="Test Description",
            metadata={"source": "test"},
        )

        service_id = service_creator.create_service(
            name="Test Service",
            description="Test Description",
            organization_id=org_id,
            metadata={"source": "test"},
        )

        # Create service_at_location
        service_at_location_id = service_creator.create_service_at_location(
            service_id=service_id,
            location_id=location_id,
            description="Service at this location",
            metadata={"source": "test"},
        )

        # Create schedule with all three IDs
        schedule_id, _ = service_creator.update_or_create_schedule(
            freq=sample_schedule_data["freq"],
            wkst=sample_schedule_data["wkst"],
            opens_at=sample_schedule_data["opens_at"],
            closes_at=sample_schedule_data["closes_at"],
            metadata=sample_schedule_data["metadata"],
            service_id=service_id,
            location_id=location_id,
            service_at_location_id=service_at_location_id,
            byday=sample_schedule_data["byday"],
            description=sample_schedule_data["description"],
        )

        # Verify schedule is linked to service_at_location
        result = service_creator.db.execute(
            text("SELECT * FROM schedule WHERE id = :id"), {"id": str(schedule_id)}
        ).first()

        assert str(result.service_at_location_id) == str(service_at_location_id)
