"""Transformer tests for PTF /locations endpoints.

Table-driven cases — one row per Plentiful quirk, so when something
regresses the failure points straight at the broken rule.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.partners.ptf.locations_transformer import (
    fa_pantry_id_from_uuid,
    to_list_item,
    to_detail,
)


# A minimal location-row shape (mirrors what queries.py SELECTs). Keep
# the field set small and explicit — transformer should tolerate Nones.
def make_row(**overrides):
    base = {
        "id": str(uuid4()),
        "name": "Test Pantry",
        "short_name": None,
        "description": None,
        "latitude": 40.0,
        "longitude": -74.0,
        "organization_id": None,
        "org_name": None,
        "org_description": None,
        "org_email": None,
        "org_website": None,
        "address_1": "1 Main St",
        "address_2": None,
        "city": "Newark",
        "state_province": "NJ",
        "postal_code": "07102",
        "phone_number": None,
        "fa_org_id": None,
        "fa_org_name": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestPantryIdHash:
    def test_deterministic_per_uuid(self):
        u = str(uuid4())
        assert fa_pantry_id_from_uuid(u) == fa_pantry_id_from_uuid(u)

    def test_always_negative(self):
        for _ in range(20):
            assert fa_pantry_id_from_uuid(str(uuid4())) < 0

    def test_distinct_uuids_distinct_hash(self):
        # Sanity check — not a guarantee, but ~0 chance of collision at
        # this volume given crc32 spans 31 bits.
        ids = {fa_pantry_id_from_uuid(str(uuid4())) for _ in range(200)}
        assert len(ids) == 200


class TestPhoneQuirk:
    def test_null_phone_becomes_zero(self):
        item = to_list_item(make_row(phone_number=None), catalogue={})
        assert item.phone == 0

    def test_phone_normalized_to_int(self):
        item = to_list_item(make_row(phone_number="(973) 555-1234"), catalogue={})
        assert item.phone == 9735551234

    def test_unparseable_phone_becomes_zero(self):
        item = to_list_item(make_row(phone_number="not-a-phone"), catalogue={})
        assert item.phone == 0


class TestTimezoneDefault:
    def test_us_state_resolves_to_iana(self):
        item = to_list_item(make_row(state_province="CA"), catalogue={})
        assert item.pantry_timezone == "America/Los_Angeles"

    def test_unknown_state_defaults_eastern(self):
        item = to_list_item(make_row(state_province=None), catalogue={})
        assert item.pantry_timezone == "America/New_York"


class TestUnauthDefaults:
    def test_list_avatar_empty_string(self):
        item = to_list_item(make_row(), catalogue={})
        assert item.avatar == ""

    def test_list_has_plentiful_pantry_false(self):
        item = to_list_item(make_row(), catalogue={})
        assert item.has_plentiful_pantry is False

    def test_list_service_type_default_one(self):
        item = to_list_item(make_row(), catalogue={})
        assert item.service_type == 1

    def test_list_services_null_and_next_service_null(self):
        item = to_list_item(make_row(), catalogue={})
        assert item.services is None
        assert item.next_service is None

    def test_list_programs_empty_array(self):
        item = to_list_item(make_row(), catalogue={})
        assert item.programs == []

    def test_detail_user_can_visit_false(self):
        d = to_detail(make_row(), catalogue={}, schedules=[])
        assert d.user_can_visit is False
        assert d.user_visit_summary == ""

    def test_detail_amenities_conditions_empty(self):
        d = to_detail(make_row(), catalogue={}, schedules=[])
        assert d.amenities == []
        assert d.conditions == []

    def test_detail_has_appointment_false(self):
        d = to_detail(make_row(), catalogue={}, schedules=[])
        assert d.has_appointment is False


class TestZipCode:
    def test_valid_5_digit_zip_int(self):
        item = to_list_item(make_row(postal_code="07102"), catalogue={})
        assert item.zip_code == 7102

    def test_zip_with_plus_four_keeps_first_5(self):
        item = to_list_item(make_row(postal_code="07102-4567"), catalogue={})
        assert item.zip_code == 7102

    def test_invalid_zip_is_none(self):
        item = to_list_item(make_row(postal_code="invalid"), catalogue={})
        assert item.zip_code is None


class TestPantryIdField:
    def test_pantry_id_is_negative_hash_of_uuid(self):
        u = "11111111-2222-3333-4444-555555555555"
        item = to_list_item(make_row(id=u), catalogue={})
        assert item.pantry_id == fa_pantry_id_from_uuid(u)
        assert item.id == u  # UUID preserved verbatim


class TestFeedingAmericaEnrichment:
    def test_zip_miss_returns_null_block(self):
        # No fa_org_id from the JOIN
        item = to_list_item(make_row(fa_org_id=None, fa_org_name=None), catalogue={})
        assert item.feeding_america_food_bank is None

    def test_zip_hit_no_catalogue_returns_minimum_block(self):
        # JOIN found a row but the in-memory catalogue has no enrichment
        item = to_list_item(
            make_row(fa_org_id=58, fa_org_name="Community Foodbank of New Jersey"),
            catalogue={},
        )
        fa = item.feeding_america_food_bank
        assert fa is not None
        assert fa.id == 58
        assert fa.name == "Community Foodbank of New Jersey"
        # Optional fields not present (omitted, not null) when no catalogue hit
        dumped = fa.model_dump(exclude_none=True)
        assert set(dumped.keys()) == {"id", "name"}

    def test_zip_hit_with_catalogue_returns_full_block(self):
        catalogue = {
            58: {
                "id": 58,
                "name": "Community Foodbank of New Jersey",
                "state": "NJ",
                "find_food_url": "https://cfbnj.org/find-food/",
                "url_slug": "community-foodbank-of-new-jersey",
                "is_affiliate": False,
            }
        }
        item = to_list_item(
            make_row(fa_org_id=58, fa_org_name="Community Foodbank of New Jersey"),
            catalogue=catalogue,
        )
        fa = item.feeding_america_food_bank
        assert fa is not None
        assert fa.state == "NJ"
        assert fa.url_slug == "community-foodbank-of-new-jersey"

    def test_affiliate_block_carries_parent(self):
        catalogue = {
            999: {
                "id": 999,
                "name": "Local Affiliate",
                "is_affiliate": True,
                "parent_org_id": 58,
                "parent_name": "Community Foodbank of New Jersey",
            }
        }
        item = to_list_item(
            make_row(fa_org_id=999, fa_org_name="Local Affiliate"),
            catalogue=catalogue,
        )
        fa = item.feeding_america_food_bank
        assert fa is not None
        assert fa.is_affiliate is True
        assert fa.parent_org_id == 58
        assert fa.parent_name == "Community Foodbank of New Jersey"


class TestDetailExtras:
    def test_composed_address_string(self):
        d = to_detail(
            make_row(
                address_1="1 Main St",
                address_2=None,
                city="Newark",
                state_province="NJ",
                postal_code="07102",
            ),
            catalogue={},
            schedules=[],
        )
        assert "1 Main St" in d.address
        assert "Newark" in d.address
        assert "NJ" in d.address
        assert "07102" in d.address

    def test_detail_carries_email_and_description(self):
        d = to_detail(
            make_row(org_email="info@example.org", description="Free groceries"),
            catalogue={},
            schedules=[],
        )
        assert d.email == "info@example.org"
        assert d.additional_info == "Free groceries"
