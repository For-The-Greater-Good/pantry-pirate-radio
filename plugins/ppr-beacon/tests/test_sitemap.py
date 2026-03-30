"""Tests for sitemap and robots.txt generation."""

from app.sitemap import generate_robots, generate_sitemap


class TestGenerateSitemap:
    def test_basic(self):
        pages = [{"url": "https://example.com/page1", "priority": "0.8"}]
        xml = generate_sitemap(pages, "https://example.com")
        assert '<?xml version="1.0"' in xml
        assert "<loc>https://example.com/page1</loc>" in xml
        assert "<priority>0.8</priority>" in xml

    def test_multiple_pages(self):
        pages = [
            {"url": "https://example.com/a"},
            {"url": "https://example.com/b"},
        ]
        xml = generate_sitemap(pages, "https://example.com")
        assert xml.count("<url>") == 2

    def test_lastmod(self):
        pages = [{"url": "https://example.com", "lastmod": "2026-03-30"}]
        xml = generate_sitemap(pages, "https://example.com")
        assert "<lastmod>2026-03-30</lastmod>" in xml


class TestGenerateRobots:
    def test_content(self):
        txt = generate_robots("https://example.com")
        assert "User-agent: *" in txt
        assert "Allow: /" in txt
        assert "Sitemap: https://example.com/sitemap.xml" in txt
