"""Main entry point for LLM worker."""

import asyncio
import logging
import os

import redis.asyncio as redis

from typing import Any, cast

from app.core.events import get_setting
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.openai import OpenAIConfig, OpenAIProvider
from app.llm.providers.claude import ClaudeConfig, ClaudeProvider
from app.llm.queue.models import LLMJob
from app.llm.queue.worker import QueueWorker

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Run the LLM worker."""
    logger.info("Starting LLM worker...")
    # Initialize Redis connection
    redis_url = get_setting("redis_url", str, required=True)
    logger.info(f"Connecting to Redis at {redis_url}")
    redis_client = redis.from_url(redis_url)

    # Initialize LLM provider based on configuration
    llm_provider = get_setting("llm_provider", str, required=True)
    llm_model = get_setting("llm_model_name", str, required=True)
    llm_temperature = get_setting("llm_temperature", float, required=True)
    llm_max_tokens = get_setting("llm_max_tokens", int, None, required=False)

    logger.info(f"Initializing {llm_provider} provider...")
    if llm_provider == "openai":
        openai_config = OpenAIConfig(
            model_name=llm_model,
            temperature=llm_temperature,
            max_tokens=llm_max_tokens,
        )
        provider = cast(BaseLLMProvider[Any, Any], OpenAIProvider(openai_config))
    elif llm_provider == "claude":
        claude_config = ClaudeConfig(
            model_name=llm_model,
            temperature=llm_temperature,
            max_tokens=llm_max_tokens,
        )
        provider = cast(BaseLLMProvider[Any, Any], ClaudeProvider(claude_config))
    else:
        raise ValueError(
            f"Unsupported LLM provider: {llm_provider}. "
            f"Supported providers: openai, claude"
        )

    # Create and run worker
    logger.info("Creating worker...")
    worker = QueueWorker[LLMJob](
        redis=redis_client,
        provider=provider,
    )

    try:
        logger.info("Setting up worker...")
        await worker.setup()
        logger.info("Worker setup complete, starting main loop...")
        await worker.run()
    except Exception as e:
        logger.exception(f"Worker error: {e}")
    finally:
        logger.info("Stopping worker...")
        try:
            await worker.stop()
        except Exception as e:
            logger.warning(f"Error stopping worker: {e}")
        await redis_client.close()
        logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
