#!/usr/bin/env python
"""Export PPR locations to a single CSV + manifest for the data-quality map.

Produces three artifacts in --out-dir (default `outputs/`):
  - data_quality_map_<YYYYMMDD>.csv      one row per included canonical location
  - data_quality_map_manifest.json       paths, counts, allow-list provenance
  - map.html                              copy of `scripts/data_quality_map.html`

A location is included iff at least one of its `location_source.scraper_id`
values appears in the allow-list TSV at `scripts/data_quality_map_scrapers.tsv`
(canonical FA spine + per-food-bank scrapers; non-FA aggregators are omitted).
Override the TSV with --classification.

Each row carries the QA fields the map's popup uses: confidence_score,
verified_by, validation_status, source_count, scrapers, missing_fields
(phone/email/website/hours), organization (operating org), and fa_food_banks
(joined from the `feeding_america_zip_coverage` ZIP crosswalk; pipe-delimited
when a ZIP is multi-served, e.g. NYC).

Run with the prod DB reachable. Locally this means tunnelling RDS Proxy via
SSM (see CLAUDE.md "Bastion / Ad-hoc DB Access") then running inside the app
container with DATABASE_URL pointed at host.docker.internal on the tunnel
port. Inside the prod VPC just run it directly.

Examples:
    ./bouy exec app python scripts/data_quality_map_export.py
    ./bouy exec app python scripts/data_quality_map_export.py --state NY
    ./bouy exec app python scripts/data_quality_map_export.py --min-confidence 70

To preview the map locally:
    cd outputs && python3 -m http.server 8765
    open http://localhost:8765/map.html

To re-publish the snapshot to S3 (semi-external share URL):
    aws s3 cp outputs/map.html                            \\
        s3://pantry-pirate-radio-exports-prod/sqlite-exports/data-quality-map/map.html \\
        --content-type text/html --cache-control "public, max-age=300"
    aws s3 cp outputs/data_quality_map_<date>.csv          \\
        s3://pantry-pirate-radio-exports-prod/sqlite-exports/data-quality-map/ \\
        --content-type text/csv --cache-control "public, max-age=3600"
    aws s3 cp outputs/data_quality_map_manifest.json       \\
        s3://pantry-pirate-radio-exports-prod/sqlite-exports/data-quality-map/ \\
        --content-type application/json --cache-control "public, max-age=300"
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import psycopg2
from psycopg2.extras import RealDictCursor


DEFAULT_CLASSIFICATION_PATH = Path(__file__).resolve().parent / "data_quality_map_scrapers.tsv"

# Fallback if no classification TSV is provided: anything not in this set is treated
# as included. Used only when the TSV is missing.
AGGREGATOR_SCRAPER_IDS: set[str] = {
    "the_food_pantries_org",
    "foodfinder_us",
    "food_helpline_org",
    "getfull_app_api",
    "portal_ingest",
}


def load_allowed_from_tsv(path: Path) -> set[str] | None:
    """Return the set of scraper_ids the TSV says to keep, or None if missing."""
    if not path.exists():
        return None
    allowed: set[str] = set()
    with path.open() as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            sid = (row.get("scraper_id") or "").strip()
            if sid:
                allowed.add(sid)
    return allowed

CSV_COLUMNS = [
    "name",
    "latitude",
    "longitude",
    "address",
    "city",
    "state",
    "postal_code",
    "organization",
    "fa_food_banks",
    "scrapers",
    "source_count",
    "confidence_score",
    "verified_by",
    "validation_status",
    "missing_fields",
    "geocoding_source",
    "submarine_status",
    "location_id",
]

GOOGLE_MY_MAPS_LAYER_LIMIT = 10_000


def get_connection_string() -> str:
    db_url = os.getenv("DATABASE_URL")
    if db_url and db_url.startswith("postgresql+psycopg2://"):
        return db_url.replace("postgresql+psycopg2://", "postgresql://")
    if db_url:
        return db_url
    host = os.getenv("POSTGRES_HOST", "db")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "pantry_pirate_radio")
    name = os.getenv("POSTGRES_DB", "pantry_pirate_radio")
    password = os.getenv("POSTGRES_PASSWORD", "")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


QUERY = """
WITH location_scrapers AS (
    SELECT
        location_id,
        ARRAY_AGG(DISTINCT scraper_id ORDER BY scraper_id) AS scraper_ids,
        COUNT(DISTINCT scraper_id) FILTER (
            WHERE source_type IS NULL OR source_type != 'submarine'
        ) AS source_count
    FROM location_source
    GROUP BY location_id
),
location_phones AS (
    SELECT DISTINCT location_id FROM phone WHERE location_id IS NOT NULL
),
location_emails AS (
    SELECT DISTINCT location_id
    FROM contact
    WHERE location_id IS NOT NULL
      AND email IS NOT NULL
      AND email <> ''
),
location_has_schedule AS (
    SELECT DISTINCT sal.location_id
    FROM service_at_location sal
    JOIN schedule s ON s.service_id = sal.service_id
    WHERE sal.location_id IS NOT NULL
      AND (s.opens_at IS NOT NULL OR s.closes_at IS NOT NULL OR s.byday IS NOT NULL)
),
zip_fa AS (
    -- Aggregate FA food banks per 5-digit ZIP (handles ZIP+4 in address.postal_code)
    SELECT zip, ARRAY_AGG(fa_org_name ORDER BY fa_org_name) AS fa_food_banks
    FROM feeding_america_zip_coverage
    GROUP BY zip
)
SELECT
    l.id AS location_id,
    l.latitude AS lat,
    l.longitude AS lng,
    l.name,
    a.address_1,
    a.city,
    a.state_province AS state,
    a.postal_code,
    o.name AS organization_name,
    COALESCE(l.confidence_score, 50) AS confidence_score,
    l.verified_by,
    COALESCE(l.validation_status, 'needs_review') AS validation_status,
    l.geocoding_source,
    l.submarine_last_status,
    ls.scraper_ids,
    COALESCE(ls.source_count, 0) AS source_count,
    (lp.location_id IS NOT NULL) AS has_phone,
    (le.location_id IS NOT NULL) AS has_email,
    (COALESCE(NULLIF(l.url, ''), NULLIF(o.website, '')) IS NOT NULL) AS has_website,
    (lhs.location_id IS NOT NULL) AS has_schedule,
    zf.fa_food_banks
