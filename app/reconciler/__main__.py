"""Main entry point for reconciler service."""

import logging

from redis import Redis
from rq import Connection, Worker

from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the reconciler worker."""
    # Initialize Redis connection
    redis = Redis.from_url(settings.REDIS_URL)

    # Create queue
    with Connection(redis):
        # 10 minute timeout
        worker = Worker(["reconciler"], default_worker_ttl=600)
        logger.info("Starting reconciler worker...")
        worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
