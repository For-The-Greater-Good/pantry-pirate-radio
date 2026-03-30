"""Schema.org JSON-LD structured data builders for SEO."""

from __future__ import annotations

import json
from typing import Any

from .models import LocationDetail, OrgDetail

# Day abbreviation mapping for OpeningHoursSpecification
_DAY_MAP = {
    "MO": "Monday", "TU": "Tuesday", "WE": "Wednesday",
    "TH": "Thursday", "FR": "Friday", "SA": "Saturday", "SU": "Sunday",
}


def build_location_jsonld(location: LocationDetail) -> str:
    """Build FoodEstablishment JSON-LD for a location page."""
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "FoodEstablishment",
        "name": location.name,
        "url": location.url,
    }

    if location.description:
        data["description"] = location.description

    if location.address_1 and location.city and location.state:
        data["address"] = {
            "@type": "PostalAddress",
            "streetAddress": location.address_1,
            "addressLocality": location.city,
            "addressRegion": location.state,
            "postalCode": location.postal_code or "",
            "addressCountry": "US",
        }

    if location.latitude and location.longitude:
        data["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": location.latitude,
            "longitude": location.longitude,
        }

    if location.phone:
        data["telephone"] = location.phone

    if location.email:
        data["email"] = location.email

    if location.website:
        data["sameAs"] = location.website

    # Opening hours
    hours_specs = _build_opening_hours(location)
    if hours_specs:
        data["openingHoursSpecification"] = hours_specs

    return json.dumps(data, indent=2)


def build_org_jsonld(org: OrgDetail) -> str:
    """Build Organization JSON-LD for an org hub page."""
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": org.name,
        "url": org.url,
    }

    if org.description:
        data["description"] = org.description

    if org.email:
        data["email"] = org.email

    if org.website:
        data["sameAs"] = org.website

    if org.locations:
        data["location"] = [
            {
                "@type": "Place",
                "name": loc.name,
                "url": loc.url,
            }
            for loc in org.locations
        ]

    return json.dumps(data, indent=2)


def build_breadcrumbs(crumbs: list[tuple[str, str]]) -> str:
    """Build BreadcrumbList JSON-LD from (name, url) tuples."""
    items = []
    for i, (name, url) in enumerate(crumbs, start=1):
        items.append({
            "@type": "ListItem",
            "position": i,
            "name": name,
            "item": url,
        })

    data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": items,
    }

    return json.dumps(data, indent=2)


def _build_opening_hours(location: LocationDetail) -> list[dict[str, Any]]:
    """Convert schedules to OpeningHoursSpecification entries."""
    specs = []
    for sched in location.schedules:
        if not sched.opens_at or not sched.closes_at:
            continue

        days = []
        if sched.byday:
            for abbrev in sched.byday.split(","):
                full = _DAY_MAP.get(abbrev.strip().upper())
                if full:
                    days.append(full)

        if not days:
            continue

        spec: dict[str, Any] = {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": days,
            "opens": sched.opens_at,
            "closes": sched.closes_at,
        }

        if sched.description:
            spec["description"] = sched.description

        specs.append(spec)

    return specs
