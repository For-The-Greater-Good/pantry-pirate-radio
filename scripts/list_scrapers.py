#!/usr/bin/env python
"""Script to list all available scrapers in JSON format for CI/CD."""

import json
import sys
from pathlib import Path


def list_available_scrapers() -> list[str]:
    """List all available scrapers in the app/scraper directory.

    Returns:
        List of scraper names (without '_scraper.py' suffix)
    """
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    scraper_dir = project_root / "app" / "scraper"

    scrapers: list[str] = []

    for file in scraper_dir.glob("*_scraper.py"):
        name = file.stem.replace("_scraper", "")
        if name != "__init__":  # Skip __init__.py
            scrapers.append(name)

    return sorted(scrapers)


if __name__ == "__main__":
    scrapers = list_available_scrapers()

    # Output as JSON
    print(json.dumps(scrapers))

    # Also output as GitLab CI compatible format if requested
    if len(sys.argv) > 1 and sys.argv[1] == "--gitlab-ci":
        print("\nGitLab CI parallel jobs:")
        for scraper in scrapers:
            print(f"  {scraper}: ['{scraper}']")
