#!/usr/bin/env python
"""Script to generate GitLab CI jobs for each scraper."""

import json
import sys
import yaml
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
        if name != "__init__" and not name.startswith(
            "test_"
        ):  # Skip __init__.py and test files
            scrapers.append(name)

    return sorted(scrapers)


def generate_scraper_jobs() -> dict:
    """Generate GitLab CI jobs for each scraper.

    Returns:
        Dictionary containing GitLab CI jobs
    """
    scrapers = list_available_scrapers()
    jobs = {}

    # Create a job for each scraper
    for scraper in scrapers:
        job_name = f"test-scraper-{scraper}"
        jobs[job_name] = {
            "stage": "test",
            "extends": ".test-setup",
            "script": [
                "mkdir -p outputs",
                f"poetry run python -m app.scraper.test_scrapers {scraper} --output outputs/scraper_{scraper}_test.json",
            ],
            "artifacts": {
                "paths": [f"outputs/scraper_{scraper}_test.json"],
                "expire_in": "1 week",
            },
            "allow_failure": True,
            "when": "manual",
        }

    return jobs


if __name__ == "__main__":
    # Generate jobs
    jobs = generate_scraper_jobs()

    # Output as YAML
    print(yaml.dump(jobs, sort_keys=False))

    # If output file is specified, write to file
    if len(sys.argv) > 1:
        output_file = Path(sys.argv[1])
        output_file.write_text(yaml.dump(jobs, sort_keys=False))
        print(f"Generated CI jobs written to {output_file}")
