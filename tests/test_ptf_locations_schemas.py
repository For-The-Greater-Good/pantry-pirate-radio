"""Schema parity tests for the PTF /locations endpoints.

These tests freeze the wire contract: the captured Plentiful fixtures
under tests/fixtures/ptf_locations/ must round-trip cleanly through our
Pydantic schemas with extra='forbid'. Any future Plentiful field rename
or addition will fail loudly here instead of silently passing through.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api.v1.partners.ptf.locations_schemas import (
    PtfFeedingAmericaFoodBank,
    PtfLocationDetail,
    PtfLocationListItem,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ptf_locations"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text())


class TestPtfLocationListItem:
    def test_every_fixture_row_round_trips(self):
        for row in _load("plentiful_locations_sample.json"):
            item = PtfLocationListItem.model_validate(row)
            # The dump must contain every original key (no silent drops)
            dumped = item.model_dump(mode="json")
            assert set(dumped.keys()) == set(
                row.keys()
            ), f"Schema dropped keys: {set(row.keys()) - set(dumped.keys())}"

    def test_unknown_key_is_rejected(self):
        # Future Plentiful additions go red, not silent
        row = _load("plentiful_locations_sample.json")[0]
        row["new_plentiful_field"] = "surprise"
        with pytest.raises(ValidationError):
            PtfLocationListItem.model_validate(row)

    def test_phone_zero_when_null_in_plentiful(self):
        # Second row has phone: 0 (the Plentiful null-phone convention)
        rows = _load("plentiful_locations_sample.json")
        item = PtfLocationListItem.model_validate(rows[1])
        assert item.phone == 0

    def test_negative_pantry_id_is_accepted(self):
        # All PPR rows have pantry_id = -<hash>; must validate
        row = _load("plentiful_locations_sample.json")[0]
        assert row["pantry_id"] < 0
        PtfLocationListItem.model_validate(row)

    def test_fa_block_can_be_null(self):
        rows = _load("plentiful_locations_sample.json")
        # Third fixture row has no FA mapping
        item = PtfLocationListItem.model_validate(rows[2])
        assert item.feeding_america_food_bank is None


class TestPtfLocationDetail:
    def test_fixture_round_trips(self):
        row = _load("plentiful_location_detail_sample.json")
        item = PtfLocationDetail.model_validate(row)
        dumped = item.model_dump(mode="json")
        assert set(dumped.keys()) == set(
            row.keys()
        ), f"Schema dropped keys: {set(row.keys()) - set(dumped.keys())}"

    def test_unknown_key_is_rejected(self):
        row = _load("plentiful_location_detail_sample.json")
        row["unexpected"] = 1
        with pytest.raises(ValidationError):
            PtfLocationDetail.model_validate(row)


class TestPtfFeedingAmericaFoodBank:
    def test_minimum_payload_id_and_name(self):
        fa = PtfFeedingAmericaFoodBank.model_validate({"id": 71, "name": "CFBNJ"})
        assert fa.id == 71
        assert fa.name == "CFBNJ"

    def test_richer_optional_fields_accepted(self):
        fa = PtfFeedingAmericaFoodBank.model_validate(
            {
                "id": 229,
                "name": "Banco de Alimentos de Puerto Rico",
                "state": "PR",
                "find_food_url": "https://example.org/find",
                "url_slug": "banco-de-alimentos-de-puerto-rico",
                "is_affiliate": False,
                "parent_org_id": None,
                "parent_name": None,
            }
        )
        assert fa.state == "PR"
        assert fa.url_slug == "banco-de-alimentos-de-puerto-rico"

    def test_unknown_key_is_rejected(self):
        with pytest.raises(ValidationError):
            PtfFeedingAmericaFoodBank.model_validate(
                {"id": 1, "name": "X", "made_up_field": True}
            )

    def test_missing_required_keys_rejected(self):
        with pytest.raises(ValidationError):
            PtfFeedingAmericaFoodBank.model_validate({"name": "no id"})
        with pytest.raises(ValidationError):
            PtfFeedingAmericaFoodBank.model_validate({"id": 1})
