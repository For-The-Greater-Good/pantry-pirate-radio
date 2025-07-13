"""LLM test configuration."""

import os
from pathlib import Path
from typing import AsyncGenerator

import pytest_asyncio
from redis.asyncio import Redis


@pytest_asyncio.fixture(scope="session")
def project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


# Import fixtures from root conftest and cache
pytest_plugins = ["tests.fixtures.cache"]

# Set required LLM environment variables for tests
os.environ.update(
    {
        "LLM_MODEL": "test-model",  # Required by events.py
        "LLM_PROVIDER": "openai",
        "LLM_TEMPERATURE": "0.7",
        "LLM_MAX_TOKENS": "100",
        "LLM_WORKER_COUNT": "1",
    }
)


@pytest_asyncio.fixture
async def redis(redis_client: Redis) -> AsyncGenerator[Redis, None]:
    """Alias for redis_client fixture."""
    yield redis_client
