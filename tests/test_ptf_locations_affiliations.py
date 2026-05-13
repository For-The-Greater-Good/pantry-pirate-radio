"""Tests for the FANO allowlist + `affiliations` field on PTF endpoints.

Allowlist semantics: a location is a Feeding America Network Organization
affiliate (`affiliations: ["FANO"]`) iff at least one of its location_source
rows has a `scraper_id` in the curated allowlist AND `source_type` is not
`'submarine'`. The `feeding_america_food_bank` block is additionally gated
on the ZIP appearing in `feeding_america_zip_coverage`.

These tests are layered (constitution III):
  - allowlist module (loads the TSV)
  - SQL query layer (qualifying_source CTE + FA gating)
  - schemas (default-empty `affiliations`)
  - transformer (FANO when qualifying source present)
"""

from __future__ import annotations


class TestAllowlistModule:
    """The allowlist is loaded once from the bundled TSV at import time."""

    def test_allowlist_loaded_as_frozenset(self) -> None:
        from app.api.v1.partners.ptf._allowlist import FANO_ALLOWLIST

        assert isinstance(FANO_ALLOWLIST, frozenset)
        assert len(FANO_ALLOWLIST) > 100  # Sanity floor; TSV has ~150 rows.

    def test_known_fa_spine_member_present(self) -> None:
        from app.api.v1.partners.ptf._allowlist import FANO_ALLOWLIST

        # `vivery_api` is the fa-spine entry that covers the largest set of
        # FA-affiliated locations. If it ever falls out of the TSV the
        # allowlist is broken.
        assert "vivery_api" in FANO_ALLOWLIST

    def test_known_individual_food_bank_scraper_present(self) -> None:
        from app.api.v1.partners.ptf._allowlist import FANO_ALLOWLIST

        # Picked because they appear in the committed TSV and are stable.
        assert "feeding_the_gulf_coast_al" in FANO_ALLOWLIST
        assert "oregon_food_bank_or" in FANO_ALLOWLIST

    def test_aggregators_and_enrichments_excluded(self) -> None:
        from app.api.v1.partners.ptf._allowlist import FANO_ALLOWLIST

        # These scrapers / source-types index food pantries but do not
        # themselves attest that a location is in the FA network.
        for blocked in (
            "foodfinder_us",
            "food_helpline_org",
            "getfull_app_api",
            "the_food_pantries_org",
            "nyc_efap_programs",
            "human_update",
            "submarine",
            "portal_ingest",
        ):
            assert blocked not in FANO_ALLOWLIST, (
                f"{blocked!r} leaked into FANO_ALLOWLIST — would falsely "
                "tag aggregator-only locations as FA-network."
            )


class TestAllowlistLoaderFailsLoudly:
    """The TSV is data critical to FA enrichment correctness; any corruption
    must crash at process startup rather than silently degrade to an empty
    or partial allowlist (Constitution VI + XI).
    """

    def _write_tsv(self, tmp_path, content: str):
        # Patch the loader to read a temp TSV path. The module-level constant
        # was already loaded at import; we test the helper directly.
        from app.api.v1.partners.ptf import _allowlist as mod

        path = tmp_path / "fano_allowlist.tsv"
        path.write_text(content)
        return mod, path

    def test_missing_scraper_id_column_raises(self, tmp_path, monkeypatch) -> None:
        mod, path = self._write_tsv(
            tmp_path,
            "category\tcount\twrong_col\nfa\t1\tsomething\n",
        )
        monkeypatch.setattr(mod, "_TSV_PATH", path)
        try:
            mod._load()
        except RuntimeError as exc:
            assert "scraper_id" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for missing column")

    def test_empty_scraper_id_cell_raises(self, tmp_path, monkeypatch) -> None:
        mod, path = self._write_tsv(
            tmp_path,
            "category\tcount\tscraper_id\nfa\t1\tgood_scraper\nfa\t1\t\n",
        )
        monkeypatch.setattr(mod, "_TSV_PATH", path)
        try:
            mod._load()
        except RuntimeError as exc:
            assert "empty scraper_id" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for empty cell")

    def test_empty_allowlist_raises(self, tmp_path, monkeypatch) -> None:
        # Header-only TSV — no data rows.
        mod, path = self._write_tsv(tmp_path, "category\tcount\tscraper_id\n")
        monkeypatch.setattr(mod, "_TSV_PATH", path)
        try:
            mod._load()
        except RuntimeError as exc:
            assert "empty allowlist" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for empty allowlist")

    def test_bom_in_header_does_not_corrupt_column_lookup(
        self, tmp_path, monkeypatch
    ) -> None:
        """A Windows-edited TSV that ships with a UTF-8 BOM prefix must
        still load correctly — otherwise the first column header becomes
        `\\ufeffcategory` and DictReader silently misses `scraper_id`.
        """
        mod, path = self._write_tsv(
            tmp_path,
            "﻿category\tcount\tscraper_id\nfa\t1\tgood_scraper\n",
        )
        monkeypatch.setattr(mod, "_TSV_PATH", path)
        loaded = mod._load()
        assert "good_scraper" in loaded


