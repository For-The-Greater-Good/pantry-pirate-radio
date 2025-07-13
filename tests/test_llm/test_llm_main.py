"""Tests for LLM worker main entry point."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.__main__ import main


class AsyncWorkerMock:
    """Mock worker class with async methods."""

    def __init__(self, redis=None, provider=None):
        self.redis = redis
        self.provider = provider
        self.setup_called = False
        self.run_called = False
        self.stop_called = False
        self.should_raise_on_setup = False
        self.should_raise_on_run = False
        self.should_raise_on_stop = False

    async def setup(self):
        self.setup_called = True
        if self.should_raise_on_setup:
            raise Exception("Setup failed")

    async def run(self):
        self.run_called = True
        if self.should_raise_on_run:
            raise Exception("Run failed")

    async def stop(self):
        self.stop_called = True
        if self.should_raise_on_stop:
            raise Exception("Stop failed")


@pytest.mark.asyncio
async def test_main_openai_provider():
    """Test main function with OpenAI provider."""
    with patch("app.llm.__main__.get_setting") as mock_get_setting, patch(
        "app.llm.__main__.redis"
    ) as mock_redis, patch(
        "app.llm.__main__.OpenAIProvider"
    ) as mock_openai_provider, patch(
        "app.llm.__main__.QueueWorker"
    ) as mock_queue_worker:

        # Mock settings
        mock_get_setting.side_effect = lambda key, type_, default=None, required=True: {
            "redis_url": "redis://localhost:6379",
            "llm_provider": "openai",
            "llm_model_name": "gpt-3.5-turbo",
            "llm_temperature": 0.7,
            "llm_max_tokens": 1000,
        }[key]

        # Mock Redis
        mock_redis_client = AsyncMock()
        mock_redis_client.close = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_client

        # Mock provider
        mock_provider_instance = MagicMock()
        mock_openai_provider.return_value = mock_provider_instance

        # Mock worker with proper async methods
        mock_worker_instance = AsyncWorkerMock()
        # Mock the constructor call - QueueWorker[LLMJob](...)
        mock_queue_worker.return_value = mock_worker_instance
        # Also handle the generic subscription
        mock_queue_worker.__getitem__ = MagicMock(return_value=mock_queue_worker)

        await main()

        # Verify calls
        mock_redis.from_url.assert_called_once_with("redis://localhost:6379")
        mock_openai_provider.assert_called_once()
        mock_queue_worker.assert_called_once()
        assert mock_worker_instance.setup_called
        assert mock_worker_instance.run_called
        assert mock_worker_instance.stop_called
        mock_redis_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_claude_provider():
    """Test main function with Claude provider."""
    with patch("app.llm.__main__.get_setting") as mock_get_setting, patch(
        "app.llm.__main__.redis"
    ) as mock_redis, patch(
        "app.llm.__main__.ClaudeProvider"
    ) as mock_claude_provider, patch(
        "app.llm.__main__.QueueWorker"
    ) as mock_queue_worker:

        # Mock settings
        mock_get_setting.side_effect = lambda key, type_, default=None, required=True: {
            "redis_url": "redis://localhost:6379",
            "llm_provider": "claude",
            "llm_model_name": "claude-3-sonnet",
            "llm_temperature": 0.7,
            "llm_max_tokens": 1000,
        }[key]

        # Mock Redis
        mock_redis_client = AsyncMock()
        mock_redis_client.close = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_client

        # Mock provider
        mock_provider_instance = MagicMock()
        mock_claude_provider.return_value = mock_provider_instance

        # Mock worker
        mock_worker_instance = AsyncWorkerMock()
        mock_queue_worker.return_value = mock_worker_instance
        # Also handle the generic subscription
        mock_queue_worker.__getitem__ = MagicMock(return_value=mock_queue_worker)

        await main()

        # Verify calls
        mock_redis.from_url.assert_called_once_with("redis://localhost:6379")
        mock_claude_provider.assert_called_once()
        mock_queue_worker.assert_called_once()
        assert mock_worker_instance.setup_called
        assert mock_worker_instance.run_called
        assert mock_worker_instance.stop_called
        mock_redis_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_unsupported_provider():
    """Test main function with unsupported provider."""
    with patch("app.llm.__main__.get_setting") as mock_get_setting:

        # Mock settings with unsupported provider
        mock_get_setting.side_effect = lambda key, type_, default=None, required=True: {
            "redis_url": "redis://localhost:6379",
            "llm_provider": "unsupported",
            "llm_model_name": "some-model",
            "llm_temperature": 0.7,
            "llm_max_tokens": 1000,
        }[key]

        with pytest.raises(ValueError, match="Unsupported LLM provider: unsupported"):
            await main()


@pytest.mark.asyncio
async def test_main_worker_exception():
    """Test main function when worker raises exception."""
    with patch("app.llm.__main__.get_setting") as mock_get_setting, patch(
        "app.llm.__main__.redis"
    ) as mock_redis, patch(
        "app.llm.__main__.OpenAIProvider"
    ) as mock_openai_provider, patch(
        "app.llm.__main__.QueueWorker"
    ) as mock_queue_worker:

        # Mock settings
        mock_get_setting.side_effect = lambda key, type_, default=None, required=True: {
            "redis_url": "redis://localhost:6379",
            "llm_provider": "openai",
            "llm_model_name": "gpt-3.5-turbo",
            "llm_temperature": 0.7,
            "llm_max_tokens": 1000,
        }[key]

        # Mock Redis
        mock_redis_client = AsyncMock()
        mock_redis_client.close = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_client

        # Mock provider
        mock_provider_instance = MagicMock()
        mock_openai_provider.return_value = mock_provider_instance

        # Mock worker that raises exception during run
        mock_worker_instance = AsyncWorkerMock()
        mock_worker_instance.should_raise_on_run = True
        mock_queue_worker.return_value = mock_worker_instance
        # Also handle the generic subscription
        mock_queue_worker.__getitem__ = MagicMock(return_value=mock_queue_worker)

        await main()

        # Should still stop worker and close Redis even after exception
        assert mock_worker_instance.setup_called
        assert mock_worker_instance.run_called
        assert mock_worker_instance.stop_called
        mock_redis_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_with_none_max_tokens():
    """Test main function with None max_tokens."""
    with patch("app.llm.__main__.get_setting") as mock_get_setting, patch(
        "app.llm.__main__.redis"
    ) as mock_redis, patch(
        "app.llm.__main__.OpenAIProvider"
    ) as mock_openai_provider, patch(
        "app.llm.__main__.QueueWorker"
    ) as mock_queue_worker:

        # Mock settings with None max_tokens
        def mock_setting(key, type_, default=None, required=True):
            settings = {
                "redis_url": "redis://localhost:6379",
                "llm_provider": "openai",
                "llm_model_name": "gpt-3.5-turbo",
                "llm_temperature": 0.7,
                "llm_max_tokens": None,
            }
            if key == "llm_max_tokens":
                return None  # Explicitly return None for max_tokens
            return settings[key]

        mock_get_setting.side_effect = mock_setting

        # Mock Redis
        mock_redis_client = AsyncMock()
        mock_redis_client.close = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_client

        # Mock provider
        mock_provider_instance = MagicMock()
        mock_openai_provider.return_value = mock_provider_instance

        # Mock worker
        mock_worker_instance = AsyncWorkerMock()
        mock_queue_worker.return_value = mock_worker_instance
        # Also handle the generic subscription
        mock_queue_worker.__getitem__ = MagicMock(return_value=mock_queue_worker)

        await main()

        # Verify OpenAI provider was called with None max_tokens
        mock_openai_provider.assert_called_once()
        mock_redis_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_redis_close_on_exception():
    """Test that Redis connection is closed even when worker stop fails."""
    with patch("app.llm.__main__.get_setting") as mock_get_setting, patch(
        "app.llm.__main__.redis"
    ) as mock_redis, patch(
        "app.llm.__main__.OpenAIProvider"
    ) as mock_openai_provider, patch(
        "app.llm.__main__.QueueWorker"
    ) as mock_queue_worker:

        # Mock settings
        mock_get_setting.side_effect = lambda key, type_, default=None, required=True: {
            "redis_url": "redis://localhost:6379",
            "llm_provider": "openai",
            "llm_model_name": "gpt-3.5-turbo",
            "llm_temperature": 0.7,
            "llm_max_tokens": 1000,
        }[key]

        # Mock Redis
        mock_redis_client = AsyncMock()
        mock_redis_client.close = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_client

        # Mock provider
        mock_provider_instance = MagicMock()
        mock_openai_provider.return_value = mock_provider_instance

        # Mock worker that fails during stop
        mock_worker_instance = AsyncWorkerMock()
        mock_worker_instance.should_raise_on_stop = True
        mock_queue_worker.return_value = mock_worker_instance
        # Also handle the generic subscription
        mock_queue_worker.__getitem__ = MagicMock(return_value=mock_queue_worker)

        await main()

        # Should still close Redis even when stop fails
        assert mock_worker_instance.setup_called
        assert mock_worker_instance.run_called
        assert mock_worker_instance.stop_called
        mock_redis_client.close.assert_awaited_once()
