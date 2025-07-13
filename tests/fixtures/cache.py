"""Redis cache test fixtures."""

from collections.abc import Mapping

import pytest
import redis

from .types.config import Settings, get_test_settings

settings: Settings = get_test_settings()


@pytest.fixture(scope="function")
def redis_client() -> redis.Redis:
    """Get Redis client for testing.

    Returns:
        Redis client that flushes data after test
    """
    # Create sync Redis client
    client = redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=False,  # Keep raw bytes for consistent handling
        socket_timeout=5,  # Add timeout for operations
        socket_connect_timeout=5,  # Add connection timeout
    )

    try:
        # Verify Redis connection
        client.ping()

        # Clear any existing data
        client.flushdb()

        return client

    except Exception:
        client.close()
        raise


@pytest.fixture(scope="function")
def llm_redis_client(redis_client: redis.Redis) -> redis.Redis:
    """Get Redis client configured for LLM job processing.

    Args:
        redis_client: Base Redis client fixture

    Returns:
        Redis client with LLM job processing setup
    """
    try:
        # Set up stream and consumer group
        stream_key = b"llm:jobs"
        consumer_group = b"llm-workers"

        # Create stream with initial message
        redis_client.xadd(stream_key, {"init": "1"})

        # Create consumer group
        try:
            redis_client.xgroup_create(
                name=stream_key,
                groupname=consumer_group,
                id="$",  # Start from latest message
                mkstream=True,
            )
        except Exception:
            # Group may already exist
            pass

        # Initialize job status counters
        status_counts: Mapping[bytes, bytes] = {
            b"queued": b"0",
            b"processing": b"0",
            b"completed": b"0",
            b"failed": b"0",
            b"cancelled": b"0",
        }
        redis_client.hset(b"llm:jobs:status", mapping=status_counts)

        return redis_client

    finally:
        # Clean up LLM-specific keys
        try:
            redis_client.delete("llm:jobs", "llm:jobs:status", "llm:jobs:errors")
        except Exception:
            pass