# ---- SQL layer (qualifying_source CTE) -----------------------------------


def _capture_session():
    """Return a mock AsyncSession that records every execute() call.

    Matches the helper in test_ptf_locations_queries.py so we can inspect
    generated SQL and bind params without a live DB.
    """
    from unittest.mock import AsyncMock, MagicMock

    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            fetchall=MagicMock(return_value=[]),
            fetchone=MagicMock(return_value=None),
        )
    )
    return session


class TestQualifyingSourceCTE:
    """The list + detail queries must compute `has_qualifying_source` per
    location via a CTE that filters location_source rows to those with
    `scraper_id IN :allowlist` AND `source_type != 'submarine'`.
    """

    import pytest

    @pytest.mark.asyncio
    async def test_list_query_contains_qualifying_source_cte(self):
        from app.api.v1.partners.ptf.locations_queries import PtfLocationsQuery

        session = _capture_session()
        await PtfLocationsQuery(session).list_locations(limit=10, offset=0)
        sql_text = str(session.execute.call_args[0][0])
        assert "qualifying_source" in sql_text
        assert "has_qualifying_source" in sql_text

    @pytest.mark.asyncio
    async def test_list_query_filters_by_allowlist_param(self):
        from app.api.v1.partners.ptf.locations_queries import PtfLocationsQuery

        session = _capture_session()
        await PtfLocationsQuery(session).list_locations(limit=10, offset=0)
        sql_text = str(session.execute.call_args[0][0])
        params = session.execute.call_args[0][1]
        # IN clause must reference a bound param, not an inlined list.
        assert "scraper_id IN" in sql_text
        assert "allowlist" in sql_text  # the bind name
        assert "allowlist" in params
        # Tuple of scraper ids, expanding=True at the bind site.
        assert isinstance(params["allowlist"], tuple | list)
        assert "vivery_api" in params["allowlist"]
        # Aggregator MUST NOT be in the bound allowlist tuple.
        assert "foodfinder_us" not in params["allowlist"]

    @pytest.mark.asyncio
    async def test_list_query_excludes_submarine_source_type(self):
        """`submarine` is a source_type, not a scraper_id. The CTE must
        filter it out so a submarine enrichment alone does not qualify
        a location for FANO."""
        from app.api.v1.partners.ptf.locations_queries import PtfLocationsQuery

        session = _capture_session()
        await PtfLocationsQuery(session).list_locations(limit=10, offset=0)
        sql_text = str(session.execute.call_args[0][0])
        # The filter combines scraper_id allowlist with a source_type guard.
        assert "source_type" in sql_text
        assert "submarine" in sql_text

    @pytest.mark.asyncio
    async def test_list_query_gates_fa_columns_on_qualifying_source(self):
        """`fa_org_id` and `fa_org_name` must be NULL whenever no
        qualifying source exists, even if the ZIP joins to
        `feeding_america_zip_coverage`. The transformer reads NULL as
        "no FA block to render"."""
        from app.api.v1.partners.ptf.locations_queries import PtfLocationsQuery

        session = _capture_session()
        await PtfLocationsQuery(session).list_locations(limit=10, offset=0)
        sql_text = str(session.execute.call_args[0][0])
        # CASE WHEN ... THEN fa.fa_org_id END is the gating pattern.
        upper = sql_text.upper()
        assert "CASE WHEN" in upper
        # `zip_matched_fa` is the observability flag: True when the JOIN
        # matched FA crosswalk but the CASE suppressed `fa_org_id`.
        assert "zip_matched_fa" in sql_text

    @pytest.mark.asyncio
    async def test_detail_query_has_same_cte_and_gating(self):
        from app.api.v1.partners.ptf.locations_queries import PtfLocationsQuery

        session = _capture_session()
        await PtfLocationsQuery(session).get_location("any-id")
        sql_text = str(session.execute.call_args[0][0])
        params = session.execute.call_args[0][1]
        assert "qualifying_source" in sql_text
        assert "has_qualifying_source" in sql_text
        assert "zip_matched_fa" in sql_text
        assert "allowlist" in params


