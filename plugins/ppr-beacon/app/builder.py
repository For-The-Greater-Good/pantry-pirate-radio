"""Orchestrator: query database → render templates → write static files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import structlog

from .config import BeaconConfig
from .data_source import (
    get_all_states,
    get_cities_in_state,
    get_connection,
    get_eligible_locations,
    get_location_detail,
    get_locations_in_city,
    get_org_detail,
)
from .renderer import BeaconRenderer
from .sitemap import generate_robots, generate_sitemap, now_iso
from .slug import city_slug, state_slug

log = structlog.get_logger()


@dataclass
class BuildStats:
    """Statistics from a build run."""

    locations: int = 0
    cities: int = 0
    states: int = 0
    orgs: int = 0
    pages_total: int = 0


class BeaconBuilder:
    """Orchestrates the full static site build."""

    def __init__(self, config: BeaconConfig, renderer: BeaconRenderer):
        self.config = config
        self.renderer = renderer
        self.output_dir = Path(config.output_dir)

    def build_all(self) -> BuildStats:
        """Full rebuild: all eligible locations + index pages."""
        stats = BuildStats()
        conn = get_connection(self.config)
        sitemap_pages: list[dict] = []
        base_url = self.config.base_url.rstrip("/")

        try:
            # 1. Get eligible locations
            eligible = get_eligible_locations(conn, self.config)
            log.info("beacon_build_start", eligible_count=len(eligible))

            # 2. Build location pages
            seen_orgs: set[str] = set()
            state_city_map: dict[str, set[str]] = {}

            for loc_info in eligible:
                detail = get_location_detail(conn, loc_info["id"], self.config)
                if not detail:
                    continue

                html = self.renderer.render_location(detail)
                path = self._location_path(detail.state or "", detail.city or "", detail.slug)
                self._write(path, html)
                stats.locations += 1

                sitemap_pages.append({
                    "url": detail.url,
                    "lastmod": now_iso(),
                    "priority": "0.8",
                })

                # Track state/city/org
                if detail.state:
                    state_city_map.setdefault(detail.state, set())
                    if detail.city:
                        state_city_map[detail.state].add(detail.city)
                if detail.organization_id:
                    seen_orgs.add(detail.organization_id)

            # 3. Build city pages
            for state, cities in state_city_map.items():
                for city_name in sorted(cities):
                    locations = get_locations_in_city(conn, state, city_name, self.config)
                    html = self.renderer.render_city(city_name, state, locations)
                    path = f"{state_slug(state)}/{city_slug(city_name)}/index.html"
                    self._write(path, html)
                    stats.cities += 1

                    sitemap_pages.append({
                        "url": f"{base_url}/{state_slug(state)}/{city_slug(city_name)}",
                        "lastmod": now_iso(),
                        "priority": "0.6",
                    })

            # 4. Build state pages
            states = get_all_states(conn, self.config)
            for st in states:
                cities = get_cities_in_state(conn, st.state, self.config)
                city_dicts = [{"name": c.city, "slug": c.slug, "count": c.location_count} for c in cities]
                html = self.renderer.render_state(
                    st.state, city_dicts, st.location_count
                )
                path = f"{st.slug}/index.html"
                self._write(path, html)
                stats.states += 1

                sitemap_pages.append({
                    "url": f"{base_url}/{st.slug}",
                    "lastmod": now_iso(),
                    "priority": "0.7",
                })

            # 5. Build org pages
            for org_id in seen_orgs:
                org = get_org_detail(conn, org_id, self.config)
                if not org or not org.locations:
                    continue
                html = self.renderer.render_org(org)
                path = f"org/{org.slug}/index.html"
                self._write(path, html)
                stats.orgs += 1

                sitemap_pages.append({
                    "url": org.url,
                    "lastmod": now_iso(),
                    "priority": "0.5",
                })

            # 6. Build homepage
            state_dicts = [
                {"name": s.state_full, "slug": s.slug, "count": s.location_count, "cities": s.city_count}
                for s in states
            ]
            total = sum(s.location_count for s in states)
            html = self.renderer.render_home(state_dicts, total)
            self._write("index.html", html)

            sitemap_pages.append({
                "url": base_url,
                "lastmod": now_iso(),
                "priority": "1.0",
                "changefreq": "daily",
            })

            # 7. Sitemap + robots.txt
            self._write("sitemap.xml", generate_sitemap(sitemap_pages, base_url))
            self._write("robots.txt", generate_robots(base_url))

            stats.pages_total = (
                stats.locations + stats.cities + stats.states + stats.orgs + 3
            )  # +3 = home + sitemap + robots

        finally:
            conn.close()

        log.info(
            "beacon_build_complete",
            locations=stats.locations,
            cities=stats.cities,
            states=stats.states,
            orgs=stats.orgs,
            total_pages=stats.pages_total,
        )
        return stats

    def build_location(self, location_id: str) -> str | None:
        """Build a single location page (for preview)."""
        conn = get_connection(self.config)
        try:
            detail = get_location_detail(conn, location_id, self.config)
            if not detail:
                log.warning("location_not_found", location_id=location_id)
                return None
            html = self.renderer.render_location(detail)
            path = self._location_path(detail.state or "", detail.city or "", detail.slug)
            self._write(path, html)
            return str(self.output_dir / path)
        finally:
            conn.close()

    def _location_path(self, state: str, city: str, slug: str) -> str:
        """Build filesystem path for a location page."""
        return f"{state_slug(state)}/{city_slug(city)}/{slug}/index.html"

    def _write(self, rel_path: str, content: str) -> None:
        """Write content to output directory."""
        full = self.output_dir / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
