#!/usr/bin/env python3
"""Run RQ worker with Claude authentication management."""

import os
import sys
import logging
from redis import Redis
from rq import Connection

# Add project root to path
sys.path.insert(0, "/app")

from app.llm.queue.claude_worker import ClaudeWorker
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def main():
    """Run Claude-aware RQ worker."""
    # Get queue name from args or environment
    queue_name = (
        sys.argv[1] if len(sys.argv) > 1 else os.environ.get("QUEUE_NAME", "llm")
    )

    # Get worker name from args or generate
    worker_name = sys.argv[2] if len(sys.argv) > 2 else None

    # Connect to Redis
    redis_url = os.environ.get("REDIS_URL", settings.REDIS_URL)
    redis_conn = Redis.from_url(redis_url)

    with Connection(redis_conn):
        # Create and run worker
        worker = ClaudeWorker(
            [queue_name],
            name=worker_name,
            default_worker_ttl=-1,  # Never expire (keep worker running)
            job_monitoring_interval=1,  # Check jobs frequently
        )

        worker.work()


if __name__ == "__main__":
    main()
