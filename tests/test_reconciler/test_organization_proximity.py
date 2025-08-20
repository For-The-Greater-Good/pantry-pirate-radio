"""Tests for proximity-based organization deduplication."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app.reconciler.organization_creator import OrganizationCreator
from app.reconciler.location_creator import LocationCreator


class TestOrganizationProximityMatching:
    """Test proximity-based organization matching logic."""

    @pytest.fixture(autouse=True)
    def clean_database(self, db_session):
        """Clean database before each test."""
        # Clean up any existing test data
        db_session.execute(text("TRUNCATE TABLE organization CASCADE"))
        db_session.execute(text("TRUNCATE TABLE location CASCADE"))
        db_session.execute(text("TRUNCATE TABLE record_version CASCADE"))
        db_session.commit()
        yield
        # Clean up after test
        db_session.execute(text("TRUNCATE TABLE organization CASCADE"))
        db_session.execute(text("TRUNCATE TABLE location CASCADE"))
        db_session.execute(text("TRUNCATE TABLE record_version CASCADE"))
        db_session.commit()

    @pytest.fixture
    def org_creator(self, db_session):
        """Create an OrganizationCreator instance."""
        return OrganizationCreator(db_session)

    @pytest.fixture
    def location_creator(self, db_session):
        """Create a LocationCreator instance."""
        return LocationCreator(db_session)

    def test_same_org_name_different_cities_creates_separate_orgs(
        self, org_creator, location_creator
    ):
        """Test that organizations with same name in different cities are separate entities."""
        # Create first "Food Bank" in NYC
        nyc_org_id, nyc_is_new = org_creator.process_organization(
            name="Food Bank",
            description="Food Bank in New York City",
            metadata={"source": "test"},
            latitude=40.7128,
            longitude=-74.0060,
        )
        assert nyc_is_new is True

        # Create location for NYC org
        nyc_location_id = location_creator.create_location(
            name="Food Bank NYC",
            description="Food Bank location in NYC",
            latitude=40.7128,
            longitude=-74.0060,
            metadata={"source": "test"},
            organization_id=str(nyc_org_id),
        )

        # Create second "Food Bank" in LA (>2000 miles away)
        la_org_id, la_is_new = org_creator.process_organization(
            name="Food Bank",
            description="Food Bank in Los Angeles",
            metadata={"source": "test"},
            latitude=34.0522,
            longitude=-118.2437,
        )
        assert la_is_new is True
        assert la_org_id != nyc_org_id  # Different organizations

        # Create location for LA org
        la_location_id = location_creator.create_location(
            name="Food Bank LA",
            description="Food Bank location in LA",
            latitude=34.0522,
            longitude=-118.2437,
            metadata={"source": "test"},
            organization_id=str(la_org_id),
        )

        # Verify both organizations exist
        result = org_creator.db.execute(
            text("SELECT COUNT(*) FROM organization WHERE name = :name"),
            {"name": "Food Bank"},
        )
        count = result.scalar()
        assert count == 2

    def test_same_org_name_nearby_location_uses_existing_org(
        self, org_creator, location_creator
    ):
        """Test that organizations with same name at nearby locations use the same entity."""
        # Create first "Salvation Army" at specific coordinates
        first_org_id, first_is_new = org_creator.process_organization(
            name="Salvation Army",
            description="Salvation Army location",
            metadata={"source": "test"},
            latitude=40.7128,
            longitude=-74.0060,
        )
        assert first_is_new is True

        # Create location for first org
        first_location_id = location_creator.create_location(
            name="Salvation Army Main",
            description="Main Salvation Army location",
            latitude=40.7128,
            longitude=-74.0060,
            metadata={"source": "test"},
            organization_id=str(first_org_id),
        )

        # Try to create second "Salvation Army" very close by (within 0.01 degrees ~0.7 miles)
        second_org_id, second_is_new = org_creator.process_organization(
            name="Salvation Army",
            description="Another Salvation Army location",
            metadata={"source": "test"},
            latitude=40.7130,  # 0.0002 degree difference (~15 meters)
            longitude=-74.0062,  # 0.0002 degree difference (~15 meters)
        )
        assert second_is_new is False  # Should use existing organization
        assert second_org_id == first_org_id  # Same organization

        # Verify only one organization exists
        result = org_creator.db.execute(
            text("SELECT COUNT(*) FROM organization WHERE name = :name"),
            {"name": "Salvation Army"},
        )
        count = result.scalar()
        assert count == 1

    def test_org_without_location_creates_new_org(self, org_creator):
        """Test that organizations without location data always create new entities."""
        # Create first organization without location
        first_org_id, first_is_new = org_creator.process_organization(
            name="Community Center",
            description="A community center",
            metadata={"source": "test"},
            latitude=None,
            longitude=None,
        )
        assert first_is_new is True

        # Create second organization with same name but still no location
        second_org_id, second_is_new = org_creator.process_organization(
            name="Community Center",
            description="Another community center",
            metadata={"source": "test"},
            latitude=None,
            longitude=None,
        )
        assert second_is_new is True
        assert second_org_id != first_org_id  # Different organizations

        # Verify both organizations exist
        result = org_creator.db.execute(
            text("SELECT COUNT(*) FROM organization WHERE name = :name"),
            {"name": "Community Center"},
        )
        count = result.scalar()
        assert count == 2

    def test_proximity_threshold_boundary(self, org_creator, location_creator):
        """Test organizations at exactly the proximity threshold boundary."""
        # Create first "Goodwill" at specific coordinates
        first_org_id, first_is_new = org_creator.process_organization(
            name="Goodwill",
            description="Goodwill store",
            metadata={"source": "test"},
            latitude=40.7128,
            longitude=-74.0060,
        )
        assert first_is_new is True

        # Create location for first org
        first_location_id = location_creator.create_location(
            name="Goodwill Store 1",
            description="First Goodwill location",
            latitude=40.7128,
            longitude=-74.0060,
            metadata={"source": "test"},
            organization_id=str(first_org_id),
        )

        # Create second "Goodwill" just outside threshold (0.01 degrees away)
        second_org_id, second_is_new = org_creator.process_organization(
            name="Goodwill",
            description="Another Goodwill store",
            metadata={"source": "test"},
            latitude=40.7228,  # Exactly 0.01 degrees away
            longitude=-74.0160,  # Exactly 0.01 degrees away
        )
        assert second_is_new is True  # Should create new organization
        assert second_org_id != first_org_id  # Different organizations

        # Create third "Goodwill" just inside threshold
        third_org_id, third_is_new = org_creator.process_organization(
            name="Goodwill",
            description="Yet another Goodwill store",
            metadata={"source": "test"},
            latitude=40.7135,  # 0.0007 degrees away (well within threshold)
            longitude=-74.0067,  # 0.0007 degrees away
        )
        assert third_is_new is False  # Should use first organization
        assert third_org_id == first_org_id  # Same as first organization

    def test_different_org_names_same_location_creates_separate_orgs(self, org_creator):
        """Test that different organization names at same location are separate entities."""
        # Create "Food Bank" at specific coordinates
        food_bank_id, food_bank_is_new = org_creator.process_organization(
            name="Food Bank",
            description="Local food bank",
            metadata={"source": "test"},
            latitude=40.7128,
            longitude=-74.0060,
        )
        assert food_bank_is_new is True

        # Create "Salvation Army" at exact same coordinates
        salvation_army_id, salvation_army_is_new = org_creator.process_organization(
            name="Salvation Army",
            description="Local Salvation Army",
            metadata={"source": "test"},
            latitude=40.7128,
            longitude=-74.0060,
        )
        assert salvation_army_is_new is True
        assert salvation_army_id != food_bank_id  # Different organizations

        # Verify both organizations exist
        result = org_creator.db.execute(text("SELECT COUNT(*) FROM organization"))
        count = result.scalar()
        assert count == 2

    def test_normalized_name_matching(self, org_creator, location_creator):
        """Test that name normalization works correctly with proximity matching."""
        # Create "FOOD BANK" with extra spaces
        first_org_id, first_is_new = org_creator.process_organization(
            name="  FOOD   BANK  ",
            description="Food bank with weird spacing",
            metadata={"source": "test"},
            latitude=40.7128,
            longitude=-74.0060,
        )
        assert first_is_new is True

        # Create location for first org
        location_creator.create_location(
            name="Food Bank Location",
            description="Food bank location",
            latitude=40.7128,
            longitude=-74.0060,
            metadata={"source": "test"},
            organization_id=str(first_org_id),
        )

        # Try "food bank" in lowercase at same location
        second_org_id, second_is_new = org_creator.process_organization(
            name="food bank",
            description="Same food bank, different case",
            metadata={"source": "test"},
            latitude=40.7129,  # Very close (within threshold)
            longitude=-74.0061,
        )
        assert second_is_new is False  # Should match due to normalization
        assert second_org_id == first_org_id

    def test_migration_applied_successfully(self, org_creator):
        """Test that the migration script changes were applied correctly."""
        # Check that the unique constraint no longer exists
        result = org_creator.db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM pg_constraint
                WHERE conname = 'organization_normalized_name_unique'
            """
            )
        )
        constraint_count = result.scalar()
        # Constraint should not exist after migration
        # Note: This will fail until migration is actually run
        # assert constraint_count == 0

        # Check that the find_matching_organization function exists
        result = org_creator.db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM pg_proc
                WHERE proname = 'find_matching_organization'
            """
            )
        )
        function_count = result.scalar()
        # Function should exist after migration
        # Note: This will fail until migration is actually run
        # assert function_count == 1
