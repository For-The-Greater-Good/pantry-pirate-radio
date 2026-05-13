"""FANO allowlist — scrapers whose presence on a location qualifies it as a
Feeding America Network Organization affiliate.

The allowlist is loaded once at module import from the TSV that ships with
the package (`fano_allowlist.tsv`). The TSV columns are `category`
(`fa` | `fa-spine`), `count` (point-in-time snapshot, ignored here), and
`scraper_id`. Only `scraper_id` is consumed by this module; the other
columns are kept for human review and use by the data-quality-map
exporter that shares this file.

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
    with _TSV_PATH.open() as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return frozenset(
            row["scraper_id"].strip()
            for row in reader
            if (row.get("scraper_id") or "").strip()
        )


FANO_ALLOWLIST: frozenset[str] = _load()
