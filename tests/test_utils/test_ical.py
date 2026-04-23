"""Tests for app/utils/ical.py — RFC 5545 BYDAY + BYMONTHDAY normalization."""

from __future__ import annotations

import pytest

from app.utils.ical import (
    BYDAY_TOKEN_PATTERN,
    BYMONTHDAY_TOKEN_PATTERN,
    normalize_byday,
    normalize_bymonthday,
)


class TestBydayTokenPattern:
    """BYDAY_TOKEN_PATTERN matches a single RFC 5545 §3.3.10 token."""

    @pytest.mark.parametrize(
        "token",
        [
            "MO",
            "TU",
            "WE",
            "TH",
            "FR",
            "SA",
            "SU",
            "1FR",
            "3TU",
            "5SU",
            "-1MO",
            "-5SA",
            "+1WE",
        ],
    )
    def test_valid_tokens(self, token: str) -> None:
        assert BYDAY_TOKEN_PATTERN.match(token) is not None

    @pytest.mark.parametrize(
        "token",
        [
            "",
            "mo",
            "Monday",
            "today",
            "LTU",
            "3F",
            "2F",
            "15",
            "10MO",
            "6MO",
            "0MO",
            "-10MO",
            "1",
            "-1",
            "+",
        ],
    )
    def test_invalid_tokens(self, token: str) -> None:
        assert BYDAY_TOKEN_PATTERN.match(token) is None


class TestNormalizeBydayValid:
    """Valid RFC 5545 BYDAY strings pass through (uppercased, whitespace-trimmed)."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("MO", "MO"),
            ("MO,TU,WE,TH,FR", "MO,TU,WE,TH,FR"),
            ("1FR", "1FR"),
            ("3TU", "3TU"),
            ("-1MO", "-1MO"),
            ("-5SA", "-5SA"),
            ("2WE,-1MO", "2WE,-1MO"),
            ("+1WE", "+1WE"),
            ("3SA,+1WE", "3SA,+1WE"),
            ("mo,tu", "MO,TU"),
            ("  1FR , -1MO  ", "1FR,-1MO"),
            ("MO ,TU , WE", "MO,TU,WE"),
        ],
    )
    def test_valid_inputs(self, raw: str, expected: str) -> None:
        assert normalize_byday(raw) == expected


class TestNormalizeBydayCoercions:
    """Known-benign non-spec forms are coerced to RFC 5545 tokens."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            # Issue 1: Unicode minus U+2212 → ASCII hyphen
            ("−1MO", "-1MO"),
            ("2WE,−1MO", "2WE,-1MO"),
            ("1TU,−1TU", "1TU,-1TU"),
            # Issue 4: L-prefix → -1 prefix (standalone + compound)
            ("LTU", "-1TU"),
            ("LTH", "-1TH"),
            ("LFR", "-1FR"),
            ("2TU,LTU", "2TU,-1TU"),
            ("2TH,LTH", "2TH,-1TH"),
            ("3FR,LFR", "3FR,-1FR"),
            # Issue 2: prose with ordinal
            ("Third Tuesday", "3TU"),
            ("third Tuesday", "3TU"),
            ("third tuesday", "3TU"),
            ("First Monday", "1MO"),
            ("last friday", "-1FR"),
            # Full day names without ordinal
            ("Monday", "MO"),
            ("SUNDAY", "SU"),
            ("tuesday,wednesday", "TU,WE"),
        ],
    )
    def test_coercions(self, raw: str, expected: str) -> None:
        assert normalize_byday(raw) == expected


class TestNormalizeBydayRejections:
    """Unrecoverable inputs return None."""

    @pytest.mark.parametrize(
        "raw",
        [
            "today",
            "Today",
            "tomorrow",
            "yesterday",
            "3F",
            "2F",
            "2F,3F",
            "15",
            "20",
            "20,28",
            "8,22",
            "1,3",
            "12,26",
            "random text",
            "10MO",  # ordinal out of range
            "6MO",  # ordinal out of range
            "MO,today",  # one bad token poisons the list
            "random,MO",
            "MO,",  # trailing empty token
        ],
    )
    def test_rejections(self, raw: str) -> None:
        assert normalize_byday(raw) is None


class TestNormalizeBydayEmpty:
    """Empty / None inputs return None (without emitting a warning log)."""

    @pytest.mark.parametrize("raw", [None, "", "   ", "\t", "\n"])
    def test_empty_inputs(self, raw: str | None) -> None:
        assert normalize_byday(raw) is None


