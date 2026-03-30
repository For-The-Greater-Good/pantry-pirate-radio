"""Tests for SubmarineStagingMessage model."""

from datetime import datetime, timezone

from app.submarine.staging import SubmarineStagingMessage


class TestSubmarineStagingMessage:
    """Tests for the staging queue message model."""

    def test_create_minimal(self):
        """Message can be created with required fields."""
        msg = SubmarineStagingMessage(
            job_id="sub-001",
            location_id="loc-123",
            submarine_job={"id": "sub-001", "website_url": "https://example.com"},
            prompt=[
                {"role": "system", "content": "Extract data"},
                {"role": "user", "content": "Content here"},
            ],
            missing_fields=["phone", "hours"],
        )
        assert msg.job_id == "sub-001"
        assert msg.location_id == "loc-123"
        assert len(msg.prompt) == 2
        assert msg.missing_fields == ["phone", "hours"]
        assert msg.crawl_metadata == {}
        assert msg.created_at is not None

    def test_create_with_crawl_metadata(self):
        """Message carries crawl provenance."""
        msg = SubmarineStagingMessage(
            job_id="sub-002",
            location_id="loc-456",
            submarine_job={"id": "sub-002"},
            prompt=[{"role": "user", "content": "test"}],
            missing_fields=["email"],
            crawl_metadata={
                "url": "https://foodbank.example.com",
                "pages_crawled": 3,
                "links_followed": ["https://foodbank.example.com/contact"],
            },
        )
        assert msg.crawl_metadata["pages_crawled"] == 3
        assert len(msg.crawl_metadata["links_followed"]) == 1

    def test_serialization_roundtrip(self):
        """Message can be serialized to dict and back (for SQS transport)."""
        msg = SubmarineStagingMessage(
            job_id="sub-003",
            location_id="loc-789",
            submarine_job={"id": "sub-003", "missing_fields": ["phone"]},
            prompt=[{"role": "user", "content": "Extract phone"}],
            missing_fields=["phone"],
        )
        data = msg.model_dump(mode="json")
        restored = SubmarineStagingMessage.model_validate(data)
        assert restored.job_id == msg.job_id
        assert restored.prompt == msg.prompt
        assert restored.submarine_job == msg.submarine_job
