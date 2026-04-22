"""Tests for submarine result builder — converts extraction results to JobResult."""

import pytest

from app.submarine.models import SubmarineJob, SubmarineResult
from app.submarine.result_builder import SubmarineResultBuilder


class TestSubmarineResultBuilder:
    """Tests for the SubmarineResultBuilder."""

    @pytest.fixture
    def builder(self):
        return SubmarineResultBuilder()

    @pytest.fixture
    def sample_job(self):
        return SubmarineJob(
            id="sub-001",
            location_id="loc-123",
            organization_id="org-456",
            website_url="https://gracechurch.example.com",
            missing_fields=["phone", "hours", "email", "description"],
            source_scraper_id="capital_area_food_bank_dc",
            location_name="Grace Community Food Pantry",
            latitude=39.7817,
            longitude=-89.6501,
        )

    @pytest.fixture
    def full_result(self):
        return SubmarineResult(
            job_id="sub-001",
            location_id="loc-123",
            status="success",
            extracted_fields={
                "phone": "(555) 234-5678",
                "hours": [
                    {"day": "Tuesday", "opens_at": "10:00", "closes_at": "14:00"},
                    {"day": "Thursday", "opens_at": "10:00", "closes_at": "14:00"},
                    {"day": "Saturday", "opens_at": "09:00", "closes_at": "12:00"},
                ],
                "email": "pantry@gracechurch.example.com",
                "description": "Community food pantry serving 200 families monthly",
            },
            crawl_metadata={
                "pages_crawled": 2,
                "url": "https://gracechurch.example.com",
            },
        )

    def test_builds_valid_job_result(self, builder, sample_job, full_result):
        """Builder produces a valid JobResult."""
        from app.llm.queue.types import JobResult, JobStatus

        job_result = builder.build(sample_job, full_result)

        assert isinstance(job_result, JobResult)
        assert job_result.status == JobStatus.COMPLETED

    def test_metadata_has_submarine_source(self, builder, sample_job, full_result):
        """JobResult metadata marks source as submarine for cycle prevention."""
        job_result = builder.build(sample_job, full_result)

        assert job_result.job.metadata["scraper_id"] == "submarine"
        assert job_result.job.metadata["source_type"] == "submarine"

    def test_metadata_has_location_id(self, builder, sample_job, full_result):
        """JobResult metadata carries location_id for direct ID update path."""
        job_result = builder.build(sample_job, full_result)

        assert job_result.job.metadata["location_id"] == "loc-123"

    def test_metadata_has_original_scraper(self, builder, sample_job, full_result):
        """JobResult metadata preserves the original scraper ID."""
        job_result = builder.build(sample_job, full_result)

        assert (
            job_result.job.metadata["source_scraper_id"] == "capital_area_food_bank_dc"
        )

    def test_data_has_location_with_coordinates(self, builder, sample_job, full_result):
        """Data includes location with lat/lon for reconciler processing."""
        job_result = builder.build(sample_job, full_result)

        locations = job_result.data["location"]
        assert len(locations) == 1
        assert locations[0]["latitude"] == 39.7817
        assert locations[0]["longitude"] == -89.6501
        assert locations[0]["name"] == "Grace Community Food Pantry"

    def test_data_has_extracted_phones(self, builder, sample_job, full_result):
        """Extracted phone is mapped to HSDS phone structure."""
        job_result = builder.build(sample_job, full_result)

        phones = job_result.data["location"][0].get("phones", [])
        assert len(phones) == 1
        assert phones[0]["number"] == "(555) 234-5678"

    def test_data_has_extracted_schedules(self, builder, sample_job, full_result):
        """Extracted hours are mapped to HSDS schedule structure."""
        job_result = builder.build(sample_job, full_result)

        schedules = job_result.data["location"][0].get("schedules", [])
        assert len(schedules) == 3
        assert schedules[0]["byday"] == "TU"
        assert schedules[0]["opens_at"] == "10:00"

    def test_data_has_extracted_description(self, builder, sample_job, full_result):
        """Extracted description is set on location."""
        job_result = builder.build(sample_job, full_result)

        desc = job_result.data["location"][0].get("description")
        assert "200 families" in desc

    def test_data_has_extracted_email(self, builder, sample_job, full_result):
        """Extracted email is set on organization."""
        job_result = builder.build(sample_job, full_result)

        orgs = job_result.data.get("organization", [])
        assert len(orgs) == 1
        assert orgs[0]["email"] == "pantry@gracechurch.example.com"

    def test_partial_result_only_includes_found_fields(self, builder, sample_job):
        """Partial result only maps fields that were actually found."""
        partial = SubmarineResult(
            job_id="sub-001",
            location_id="loc-123",
            status="partial",
            extracted_fields={"phone": "(555) 234-5678"},
        )

        job_result = builder.build(sample_job, partial)

        location = job_result.data["location"][0]
        assert len(location.get("phones", [])) == 1
        assert location.get("schedules", []) == []
        assert "description" not in location

    def test_empty_result_returns_none(self, builder, sample_job):
        """No-data result returns None (nothing to send to reconciler)."""
        empty = SubmarineResult(
            job_id="sub-001",
            location_id="loc-123",
            status="no_data",
        )

        job_result = builder.build(sample_job, empty)
        assert job_result is None

    def test_error_result_returns_none(self, builder, sample_job):
        """Error result returns None."""
        error = SubmarineResult(
            job_id="sub-001",
            location_id="loc-123",
            status="error",
            error="Connection timeout",
        )

        job_result = builder.build(sample_job, error)
        assert job_result is None


