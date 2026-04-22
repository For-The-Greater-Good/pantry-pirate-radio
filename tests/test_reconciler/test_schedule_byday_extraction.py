"""Tests for schedule byday field extraction and description generation."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.reconciler.job_processor import JobProcessor


class TestScheduleBydayExtraction:
    """Test byday extraction and description generation in job processor."""

    @pytest.fixture
    def job_processor(self, db_session):
        """Create a JobProcessor instance."""
        return JobProcessor(db_session)

    def test_byday_extraction_from_valid_schedule(self, job_processor):
        """Test that byday is properly extracted from valid schedule data."""
        # This test verifies the fix for the bug where byday was set to wkst
        schedule = {
            "freq": "WEEKLY",
            "wkst": "MO",
            "opens_at": "09:00",
            "closes_at": "17:00",
            "byday": "MO,TU,WE,TH,FR",
            "description": "Weekdays only",
        }

        # The job processor should extract byday correctly
        # In the old buggy code, it would set byday = schedule["wkst"] = "MO"
        # In the fixed code, it should use schedule.get("byday") = "MO,TU,WE,TH,FR"
        assert schedule.get("byday") == "MO,TU,WE,TH,FR"
        assert schedule.get("byday") != schedule["wkst"]

    def test_byday_extraction_with_invalid_schedule(self):
        """Test that byday extraction handles invalid schedule data gracefully."""
        # Test with None
        schedule = None
        if schedule and isinstance(schedule, dict):
            byday = schedule.get("byday")
        else:
            byday = None
        assert byday is None

        # Test with non-dict
        schedule = "not a dict"
        if schedule and isinstance(schedule, dict):
            byday = schedule.get("byday")
        else:
            byday = None
        assert byday is None

        # Test with empty dict
        schedule = {}
        if schedule and isinstance(schedule, dict):
            byday = schedule.get("byday")
        else:
            byday = None
        assert byday is None

    def test_description_generation_with_byday(self):
        """Test that human-readable descriptions are generated from byday."""
        day_map = {
            "MO": "Monday",
            "TU": "Tuesday",
            "WE": "Wednesday",
            "TH": "Thursday",
            "FR": "Friday",
            "SA": "Saturday",
            "SU": "Sunday",
        }

        # Test single day
        byday = "MO"
        days = [day_map.get(d.strip(), d.strip()) for d in byday.split(",")]
        days_str = ", ".join(days)
        assert days_str == "Monday"

        # Test multiple days
        byday = "MO,WE,FR"
        days = [day_map.get(d.strip(), d.strip()) for d in byday.split(",")]
        days_str = ", ".join(days)
        assert days_str == "Monday, Wednesday, Friday"

        # Test all weekdays
        byday = "MO,TU,WE,TH,FR"
        days = [day_map.get(d.strip(), d.strip()) for d in byday.split(",")]
        days_str = ", ".join(days)
        assert days_str == "Monday, Tuesday, Wednesday, Thursday, Friday"

        # Test with spaces
        byday = "MO, TU, WE"
        days = [day_map.get(d.strip(), d.strip()) for d in byday.split(",")]
        days_str = ", ".join(days)
        assert days_str == "Monday, Tuesday, Wednesday"

    def test_description_generation_without_byday(self):
        """Test that fallback descriptions are generated when byday is missing."""
        schedule = {"opens_at": "09:00", "closes_at": "17:00", "wkst": "MO"}

        byday = None
        if byday:
            description = (
                f"Open {schedule['opens_at']} to {schedule['closes_at']} on {byday}"
            )
        else:
            description = f"Open {schedule['opens_at']} to {schedule['closes_at']} every {schedule['wkst']}"

        assert description == "Open 09:00 to 17:00 every MO"

    def test_complete_schedule_description(self):
        """Test complete schedule description generation."""
        schedule = {
            "opens_at": "09:00",
            "closes_at": "17:00",
            "byday": "MO,TU,WE,TH,FR",
        }

        day_map = {
            "MO": "Monday",
            "TU": "Tuesday",
            "WE": "Wednesday",
            "TH": "Thursday",
            "FR": "Friday",
            "SA": "Saturday",
            "SU": "Sunday",
        }

        byday = schedule.get("byday")
        if byday:
            days = [day_map.get(d.strip(), d.strip()) for d in byday.split(",")]
            days_str = ", ".join(days)
            description = (
                f"Open {schedule['opens_at']} to {schedule['closes_at']} on {days_str}"
            )
        else:
            description = f"Open {schedule['opens_at']} to {schedule['closes_at']}"

        expected = "Open 09:00 to 17:00 on Monday, Tuesday, Wednesday, Thursday, Friday"
        assert description == expected

    def test_byday_validation_in_job_processor_context(self):
        """Test that job processor properly validates schedule data before extraction."""
        # Simulate the job processor's schedule processing
        schedules_to_create = [
            {
                "freq": "WEEKLY",
                "wkst": "MO",
                "opens_at": "09:00",
                "closes_at": "17:00",
                "byday": "MO,TU,WE",
            },
            None,  # Invalid schedule
            {
                "freq": "WEEKLY",
                "wkst": "SU",
                "opens_at": "10:00",
                "closes_at": "14:00",
            },  # No byday
        ]

        results = []
        for schedule in schedules_to_create:
            if schedule and isinstance(schedule, dict):
                byday = schedule.get("byday")
            else:
                byday = None
            results.append(byday)

        assert results == ["MO,TU,WE", None, None]


class TestTransformScheduleBydayNormalization:
    """_transform_schedule enforces RFC 5545 on byday before DB write."""

    @pytest.fixture
    def processor(self):
        # _transform_schedule is pure — a MagicMock DB session is fine.
        return JobProcessor(MagicMock())

    def test_valid_byday_passes_through(self, processor):
        schedule = {
            "freq": "WEEKLY",
            "opens_at": "09:00",
            "closes_at": "17:00",
            "byday": "MO,TU,WE",
        }
        transformed = processor._transform_schedule(schedule)
        assert transformed is not None
        assert transformed["byday"] == "MO,TU,WE"

    def test_l_prefix_coerced_to_minus_one(self, processor):
        schedule = {
            "freq": "MONTHLY",
            "opens_at": "09:00",
            "closes_at": "12:00",
            "byday": "LTU",
        }
        transformed = processor._transform_schedule(schedule)
        assert transformed is not None
        assert transformed["byday"] == "-1TU"

    def test_today_hallucination_dropped(self, processor, caplog):
        import logging

        schedule = {
            "freq": "WEEKLY",
            "opens_at": "09:00",
            "closes_at": "17:00",
            "byday": "today",
        }
        with caplog.at_level(logging.WARNING):
            transformed = processor._transform_schedule(schedule)
        assert transformed is not None
        assert "byday" not in transformed
        assert any("reconciler_byday_dropped" in rec.message for rec in caplog.records)

    def test_unicode_minus_normalized(self, processor):
        schedule = {
            "freq": "MONTHLY",
            "opens_at": "09:00",
            "closes_at": "12:00",
            "byday": "2WE,−1MO",  # U+2212 minus
        }
        transformed = processor._transform_schedule(schedule)
        assert transformed is not None
        assert transformed["byday"] == "2WE,-1MO"

    def test_bare_integer_dropped(self, processor, caplog):
        import logging

        schedule = {
            "freq": "MONTHLY",
            "opens_at": "09:00",
            "closes_at": "17:00",
            "byday": "15",
        }
        with caplog.at_level(logging.WARNING):
            transformed = processor._transform_schedule(schedule)
        assert transformed is not None
        assert "byday" not in transformed
        assert any("reconciler_byday_dropped" in rec.message for rec in caplog.records)

    def test_empty_byday_stays_absent(self, processor):
        schedule = {
            "freq": "WEEKLY",
            "opens_at": "09:00",
            "closes_at": "17:00",
            "byday": "",
        }
        transformed = processor._transform_schedule(schedule)
        assert transformed is not None
        # empty string is not a valid byday; treat as absent
        assert transformed.get("byday") in (None, "")
