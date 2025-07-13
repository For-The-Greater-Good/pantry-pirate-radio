"""RQ queue definitions."""

import logging
import os

import redis
from rq import Queue

logger = logging.getLogger(__name__)

# Get Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://cache:6379/0")

# RQ queues with sync Redis client
try:
    redis_client = redis.Redis.from_url(
        REDIS_URL,
        decode_responses=False,  # Keep raw bytes for consistent handling
        socket_timeout=5,  # Add timeout for operations
        socket_connect_timeout=5,  # Add connection timeout
    )
    # Verify connection
    redis_client.ping()
    logger.debug("Connected to Redis at %s", REDIS_URL)
except Exception as e:
    logger.error("Failed to connect to Redis at %s: %s", REDIS_URL, e)
    raise

# Create queues with shared Redis connection
connection = redis_client
llm_queue = Queue("llm", connection=connection)
reconciler_queue = Queue("reconciler", connection=connection)
recorder_queue = Queue("recorder", connection=connection)

# Export queue types for type hints
QueueType = Queue
