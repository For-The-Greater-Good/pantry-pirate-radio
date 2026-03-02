"""Regression test: schedule times in non-HH:MM formats must not crash."""

import pytest
from datetime import time
from app.reconciler.service_creator import ServiceCreator
from unittest.mock import MagicMock
from sqlalchemy.orm import Session


class TestTimeParsing:
    @pytest.mark.parametrize(
        "time_str,expected_hour,expected_minute",
        [
            ("09:00", 9, 0),
            ("17:00", 17, 0),
            ("9:00 AM", 9, 0),
            ("5:00 PM", 17, 0),
            ("09:00:00", 9, 0),
            ("9AM", 9, 0),
            ("12:30 PM", 12, 30),
        ],
    )
    def test_parse_time_various_formats(
        self, time_str, expected_hour, expected_minute
    ):
        """_parse_time must handle common time formats without crashing."""
        creator = ServiceCreator(MagicMock(spec=Session))
        result = creator._parse_time(time_str)
        assert result is not None
        assert result.hour == expected_hour
        assert result.minute == expected_minute

    def test_parse_time_none_input(self):
        """None input returns None."""
        creator = ServiceCreator(MagicMock(spec=Session))
        assert creator._parse_time(None) is None

    def test_parse_time_garbage_returns_none(self):
        """Unparseable input returns None, does not crash."""
        creator = ServiceCreator(MagicMock(spec=Session))
        assert creator._parse_time("whenever") is None

    def test_parse_time_empty_string(self):
        """Empty string returns None."""
        creator = ServiceCreator(MagicMock(spec=Session))
        assert creator._parse_time("") is None
