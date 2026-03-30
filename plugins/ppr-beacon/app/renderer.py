"""Jinja2 rendering engine for beacon static pages."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote

import structlog
from jinja2 import Environment, FileSystemLoader

from .models import LocationDetail, LocationSummary, OrgDetail
from .schema_org import build_breadcrumbs, build_location_jsonld, build_org_jsonld
from .slug import state_full_name

log = structlog.get_logger()

# Day display names
_DAY_DISPLAY = {
    "MO": "Mon", "TU": "Tue", "WE": "Wed",
    "TH": "Thu", "FR": "Fri", "SA": "Sat", "SU": "Sun",
}


class BeaconRenderer:
    """Renders Jinja2 templates for beacon static pages."""

    def __init__(self, template_dir: str, base_url: str, analytics_endpoint: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.analytics_endpoint = analytics_endpoint
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True,
        )
        self._register_filters()
        self._register_globals()

    def _register_filters(self) -> None:
        """Register custom Jinja2 filters."""
        self.env.filters["format_phone"] = _format_phone
        self.env.filters["format_hours"] = _format_hours
        self.env.filters["format_days"] = _format_days
        self.env.filters["maps_url"] = _maps_url
        self.env.filters["tel_url"] = _tel_url
        self.env.filters["trust_badge"] = _trust_badge

    def _register_globals(self) -> None:
        """Register global functions available in all templates."""
        from .slug import city_slug as _city_slug
        from .slug import state_slug as _state_slug

        self.env.globals["state_slug"] = _state_slug
        self.env.globals["city_slug"] = _city_slug
        self.env.globals["state_full_name"] = state_full_name

    def _common_ctx(self) -> dict[str, Any]:
        """Common template context."""
        return {
            "base_url": self.base_url,
            "analytics_endpoint": self.analytics_endpoint,
        }

    def render_location(self, location: LocationDetail) -> str:
        """Render a location detail page."""
        from .slug import city_slug, state_slug

        st_slug = state_slug(location.state or "")
        ct_slug = city_slug(location.city or "")
        st_full = state_full_name(location.state or "")
        crumbs = [
            ("Home", self.base_url),
            (st_full, f"{self.base_url}/{st_slug}"),
            (location.city or "", f"{self.base_url}/{st_slug}/{ct_slug}"),
            (location.name, location.url),
        ]
        template = self.env.get_template("location.html")
        return template.render(
            **self._common_ctx(),
            location=location,
            state_full=st_full,
            jsonld_location=build_location_jsonld(location),
            jsonld_breadcrumbs=build_breadcrumbs(crumbs),
            page_title=f"{location.name} | Food Pantry in {location.city}, {location.state}",
            page_description=_build_meta_description(location),
            canonical_url=location.url,
        )

    def render_city(
        self, city: str, state: str, locations: list[LocationSummary]
    ) -> str:
        """Render a city listing page."""
        from .slug import city_slug, state_slug

        url = f"{self.base_url}/{state_slug(state)}/{city_slug(city)}"
        crumbs = [
            ("Home", self.base_url),
            (state_full_name(state), f"{self.base_url}/{state_slug(state)}"),
            (city, url),
        ]
        template = self.env.get_template("city.html")
        return template.render(
            **self._common_ctx(),
            city=city,
            state=state,
            state_full=state_full_name(state),
            locations=locations,
            jsonld_breadcrumbs=build_breadcrumbs(crumbs),
            page_title=f"Food Pantries in {city}, {state}",
            page_description=(
                f"Find {len(locations)} verified food pantries in {city}, {state}. "
                f"Get addresses, hours, phone numbers, and directions."
            ),
            canonical_url=url,
        )

    def render_state(
        self,
        state: str,
        cities: list[dict[str, Any]],
        total_locations: int,
    ) -> str:
        """Render a state listing page."""
        from .slug import state_slug

        url = f"{self.base_url}/{state_slug(state)}"
        full = state_full_name(state)
        crumbs = [
            ("Home", self.base_url),
            (full, url),
        ]
        template = self.env.get_template("state.html")
        return template.render(
            **self._common_ctx(),
            state=state,
            state_full=full,
            cities=cities,
            total_locations=total_locations,
            jsonld_breadcrumbs=build_breadcrumbs(crumbs),
            page_title=f"Food Pantries in {full}",
            page_description=(
                f"Find {total_locations} verified food pantries across "
                f"{len(cities)} cities in {full}."
            ),
            canonical_url=url,
        )

    def render_home(self, states: list[dict[str, Any]], total_locations: int) -> str:
        """Render the homepage."""
        crumbs = [("Home", self.base_url)]
        template = self.env.get_template("home.html")
        return template.render(
            **self._common_ctx(),
            states=states,
            total_locations=total_locations,
            jsonld_breadcrumbs=build_breadcrumbs(crumbs),
            page_title="Find a Food Pantry Near You | Plentiful",
            page_description=(
                f"Search {total_locations} verified food pantries across the US. "
                f"Get addresses, hours, and directions to food assistance near you."
            ),
            canonical_url=self.base_url,
        )

    def render_org(self, org: OrgDetail) -> str:
        """Render an organization hub page."""
        crumbs = [
            ("Home", self.base_url),
            (org.name, org.url),
        ]
        template = self.env.get_template("organization.html")
        return template.render(
            **self._common_ctx(),
            org=org,
            jsonld_org=build_org_jsonld(org),
            jsonld_breadcrumbs=build_breadcrumbs(crumbs),
            page_title=f"{org.name} | Food Pantry Locations",
            page_description=(
                f"{org.name} operates {len(org.locations)} verified food pantry "
                f"locations. Find addresses, hours, and contact information."
            ),
            canonical_url=org.url,
        )


# ---- Template filters ----


def _format_phone(number: str | None) -> str:
    """Format phone number for display."""
    if not number:
        return ""
    digits = re.sub(r"[^\d]", "", number)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return number


def _tel_url(number: str | None) -> str:
    """Format phone number as tel: URL."""
    if not number:
        return ""
    digits = re.sub(r"[^\d]", "", number)
    return f"tel:+1{digits}" if len(digits) == 10 else f"tel:{digits}"


def _format_hours(schedule: Any) -> str:
    """Format a schedule entry for display."""
    if not schedule:
        return ""
    parts = []
    if schedule.opens_at and schedule.closes_at:
        parts.append(f"{schedule.opens_at} - {schedule.closes_at}")
    if schedule.description:
        parts.append(schedule.description)
    return " | ".join(parts) if parts else ""


def _format_days(byday: str | None) -> str:
    """Format day abbreviations for display."""
    if not byday:
        return ""
    days = [_DAY_DISPLAY.get(d.strip().upper(), d.strip()) for d in byday.split(",")]
    return ", ".join(days)


def _maps_url(location: Any) -> str:
    """Build Google Maps directions URL."""
    if not location:
        return ""
    parts = []
    if hasattr(location, "address_1") and location.address_1:
        parts.append(location.address_1)
    if hasattr(location, "city") and location.city:
        parts.append(location.city)
    if hasattr(location, "state") and location.state:
        parts.append(location.state)
    if hasattr(location, "postal_code") and location.postal_code:
        parts.append(location.postal_code)
    query = ", ".join(parts)
    return f"https://www.google.com/maps/dir/?api=1&destination={quote(query)}"


def _trust_badge(location: Any) -> str:
    """Return trust badge text based on verification status."""
    if not location:
        return ""
    vb = getattr(location, "verified_by", None)
    if vb == "source":
        return "Verified by Provider"
    if vb == "admin":
        return "Admin Verified"
    return ""


def _build_meta_description(location: LocationDetail) -> str:
    """Build meta description for a location page."""
    parts = [location.name]
    if location.city and location.state:
        parts.append(f"in {location.city}, {location.state}")
    if location.phone:
        parts.append(f"Phone: {_format_phone(location.phone)}")
    if location.schedules:
        parts.append("Hours and directions available")
    return ". ".join(parts) + "."