class TestSelectiveFieldUpdate:
    """Tests that result_builder only includes fields from missing_fields."""

    @pytest.fixture
    def builder(self):
        return SubmarineResultBuilder()

    def test_omits_description_when_not_in_missing_fields(self, builder):
        """When only phone is missing, description key should be absent."""
        job = SubmarineJob(
            id="sub-010",
            location_id="loc-123",
            website_url="https://example.com",
            missing_fields=["phone"],
            source_scraper_id="test",
            location_name="Test Pantry",
            latitude=39.78,
            longitude=-89.65,
        )
        result = SubmarineResult(
            job_id="sub-010",
            location_id="loc-123",
            status="success",
            extracted_fields={"phone": "(555) 111-2222"},
        )

        job_result = builder.build(job, result)
        location = job_result.data["location"][0]

        assert "phones" in location
        assert "description" not in location

    def test_omits_phones_when_not_in_missing_fields(self, builder):
        """When only description is missing, phones key should be absent."""
        job = SubmarineJob(
            id="sub-011",
            location_id="loc-123",
            website_url="https://example.com",
            missing_fields=["description"],
            source_scraper_id="test",
            location_name="Test Pantry",
            latitude=39.78,
            longitude=-89.65,
        )
        result = SubmarineResult(
            job_id="sub-011",
            location_id="loc-123",
            status="success",
            extracted_fields={"description": "A food pantry"},
        )

        job_result = builder.build(job, result)
        location = job_result.data["location"][0]

        assert "description" in location
        assert "phones" not in location

    def test_omits_schedules_when_not_in_missing_fields(self, builder):
        """When hours is not in missing_fields, schedules key should be absent."""
        job = SubmarineJob(
            id="sub-012",
            location_id="loc-123",
            website_url="https://example.com",
            missing_fields=["phone"],
            source_scraper_id="test",
            location_name="Test Pantry",
            latitude=39.78,
            longitude=-89.65,
        )
        result = SubmarineResult(
            job_id="sub-012",
            location_id="loc-123",
            status="success",
            extracted_fields={"phone": "(555) 111-2222"},
        )

        job_result = builder.build(job, result)
        location = job_result.data["location"][0]

        assert "schedules" not in location

    def test_omits_email_when_not_in_missing_fields(self, builder):
        """When email is not in missing_fields, org should not have email."""
        job = SubmarineJob(
            id="sub-013",
            location_id="loc-123",
            website_url="https://example.com",
            missing_fields=["phone"],
            source_scraper_id="test",
            location_name="Test Pantry",
            latitude=39.78,
            longitude=-89.65,
        )
        result = SubmarineResult(
            job_id="sub-013",
            location_id="loc-123",
            status="success",
            extracted_fields={"phone": "(555) 111-2222"},
        )

        job_result = builder.build(job, result)

        # When email is not in missing_fields, organization key is omitted entirely
        # (bare name-only org is excluded to avoid merge noise)
        assert "organization" not in job_result.data

    def test_includes_all_fields_when_all_missing(self, builder):
        """When all four fields are missing, all should be present."""
        job = SubmarineJob(
            id="sub-014",
            location_id="loc-123",
            website_url="https://example.com",
            missing_fields=["phone", "hours", "email", "description"],
            source_scraper_id="test",
            location_name="Test Pantry",
            latitude=39.78,
            longitude=-89.65,
        )
        result = SubmarineResult(
            job_id="sub-014",
            location_id="loc-123",
            status="success",
            extracted_fields={
                "phone": "(555) 111-2222",
                "hours": [{"day": "Monday", "opens_at": "09:00", "closes_at": "17:00"}],
                "email": "test@example.com",
                "description": "Food pantry services",
            },
        )

        job_result = builder.build(job, result)
        location = job_result.data["location"][0]
        org = job_result.data["organization"][0]

        assert "phones" in location
        assert "schedules" in location
        assert "description" in location
        assert "email" in org


