"""RQ queue definitions."""

import logging
import os

import redis
from rq import Queue

logger = logging.getLogger(__name__)

# Get Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://cache:6379/0")

# Create connection pool for better concurrency handling
redis_pool = redis.ConnectionPool.from_url(
    REDIS_URL,
    max_connections=50,  # Increase pool size for multiple workers
    socket_timeout=5,
    socket_connect_timeout=5,
    socket_keepalive=True,
    # Removed socket_keepalive_options as they're platform-specific
)

# RQ queues with connection pool
try:
    redis_client = redis.Redis(connection_pool=redis_pool, decode_responses=False)
    # Verify connection
    redis_client.ping()
    logger.debug("Connected to Redis at %s with connection pool (max_connections=50)", REDIS_URL)
except Exception as e:
    logger.error("Failed to connect to Redis at %s: %s", REDIS_URL, e)
    raise

# Create queues with separate connections from the pool
llm_queue = Queue("llm", connection=redis.Redis(connection_pool=redis_pool))
reconciler_queue = Queue("reconciler", connection=redis.Redis(connection_pool=redis_pool))
recorder_queue = Queue("recorder", connection=redis.Redis(connection_pool=redis_pool))

# Export queue types for type hints
QueueType = Queue
