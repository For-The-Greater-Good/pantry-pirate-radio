"""Tests for SubmarineLocationHandler — submarine-specific reconciler logic.

Extracted from job_processor.py per Constitution Principle IX (file size limits).
"""

import uuid
from unittest.mock import MagicMock, call

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.reconciler.submarine_location_handler import SubmarineLocationHandler


class TestResolveTargetLocation:
    """Test submarine's direct ID-based location resolution."""

    def test_returns_location_id_for_submarine_job(self):
        """When scraper_id='submarine' and location exists, return the verified ID."""
        db = MagicMock(spec=Session)
        handler = SubmarineLocationHandler(db)

        target_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        metadata = {
            "scraper_id": "submarine",
            "location_id": target_id,
        }

        mock_result = MagicMock()
        mock_result.first.return_value = (target_id,)
        db.execute.return_value = mock_result

        result = handler.resolve_target_location(metadata)

        assert result == target_id

    def test_returns_none_for_nonexistent_location(self):
        """When submarine targets a location_id that doesn't exist, return None."""
        db = MagicMock(spec=Session)
        handler = SubmarineLocationHandler(db)

        metadata = {
            "scraper_id": "submarine",
            "location_id": "loc-does-not-exist",
        }

        mock_result = MagicMock()
        mock_result.first.return_value = None
        db.execute.return_value = mock_result

        result = handler.resolve_target_location(metadata)

        assert result is None

    def test_returns_none_for_non_submarine_job(self):
        """Non-submarine jobs should return None (caller uses coordinate matching)."""
        db = MagicMock(spec=Session)
        handler = SubmarineLocationHandler(db)

        metadata = {
            "scraper_id": "some_scraper",
            "source_type": "scraper",
        }

        result = handler.resolve_target_location(metadata)

        assert result is None
        db.execute.assert_not_called()

    def test_returns_none_when_no_location_id_in_metadata(self):
        """Submarine job without location_id in metadata should return None."""
        db = MagicMock(spec=Session)
        handler = SubmarineLocationHandler(db)

        metadata = {
            "scraper_id": "submarine",
            # No location_id
        }

        result = handler.resolve_target_location(metadata)

        assert result is None
        db.execute.assert_not_called()


class TestIsSubmarineJob:
    """Test submarine job detection."""

    def test_returns_true_for_submarine(self):
        handler = SubmarineLocationHandler(MagicMock(spec=Session))
        assert handler.is_submarine_job(
            {"scraper_id": "submarine", "location_id": "abc"}
        )

    def test_returns_false_for_regular_scraper(self):
        handler = SubmarineLocationHandler(MagicMock(spec=Session))
        assert not handler.is_submarine_job({"scraper_id": "some_scraper"})

    def test_returns_false_for_empty_metadata(self):
        handler = SubmarineLocationHandler(MagicMock(spec=Session))
        assert not handler.is_submarine_job({})


class TestUpdateLocation:
    """Test submarine's dynamic location UPDATE."""

    def test_updates_all_fields_when_present(self):
        """When all fields are in the location dict, UPDATE includes all."""
        db = MagicMock(spec=Session)
        handler = SubmarineLocationHandler(db)

        location_id = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        location = {
            "name": "Grace Food Pantry",
            "description": "Community food pantry serving the area",
            "latitude": 39.78,
            "longitude": -89.65,
        }

        desc = handler.update_location(location_id, location, org_id=None)

        assert desc == "Community food pantry serving the area"
        db.execute.assert_called_once()
        db.commit.assert_called_once()

        # Check the SQL includes description
        sql_arg = str(db.execute.call_args[0][0].text)
        assert "description" in sql_arg

    def test_skips_description_when_absent(self):
        """When description key is missing, UPDATE should not include it."""
        db = MagicMock(spec=Session)
        handler = SubmarineLocationHandler(db)

        location_id = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        location = {
            "name": "Grace Food Pantry",
            "latitude": 39.78,
            "longitude": -89.65,
            # No description key
        }

        desc = handler.update_location(location_id, location, org_id=None)

        assert desc is None
        db.execute.assert_called_once()

        # Check the SQL does NOT include description
        sql_arg = str(db.execute.call_args[0][0].text)
        assert "description" not in sql_arg

    def test_generates_description_when_empty_string(self):
        """Empty string description should generate a placeholder."""
        db = MagicMock(spec=Session)
        handler = SubmarineLocationHandler(db)

        location_id = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        location = {
            "name": "Grace Food Pantry",
            "description": "",
            "latitude": 39.78,
            "longitude": -89.65,
        }

        desc = handler.update_location(location_id, location, org_id=None)

        assert desc == "Food service location: Grace Food Pantry"

    def test_includes_organization_id_when_provided(self):
        """org_id should be included in the UPDATE params."""
        db = MagicMock(spec=Session)
        handler = SubmarineLocationHandler(db)

        location_id = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        org_id = uuid.UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901")
        location = {
            "name": "Grace Food Pantry",
            "latitude": 39.78,
            "longitude": -89.65,
        }

        handler.update_location(location_id, location, org_id=org_id)

        params = db.execute.call_args[0][1]
        assert params["organization_id"] == str(org_id)


