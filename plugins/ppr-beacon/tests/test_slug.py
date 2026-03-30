"""Tests for URL slug generation."""

import pytest
from app.slug import city_slug, location_slug, org_slug, state_full_name, state_slug


class TestStateSlug:
    def test_abbreviation(self):
        assert state_slug("IL") == "illinois"

    def test_full_name(self):
        assert state_slug("New York") == "new-york"

    def test_dc(self):
        assert state_slug("DC") == "district-of-columbia"

    def test_case_insensitive(self):
        assert state_slug("ca") == "california"


class TestStateFullName:
    def test_known(self):
        assert state_full_name("IL") == "Illinois"

    def test_unknown_passthrough(self):
        assert state_full_name("XX") == "XX"


class TestCitySlug:
    def test_simple(self):
        assert city_slug("Springfield") == "springfield"

    def test_with_punctuation(self):
        assert city_slug("St. Louis") == "st-louis"

    def test_with_spaces(self):
        assert city_slug("New York City") == "new-york-city"


class TestLocationSlug:
    def test_normal(self):
        assert location_slug("Springfield Community Food Pantry") == "springfield-community-food-pantry"

    def test_empty_with_id(self):
        assert location_slug("", "abc12345-678") == "abc12345"

    def test_empty_no_id(self):
        assert location_slug("") == "location"


class TestOrgSlug:
    def test_normal(self):
        assert org_slug("Feeding America Eastern Illinois") == "feeding-america-eastern-illinois"

    def test_empty(self):
        assert org_slug("") == "org"
