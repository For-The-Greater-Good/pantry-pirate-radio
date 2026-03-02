"""Regression test: duplicate-named locations must not overwrite each other."""

from app.reconciler.job_processor import JobProcessor
from unittest.mock import MagicMock
from sqlalchemy.orm import Session


class TestLocationKeyMapping:
    def test_duplicate_names_different_coords_preserved(self):
        """Two locations named 'Food Pantry' at different coords must both be tracked."""
        processor = JobProcessor(db=MagicMock(spec=Session))
        loc1 = {
            "name": "Food Pantry",
            "latitude": 40.7128,
            "longitude": -74.006,
        }
        loc2 = {
            "name": "Food Pantry",
            "latitude": 34.0522,
            "longitude": -118.2437,
        }

        key1 = processor._location_key(loc1)
        key2 = processor._location_key(loc2)
        assert key1 != key2

    def test_same_location_same_key(self):
        """Same name and coords must produce the same key."""
        processor = JobProcessor(db=MagicMock(spec=Session))
        loc = {
            "name": "Food Pantry",
            "latitude": 40.7128,
            "longitude": -74.006,
        }

        assert processor._location_key(loc) == processor._location_key(loc)

    def test_missing_coords_uses_name_only(self):
        """Locations without coords fall back to name-based keys."""
        processor = JobProcessor(db=MagicMock(spec=Session))
        loc = {"name": "Food Pantry"}

        key = processor._location_key(loc)
        assert "Food Pantry" in key
