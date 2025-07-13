"""Main entry point for the Datasette exporter service."""

import logging
import os
import sys

from app.datasette.scheduler import get_interval_from_env, scheduled_export

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def main():
    """Run the Datasette exporter service."""
    logger.info("Starting Datasette exporter service")

    # Get configuration from environment
    output_dir = os.environ.get("OUTPUT_DIR", "/data")
    interval = get_interval_from_env()

    logger.info(f"Export interval: {interval} seconds")
    logger.info(f"Output directory: {output_dir}")

    # Run the scheduler
    scheduled_export(output_dir=output_dir, interval_seconds=interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Exporter service stopped by user")
    except Exception as e:
        logger.error(f"Exporter service failed: {e}", exc_info=True)
        sys.exit(1)
