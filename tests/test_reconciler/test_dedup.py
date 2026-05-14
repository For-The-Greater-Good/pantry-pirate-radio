"""Unit tests for app.reconciler.dedup — module-shape only.

These tests lock the contract of `tier3_match_sql()` and
`accent_fold_expr()` without touching the database. Integration tests
in `tests/test_reconciler/test_location_creator.py` (mocked DB) and
the cross-stage drift guard in
`tests/test_ptf_locations_queries.py` cover real call paths.
"""

from __future__ import annotations

from app.reconciler.dedup import (
    _ADDR_SIM_THRESHOLD,
    _DEDUP_LOOSE_DEG,
    _HUMAN_VERIFIED_TIERS,
    _NAME_SIM_THRESHOLD,
    accent_fold_expr,
    tier3_match_sql,
)


class TestConstants:
    """The constants are the cross-stage contract — accidental edits
    here can silently widen or narrow dedup behaviour everywhere."""

    def test_loose_deg_matches_ptf_api(self) -> None:
        # ~200m in SRID-4326 degrees. PTF API imports this same value.
        assert _DEDUP_LOOSE_DEG == 0.00180

    def test_name_sim_threshold_lower_than_addr(self) -> None:
        # Names are noisier than addresses ("Church of X" vs "X Church")
        # so the name gate must be more permissive than the address
        # gate. Locking this invariant prevents a future tweak from
        # accidentally inverting the relationship.
        assert _NAME_SIM_THRESHOLD < _ADDR_SIM_THRESHOLD

    def test_name_sim_threshold(self) -> None:
        assert _NAME_SIM_THRESHOLD == 0.5

    def test_addr_sim_threshold(self) -> None:
        assert _ADDR_SIM_THRESHOLD == 0.7

    def test_human_verified_tiers_is_invariant(self) -> None:
        # Principle VI: never merge a scrape into a human-curated row.
        # If this list ever differs from merge_strategy's protected
        # tiers, Tier 3 can silently overwrite admin work.
        assert _HUMAN_VERIFIED_TIERS == ("admin", "source", "claimed")


class TestAccentFoldExpr:
    """The folding helper must produce SQL that is functionally
    identical to the PTF API's inline literal — otherwise a name like
    'San José' folds one way at ingest and another way at serve."""

    def test_lowercases_and_strips_punctuation(self) -> None:
        sql = accent_fold_expr("l.name")
        assert "lower(" in sql
        assert "regexp_replace(" in sql
        assert "'[^a-zA-Z0-9 ]'" in sql

    def test_translates_accents_to_ascii(self) -> None:
        sql = accent_fold_expr("l.name")
        # Both the from-set and to-set must be present, in the same
        # one-char-per-position pairing that the PTF API uses.
        assert "áàâäãåÁÀÂÄÃÅéèêëÉÈÊËíìîïÍÌÎÏóòôöõÓÒÔÖÕúùûüÚÙÛÜñÑçÇ" in sql
        assert "aaaaaaAAAAAAeeeeEEEEiiiiIIIIoooooOOOOOuuuuUUUUnNcC" in sql

    def test_handles_null_via_coalesce(self) -> None:
        # NULL name/address columns must fold to empty string rather
        # than NULL so similarity() doesn't bomb at row 1.
        sql = accent_fold_expr("l.name")
        assert "coalesce(" in sql.lower()

    def test_accepts_column_or_bind_param(self) -> None:
        # The helper has to work uniformly for column refs and bind
        # placeholders — the SQL is the same shape, just with the
        # argument substituted in.
        col_sql = accent_fold_expr("l.name")
        param_sql = accent_fold_expr(":name")
        assert "l.name" in col_sql
        assert ":name" in param_sql


