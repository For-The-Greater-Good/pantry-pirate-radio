"""Shared dedup primitives for reconciler Tier 3 + PTF API cluster-dedup.

Single source of truth for tiered cluster-dedup thresholds so the
"prevent on ingest" path (reconciler) and the "hide on serve" path
(PTF API) can't drift. The reconciler imports `tier3_match_sql()` to
find an existing canonical the strict tiers missed; the PTF endpoint
imports the constants only — its SQL builds a different shape
(connected-components walk across ALL candidates in a request) but uses
the same thresholds and the same accent-folding rule.

Tier 3 in the reconciler runs ONLY when Tiers 1 (~11m exact) and 2
(~165m + exact-name OR same-org) miss. It uses pg_trgm `similarity()`
to catch real duplicates where independent scrapers produced different
names AND different orgs for the same physical pantry. The
`verified_by IN ('admin','source','claimed')` exemption prevents the
reconciler from ever merging a scraped record into a human-curated row
(Principle VI: data quality for vulnerable populations).
"""

from __future__ import annotations

# SRID-4326 degrees. ~111km per degree at the equator, narrower at
# higher US latitudes. Loose-tier ceiling shared with PTF API.
_DEDUP_LOOSE_DEG = 0.00180  # ~200m

# pg_trgm similarity thresholds. Names are shorter and noisier
# ("Church of X" vs "X Church") so we use a lower bar than addresses.
_NAME_SIM_THRESHOLD = 0.5
_ADDR_SIM_THRESHOLD = 0.7

# Human-curated `verified_by` tier values that Tier 3 must never merge
# *into*. The reconciler is allowed to look at scraped rows; merging a
# new scrape into an admin/source/claimed row would silently overwrite
# human work. Mirrors `app/reconciler/merge_strategy.py` protected-tier
# semantics.
_HUMAN_VERIFIED_TIERS = ("admin", "source", "claimed")


def accent_fold_expr(column_sql: str) -> str:
    """Return a SQL fragment that lowercases, accent-folds, and strips
    punctuation from `column_sql`.

    Uses Postgres `translate()` for diacritic folding instead of the
    `unaccent` extension so the dedup module stays portable to
    deployments that haven't installed contrib extensions. Folds the
    common Latin diacritics covering Spanish, French, Italian, and
    Portuguese — the languages most relevant for US food-pantry names.

    Identical to the inline literal at
    `app/api/v1/partners/ptf/locations_queries.py:140-159`. Both copies
    must move together if a future refactor switches to `unaccent`.

    Args:
        column_sql: A SQL expression that evaluates to text. Trusted
            input — this is always either a column reference (e.g.,
            `l.name`) or a bind-parameter placeholder (e.g., `:name`),
            never user input. Callers are responsible for that
            discipline; bandit B608 catches direct concatenation of
            untrusted values into SQL elsewhere in this codebase.

    Returns:
        SQL fragment that, when used in a query, normalizes the column.
    """
    return (
        "lower(regexp_replace(translate(coalesce("
        f"{column_sql}, ''),"
        " 'áàâäãåÁÀÂÄÃÅéèêëÉÈÊËíìîïÍÌÎÏóòôöõÓÒÔÖÕúùûüÚÙÛÜñÑçÇ',"
        " 'aaaaaaAAAAAAeeeeEEEEiiiiIIIIoooooOOOOOuuuuUUUUnNcC'),"
        " '[^a-zA-Z0-9 ]', '', 'g'))"
    )


def tier3_match_sql() -> str:
    """Tier 3 fuzzy match — find a near-duplicate canonical location.

    Runs after reconciler Tier 1 (~11m strict coord) and Tier 2 (~165m
    + exact-name OR same-org) both miss. Catches the "two scrapers,
    different name AND different org, same physical pantry" case.

    The query expects these bind parameters:
      * `lat1`, `lon1`        — incoming location's coordinates
      * `loose_deg`           — distance ceiling in SRID-4326 degrees
      * `name`                — incoming name (may be None / empty)
      * `addr_1`              — incoming address_1 (may be None / empty)
      * `zip5`                — first 5 chars of incoming postal_code
      * `name_sim`            — trigram name similarity floor
      * `addr_sim`            — trigram address similarity floor

    The `verified_by` exemption (Principle VI) is hard-coded as a
    literal IN-list rather than a bind param because the exempt tiers
    are an invariant of the merge_strategy module — they can't be
    overridden per-call without breaking the data-quality contract.
    """
    name_fold_col = accent_fold_expr("l.name")
    name_fold_param = accent_fold_expr(":name")
    addr_fold_col = accent_fold_expr("a.address_1")
    addr_fold_param = accent_fold_expr(":addr_1")
    # The human-tier list comes from a module-level tuple of string
    # literals (`_HUMAN_VERIFIED_TIERS`), not user input. Ruff's S608
    # heuristic flags any f-string SQL but the same pattern is used by
    # `scripts/dedupe_same_org_locations.py` and was already
    # bandit-cleared on that script. Identical risk profile.
    human_tiers_csv = ", ".join(f"'{tier}'" for tier in _HUMAN_VERIFIED_TIERS)

    # Interpolated values are bind-param placeholders and a static
    # tuple of string literals (`_HUMAN_VERIFIED_TIERS`), never user
    # input. Same pattern as the bandit-cleared SQL builders in
    # `scripts/dedupe_same_org_locations.py`. The nosec/noqa on the
    # assignment line below is what bandit/ruff actually see.
    sql = f"""
        SELECT l.id
        FROM location l
        LEFT JOIN address a
            ON a.location_id = l.id AND a.address_type = 'physical'
        WHERE l.is_canonical = TRUE
          AND ABS(l.latitude  - :lat1) < :loose_deg
          AND ABS(l.longitude - :lon1) < :loose_deg
          AND ST_DWithin(
                ST_SetSRID(ST_MakePoint(CAST(l.longitude AS float8),
                                        CAST(l.latitude  AS float8)), 4326),
                ST_SetSRID(ST_MakePoint(:lon1, :lat1), 4326),
                :loose_deg
              )
          AND (l.verified_by IS NULL OR l.verified_by NOT IN ({human_tiers_csv}))
          AND (
                (
                    :name IS NOT NULL AND :name <> ''
                    AND similarity({name_fold_col}, {name_fold_param}) > :name_sim
                )
                OR (
                    :addr_1 IS NOT NULL AND :addr_1 <> ''
                    AND :zip5 IS NOT NULL
                    AND SUBSTR(a.postal_code, 1, 5) = :zip5
                    AND similarity({addr_fold_col}, {addr_fold_param}) > :addr_sim
                )
          )
        ORDER BY ABS(l.latitude - :lat1) + ABS(l.longitude - :lon1)
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    """  # noqa: S608  # nosec B608 - bind params and a static tuple of literals
    return sql
