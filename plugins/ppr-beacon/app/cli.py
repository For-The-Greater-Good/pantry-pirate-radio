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
            log.info("build_single_complete", path=path)
        else:
            log.error("location_not_eligible", location_id=args.location)
            sys.exit(1)
    else:
        stats = builder.build_all()
        log.info(
            "build_complete",
            locations=stats.locations,
            cities=stats.cities,
            states=stats.states,
            orgs=stats.orgs,
            total_pages=stats.pages_total,
        )


def _cmd_status() -> None:
    """Show build status."""
    config = BeaconConfig()
    output = Path(config.output_dir)

    if not output.exists():
        log.warning("no_build_output", output_dir=str(output))
        return

    html_files = list(output.rglob("*.html"))
    sitemap = output / "sitemap.xml"

    log.info(
        "build_status",
        output_dir=str(output),
        html_pages=len(html_files),
        sitemap_exists=sitemap.exists(),
    )


if __name__ == "__main__":
    main()
