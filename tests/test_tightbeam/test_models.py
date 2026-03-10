"""Tests for Tightbeam Pydantic models."""

import pytest
from datetime import datetime, UTC

from app.api.v1.tightbeam.models import (
    AuditEntry,
    CallerIdentity,
    HistoryResponse,
    LocationDetail,
    LocationResult,
    LocationUpdateRequest,
    LocationUpdateResponse,
    MutationResponse,
    RestoreRequest,
    SearchResponse,
    SoftDeleteRequest,
    SourceRecord,
)


class TestCallerIdentity:
    """Test CallerIdentity model."""

    def test_minimal_creation(self):
        identity = CallerIdentity(api_key_id="abc123")
        assert identity.api_key_id == "abc123"
        assert identity.api_key_name is None
        assert identity.source_ip is None
        assert identity.caller_context is None

    def test_full_creation(self):
        identity = CallerIdentity(
            api_key_id="key-001",
            api_key_name="slackbot",
            source_ip="10.0.0.1",
            user_agent="SlackBot/1.0",
            caller_context={"slack_user_id": "U123", "channel_id": "C456"},
        )
        assert identity.api_key_name == "slackbot"
        assert identity.caller_context["slack_user_id"] == "U123"


class TestSearchResponse:
    """Test SearchResponse model."""

    def test_empty_results(self):
        resp = SearchResponse(results=[], total=0, limit=20, offset=0)
        assert resp.total == 0
        assert len(resp.results) == 0

    def test_with_results(self):
        loc = LocationResult(
            id="loc-001",
            name="Test Food Bank",
            city="Newark",
            state="NJ",
            confidence_score=85,
        )
        resp = SearchResponse(results=[loc], total=1, limit=20, offset=0)
        assert resp.results[0].name == "Test Food Bank"


class TestLocationResult:
    """Test LocationResult model."""

    def test_minimal(self):
        loc = LocationResult(id="loc-001")
        assert loc.id == "loc-001"
        assert loc.name is None
        assert loc.latitude is None

    def test_full(self):
        loc = LocationResult(
            id="loc-001",
            name="Food Bank",
            organization_name="Org Inc",
            address_1="123 Main St",
            city="Newark",
            state="NJ",
            postal_code="07102",
            latitude=40.7128,
            longitude=-74.006,
            phone="555-123-4567",
            email="info@example.com",
            website="https://example.org",
            description="A food bank",
            confidence_score=90,
            validation_status="verified",
        )
        assert loc.latitude == 40.7128


class TestLocationUpdateRequest:
    """Test LocationUpdateRequest model."""

    def test_partial_update(self):
        req = LocationUpdateRequest(name="New Name")
        assert req.name == "New Name"
        assert req.city is None
        assert req.caller_context is None

    def test_with_caller_context(self):
        req = LocationUpdateRequest(
            name="Updated",
            caller_context={"slack_user_id": "U123"},
        )
        assert req.caller_context["slack_user_id"] == "U123"


class TestLocationUpdateResponse:
    """Test LocationUpdateResponse model."""

    def test_creation(self):
        resp = LocationUpdateResponse(
            location_id="loc-001",
            source_id="src-001",
            audit_id="audit-001",
        )
        assert resp.message == "Location updated successfully"


class TestSoftDeleteRequest:
    """Test SoftDeleteRequest model."""

    def test_with_reason(self):
        req = SoftDeleteRequest(reason="Permanently closed")
        assert req.reason == "Permanently closed"

    def test_without_reason(self):
        req = SoftDeleteRequest()
        assert req.reason is None


class TestRestoreRequest:
    """Test RestoreRequest model."""

    def test_with_reason(self):
        req = RestoreRequest(reason="Confirmed still open")
        assert req.reason == "Confirmed still open"


class TestMutationResponse:
    """Test MutationResponse model."""

    def test_creation(self):
        resp = MutationResponse(
            location_id="loc-001",
            audit_id="audit-001",
            message="Location soft-deleted successfully",
        )
        assert resp.location_id == "loc-001"


class TestAuditEntry:
    """Test AuditEntry model."""

    def test_minimal(self):
        entry = AuditEntry(id="audit-001", location_id="loc-001", action="update")
        assert entry.action == "update"
        assert entry.changed_fields is None

    def test_full(self):
        now = datetime.now(UTC)
        entry = AuditEntry(
            id="audit-001",
            location_id="loc-001",
            action="update",
            changed_fields=["name"],
            previous_values={"name": "Old Name"},
            new_values={"name": "New Name"},
            api_key_id="key-001",
            api_key_name="slackbot",
            source_ip="10.0.0.1",
            user_agent="SlackBot/1.0",
            caller_context={"slack_user_id": "U123"},
            created_at=now,
        )
        assert entry.created_at == now
        assert entry.caller_context["slack_user_id"] == "U123"


class TestHistoryResponse:
    """Test HistoryResponse model."""

    def test_empty(self):
        resp = HistoryResponse(location_id="loc-001", entries=[], total=0)
        assert resp.total == 0

    def test_with_entries(self):
        entry = AuditEntry(id="a1", location_id="loc-001", action="update")
        resp = HistoryResponse(location_id="loc-001", entries=[entry], total=1)
        assert len(resp.entries) == 1


class TestSourceRecord:
    """Test SourceRecord model."""

    def test_scraper_source(self):
        src = SourceRecord(
            id="src-001",
            scraper_id="capital_area_scraper",
            name="Capital Area Food Bank",
            source_type="scraper",
            confidence_score=75,
        )
        assert src.source_type == "scraper"

    def test_human_update_source(self):
        src = SourceRecord(
            id="src-002",
            scraper_id="human_update",
            name="Updated Name",
            source_type="human_update",
            confidence_score=100,
            validation_status="verified",
            updated_by="slackbot",
        )
        assert src.confidence_score == 100
        assert src.updated_by == "slackbot"


class TestLocationDetail:
    """Test LocationDetail model."""

    def test_with_sources(self):
        loc = LocationResult(id="loc-001", name="Food Bank")
        src = SourceRecord(id="src-001", scraper_id="test", name="Food Bank")
        detail = LocationDetail(location=loc, sources=[src])
        assert len(detail.sources) == 1
        assert detail.location.id == "loc-001"
