"""Tests for Submarine job and result models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.submarine.models import SubmarineJob, SubmarineResult, SubmarineStatus


class TestSubmarineJob:
    """Tests for SubmarineJob model."""

    def test_create_minimal_job(self):
        """Job can be created with required fields only."""
        job = SubmarineJob(
            id="sub-001",
            location_id="loc-123",
            website_url="https://example-foodbank.org",
            missing_fields=["phone", "hours"],
            source_scraper_id="capital_area_food_bank_dc",
        )
        assert job.id == "sub-001"
        assert job.location_id == "loc-123"
        assert job.website_url == "https://example-foodbank.org"
        assert job.missing_fields == ["phone", "hours"]
        assert job.source_scraper_id == "capital_area_food_bank_dc"
        assert job.attempt == 0
        assert job.max_attempts == 3
        assert job.organization_id is None
        assert job.latitude is None
        assert job.longitude is None

    def test_create_full_job(self):
        """Job can be created with all fields including location data."""
        job = SubmarineJob(
            id="sub-002",
            location_id="loc-456",
            organization_id="org-789",
            website_url="https://foodbank.example.com",
            missing_fields=["phone", "hours", "email", "description"],
            source_scraper_id="north_country_food_bank_mn",
            location_name="North Country Food Bank",
            latitude=47.4738,
            longitude=-94.8802,
            attempt=1,
            max_attempts=5,
            metadata={"priority": "high"},
        )
        assert job.organization_id == "org-789"
        assert job.location_name == "North Country Food Bank"
        assert job.latitude == 47.4738
        assert job.longitude == -94.8802
        assert job.attempt == 1
        assert job.max_attempts == 5
        assert job.metadata == {"priority": "high"}

    def test_created_at_default(self):
        """Job gets a UTC timestamp by default."""
        job = SubmarineJob(
            id="sub-003",
            location_id="loc-000",
            website_url="https://example.com",
            missing_fields=["phone"],
            source_scraper_id="test",
        )
        assert job.created_at is not None
        assert job.created_at.tzinfo is not None

    def test_missing_fields_must_be_list(self):
        """missing_fields must be a list of strings."""
        job = SubmarineJob(
            id="sub-004",
            location_id="loc-000",
            website_url="https://example.com",
            missing_fields=["phone", "hours"],
            source_scraper_id="test",
        )
        assert isinstance(job.missing_fields, list)
        assert all(isinstance(f, str) for f in job.missing_fields)

    def test_serialization_roundtrip(self):
        """Job can be serialized to dict and back."""
        job = SubmarineJob(
            id="sub-005",
            location_id="loc-111",
            website_url="https://example.com",
            missing_fields=["email"],
            source_scraper_id="test",
            latitude=40.7128,
            longitude=-74.0060,
        )
        data = job.model_dump(mode="json")
        restored = SubmarineJob.model_validate(data)
        assert restored.id == job.id
        assert restored.location_id == job.location_id
        assert restored.latitude == job.latitude
        assert restored.longitude == job.longitude


class TestSubmarineResult:
    """Tests for SubmarineResult model."""

    def test_success_result(self):
        """Result with successfully extracted fields."""
        result = SubmarineResult(
            job_id="sub-001",
            location_id="loc-123",
            status="success",
            extracted_fields={
                "phone": "555-123-4567",
                "hours": [
                    {"day": "Monday", "opens_at": "09:00", "closes_at": "17:00"},
                ],
                "email": "info@example-foodbank.org",
            },
            crawl_metadata={
                "url": "https://example-foodbank.org",
                "pages_crawled": 2,
                "content_hash": "abc123",
            },
        )
        assert result.status == "success"
        assert result.extracted_fields["phone"] == "555-123-4567"
        assert result.error is None

    def test_partial_result(self):
        """Result where only some fields were found."""
        result = SubmarineResult(
            job_id="sub-002",
            location_id="loc-456",
            status="partial",
            extracted_fields={"phone": "555-987-6543"},
        )
        assert result.status == "partial"
        assert "phone" in result.extracted_fields
        assert "hours" not in result.extracted_fields

    def test_no_data_result(self):
        """Result when website had no useful food pantry data."""
        result = SubmarineResult(
            job_id="sub-003",
            location_id="loc-789",
            status="no_data",
        )
        assert result.status == "no_data"
        assert result.extracted_fields == {}

    def test_error_result(self):
        """Result when crawl failed with an error."""
        result = SubmarineResult(
            job_id="sub-004",
            location_id="loc-000",
            status="error",
            error="Connection timeout after 30s",
        )
        assert result.status == "error"
        assert result.error == "Connection timeout after 30s"

    def test_blocked_result(self):
        """Result when website blocked the crawler."""
        result = SubmarineResult(
            job_id="sub-005",
            location_id="loc-111",
            status="blocked",
            crawl_metadata={"reason": "robots.txt disallowed"},
        )
        assert result.status == "blocked"

    def test_serialization_roundtrip(self):
        """Result can be serialized to dict and back."""
        result = SubmarineResult(
            job_id="sub-006",
            location_id="loc-222",
            status="success",
            extracted_fields={"description": "Community food pantry"},
        )
        data = result.model_dump(mode="json")
        restored = SubmarineResult.model_validate(data)
        assert restored.job_id == result.job_id
        assert restored.extracted_fields == result.extracted_fields


class TestSubmarineResultValidator:
    """Tests for SubmarineResult status-field correlation validator."""

    def test_success_requires_extracted_fields(self):
        """SUCCESS status with empty extracted_fields is rejected."""
        with pytest.raises(ValidationError, match="requires non-empty"):
            SubmarineResult(
                job_id="val-001",
                location_id="loc-001",
                status=SubmarineStatus.SUCCESS,
            )

    def test_partial_requires_extracted_fields(self):
        """PARTIAL status with empty extracted_fields is rejected."""
        with pytest.raises(ValidationError, match="requires non-empty"):
            SubmarineResult(
                job_id="val-002",
                location_id="loc-002",
                status=SubmarineStatus.PARTIAL,
            )

    def test_error_requires_error_string(self):
        """ERROR status without error message is rejected."""
        with pytest.raises(ValidationError, match="requires an error"):
            SubmarineResult(
                job_id="val-003",
                location_id="loc-003",
                status=SubmarineStatus.ERROR,
            )

    def test_no_data_accepts_empty_fields(self):
        """NO_DATA status with empty extracted_fields is valid."""
        result = SubmarineResult(
            job_id="val-004",
            location_id="loc-004",
            status=SubmarineStatus.NO_DATA,
        )
        assert result.status == SubmarineStatus.NO_DATA

    def test_blocked_accepts_empty_fields(self):
        """BLOCKED status with empty extracted_fields is valid."""
        result = SubmarineResult(
            job_id="val-005",
            location_id="loc-005",
            status=SubmarineStatus.BLOCKED,
        )
        assert result.status == SubmarineStatus.BLOCKED
