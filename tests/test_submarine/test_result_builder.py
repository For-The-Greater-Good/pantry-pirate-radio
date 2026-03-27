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
        assert schedules[0]["byday"] == "Tuesday"
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
        assert "description" not in location or location["description"] is None

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