class TestBydayNormalization:
    """Tests that day names are converted to RRULE abbreviations."""

    @pytest.fixture
    def builder(self):
        return SubmarineResultBuilder()

    def _build_with_hours(self, builder, hours_list):
        job = SubmarineJob(
            id="sub-020",
            location_id="loc-123",
            website_url="https://example.com",
            missing_fields=["hours"],
            source_scraper_id="test",
            location_name="Test Pantry",
            latitude=39.78,
            longitude=-89.65,
        )
        result = SubmarineResult(
            job_id="sub-020",
            location_id="loc-123",
            status="success",
            extracted_fields={"hours": hours_list},
        )
        return builder.build(job, result)

    def test_byday_uses_rrule_abbreviations(self, builder):
        """Full day names should be converted to two-letter RRULE codes."""
        job_result = self._build_with_hours(
            builder,
            [
                {"day": "Tuesday", "opens_at": "10:00", "closes_at": "14:00"},
                {"day": "thursday", "opens_at": "09:00", "closes_at": "12:00"},
            ],
        )

        schedules = job_result.data["location"][0]["schedules"]
        assert schedules[0]["byday"] == "TU"
        assert schedules[1]["byday"] == "TH"

    def test_schedule_includes_wkst_default(self, builder):
        """Each schedule should have wkst defaulting to MO."""
        job_result = self._build_with_hours(
            builder,
            [{"day": "Monday", "opens_at": "09:00", "closes_at": "17:00"}],
        )

        schedules = job_result.data["location"][0]["schedules"]
        assert schedules[0]["wkst"] == "MO"

    def test_already_abbreviated_day_passes_through(self, builder):
        """If LLM returns an abbreviation already, it should pass through."""
        job_result = self._build_with_hours(
            builder,
            [{"day": "FR", "opens_at": "09:00", "closes_at": "15:00"}],
        )

        schedules = job_result.data["location"][0]["schedules"]
        assert schedules[0]["byday"] == "FR"

    def test_unknown_day_dropped(self, builder, caplog):
        """Unknown day values (RFC 5545 incompatible) drop the entry with a warning."""
        import logging

        with caplog.at_level(logging.WARNING):
            job_result = self._build_with_hours(
                builder,
                [
                    {"day": "Everyday", "opens_at": "09:00", "closes_at": "17:00"},
                    {"day": "Monday", "opens_at": "10:00", "closes_at": "14:00"},
                ],
            )

        # Only the Monday entry should survive; Everyday dropped with warning.
        schedules = job_result.data["location"][0]["schedules"]
        assert len(schedules) == 1
        assert schedules[0]["byday"] == "MO"
        assert any(
            "submarine_unrecognized_byday" in rec.message for rec in caplog.records
        )

    def test_today_hallucination_dropped(self, builder, caplog):
        """LLM hallucinations like 'today' drop the entry rather than pass through."""
        import logging

        with caplog.at_level(logging.WARNING):
            job_result = self._build_with_hours(
                builder,
                [{"day": "today", "opens_at": "09:00", "closes_at": "17:00"}],
            )

        # No schedules should be attached when the only hours entry is rejected.
        location = job_result.data["location"][0]
        assert "schedules" not in location
        assert any(
            "submarine_unrecognized_byday" in rec.message for rec in caplog.records
        )

    def test_prose_ordinal_coerced(self, builder):
        """'Third Tuesday' should coerce to '3TU' (RFC 5545 ordinal)."""
        job_result = self._build_with_hours(
            builder,
            [{"day": "Third Tuesday", "opens_at": "09:00", "closes_at": "12:00"}],
        )

        schedules = job_result.data["location"][0]["schedules"]
        assert schedules[0]["byday"] == "3TU"

    def test_l_prefix_coerced(self, builder):
        """'LTU' should coerce to '-1TU' (last Tuesday of month)."""
        job_result = self._build_with_hours(
            builder,
            [{"day": "LTU", "opens_at": "09:00", "closes_at": "12:00"}],
        )

        schedules = job_result.data["location"][0]["schedules"]
        assert schedules[0]["byday"] == "-1TU"