# ---- Schema layer (`affiliations` field) ---------------------------------


class TestAffiliationsField:
    """Both list-item and detail schemas must carry an optional
    `affiliations: list[str]` field that defaults to an empty list.
    """

    def _minimal_list_item(self) -> dict:
        # Smallest payload that satisfies all required fields. Mirrors the
        # transformer's output for a non-FA-network location.
        return {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "Test Pantry",
            "short_name": "Test Pantry",
            "address_street_1": "1 Main St",
            "address_street_2": "",
            "city": "Newark",
            "zip_code": 7102,
            "state": "NJ",
            "phone": 0,
            "website": "",
            "pantry_id": -42,
            "pantry_timezone": "America/New_York",
            "avatar": "",
            "longitude": -74.0,
            "latitude": 40.0,
            "has_plentiful_pantry": False,
            "has_appointments": False,
            "service_type": 1,
            "programs": [],
            "services": None,
            "services_detailed": None,
            "next_service": None,
            "feeding_america_food_bank": None,
        }

    def test_list_item_default_affiliations_is_empty(self) -> None:
        from app.api.v1.partners.ptf.locations_schemas import PtfLocationListItem

        # No affiliations key in input → default empty list.
        item = PtfLocationListItem.model_validate(self._minimal_list_item())
        assert item.affiliations == []

    def test_list_item_accepts_fano(self) -> None:
        from app.api.v1.partners.ptf.locations_schemas import PtfLocationListItem

        payload = self._minimal_list_item()
        payload["affiliations"] = ["FANO"]
        item = PtfLocationListItem.model_validate(payload)
        assert item.affiliations == ["FANO"]

    def test_list_item_accepts_multiple_codes(self) -> None:
        from app.api.v1.partners.ptf.locations_schemas import PtfLocationListItem

        payload = self._minimal_list_item()
        # Spec: a location MAY have multiple affiliations; order not significant.
        payload["affiliations"] = ["FANO", "CITYHARVEST"]
        item = PtfLocationListItem.model_validate(payload)
        assert set(item.affiliations) == {"FANO", "CITYHARVEST"}

    def test_list_item_accepts_explicit_empty(self) -> None:
        from app.api.v1.partners.ptf.locations_schemas import PtfLocationListItem

        payload = self._minimal_list_item()
        payload["affiliations"] = []
        item = PtfLocationListItem.model_validate(payload)
        assert item.affiliations == []

    def test_detail_default_affiliations_is_empty(self) -> None:
        # Compose from the existing fixture so we don't duplicate the full
        # detail required-fields list inline.
        import json
        from pathlib import Path

        from app.api.v1.partners.ptf.locations_schemas import PtfLocationDetail

        fixtures_dir = Path(__file__).parent / "fixtures" / "ptf_locations"
        detail_row = json.loads(
            (fixtures_dir / "plentiful_location_detail_sample.json").read_text()
        )
        # Strip affiliations if the fixture has been updated to include it,
        # so we test the default-empty path explicitly.
        detail_row.pop("affiliations", None)
        detail = PtfLocationDetail.model_validate(detail_row)
        assert detail.affiliations == []


