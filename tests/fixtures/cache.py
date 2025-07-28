"""Redis cache test fixtures."""

import os
from collections.abc import Mapping

import pytest
import redis

from .types.config import Settings, get_test_settings

settings: Settings = get_test_settings()


@pytest.fixture(scope="function")
def redis_client() -> redis.Redis:
    """Get Redis client for testing.

    Returns:
        Redis client that cleans up test data after test
    """
    # Safety check: ensure we're using test Redis (different DB or test in hostname)
    redis_url = settings.REDIS_URL.lower()
    if "test" not in redis_url and not redis_url.endswith("/1"):
        raise ValueError(
            f"Redis URL '{settings.REDIS_URL}' doesn't appear to be a test instance! "
            "Test Redis URL should contain 'test' or use database 1 to prevent data loss."
        )

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

        # Get test prefix for this test run
        test_prefix = f"test:{os.getpid()}:"

        # Clear only test-prefixed keys from previous runs
        for key in client.scan_iter(match=f"{test_prefix}*"):
            client.delete(key)

        # Store the test prefix for use in tests
        client.test_prefix = test_prefix  # type: ignore

        yield client

    finally:
        # Cleanup: remove all keys created by this test
        try:
            for key in client.scan_iter(match=f"{test_prefix}*"):
                client.delete(key)
        except Exception:
            pass
        client.close()


@pytest.fixture(scope="function")
def llm_redis_client(redis_client: redis.Redis) -> redis.Redis:
    """Get Redis client configured for LLM job processing.

    Args:
        redis_client: Base Redis client fixture

    Returns:
        Redis client with LLM job processing setup
    """
    try:
        # Use test prefix for all keys
        test_prefix = getattr(redis_client, "test_prefix", "test:")
        test_prefix_bytes = test_prefix.encode()

        # Set up stream and consumer group with test prefix
        stream_key = test_prefix_bytes + b"llm:jobs"
        consumer_group = test_prefix_bytes + b"llm-workers"

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
        status_key = test_prefix_bytes + b"llm:jobs:status"
        redis_client.hset(status_key, mapping=status_counts)

        return redis_client

    finally:
        # Clean up LLM-specific keys with test prefix
        try:
            test_prefix = getattr(redis_client, "test_prefix", "test:")
            test_prefix_bytes = test_prefix.encode()
            redis_client.delete(
                test_prefix_bytes + b"llm:jobs",
                test_prefix_bytes + b"llm:jobs:status",
                test_prefix_bytes + b"llm:jobs:errors",
            )
        except Exception:
            pass
