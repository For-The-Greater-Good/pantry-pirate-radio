"""Tests for PTF partner sync formatting functions."""

import pytest

from app.api.v1.partners.ptf.formatters import (
    normalize_phone,
    filter_website,
    format_schedule,
    state_to_timezone,
    build_additional_info,
    parse_zip_code,
    humanize_scraper_id,
)


class TestNormalizePhone:
    """Test phone number normalization."""

    def test_ten_digit_phone(self):
        assert normalize_phone("(555) 123-4567") == 5551234567

    def test_eleven_digit_with_country_code(self):
        assert normalize_phone("1-555-987-6543") == 15559876543

    def test_digits_only_input(self):
        assert normalize_phone("5551234567") == 5551234567

    def test_spaces_and_dashes(self):
        assert normalize_phone("555 123 4567") == 5551234567

    def test_too_short_rejected(self):
        assert normalize_phone("555123") is None

    def test_too_long_rejected(self):
        assert normalize_phone("123456789012") is None

    def test_facebook_id_filtered(self):
        assert normalize_phone("100064523456789") is None

    def test_empty_string(self):
        assert normalize_phone("") is None

    def test_none_input(self):
        assert normalize_phone(None) is None

    def test_non_numeric_garbage(self):
        assert normalize_phone("call us anytime") is None

    def test_extension_stripped(self):
        assert normalize_phone("(555) 123-4567 ext 100") == 5551234567

    def test_plus_one_prefix(self):
        assert normalize_phone("+1 555-123-4567") == 15551234567


class TestFilterWebsite:
    """Test URL filtering for junk domains."""

    def test_clean_url_passes(self):
        assert filter_website("https://example.org") == "https://example.org"

    def test_dropbox_filtered(self):
        assert filter_website("https://www.dropbox.com/s/abc123/file.pdf") is None

    def test_google_drive_filtered(self):
        assert filter_website("https://drive.google.com/file/d/abc") is None

    def test_sharepoint_filtered(self):
        assert filter_website("https://myorg.sharepoint.com/sites/food") is None

    def test_google_docs_filtered(self):
        assert filter_website("https://docs.google.com/spreadsheets/d/abc") is None

    def test_none_input(self):
        assert filter_website(None) is None

    def test_empty_string(self):
        assert filter_website("") is None

    def test_facebook_url_passes(self):
        assert (
            filter_website("https://facebook.com/foodbank")
            == "https://facebook.com/foodbank"
        )

    def test_google_forms_filtered(self):
        assert filter_website("https://forms.google.com/abc") is None


class TestFormatSchedule:
    """Test schedule formatting from DB rows."""

    def test_single_day_schedule(self):
        rows = [_schedule_row(byday="MO", opens_at="09:00:00", closes_at="17:00:00")]
        result = format_schedule(rows)
        assert result == "Monday: 9:00 AM - 5:00 PM"

    def test_multiple_days(self):
        rows = [
            _schedule_row(byday="MO", opens_at="09:00:00", closes_at="17:00:00"),
            _schedule_row(byday="TU", opens_at="10:00:00", closes_at="14:00:00"),
        ]
        result = format_schedule(rows)
        assert "Monday: 9:00 AM - 5:00 PM" in result
        assert "Tuesday: 10:00 AM - 2:00 PM" in result
        assert "; " in result

    def test_description_fallback(self):
        rows = [_schedule_row(description="Open weekdays 9-5")]
        result = format_schedule(rows)
        assert result == "Open weekdays 9-5"

    def test_empty_rows(self):
        assert format_schedule([]) is None

    def test_multi_day_byday(self):
        rows = [
            _schedule_row(byday="MO,WE,FR", opens_at="08:00:00", closes_at="12:00:00")
        ]
        result = format_schedule(rows)
        assert "Monday" in result
        assert "Wednesday" in result
        assert "Friday" in result

    def test_no_times_uses_description(self):
        rows = [_schedule_row(byday="MO", description="By appointment only")]
        result = format_schedule(rows)
        assert result == "Monday: By appointment only"


class TestStateToTimezone:
    """Test state to IANA timezone mapping."""

    def test_eastern(self):
        assert state_to_timezone("NJ") == "America/New_York"
        assert state_to_timezone("NY") == "America/New_York"

    def test_central(self):
        assert state_to_timezone("TX") == "America/Chicago"
        assert state_to_timezone("IL") == "America/Chicago"

    def test_mountain(self):
        assert state_to_timezone("CO") == "America/Denver"

    def test_pacific(self):
        assert state_to_timezone("CA") == "America/Los_Angeles"
        assert state_to_timezone("WA") == "America/Los_Angeles"

    def test_alaska(self):
        assert state_to_timezone("AK") == "America/Anchorage"

    def test_hawaii(self):
        assert state_to_timezone("HI") == "Pacific/Honolulu"

    def test_arizona(self):
        assert state_to_timezone("AZ") == "America/Phoenix"

    def test_none_for_unknown(self):
        assert state_to_timezone("XX") is None
        assert state_to_timezone(None) is None
        assert state_to_timezone("") is None

    def test_dc(self):
        assert state_to_timezone("DC") == "America/New_York"


class TestBuildAdditionalInfo:
    """Test additional_info text building."""

    def test_description_only(self):
        result = build_additional_info(description="Food distribution center")
        assert "Food distribution center" in result

    def test_with_services(self):
        result = build_additional_info(
            description="A food bank", services=["Food Pantry", "Meal Service"]
        )
        assert "Services: Food Pantry, Meal Service" in result

    def test_with_extra_phones(self):
        result = build_additional_info(description="Pantry", extra_phones=[5559876543])
        assert "555-987-6543" in result

    def test_disclaimer_included(self):
        result = build_additional_info(description="Pantry")
        assert "Data sourced from" in result

    def test_empty_components(self):
        result = build_additional_info()
        assert "Data sourced from" in result

    def test_all_components(self):
        result = build_additional_info(
            description="Great food bank",
            services=["Food Pantry"],
            extra_phones=[5551112222],
        )
        assert "Great food bank" in result
        assert "Services:" in result
        assert "Additional phone" in result


class TestParseZipCode:
    """Test ZIP code parsing."""

    def test_five_digit(self):
        assert parse_zip_code("12345") == 12345

    def test_zip_plus_four(self):
        assert parse_zip_code("07102-1234") == 7102

    def test_leading_zero(self):
        assert parse_zip_code("07102") == 7102

    def test_none_input(self):
        assert parse_zip_code(None) is None

    def test_empty_string(self):
        assert parse_zip_code("") is None

    def test_invalid(self):
        assert parse_zip_code("ABCDE") is None

    def test_too_short(self):
        assert parse_zip_code("123") is None


class TestHumanizeScraperId:
    """Test scraper ID humanization."""

    def test_simple(self):
        assert humanize_scraper_id("food_bank") == "Food Bank"

    def test_with_state(self):
        result = humanize_scraper_id("capital_area_food_bank_dc")
        assert result == "Capital Area Food Bank DC"

    def test_scraper_suffix_removed(self):
        result = humanize_scraper_id("community_food_bank_scraper")
        assert result == "Community Food Bank"

    def test_none_input(self):
        assert humanize_scraper_id(None) is None

    def test_empty_string(self):
        assert humanize_scraper_id("") is None


def _schedule_row(
    byday=None, opens_at=None, closes_at=None, description=None, freq=None
):
    """Create a mock schedule row for testing."""

    class Row:
        pass

    row = Row()
    row.byday = byday
    row.opens_at = opens_at
    row.closes_at = closes_at
    row.description = description
    row.freq = freq
    return row
