"""Command-line interface for PostgreSQL to SQLite exporter."""

import logging
import sys

import click

from app.datasette.exporter import export_to_sqlite
from app.datasette.scheduler import get_interval_from_env, scheduled_export


@click.group()
def cli():
    """PostgreSQL to SQLite exporter for Datasette."""
    pass


@cli.command()
@click.option(
    "--output",
    "-o",
    default="pantry_pirate_radio.sqlite",
    help="Output SQLite file path",
)
@click.option(
    "--tables",
    "-t",
    multiple=True,
    help="Tables to export (can be used multiple times)",
)
@click.option(
    "--batch-size", "-b", default=1000, type=int, help="Batch size for processing rows"
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def export(output: str, tables: list[str], batch_size: int, verbose: bool):
    """Export PostgreSQL database to SQLite for Datasette."""
    # Configure logging
    log_level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Run the export
    tables_list = list(tables) if tables else None
    result = export_to_sqlite(output, tables_list, batch_size)
    click.echo(f"Export completed: {result}")


@cli.command()
@click.option(
    "--output-dir", "-d", default="/data", help="Directory to store SQLite files"
)
@click.option(
    "--interval",
    "-i",
    default=None,
    type=int,
    help="Time between exports in seconds (default: from EXPORT_INTERVAL env var or 3600)",
)
@click.option(
    "--filename-template",
    "-f",
    default="pantry_pirate_radio_{timestamp}.sqlite",
    help="Template for output filenames",
)
@click.option(
    "--keep-latest/--no-keep-latest",
    default=True,
    help="Whether to maintain a 'latest.sqlite' symlink",
)
@click.option(
    "--max-files",
    "-m",
    default=5,
    type=int,
    help="Maximum number of export files to keep (0 for unlimited)",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def schedule(
    output_dir: str,
    interval: int | None,
    filename_template: str,
    keep_latest: bool,
    max_files: int,
    verbose: bool,
):
    """Run the export on a schedule."""
    # Configure logging
    log_level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Get interval from environment if not specified
    if interval is None:
        interval = get_interval_from_env()

    click.echo(f"Starting scheduled export with {interval} second interval")
    click.echo(f"Output directory: {output_dir}")
    click.echo(f"Keeping latest link: {keep_latest}")
    click.echo(f"Maximum files to keep: {max_files if max_files > 0 else 'unlimited'}")

    # Run the scheduler
    scheduled_export(
        output_dir=output_dir,
        interval_seconds=interval,
        filename_template=filename_template,
        keep_latest_link=keep_latest,
        max_files=max_files if max_files > 0 else None,
    )


if __name__ == "__main__":
    cli()
