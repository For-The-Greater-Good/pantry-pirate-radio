"""XML sitemap and robots.txt generation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def generate_sitemap(pages: list[dict[str, Any]], base_url: str) -> str:
    """Generate XML sitemap from page metadata.

    Each page dict should have 'url' and optionally 'lastmod' and 'priority'.
    """
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    for page in pages:
        lines.append("  <url>")
        lines.append(f"    <loc>{page['url']}</loc>")
        if page.get("lastmod"):
            lines.append(f"    <lastmod>{page['lastmod']}</lastmod>")
        priority = page.get("priority", "0.5")
        lines.append(f"    <priority>{priority}</priority>")
        changefreq = page.get("changefreq", "weekly")
        lines.append(f"    <changefreq>{changefreq}</changefreq>")
        lines.append("  </url>")

    lines.append("</urlset>")
    return "\n".join(lines)


def generate_robots(base_url: str) -> str:
    """Generate robots.txt with sitemap reference."""
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )


def now_iso() -> str:
    """Current UTC datetime in ISO 8601 format for lastmod."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