class TestNormalizeBydayLogging:
    """Unrecognized non-empty inputs emit a structlog warning for CloudWatch grep."""

    def test_rejection_emits_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.WARNING):
            result = normalize_byday("today")
        assert result is None
        assert any(
            "ical_byday_unrecognized" in record.message
            or "ical_byday_unrecognized" in str(record.args)
            for record in caplog.records
        )

    def test_valid_input_does_not_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.WARNING):
            result = normalize_byday("MO,TU")
        assert result == "MO,TU"
        assert not any(
            "ical_byday_unrecognized" in record.message for record in caplog.records
        )

    def test_empty_does_not_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.WARNING):
            result = normalize_byday("")
        assert result is None
        assert not any(
            "ical_byday_unrecognized" in record.message for record in caplog.records
        )


class TestBymonthdayTokenPattern:
    """BYMONTHDAY_TOKEN_PATTERN matches a single RFC 5545 §3.3.10 BYMONTHDAY."""

    @pytest.mark.parametrize(
        "token",
        [
            "1",
            "9",
            "10",
            "15",
            "29",
            "30",
            "31",
            "-1",
            "-9",
            "-15",
            "-30",
            "-31",
        ],
    )
    def test_valid_tokens(self, token: str) -> None:
        assert BYMONTHDAY_TOKEN_PATTERN.match(token) is not None

    @pytest.mark.parametrize(
        "token",
        [
            "",
            "0",
            "-0",
            "32",
            "-32",
            "100",
            "01",  # leading zero
            "-01",  # signed leading zero
            "+1",  # RFC 5545 doesn't use + for BYMONTHDAY
            "MO",  # weekday code
            "15th",
            "-",
            " 15",
            "15 ",
        ],
    )
    def test_invalid_tokens(self, token: str) -> None:
        assert BYMONTHDAY_TOKEN_PATTERN.match(token) is None


class TestNormalizeBymonthdayValid:
    """Valid RFC 5545 BYMONTHDAY strings pass through (whitespace-trimmed)."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1", "1"),
            ("15", "15"),
            ("31", "31"),
            ("-1", "-1"),
            ("-31", "-31"),
            ("1,15", "1,15"),
            ("1,-1", "1,-1"),  # first + last
            ("15,30", "15,30"),
            ("-1,-15", "-1,-15"),
            ("1,15,30", "1,15,30"),
            ("  1 , 15  ", "1,15"),  # whitespace stripped
            ("15 ,30", "15,30"),
        ],
    )
    def test_valid_inputs(self, raw: str, expected: str) -> None:
        assert normalize_bymonthday(raw) == expected


class TestNormalizeBymonthdayRejections:
    """Unrecoverable inputs return None (and emit warn log)."""

    @pytest.mark.parametrize(
        "raw",
        [
            "0",  # RFC 5545 says 1..31 / -1..-31, not 0
            "-0",
            "32",
            "-32",
            "100",
            "01",  # leading zero
            "+1",  # plus not allowed for BYMONTHDAY
            "MO",  # weekday code, not day-of-month
            "today",
            "15th",
            "1,0",  # 0 in compound invalidates the whole list
            "1,32",
            "1,MO",
            "1,,3",  # empty middle token
            "1,",  # trailing empty token
            ",15",  # leading empty token
            "random text",
        ],
    )
    def test_rejections(self, raw: str) -> None:
        assert normalize_bymonthday(raw) is None


class TestNormalizeBymonthdayEmpty:
    """Empty / None inputs return None without a warning log."""

    @pytest.mark.parametrize("raw", [None, "", "   ", "\t", "\n"])
    def test_empty_inputs(self, raw: str | None) -> None:
        assert normalize_bymonthday(raw) is None


class TestNormalizeBymonthdayLogging:
    """Unrecognized non-empty inputs emit a structlog warning for CloudWatch grep."""

    def test_rejection_emits_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.WARNING):
            result = normalize_bymonthday("32")
        assert result is None
        assert any(
            "ical_bymonthday_unrecognized" in record.message
            or "ical_bymonthday_unrecognized" in str(record.args)
            for record in caplog.records
        )

    def test_valid_input_does_not_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.WARNING):
            result = normalize_bymonthday("1,15")
        assert result == "1,15"
        assert not any(
            "ical_bymonthday_unrecognized" in record.message
            for record in caplog.records
        )

    def test_empty_does_not_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.WARNING):
            result = normalize_bymonthday("")
        assert result is None
        assert not any(
            "ical_bymonthday_unrecognized" in record.message
            for record in caplog.records
        )
