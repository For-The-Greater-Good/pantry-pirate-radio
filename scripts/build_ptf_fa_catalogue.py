#!/usr/bin/env python3
"""Build the PTF FA catalogue JSON used by /api/v1/partners/ptf/locations.

Fetches the Feeding America "GetAllOrganizations" endpoint and writes a
slim catalogue keyed by fa_org_id with only the fields exposed in the
PTF response: name, state, find_food_url, url_slug, is_affiliate,
parent_org_id, parent_name.

Run inside the app container:
    ./bouy exec app python scripts/build_ptf_fa_catalogue.py

Idempotent. Overwrites
app/api/v1/partners/ptf/data/feeding_america_catalogue.json.
"""

from __future__ import annotations

import json
import re
import sys
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


def _slug(value: str | None) -> str | None:
    if not value:
        return None
    s = value.strip().lower()
    s = re.sub(r"https?://(www\.)?", "", s)
    s = s.split("/")[-1] or s
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or None


def fetch() -> list[dict]:
    url = API_URL + "?" + urllib.parse.urlencode({"orgFields": API_FIELDS})
    # URL is a hard-coded https:// constant — schemes are not user-driven.
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310  # nosec B310
        data = json.loads(resp.read())
    return data.get("Organization", [])


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
    # The "GetAllOrganizations" feed lists full member banks; affiliates
    # come from a different endpoint we don't query here. is_affiliate
    # is set explicitly to False to make consumers' lives easy.
    entry["is_affiliate"] = False
    return entry


def main() -> int:
    orgs = fetch()
    catalogue: dict[str, dict] = {}
    for org in orgs:
        entry = build_entry(org)
        if entry is None:
            continue
        catalogue[str(entry["id"])] = entry

    catalogue = dict(sorted(catalogue.items(), key=lambda kv: int(kv[0])))
    OUT_PATH.write_text(json.dumps(catalogue, indent=2, sort_keys=True))
    print(f"wrote {len(catalogue)} food banks to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