class TestHsdsValidation:
    """Tests that result_builder validates output against HSDS Pydantic models."""

    @pytest.fixture
    def builder(self):
        return SubmarineResultBuilder()

    def test_invalid_phone_stripped(self, builder):
        """Phone with empty string number should be excluded."""
        job = SubmarineJob(
            id="sub-val-001",
            location_id="loc-123",
            website_url="https://example.com",
            missing_fields=["phone"],
            source_scraper_id="test",
            location_name="Test Pantry",
            latitude=39.78,
            longitude=-89.65,
        )
        result = SubmarineResult(
            job_id="sub-val-001",
            location_id="loc-123",
            status="success",
            extracted_fields={"phone": ""},
        )

        job_result = builder.build(job, result)

        # Empty phone should be stripped — no phones key or empty list
        if job_result is not None:
            location = job_result.data["location"][0]
            phones = location.get("phones", [])
            assert len(phones) == 0

    def test_valid_phone_passes(self, builder):
        """Valid phone entry passes validation."""
        job = SubmarineJob(
            id="sub-val-002",
            location_id="loc-123",
            website_url="https://example.com",
            missing_fields=["phone"],
            source_scraper_id="test",
            location_name="Test Pantry",
            latitude=39.78,
            longitude=-89.65,
        )
        result = SubmarineResult(
            job_id="sub-val-002",
            location_id="loc-123",
            status="success",
            extracted_fields={"phone": "(555) 234-5678"},
        )

        job_result = builder.build(job, result)

        location = job_result.data["location"][0]
        assert len(location["phones"]) == 1
        assert location["phones"][0]["number"] == "(555) 234-5678"

    def test_invalid_schedule_stripped(self, builder):
        """Schedule with missing opens_at should be excluded."""
        job = SubmarineJob(
            id="sub-val-003",
            location_id="loc-123",
            website_url="https://example.com",
            missing_fields=["hours"],
            source_scraper_id="test",
            location_name="Test Pantry",
            latitude=39.78,
            longitude=-89.65,
        )
        result = SubmarineResult(
            job_id="sub-val-003",
            location_id="loc-123",
            status="success",
            extracted_fields={
                "hours": [
                    {"day": "Monday", "opens_at": "09:00", "closes_at": "17:00"},
                    {"day": "Wednesday"},  # Missing opens_at and closes_at
                ]
            },
        )

        job_result = builder.build(job, result)

        location = job_result.data["location"][0]
        schedules = location.get("schedules", [])
        # Only the valid schedule should remain
        assert len(schedules) == 1
        assert schedules[0]["byday"] == "MO"