class TestPersistSchedules:
    """Test submarine schedule persistence to location."""

    def test_persists_schedules_to_location(self):
        """Schedules should be written via update_or_create_schedule with location_id."""
        db = MagicMock(spec=Session)
        handler = SubmarineLocationHandler(db)

        location_id = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        location = {
            "schedules": [
                {
                    "byday": "MO",
                    "opens_at": "09:00",
                    "closes_at": "17:00",
                    "freq": "WEEKLY",
                    "wkst": "MO",
                },
                {
                    "byday": "WE",
                    "opens_at": "10:00",
                    "closes_at": "14:00",
                    "freq": "WEEKLY",
                    "wkst": "MO",
                },
            ]
        }
        metadata = {"scraper_id": "submarine"}
        mock_service_creator = MagicMock()
        mock_service_creator.update_or_create_schedule.return_value = (
            uuid.uuid4(),
            False,
        )

        # transform_fn returns the schedule as-is (already normalized)
        def identity_transform(sched):
            return sched

        count = handler.persist_schedules(
            location_id, location, metadata, mock_service_creator, identity_transform
        )

        assert count == 2
        assert mock_service_creator.update_or_create_schedule.call_count == 2

        # Verify location_id is passed, service_at_location_id is None
        for c in mock_service_creator.update_or_create_schedule.call_args_list:
            assert c.kwargs["location_id"] == location_id
            assert c.kwargs.get("service_at_location_id") is None

    def test_skips_empty_schedules(self):
        """No schedules means no calls to update_or_create_schedule."""
        db = MagicMock(spec=Session)
        handler = SubmarineLocationHandler(db)

        location_id = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        mock_service_creator = MagicMock()

        count = handler.persist_schedules(
            location_id, {"schedules": []}, {}, mock_service_creator, lambda s: s
        )

        assert count == 0
        mock_service_creator.update_or_create_schedule.assert_not_called()

    def test_skips_no_schedules_key(self):
        """Location dict without schedules key means no calls."""
        db = MagicMock(spec=Session)
        handler = SubmarineLocationHandler(db)

        location_id = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        mock_service_creator = MagicMock()

        count = handler.persist_schedules(
            location_id, {}, {}, mock_service_creator, lambda s: s
        )

        assert count == 0
        mock_service_creator.update_or_create_schedule.assert_not_called()

    def test_skips_invalid_schedules(self):
        """Schedules that transform_fn rejects (returns None) are skipped."""
        db = MagicMock(spec=Session)
        handler = SubmarineLocationHandler(db)

        location_id = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        location = {
            "schedules": [
                {
                    "byday": "MO",
                    "opens_at": "09:00",
                    "closes_at": "17:00",
                    "freq": "WEEKLY",
                },
                {"invalid": "schedule"},  # transform will reject
            ]
        }
        mock_service_creator = MagicMock()
        mock_service_creator.update_or_create_schedule.return_value = (
            uuid.uuid4(),
            False,
        )

        # transform rejects schedules without opens_at
        def selective_transform(sched):
            if "opens_at" in sched and "closes_at" in sched:
                return sched
            return None

        count = handler.persist_schedules(
            location_id, location, {}, mock_service_creator, selective_transform
        )

        assert count == 1
        assert mock_service_creator.update_or_create_schedule.call_count == 1
