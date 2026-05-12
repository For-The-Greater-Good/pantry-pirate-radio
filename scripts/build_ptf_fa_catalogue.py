#!/usr/bin/env python3
"""Build the PTF FA catalogue JSON used by /api/v1/partners/ptf/locations.

Fetches the Feeding America "GetAllOrganizations" endpoint and writes a
slim catalogue keyed by fa_org_id with the fields the PTF response
exposes: name, state, find_food_url, url_slug, is_affiliate.

Notes:
- The "GetAllOrganizations" feed only lists full member banks. Affiliate
  org records (PDOs) live behind a different endpoint and are not
  fetched here. Every entry written has `is_affiliate: False` and lacks
  `parent_org_id` / `parent_name`. The runtime transformer treats those
  fields as optional in the FA response block.
- A `_metadata` row is written alongside the entries so operators can
  see when the catalogue was last refreshed without parsing every entry.

Run inside the app container:
    ./bouy exec app python scripts/build_ptf_fa_catalogue.py

Idempotent. Overwrites
app/api/v1/partners/ptf/data/feeding_america_catalogue.json on success.

Exit codes:
- 0: success
- 1: network / HTTP error fetching the FA API
- 2: parse / shape error in the response
- 3: sanity-floor tripped (fewer than the expected number of orgs);
     refused to overwrite the existing committed catalogue
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "api"
    / "v1"
    / "partners"
    / "ptf"
    / "data"
    / "feeding_america_catalogue.json"
)

API_URL = "https://www.feedingamerica.org/ws-api/GetAllOrganizations"
API_FIELDS = ",".join(
    [
        "OrganizationID",
        "FullName",
        "MailAddress",
        "Drupal",
        "URL",
        "AgencyURL",
    ]
)
USER_AGENT = (
    "Mozilla/5.0 (compatible; PantryPirateRadio/1.0; "
    "+https://github.com/For-The-Greater-Good/pantry-pirate-radio)"
)

# Feeding America has ~200 member banks. If we get fewer than this,
# something's wrong (schema drift, partial API outage, geo-block) and we
# refuse to overwrite the committed catalogue.
MIN_EXPECTED_ORGS = 100


def _slug(value: str | None) -> str | None:
    if not value:
        return None
    s = value.strip().lower()
    s = re.sub(r"https?://(www\.)?", "", s)
    s = s.split("/")[-1] or s
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or None


def fetch() -> list[dict]:
    """Hit the FA API. Raises subclasses of urllib.error.URLError on
    network / HTTP failure, ValueError on bad JSON, and KeyError-style
    failures on unexpected shape."""
    url = API_URL + "?" + urllib.parse.urlencode({"orgFields": API_FIELDS})
    # URL is a hard-coded https:// constant — schemes are not user-driven.
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310  # nosec B310
        data = json.loads(resp.read())
    if not isinstance(data, dict):
        raise ValueError(f"FA API returned non-object root: {type(data).__name__}")
    orgs = data.get("Organization")
    if not isinstance(orgs, list):
        raise ValueError(
            "FA API response missing 'Organization' list — schema may have "
            f"drifted (top-level keys: {list(data.keys())})"
        )
    return orgs


def build_entry(org: dict) -> dict | None:
    org_id = org.get("OrganizationID")
    name = (org.get("FullName") or "").strip()
    if org_id is None or not name:
        return None
    mail = org.get("MailAddress") or {}
    drupal = org.get("Drupal") or {}
    entry: dict = {"id": int(org_id), "name": name}
    if mail.get("State"):
        entry["state"] = mail["State"]
    if org.get("AgencyURL"):
        entry["find_food_url"] = org["AgencyURL"]
    drupal_path = drupal.get("Path") if isinstance(drupal, dict) else None
    slug = _slug(drupal_path) or _slug(org.get("URL"))
    if slug:
        entry["url_slug"] = slug
    # See module docstring — full member banks only; no affiliate fields.
    entry["is_affiliate"] = False
    return entry


def main() -> int:
    try:
        orgs = fetch()
    except (urllib.error.URLError, TimeoutError) as exc:
        print(
            f"FA API fetch failed (network/HTTP): {exc}. "
            "Try again later or run from a different IP if rate-limited.",
            file=sys.stderr,
        )
        return 1
    except (json.JSONDecodeError, ValueError) as exc:
        print(
            f"FA API response parse failed: {exc}. "
            "The 'GetAllOrganizations' shape may have changed; "
            "inspect manually with curl before regenerating.",
            file=sys.stderr,
        )
        return 2

    catalogue: dict[str, dict] = {}
    missing_slug = 0
    for org in orgs:
        entry = build_entry(org)
        if entry is None:
            continue
        if "url_slug" not in entry:
            missing_slug += 1
        catalogue[str(entry["id"])] = entry

    if len(catalogue) < MIN_EXPECTED_ORGS:
        print(
            f"REFUSING to overwrite: got {len(catalogue)} orgs from FA API, "
            f"expected at least {MIN_EXPECTED_ORGS}. Either the API is "
            "broken or our parsing is. Existing committed catalogue is "
            "untouched.",
            file=sys.stderr,
        )
        return 3

    if missing_slug:
        print(
            f"WARNING: {missing_slug} orgs had no derivable url_slug. "
            "If this count is growing, FA may have renamed Drupal.Path."
        )

    sorted_catalogue = dict(sorted(catalogue.items(), key=lambda kv: int(kv[0])))
    # Prepend a _metadata entry so operators can detect stale snapshots
    # without parsing every entry. JSON object key order is preserved
    # by Python's dict; we explicitly put _metadata first.
    output = {
        "_metadata": {
            "generated_at": dt.datetime.now(dt.UTC).isoformat(
                timespec="seconds"
            ),
            "source": "Feeding America GetAllOrganizations",
            "entry_count": len(sorted_catalogue),
        },
        **sorted_catalogue,
    }
    OUT_PATH.write_text(json.dumps(output, indent=2, sort_keys=False))
    print(f"wrote {len(sorted_catalogue)} food banks to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
