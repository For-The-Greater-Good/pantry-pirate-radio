"""Main entry point for queue worker."""

import asyncio
from typing import Any, cast

from redis.asyncio.client import Redis as AsyncRedis

from app.core.events import get_setting
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.openai import OpenAIConfig, OpenAIProvider
from app.llm.providers.claude import ClaudeConfig, ClaudeProvider
from app.llm.queue.worker import QueueWorker


async def main() -> None:
    """Run the LLM worker."""
    # Get Redis connection settings
    redis_url = get_setting("redis_url", str, required=True)
    pool_size = get_setting("redis_pool_size", int, default=10, required=False)

    # Create Redis connection
    redis = AsyncRedis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=False,
        max_connections=pool_size,
    )

    # Create LLM provider based on configuration
    llm_provider = get_setting("llm_provider", str, required=True)
    llm_model = get_setting("llm_model_name", str, required=True)
    llm_temperature = get_setting("llm_temperature", float, required=True)
    llm_max_tokens = get_setting("llm_max_tokens", int, None, required=False)

    # Create provider based on configuration
    if llm_provider == "openai":
        openai_config = OpenAIConfig(
            model_name=llm_model,
            temperature=llm_temperature,
            max_tokens=llm_max_tokens,
        )
        provider = cast(BaseLLMProvider, OpenAIProvider(openai_config))
    elif llm_provider == "claude":
        claude_config = ClaudeConfig(
            model_name=llm_model,
            temperature=llm_temperature,
            max_tokens=llm_max_tokens,
        )
        provider = cast(BaseLLMProvider, ClaudeProvider(claude_config))
    else:
        raise ValueError(
            f"Unsupported LLM provider: {llm_provider}. "
            f"Supported providers: openai, claude"
        )

    # Create and run worker
    worker: QueueWorker[Any] = QueueWorker(redis=redis, provider=provider)
    await worker.setup()
    await worker.run()


if __name__ == "__main__":
    # Configure logging
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run worker
    asyncio.run(main())
