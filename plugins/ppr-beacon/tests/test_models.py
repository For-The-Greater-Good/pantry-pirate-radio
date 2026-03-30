"""Tests for Pydantic template context models."""

from app.models import (
    Accessibility,
    CitySummary,
    Language,
    LocationDetail,
    LocationSummary,
    OrgDetail,
    Phone,
    Schedule,
    StateSummary,
)


class TestLocationDetail:
    def test_defaults(self):
        loc = LocationDetail(id="1", name="Test")
        assert loc.confidence_score == 0
        assert loc.schedules == []
        assert loc.phones == []
        assert loc.slug == ""

    def test_full(self):
        loc = LocationDetail(
            id="1", name="Test", city="Springfield", state="IL",
            latitude=39.7817, longitude=-89.6501,
            confidence_score=95, verified_by="source",
            schedules=[Schedule(opens_at="09:00", closes_at="17:00")],
            phones=[Phone(number="555-0100")],
            languages=[Language(name="English", code="en")],
            accessibility=Accessibility(description="Wheelchair accessible"),
        )
        assert loc.verified_by == "source"
        assert len(loc.schedules) == 1
        assert loc.phones[0].number == "555-0100"


class TestLocationSummary:
    def test_defaults(self):
        loc = LocationSummary(id="1", name="Test")
        assert loc.confidence_score == 0
        assert loc.slug == ""


class TestStateSummary:
    def test_create(self):
        s = StateSummary(
            state="IL", state_full="Illinois",
            slug="illinois", location_count=42, city_count=10,
        )
        assert s.location_count == 42


class TestOrgDetail:
    def test_defaults(self):
        org = OrgDetail(id="1", name="Test Org")
        assert org.locations == []
        assert org.slug == ""
