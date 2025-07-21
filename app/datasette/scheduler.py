"""Scheduler for periodic PostgreSQL to SQLite exports."""

import logging
import os
import time
from datetime import datetime

from app.datasette.exporter import export_to_sqlite

logger = logging.getLogger(__name__)


def scheduled_export(
    output_dir: str = "/data",
    interval_seconds: int = 3600,
    filename_template: str = "pantry_pirate_radio_{timestamp}.sqlite",
    keep_latest_link: bool = True,
    max_files: int | None = 5,
) -> None:
    """
    Run the export on a schedule.

    Args:
        output_dir: Directory to store SQLite files
        interval_seconds: Time between exports in seconds
        filename_template: Template for output filenames
        keep_latest_link: Whether to maintain a "latest.sqlite" symlink
        max_files: Maximum number of export files to keep (None for unlimited)
    """
    os.makedirs(output_dir, exist_ok=True)

    while True:
        try:
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = filename_template.format(timestamp=timestamp)
            output_path = os.path.join(output_dir, filename)

            # Run the export
            logger.info(f"Starting scheduled export to {output_path}")
            export_to_sqlite(output_path=output_path)

            # Create/update "latest" symlink
            if keep_latest_link:
                latest_path = os.path.join(output_dir, "latest.sqlite")
                if os.path.exists(latest_path) and os.path.islink(latest_path):
                    os.remove(latest_path)
                os.symlink(output_path, latest_path)
                logger.info(f"Updated latest.sqlite link to point to {filename}")

            # Clean up old files if needed
            if max_files is not None and max_files > 0:
                cleanup_old_exports(
                    output_dir, max_files, filename_template.replace("{timestamp}", "*")
                )

            logger.info(
                f"Scheduled export completed. Next export in {interval_seconds} seconds"
            )

        except Exception as e:
            logger.error(f"Error during scheduled export: {e}", exc_info=True)

        # Wait for next interval
        time.sleep(interval_seconds)


def cleanup_old_exports(
    output_dir: str,
    keep_count: int = 5,
    file_pattern: str = "pantry_pirate_radio_*.sqlite",
) -> None:
    """
    Remove old export files, keeping only the most recent ones.

    Args:
        output_dir: Directory containing export files
        keep_count: Number of most recent files to keep
        file_pattern: Glob pattern to match export files
    """
    import glob

    # Get list of export files
    pattern = os.path.join(output_dir, file_pattern)
    files = glob.glob(pattern)

    # Sort by modification time (newest first)
    files.sort(key=os.path.getmtime, reverse=True)

    # Remove old files
    for old_file in files[keep_count:]:
        try:
            os.remove(old_file)
            logger.info(f"Removed old export file: {old_file}")
        except Exception as e:
            logger.error(f"Error removing old file {old_file}: {e}")


def get_interval_from_env() -> int:
    """
    Get export interval from environment variable or use default.

    Returns:
        Interval in seconds
    """
    try:
        return int(os.environ.get("EXPORT_INTERVAL", "3600"))
    except ValueError:
        logger.warning("Invalid EXPORT_INTERVAL, using default of 3600 seconds")
        return 3600
