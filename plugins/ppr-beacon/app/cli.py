"""CLI entrypoint for beacon build/serve/status."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import structlog

from .builder import BeaconBuilder
from .config import BeaconConfig
from .renderer import BeaconRenderer

log = structlog.get_logger()


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="ppr-beacon static site generator")
    subparsers = parser.add_subparsers(dest="command")

    # build
    build_parser = subparsers.add_parser("build", help="Generate static pages")
    build_parser.add_argument("--location", help="Build single location by ID")
    build_parser.add_argument("--state", help="Build all locations in a state")

    # status
    subparsers.add_parser("status", help="Show build statistics")

    args = parser.parse_args()

    if args.command == "build":
        _cmd_build(args)
    elif args.command == "status":
        _cmd_status()
    else:
        parser.print_help()
        sys.exit(1)


def _cmd_build(args: argparse.Namespace) -> None:
    """Run the build."""
    config = BeaconConfig()
    template_dir = str(Path(__file__).parent.parent / "templates")
    renderer = BeaconRenderer(
        template_dir=template_dir,
        base_url=config.base_url,
        analytics_endpoint=config.analytics_endpoint,
    )
    builder = BeaconBuilder(config, renderer)

    if args.location:
        path = builder.build_location(args.location)
        if path:
            print(f"Built: {path}")
        else:
            print(f"Location {args.location} not found or not eligible")
            sys.exit(1)
    else:
        stats = builder.build_all()
        print(
            f"Build complete: {stats.locations} locations, "
            f"{stats.cities} cities, {stats.states} states, "
            f"{stats.orgs} orgs ({stats.pages_total} total pages)"
        )


def _cmd_status() -> None:
    """Show build status."""
    config = BeaconConfig()
    output = Path(config.output_dir)

    if not output.exists():
        print("No build output found. Run 'beacon build' first.")
        return

    html_files = list(output.rglob("*.html"))
    sitemap = output / "sitemap.xml"

    print(f"Output directory: {output}")
    print(f"HTML pages: {len(html_files)}")
    print(f"Sitemap: {'exists' if sitemap.exists() else 'missing'}")

    if html_files:
        newest = max(html_files, key=lambda f: f.stat().st_mtime)
        print(f"Last modified: {newest.name}")


if __name__ == "__main__":
    main()
