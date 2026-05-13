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
            "freshtrak",
            "nyc_efap_programs",
            "human_update",
            "submarine",
            "portal_ingest",
        ):
            assert blocked not in FANO_ALLOWLIST, (
                f"{blocked!r} leaked into FANO_ALLOWLIST — would falsely "
                "tag aggregator-only locations as FA-network."
            )
