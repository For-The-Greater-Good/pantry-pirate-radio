"""FANO allowlist — scrapers whose presence on a location qualifies it as a
Feeding America Network Organization affiliate.

The allowlist is loaded once at module import from the TSV that ships with
the package (`fano_allowlist.tsv`). The TSV columns are `category` (any
non-empty value is admitted — `fa`, `fa-spine`, `?` for human review), and
`scraper_id`. Only `scraper_id` is consumed by this module; the other
columns are kept for human review.

Failure posture (Constitution VI + XI): the TSV is data critical to the
public PTF endpoint's FA enrichment contract. A corrupted, empty, or
silently-renamed-column TSV must crash at import time rather than serve
a degraded allowlist — an empty allowlist would produce a SQL syntax
error (`IN ()`) on every PTF request, and a partial allowlist would
silently miss-classify locations as non-FA. Loud-at-startup is correct.

Constitution VII (Security): the file is bundled in the package and read
once at process start; no per-request file I/O, no string interpolation
of allowlist members into SQL — see `locations_queries.py` for the
`bindparam(expanding=True)` usage.
"""

from __future__ import annotations

import csv
from pathlib import Path

_TSV_PATH = Path(__file__).with_name("fano_allowlist.tsv")


def _load() -> frozenset[str]:
    """Load FANO_ALLOWLIST from the bundled TSV.

    Raises RuntimeError loudly if the TSV is missing required columns, has
    any empty `scraper_id` cell, or produces an empty allowlist. The
    `utf-8-sig` encoding strips a possible BOM so a Windows-edited TSV
    doesn't silently corrupt the header row.
    """
    with _TSV_PATH.open(encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if reader.fieldnames is None or "scraper_id" not in reader.fieldnames:
            raise RuntimeError(
                f"fano_allowlist.tsv missing required 'scraper_id' column; "
                f"found columns: {reader.fieldnames!r}"
            )
        ids: set[str] = set()
        for row_num, row in enumerate(reader, start=2):  # +1 for header, +1 for 1-index
            sid = (row.get("scraper_id") or "").strip()
            if not sid:
                raise RuntimeError(
                    f"fano_allowlist.tsv row {row_num} has empty scraper_id: {row!r}"
                )
            ids.add(sid)
    if not ids:
        raise RuntimeError(
            f"fano_allowlist.tsv produced an empty allowlist at {_TSV_PATH}; "
            "the PTF endpoint would 500 with SQL syntax error 'IN ()' on every request"
        )
    return frozenset(ids)


FANO_ALLOWLIST: frozenset[str] = _load()