class TestTier3MatchSql:
    """The Tier 3 query is the load-bearing part of the reconciler
    change. These tests lock its semantics without hitting a DB."""

    def test_uses_similarity_function(self) -> None:
        sql = tier3_match_sql()
        assert "similarity(" in sql, "Tier 3 must use pg_trgm similarity()"

    def test_uses_st_dwithin_for_distance(self) -> None:
        sql = tier3_match_sql()
        assert "ST_DWithin(" in sql

    def test_filters_to_canonical_only(self) -> None:
        # Merging into a soft-deleted (is_canonical=FALSE) row would
        # silently resurrect it.
        sql = tier3_match_sql()
        assert "is_canonical = TRUE" in sql

    def test_excludes_human_verified_rows(self) -> None:
        # Principle VI exemption.
        sql = tier3_match_sql()
        assert "'admin'" in sql
        assert "'source'" in sql
        assert "'claimed'" in sql
        assert "NOT IN" in sql

    def test_includes_null_verified_by_rows(self) -> None:
        # The reconciler's own scraped rows have verified_by IS NULL.
        # If we accidentally filter those out, Tier 3 never matches.
        sql = tier3_match_sql()
        assert "verified_by IS NULL" in sql

    def test_name_gate_uses_bind_param(self) -> None:
        sql = tier3_match_sql()
        assert ":name" in sql
        assert ":name_sim" in sql

    def test_address_gate_requires_zip_agreement(self) -> None:
        # Address-only similarity is too easy to coincidentally match
        # ("100 Main St" exists in every town). The address gate must
        # require zip5 agreement.
        sql = tier3_match_sql()
        assert ":zip5" in sql
        assert "SUBSTR(a.postal_code, 1, 5) = :zip5" in sql

    def test_thresholds_are_bind_params_not_hardcoded(self) -> None:
        # Operators tune thresholds by editing the module constants
        # (passed in as bind params), not by editing SQL text. A
        # regression that hard-codes `0.5` would silently disable
        # tuning and survive most reviews.
        sql = tier3_match_sql()
        assert ":name_sim" in sql
        assert ":addr_sim" in sql
        assert ":loose_deg" in sql
        # The float literals must NOT appear as SQL text — they're
        # always bound. (Apart from accidental matches inside the
        # accent-fold string set; assert against the suspicious
        # >-comparison form.)
        assert "> 0.5" not in sql
        assert "> 0.7" not in sql

    def test_joins_physical_address_only(self) -> None:
        # The address gate compares against physical addresses only;
        # joining mailing addresses would let a PO box on Main St
        # match a pantry on Main St.
        sql = tier3_match_sql()
        assert "address_type = 'physical'" in sql

    def test_for_update_skip_locked(self) -> None:
        # Concurrent reconciler workers must not all try to merge into
        # the same row — FOR UPDATE SKIP LOCKED lets the second worker
        # fall through to create a new canonical instead of blocking.
        sql = tier3_match_sql()
        assert "FOR UPDATE SKIP LOCKED" in sql

    def test_orders_by_proximity(self) -> None:
        # When two candidates pass the gate, the closer one wins —
        # otherwise we could merge into a 200m-away match when a 51m
        # match also exists.
        sql = tier3_match_sql()
        assert "ORDER BY" in sql
        assert "ABS(l.latitude" in sql

    def test_limits_to_one_result(self) -> None:
        sql = tier3_match_sql()
        assert "LIMIT 1" in sql

    def test_name_and_addr_gates_are_or_ed(self) -> None:
        # Either a name match OR an address+zip match qualifies. A
        # regression to AND would require BOTH (silently miss many
        # real dupes where one signal is strong and the other is
        # weak, e.g. address copy-paste typo + clean name match).
        sql = tier3_match_sql()
        # Find the predicate block and verify OR is present between
        # the two similarity sub-conditions. Cheap check: there should
        # be an `OR` token between two `similarity(` calls.
        first_sim = sql.find("similarity(")
        second_sim = sql.find("similarity(", first_sim + 1)
        assert first_sim != -1 and second_sim != -1
        between = sql[first_sim:second_sim]
        assert " OR " in between

    def test_empty_name_does_not_match(self) -> None:
        # An empty incoming name must not bypass the name gate (otherwise
        # similarity('', '') >= 0 would match anything within 200m).
        sql = tier3_match_sql()
        assert ":name <> ''" in sql

    def test_empty_addr_does_not_match(self) -> None:
        sql = tier3_match_sql()
        assert ":addr_1 <> ''" in sql
