"""Golden-parity tests for PTF /locations.

Compares the wire shape of our PTF responses against the captured
Plentiful fixtures. This is the test that catches Plentiful drift:
when their shape changes and someone re-captures the fixture, this
test goes red until our schema/transformer is updated to match.

Contract: the PPR response key set must equal the Plentiful key set,
with `feeding_america_food_bank` as the only PPR-only addition.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.partners.ptf.locations_transformer import to_detail, to_list_item

FIXTURES = Path(__file__).parent / "fixtures" / "ptf_locations"


def _plentiful_list_keys() -> set[str]:
    rows = json.loads((FIXTURES / "plentiful_locations_sample.json").read_text())
    return set(rows[0].keys())


def _plentiful_detail_keys() -> set[str]:
    row = json.loads((FIXTURES / "plentiful_location_detail_sample.json").read_text())
    return set(row.keys())


def _row(**overrides):
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


class TestListShapeParity:
    def test_ppr_list_keys_match_plentiful_keys(self):
        ppr_item = to_list_item(_row(), catalogue={})
        ppr_keys = set(ppr_item.model_dump(mode="json").keys())
        plentiful_keys = _plentiful_list_keys()
        # The only allowed addition is feeding_america_food_bank.
        # Plentiful already has this key in our fixture (the addition is
        # what makes it part of the contract going forward).
        assert ppr_keys == plentiful_keys, (
            f"Drift detected. "
            f"Missing from PPR: {plentiful_keys - ppr_keys}. "
            f"PPR-only: {ppr_keys - plentiful_keys}."
        )

    def test_ppr_list_field_types_match_plentiful(self):
        ppr_item = to_list_item(_row(), catalogue={})
        ppr_dump = ppr_item.model_dump(mode="json")
        plentiful_row = json.loads(
            (FIXTURES / "plentiful_locations_sample.json").read_text()
        )[0]
        for key, plentiful_val in plentiful_row.items():
            if plentiful_val is None:
                continue  # null types are universal
            ppr_val = ppr_dump.get(key)
            if ppr_val is None:
                continue
            assert type(ppr_val).__name__ == type(plentiful_val).__name__, (
                f"Type drift on '{key}': "
                f"Plentiful={type(plentiful_val).__name__}, "
                f"PPR={type(ppr_val).__name__}"
            )


class TestDetailShapeParity:
    def test_ppr_detail_keys_match_plentiful_keys(self):
        ppr_item = to_detail(_row(), catalogue={}, schedules=[])
        ppr_keys = set(ppr_item.model_dump(mode="json").keys())
        plentiful_keys = _plentiful_detail_keys()
        assert ppr_keys == plentiful_keys, (
            f"Drift detected. "
            f"Missing from PPR: {plentiful_keys - ppr_keys}. "
            f"PPR-only: {ppr_keys - plentiful_keys}."
        )