# ---- Transformer layer ----------------------------------------------------


def _make_row(**overrides):
    """Build a SimpleNamespace row matching what queries.py SELECTs.

    Mirrors the helper in test_ptf_locations_transformer.py and extends it
    with the new `has_qualifying_source` / `zip_matched_fa` columns.
    """
    from types import SimpleNamespace
    from uuid import uuid4

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
        "has_qualifying_source": False,
        "zip_matched_fa": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestTransformerAffiliations:
    """`affiliations` is driven by `has_qualifying_source` alone (the FA
    crosswalk match only affects `feeding_america_food_bank`, per the
    user's adjustment: an allowlist scraper alone proves the location is
    a food bank, regardless of whether the ZIP happens to match).
    """

    def test_qualifying_source_yields_fano_even_without_fa_match(self) -> None:
        from app.api.v1.partners.ptf.locations_transformer import to_list_item

        # ZIP doesn't appear in feeding_america_zip_coverage, but the
        # location was found by an allowlist scraper. SQL CASE-gating
        # leaves fa_org_id NULL — affiliations is still ["FANO"].
        item = to_list_item(
            _make_row(
                has_qualifying_source=True,
                zip_matched_fa=False,
                fa_org_id=None,
                fa_org_name=None,
            ),
            catalogue={},
        )
        assert item.affiliations == ["FANO"]
        assert item.feeding_america_food_bank is None

    def test_qualifying_source_plus_fa_match_yields_fano_and_food_bank(self) -> None:
        from app.api.v1.partners.ptf.locations_transformer import to_list_item

        item = to_list_item(
            _make_row(
                has_qualifying_source=True,
                zip_matched_fa=True,
                fa_org_id=10,
                fa_org_name="Food Bank For New York City",
            ),
            catalogue={},
        )
        assert item.affiliations == ["FANO"]
        assert item.feeding_america_food_bank is not None
        assert item.feeding_america_food_bank.id == 10

    def test_no_qualifying_source_yields_empty_affiliations(self) -> None:
        from app.api.v1.partners.ptf.locations_transformer import to_list_item

        # Only an aggregator source found this location — even if its ZIP
        # is in FA coverage, the SQL CASE suppressed fa_org_id.
        item = to_list_item(
            _make_row(
                has_qualifying_source=False,
                zip_matched_fa=True,
                fa_org_id=None,
                fa_org_name=None,
            ),
            catalogue={},
        )
        assert item.affiliations == []
        assert item.feeding_america_food_bank is None

    def test_zip_match_without_qualifying_source_logs(self, caplog) -> None:
        """Observability: emit a structured log when the FA crosswalk
        matched but no qualifying source exists (so we can audit how
        much aggregator-only data overlaps FA territory during the demo).
        """
        import logging

        from app.api.v1.partners.ptf.locations_transformer import to_list_item

        with caplog.at_level(logging.INFO):
            to_list_item(
                _make_row(
                    has_qualifying_source=False,
                    zip_matched_fa=True,
                ),
                catalogue={},
            )
        assert any(
            "ptf_fano_suppressed_no_qualifying_source" in record.getMessage()
            for record in caplog.records
        ), "expected ptf_fano_suppressed_no_qualifying_source log event"

    def test_detail_qualifying_source_yields_fano(self) -> None:
        from app.api.v1.partners.ptf.locations_transformer import to_detail

        detail = to_detail(
            _make_row(has_qualifying_source=True, fa_org_id=10, fa_org_name="X"),
            catalogue={},
            schedules=[],
        )
        assert detail.affiliations == ["FANO"]

    def test_detail_no_qualifying_source_yields_empty(self) -> None:
        from app.api.v1.partners.ptf.locations_transformer import to_detail

        detail = to_detail(
            _make_row(has_qualifying_source=False),
            catalogue={},
            schedules=[],
        )
        assert detail.affiliations == []
