"""Main entry point for the recorder service."""

import logging
import os
from pathlib import Path
from typing import Any

from redis import Redis
from rq import Connection, Worker

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)


def record_result(result_data: dict[str, Any]) -> dict[str, Any]:
    """Save job result to file system.

    Args:
        result_data: Job result data to save

    Returns:
        Dict with save results
    """
    try:
        # Get output directories from environment
        output_dir = Path(os.environ.get("OUTPUT_DIR", "outputs"))
        archive_dir = Path(os.environ.get("ARCHIVE_DIR", "archives"))

        # Save result using the function from utils
        from app.recorder.utils import record_result as utils_record_result

        utils_record_result(result_data)

        return {"status": "completed", "error": None}

    except Exception as e:
        logger.exception("Failed to save result")
        return {"status": "failed", "error": str(e)}


def main() -> None:
    """Run the recorder worker."""
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise KeyError("REDIS_URL environment variable not set")

    # Initialize Redis connection
    redis = Redis.from_url(redis_url)

    # Create queue
    with Connection(redis):
        worker = Worker(["recorder"])
        worker.work()


if __name__ == "__main__":
    main()
