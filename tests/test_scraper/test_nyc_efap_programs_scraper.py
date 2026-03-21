"""Tests for NYC EFAP Programs scraper column mapping."""

import pytest

from app.scraper.scrapers.nyc_efap_programs_scraper import Nyc_Efap_ProgramsScraper


@pytest.fixture
def scraper():
    return Nyc_Efap_ProgramsScraper()


# --- 9-column PDF row fixtures ---

VALID_ROW_9COL = [
    "85828",  # 0: ID
    "FP",  # 1: TYPE
    "FOOD BANK OF NYC",  # 2: PROGRAM (org name)
    "212-555-1234",  # 3: ORG PHONE
    "123 MAIN ST",  # 4: ADDRESS
    "BK",  # 5: BOROUGH
    "11201",  # 6: ZIP
    "SUN (1,3)",  # 7: DAYS
    "1:30-2:30PM",  # 8: HOURS
]

VALID_ROW_7COL = [
    "85829",
    "SK",
    "SOUP KITCHEN XYZ",
    "718-555-9999",
    "456 ELM AVE",
    "MN",
    "10001",
]

HEADER_ROW = [
    "ID",
    "TYPE",
    "PROGRAM",
    "ORG PHONE",
    "DISTADD DIS",
    "TBO",
    "DRIOSTZIP",
    "DAYS",
    "HOURS",
]


class TestParseRow:
    def test_full_9col_row(self, scraper):
        result = scraper.parse_program_row(VALID_ROW_9COL)
        assert result is not None
        assert result["name"] == "FOOD BANK OF NYC"
        assert result["phone"] == "212-555-1234"
        assert result["address"] == "123 MAIN ST"
        assert result["borough"] == "BK"
        assert result["zip_code"] == "11201"
        assert result["days"] == "SUN (1,3)"
        assert result["hours"] == "1:30-2:30PM"
        assert result["efap_id"] == "85828"
        assert result["program_type"] == "FP"
        assert result["full_address"] == "123 MAIN ST, BK, 11201, NY"

    def test_7col_row_no_schedule(self, scraper):
        result = scraper.parse_program_row(VALID_ROW_7COL)
        assert result is not None
        assert result["name"] == "SOUP KITCHEN XYZ"
        assert result["phone"] == "718-555-9999"
        assert result["address"] == "456 ELM AVE"
        assert result["borough"] == "MN"
        assert result["zip_code"] == "10001"
        assert "days" not in result
        assert "hours" not in result

    def test_rejects_short_row(self, scraper):
        assert scraper.parse_program_row(["85828", "FP", "NAME", "PHONE"]) is None

    def test_rejects_empty_name(self, scraper):
        row = ["85828", "FP", "", "212-555-1234", "123 MAIN ST", "BK", "11201"]
        assert scraper.parse_program_row(row) is None

    def test_rejects_empty_address(self, scraper):
        row = ["85828", "FP", "ORG NAME", "212-555-1234", "", "BK", "11201"]
        assert scraper.parse_program_row(row) is None

    def test_rejects_none_row(self, scraper):
        assert scraper.parse_program_row(None) is None

    def test_rejects_empty_row(self, scraper):
        assert scraper.parse_program_row([]) is None

    def test_handles_none_cells(self, scraper):
        row = ["85828", None, "ORG NAME", None, "123 MAIN ST", None, None]
        result = scraper.parse_program_row(row)
        assert result is not None
        assert result["name"] == "ORG NAME"
        assert result["address"] == "123 MAIN ST"
        assert "phone" not in result
        assert "borough" not in result
        assert result["full_address"] == "123 MAIN ST, NY"

    def test_optional_phone_missing(self, scraper):
        row = ["85828", "FP", "ORG NAME", "", "123 MAIN ST", "BK", "11201"]
        result = scraper.parse_program_row(row)
        assert result is not None
        assert "phone" not in result


class TestHeaderFiltering:
    def test_header_rows_filtered_on_all_pages(self, scraper):
        """Header rows should be filtered on every page, not just page 1."""
        table_with_header = [
            HEADER_ROW,
            VALID_ROW_9COL,
        ]

        # Simulate extract_text_from_pdf logic: build a fake PDF with two pages
        # that both have header rows. The scraper should filter headers on both.
        import io
        from unittest.mock import MagicMock, patch

        mock_pdf = MagicMock()
        page1 = MagicMock()
        page1.extract_tables.return_value = [table_with_header]
        page2 = MagicMock()
        page2.extract_tables.return_value = [table_with_header]
        mock_pdf.pages = [page1, page2]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("pdfplumber.open", return_value=mock_pdf):
            programs = scraper.extract_text_from_pdf(b"fake-pdf")

        # Should get 2 data rows (one per page), no header rows
        assert len(programs) == 2
        for p in programs:
            assert p["name"] == "FOOD BANK OF NYC"
            assert p["efap_id"] == "85828"


class TestTransformToHsds:
    def test_transform_with_all_fields(self, scraper):
        program = {
            "name": "FOOD BANK OF NYC",
            "address": "123 MAIN ST",
            "phone": "212-555-1234",
            "borough": "BK",
            "zip_code": "11201",
            "days": "SUN (1,3)",
            "hours": "1:30-2:30PM",
            "program_type": "FP",
        }
        hsds = scraper.transform_to_hsds(program)
        assert hsds["name"] == "FOOD BANK OF NYC"
        assert hsds["address"]["address_1"] == "123 MAIN ST"
        assert hsds["address"]["postal_code"] == "11201"
        assert hsds["phones"] == [{"number": "212-555-1234", "type": "voice"}]
        assert hsds["regular_schedule_text"] == "SUN (1,3) 1:30-2:30PM"
        assert any(
            a["attribute_key"] == "PROGRAM_TYPE" and a["attribute_value"] == "FP"
            for a in hsds["service_attributes"]
        )
        assert any(
            a["attribute_key"] == "BOROUGH" and a["attribute_value"] == "BK"
            for a in hsds["service_attributes"]
        )

    def test_transform_without_phone(self, scraper):
        program = {"name": "ORG", "address": "123 ST", "borough": "MN"}
        hsds = scraper.transform_to_hsds(program)
        assert hsds["phones"] == []

    def test_transform_without_schedule(self, scraper):
        program = {"name": "ORG", "address": "123 ST"}
        hsds = scraper.transform_to_hsds(program)
        assert "regular_schedule_text" not in hsds