FROM location l
LEFT JOIN address a ON a.location_id = l.id
LEFT JOIN organization o ON o.id = l.organization_id
LEFT JOIN location_scrapers ls ON ls.location_id = l.id
LEFT JOIN location_phones lp ON lp.location_id = l.id
LEFT JOIN location_emails le ON le.location_id = l.id
LEFT JOIN location_has_schedule lhs ON lhs.location_id = l.id
LEFT JOIN zip_fa zf ON zf.zip = LEFT(a.postal_code, 5)
WHERE l.latitude IS NOT NULL
  AND l.longitude IS NOT NULL
  AND l.latitude BETWEEN -90 AND 90
  AND l.longitude BETWEEN -180 AND 180
  AND NOT (l.latitude = 0 AND l.longitude = 0)
  AND l.is_canonical = true
  AND (l.validation_status IS NULL OR l.validation_status != 'rejected')
  {state_filter}
  {confidence_filter}
ORDER BY a.state_province, a.city, l.name
"""


def build_query(state: str | None, min_confidence: int | None) -> tuple[str, dict]:
    params: dict[str, object] = {}
    state_filter = ""
    if state:
        state_filter = "AND UPPER(a.state_province) = :state"
        params["state"] = state.upper().strip()
    confidence_filter = ""
    if min_confidence is not None:
        confidence_filter = "AND COALESCE(l.confidence_score, 50) >= :min_confidence"
        params["min_confidence"] = min_confidence
    sql = QUERY.format(state_filter=state_filter, confidence_filter=confidence_filter)
    # psycopg2 uses %(name)s, not :name — translate.
    for key in list(params.keys()):
        sql = sql.replace(f":{key}", f"%({key})s")
    return sql, params


def is_included(
    scraper_ids: Iterable[str] | None,
    allowed: set[str] | None,
    blocklist: set[str],
) -> bool:
    """Decide whether a location belongs on the map.

    If `allowed` is set (TSV-driven), keep the location iff at least one of
    its sources is in the allowed set. Otherwise, fall back to the legacy
    blocklist rule: drop only when every source is blocklisted.
    """
    ids = [s for s in (scraper_ids or []) if s]
    if allowed is not None:
        return any(s in allowed for s in ids) if ids else False
    if not ids:
        return True
    return not all(s in blocklist for s in ids)


def missing_fields_summary(row: dict, has_schedule: bool) -> str:
    missing: list[str] = []
    if not row.get("has_phone"):
        missing.append("phone")
    if not row.get("has_email"):
        missing.append("email")
    if not row.get("has_website"):
        missing.append("website")
    if not has_schedule:
        missing.append("hours")
    return ",".join(missing)


def format_address(row: dict) -> str:
    parts = [
        (row.get("address_1") or "").strip(),
        (row.get("city") or "").strip(),
        (row.get("state") or "").strip(),
        (row.get("postal_code") or "").strip(),
    ]
    return ", ".join(p for p in parts if p)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state", help="Filter to a single state (2-letter code, e.g. NY)")
    parser.add_argument(
        "--min-confidence",
        type=int,
        help="Only include locations with confidence_score >= this value (0-100)",
    )
    parser.add_argument(
        "--out-dir",
        default="outputs",
        help="Directory to write CSVs into (default: outputs/)",
    )
    parser.add_argument(
        "--classification",
        default=str(DEFAULT_CLASSIFICATION_PATH),
        help=(
            "Path to a TSV (category, count, scraper_id) listing scrapers to keep. "
            "Locations whose every source is missing from this file are dropped. "
            "If the file doesn't exist, falls back to the in-script aggregator blocklist."
        ),
    )
    parser.add_argument(
        "--extra-blocklist",
        default="",
        help="(Fallback mode only) Comma-separated scraper_ids to treat as aggregators",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.state and not (len(args.state) == 2 and args.state.isalpha()):
        print(f"Invalid --state value: {args.state!r}. Use a 2-letter code.", file=sys.stderr)
        return 2

    blocklist = set(AGGREGATOR_SCRAPER_IDS)
    for extra in args.extra_blocklist.split(","):
        extra = extra.strip()
        if extra:
            blocklist.add(extra)

    classification_path = Path(args.classification)
    allowed = load_allowed_from_tsv(classification_path)
    if allowed is not None:
        print(
            f"Classification: {classification_path} ({len(allowed)} scrapers allowed)",
            flush=True,
        )
    else:
        print(
            f"Classification TSV not found at {classification_path}; "
            f"falling back to in-script blocklist of {len(blocklist)} scraper_ids",
            flush=True,
        )

    sql, params = build_query(args.state, args.min_confidence)

    print(f"Connecting to {os.getenv('POSTGRES_HOST', 'db')}…", flush=True)
    conn = psycopg2.connect(get_connection_string())
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            db_rows = cur.fetchall()
    finally:
        conn.close()

    kept_rows: list[dict] = []
    excluded_count = 0
    scraper_counter: Counter[str] = Counter()
    excluded_scraper_counter: Counter[str] = Counter()

    for r in db_rows:
        scraper_ids = list(r.get("scraper_ids") or [])
        for s in scraper_ids:
            scraper_counter[s] += 1

        if not is_included(scraper_ids, allowed, blocklist):
            excluded_count += 1
            for s in scraper_ids:
                excluded_scraper_counter[s] += 1
            continue

        out_row = {
            "name": r["name"] or "",
            "latitude": float(r["lat"]),
            "longitude": float(r["lng"]),
            "address": format_address(r),
            "city": r.get("city") or "",
            "state": r.get("state") or "",
            "postal_code": r.get("postal_code") or "",
            "organization": r.get("organization_name") or "",
            "fa_food_banks": "|".join(r.get("fa_food_banks") or []),
            "scrapers": "|".join(scraper_ids),
            "source_count": int(r.get("source_count") or 0),
            "confidence_score": int(r.get("confidence_score") or 0),
            "verified_by": r.get("verified_by") or "",
            "validation_status": r.get("validation_status") or "",
            "missing_fields": missing_fields_summary(r, bool(r.get("has_schedule"))),
            "geocoding_source": r.get("geocoding_source") or "",
            "submarine_status": r.get("submarine_last_status") or "",
            "location_id": str(r["location_id"]),
        }
        kept_rows.append(out_row)

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d")
    out_dir = Path(args.out_dir)
    csv_path = out_dir / f"data_quality_map_{stamp}.csv"
    write_csv(csv_path, kept_rows)

    manifest = {
        "generated": now.isoformat(),
        "csv": csv_path.name,
        "count": len(kept_rows),
        "excluded": excluded_count,
        "filters": {
            "state": args.state.upper() if args.state else None,
            "min_confidence": args.min_confidence,
        },
        "classification_source": (
            str(classification_path) if allowed is not None else None
        ),
        "allowed_scrapers": sorted(allowed) if allowed is not None else None,
        "fallback_blocklist": sorted(blocklist) if allowed is None else None,
    }
    (out_dir / "data_quality_map_manifest.json").write_text(
        json.dumps(manifest, indent=2)
    )

    html_src = Path(__file__).with_suffix("").parent / "data_quality_map.html"
    html_dst = out_dir / "map.html"
    if html_src.exists():
        shutil.copyfile(html_src, html_dst)

    total = len(db_rows)
    print()
    print("=== Data-Quality Map Export ===")
    print(f"Total canonical locations with valid coords: {total}")
    print(f"  Kept: {len(kept_rows)}  -> {csv_path}")
    print(f"  Excluded: {excluded_count}")
    if args.state:
        print(f"Filter: state={args.state.upper()}")
    if args.min_confidence is not None:
        print(f"Filter: min_confidence={args.min_confidence}")

    print()
    print("Top 15 included scraper_ids:")
    for scraper_id, count in scraper_counter.most_common(15):
        is_allowed = allowed is None or scraper_id in allowed
        flag = "" if is_allowed else "  [EXCLUDED]"
        print(f"  {count:>7}  {scraper_id}{flag}")

    if excluded_scraper_counter:
        print()
        print("Top excluded scraper_ids (locations whose only sources were these):")
        for scraper_id, count in excluded_scraper_counter.most_common(8):
            print(f"  {count:>7}  {scraper_id}")

    if len(kept_rows) > GOOGLE_MY_MAPS_LAYER_LIMIT:
        print()
        print(
            f"NOTE: Google My Maps imports up to {GOOGLE_MY_MAPS_LAYER_LIMIT} rows per layer; "
            f"this CSV has {len(kept_rows)} rows. The bundled map.html has no such limit."
        )

    print()
    print("Self-hosted Plentiful-branded map:")
    print(f"  cd {out_dir} && python3 -m http.server 8765")
    print("  open http://localhost:8765/map.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
