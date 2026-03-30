"""Tests for Schema.org JSON-LD generation."""

import json

import pytest
from app.models import LocationDetail, OrgDetail, Schedule, LocationSummary
from app.schema_org import build_breadcrumbs, build_location_jsonld, build_org_jsonld


class TestBuildLocationJsonld:
    def test_basic_fields(self):
        loc = LocationDetail(
            id="1", name="Test Pantry", slug="test-pantry",
            url="https://plentiful.org/providers/illinois/springfield/test-pantry",
        )
        data = json.loads(build_location_jsonld(loc))
        assert data["@context"] == "https://schema.org"
        assert data["@type"] == "FoodEstablishment"
        assert data["name"] == "Test Pantry"

    def test_address(self):
        loc = LocationDetail(
            id="1", name="Test", slug="test",
            url="https://example.com/test",
            address_1="123 Main St", city="Springfield",
            state="IL", postal_code="62701",
        )
        data = json.loads(build_location_jsonld(loc))
        assert data["address"]["@type"] == "PostalAddress"
        assert data["address"]["streetAddress"] == "123 Main St"
        assert data["address"]["addressRegion"] == "IL"

    def test_geo(self):
        loc = LocationDetail(
            id="1", name="Test", slug="test",
            url="https://example.com/test",
            latitude=40.7128, longitude=-74.006,
        )
        data = json.loads(build_location_jsonld(loc))
        assert data["geo"]["latitude"] == 40.7128

    def test_opening_hours(self):
        loc = LocationDetail(
            id="1", name="Test", slug="test",
            url="https://example.com/test",
            schedules=[
                Schedule(opens_at="09:00", closes_at="17:00", byday="MO,WE,FR"),
            ],
        )
        data = json.loads(build_location_jsonld(loc))
        hours = data["openingHoursSpecification"]
        assert len(hours) == 1
        assert hours[0]["opens"] == "09:00"
        assert "Monday" in hours[0]["dayOfWeek"]

    def test_no_hours_without_times(self):
        loc = LocationDetail(
            id="1", name="Test", slug="test",
            url="https://example.com/test",
            schedules=[Schedule(description="Call for hours")],
        )
        data = json.loads(build_location_jsonld(loc))
        assert "openingHoursSpecification" not in data


class TestBuildOrgJsonld:
    def test_basic(self):
        org = OrgDetail(
            id="1", name="Test Org", slug="test-org",
            url="https://example.com/org/test-org",
        )
        data = json.loads(build_org_jsonld(org))
        assert data["@type"] == "Organization"
        assert data["name"] == "Test Org"

    def test_with_locations(self):
        org = OrgDetail(
            id="1", name="Test Org", slug="test-org",
            url="https://example.com/org/test-org",
            locations=[
                LocationSummary(id="l1", name="Loc 1", slug="loc-1", url="https://example.com/loc-1"),
            ],
        )
        data = json.loads(build_org_jsonld(org))
        assert len(data["location"]) == 1
        assert data["location"][0]["name"] == "Loc 1"


class TestBuildBreadcrumbs:
    def test_structure(self):
        crumbs = [("Home", "https://example.com"), ("State", "https://example.com/il")]
        data = json.loads(build_breadcrumbs(crumbs))
        assert data["@type"] == "BreadcrumbList"
        assert len(data["itemListElement"]) == 2
        assert data["itemListElement"][0]["position"] == 1
        assert data["itemListElement"][1]["position"] == 2
