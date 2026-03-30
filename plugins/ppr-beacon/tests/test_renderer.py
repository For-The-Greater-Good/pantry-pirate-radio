"""Tests for Jinja2 rendering engine — HTML quality and SEO compliance.

Constitution Principle 2 (SEO Correctness) and Principle 3 (Page Performance).
"""

import os
import re
from pathlib import Path

import pytest
from app.models import LocationDetail, LocationSummary, OrgDetail, Phone, Schedule
from app.renderer import BeaconRenderer

TEMPLATE_DIR = str(Path(__file__).parent.parent / "templates")
BASE_URL = "https://plentiful.org/providers"


@pytest.fixture
def renderer():
    return BeaconRenderer(
        template_dir=TEMPLATE_DIR,
        base_url=BASE_URL,
        analytics_endpoint="https://analytics.example.com/events",
    )


@pytest.fixture
def sample_location():
    return LocationDetail(
        id="loc-1",
        name="Springfield Community Food Pantry",
        organization_name="Feeding Illinois",
        organization_id="org-1",
        address_1="123 Main St",
        city="Springfield",
        state="IL",
        postal_code="62701",
        latitude=39.7817,
        longitude=-89.6501,
        phone="555-0100",
        email="info@example.com",
        website="https://example.com",
        description="A community food pantry serving Springfield area residents.",
        confidence_score=95,
        validation_status="verified",
        verified_by="source",
        verified_at="2026-03-30T12:00:00Z",
        schedules=[
            Schedule(opens_at="09:00", closes_at="17:00", byday="MO,WE,FR"),
        ],
        phones=[Phone(number="555-0100", type="voice")],
        slug="springfield-community-food-pantry",
        url=f"{BASE_URL}/illinois/springfield/springfield-community-food-pantry",
    )


class TestLocationPage:
    """HTML quality assertions for location detail pages."""

    def test_exactly_one_h1(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        h1_count = len(re.findall(r"<h1[^>]*>", html))
        assert h1_count == 1, f"Expected 1 <h1>, found {h1_count}"

    def test_has_title_tag(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert "<title>" in html
        assert "Springfield Community Food Pantry" in html

    def test_has_meta_description(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert 'name="description"' in html

    def test_has_canonical_url(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert 'rel="canonical"' in html
        assert sample_location.url in html

    def test_has_og_tags(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert 'property="og:title"' in html
        assert 'property="og:description"' in html
        assert 'property="og:url"' in html

    def test_has_twitter_card(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert 'name="twitter:card"' in html

    def test_has_jsonld(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert "application/ld+json" in html
        assert "FoodEstablishment" in html
        assert "BreadcrumbList" in html

    def test_has_semantic_html(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert "<header" in html
        assert "<main>" in html or "<main " in html
        assert "<nav" in html
        assert "<article>" in html or "<article " in html
        assert "<footer" in html

    def test_has_lang_attribute(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert '<html lang="en">' in html

    def test_has_charset(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert 'charset="utf-8"' in html

    def test_tel_link(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert "tel:" in html

    def test_maps_link(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert "google.com/maps" in html

    def test_trust_badge(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert "Verified by Provider" in html

    def test_breadcrumb_uses_slugs(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert f"{BASE_URL}/illinois" in html
        assert f"{BASE_URL}/illinois/springfield" in html
        # Should NOT contain raw abbreviation in URL
        assert f'{BASE_URL}/IL"' not in html

    def test_breadcrumb_shows_full_state_name(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert "Illinois" in html

    def test_analytics_meta_tag(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert 'name="beacon-analytics"' in html
        assert "https://analytics.example.com/events" in html

    def test_data_track_attributes(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        assert 'data-track="directions"' in html
        assert 'data-track="call"' in html


class TestHomePage:
    def test_has_h1(self, renderer):
        html = renderer.render_home(
            [{"name": "Illinois", "slug": "illinois", "count": 10, "cities": 3}],
            total_locations=10,
        )
        h1_count = len(re.findall(r"<h1[^>]*>", html))
        assert h1_count == 1

    def test_has_breadcrumb_jsonld(self, renderer):
        html = renderer.render_home([], total_locations=0)
        assert "BreadcrumbList" in html

    def test_has_canonical(self, renderer):
        html = renderer.render_home([], total_locations=0)
        assert 'rel="canonical"' in html
        assert BASE_URL in html


class TestCityPage:
    def test_has_h1(self, renderer):
        html = renderer.render_city("Springfield", "IL", [])
        h1_count = len(re.findall(r"<h1[^>]*>", html))
        assert h1_count == 1

    def test_breadcrumb_uses_slug(self, renderer):
        html = renderer.render_city("Springfield", "IL", [])
        assert f"{BASE_URL}/illinois" in html


class TestPageBudget:
    """Constitution Principle 3: Page Performance."""

    def test_location_page_under_100kb(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        size_kb = len(html.encode("utf-8")) / 1024
        assert size_kb < 100, f"Location page is {size_kb:.1f}KB, budget is 100KB"

    def test_css_under_15kb(self):
        css_path = Path(__file__).parent.parent / "static" / "css" / "beacon.css"
        size_kb = css_path.stat().st_size / 1024
        assert size_kb < 15, f"CSS is {size_kb:.1f}KB, budget is 15KB"

    def test_no_inline_styles_in_location(self, renderer, sample_location):
        html = renderer.render_location(sample_location)
        # Allow style on script tags but not on regular elements
        style_matches = re.findall(r'<(?!script)[^>]*\sstyle="[^"]*"', html)
        assert len(style_matches) == 0, f"Found inline styles: {style_matches}"
