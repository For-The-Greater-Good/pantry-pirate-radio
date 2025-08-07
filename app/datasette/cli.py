"""Command-line interface for PostgreSQL to SQLite exporter."""

import logging
import sys

import click

from app.datasette.exporter import export_to_sqlite


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


if __name__ == "__main__":
    cli()
