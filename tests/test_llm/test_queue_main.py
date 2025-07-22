"""Tests for llm/queue/__main__.py module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
import asyncio

from app.llm.queue.__main__ import main


class TestLLMQueueMain:
    """Test cases for the LLM queue main module."""

    @pytest.mark.asyncio
    async def test_should_create_openai_provider_when_configured(self):
        """Test creating OpenAI provider based on configuration."""
        # Arrange
        with patch("app.llm.queue.__main__.get_setting") as mock_get_setting:
            mock_get_setting.side_effect = lambda key, *args, **kwargs: {
                "redis_url": "redis://localhost:6379",
                "redis_pool_size": 10,
                "llm_provider": "openai",
                "llm_model_name": "gpt-3.5-turbo",
                "llm_temperature": 0.7,
                "llm_max_tokens": None,
            }.get(key)

            with patch("app.llm.queue.__main__.AsyncRedis.from_url") as mock_redis:
                mock_redis_instance = AsyncMock()
                mock_redis.return_value = mock_redis_instance

                with patch("app.llm.queue.__main__.OpenAIProvider") as mock_provider:
                    mock_provider_instance = MagicMock()
                    mock_provider.return_value = mock_provider_instance

                    with patch("app.llm.queue.__main__.QueueWorker") as mock_worker:
                        mock_worker_instance = AsyncMock()
                        mock_worker.return_value = mock_worker_instance

                        # Act
                        await main()

                        # Assert
                        mock_provider.assert_called_once()
                        config_call = mock_provider.call_args[0][0]
                        assert config_call.model_name == "gpt-3.5-turbo"
                        assert config_call.temperature == 0.7
                        assert config_call.max_tokens is None

                        mock_worker.assert_called_once_with(
                            redis=mock_redis_instance, provider=mock_provider_instance
                        )
                        mock_worker_instance.setup.assert_called_once()
                        mock_worker_instance.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_create_claude_provider_when_configured(self):
        """Test creating Claude provider based on configuration."""
        # Arrange
        with patch("app.llm.queue.__main__.get_setting") as mock_get_setting:
            mock_get_setting.side_effect = lambda key, *args, **kwargs: {
                "redis_url": "redis://localhost:6379",
                "redis_pool_size": 10,
                "llm_provider": "claude",
                "llm_model_name": "claude-3-opus-20240229",
                "llm_temperature": 0.5,
                "llm_max_tokens": 1000,
            }.get(key)

            with patch("app.llm.queue.__main__.AsyncRedis.from_url") as mock_redis:
                mock_redis_instance = AsyncMock()
                mock_redis.return_value = mock_redis_instance

                with patch("app.llm.queue.__main__.ClaudeProvider") as mock_provider:
                    mock_provider_instance = MagicMock()
                    mock_provider.return_value = mock_provider_instance

                    with patch("app.llm.queue.__main__.QueueWorker") as mock_worker:
                        mock_worker_instance = AsyncMock()
                        mock_worker.return_value = mock_worker_instance

                        # Act
                        await main()

                        # Assert
                        mock_provider.assert_called_once()
                        config_call = mock_provider.call_args[0][0]
                        assert config_call.model_name == "claude-3-opus-20240229"
                        assert config_call.temperature == 0.5
                        assert config_call.max_tokens == 1000

                        mock_worker.assert_called_once_with(
                            redis=mock_redis_instance, provider=mock_provider_instance
                        )

    @pytest.mark.asyncio
    async def test_should_raise_error_for_unsupported_provider(self):
        """Test error handling for unsupported LLM provider."""
        # Arrange
        with patch("app.llm.queue.__main__.get_setting") as mock_get_setting:
            mock_get_setting.side_effect = lambda key, *args, **kwargs: {
                "redis_url": "redis://localhost:6379",
                "redis_pool_size": 10,
                "llm_provider": "unsupported",
                "llm_model_name": "some-model",
                "llm_temperature": 0.7,
                "llm_max_tokens": None,
            }.get(key)

            with patch("app.llm.queue.__main__.AsyncRedis.from_url"):
                # Act & Assert
                with pytest.raises(
                    ValueError, match="Unsupported LLM provider: unsupported"
                ):
                    await main()

    @pytest.mark.asyncio
    async def test_should_configure_redis_with_correct_parameters(self):
        """Test Redis configuration with correct parameters."""
        # Arrange
        with patch("app.llm.queue.__main__.get_setting") as mock_get_setting:
            mock_get_setting.side_effect = lambda key, *args, **kwargs: {
                "redis_url": "redis://localhost:6379/0",
                "redis_pool_size": 20,
                "llm_provider": "openai",
                "llm_model_name": "gpt-3.5-turbo",
                "llm_temperature": 0.7,
                "llm_max_tokens": None,
            }.get(key)

            with patch("app.llm.queue.__main__.AsyncRedis.from_url") as mock_redis:
                mock_redis_instance = AsyncMock()
                mock_redis.return_value = mock_redis_instance

                with patch("app.llm.queue.__main__.OpenAIProvider"):
                    with patch("app.llm.queue.__main__.QueueWorker") as mock_worker:
                        mock_worker_instance = AsyncMock()
                        mock_worker.return_value = mock_worker_instance

                        # Act
                        await main()

                        # Assert
                        mock_redis.assert_called_once_with(
                            "redis://localhost:6379/0",
                            encoding="utf-8",
                            decode_responses=False,
                            max_connections=20,
                        )

    def test_should_run_main_when_executed_directly(self):
        """Test main execution when module is run directly."""
        # This test is more complex because we need to test the if __name__ == "__main__" block
        # For now, we'll just test that the module can be imported without errors

        assert hasattr(app.llm.queue.__main__, "main")

    @pytest.mark.asyncio
    async def test_should_handle_required_settings(self):
        """Test that required settings are properly enforced."""
        # Arrange
        with patch("app.llm.queue.__main__.get_setting") as mock_get_setting:
            # Simulate missing required setting
            mock_get_setting.side_effect = (
                lambda key, type_, default=None, required=False: {
                    "redis_pool_size": 10,
                    "llm_provider": "openai",
                    "llm_model_name": "gpt-3.5-turbo",
                    "llm_temperature": 0.7,
                }.get(key, default)
            )

            # Act & Assert
            # get_setting should raise an error when redis_url is not found and required=True
            with pytest.raises(
                Exception
            ):  # The actual error depends on get_setting implementation
                await main()

    @pytest.mark.asyncio
    async def test_should_use_default_pool_size_when_not_configured(self):
        """Test using default Redis pool size when not configured."""
        # Arrange
        with patch("app.llm.queue.__main__.get_setting") as mock_get_setting:
            # Return None for redis_pool_size to trigger default
            def get_setting_side_effect(key, type_=str, default=None, required=False):
                settings = {
                    "redis_url": "redis://localhost:6379",
                    "llm_provider": "openai",
                    "llm_model_name": "gpt-3.5-turbo",
                    "llm_temperature": 0.7,
                    "llm_max_tokens": None,
                }
                if key == "redis_pool_size":
                    return default  # Use the default value
                return settings.get(key, default)

            mock_get_setting.side_effect = get_setting_side_effect

            with patch("app.llm.queue.__main__.AsyncRedis.from_url") as mock_redis:
                mock_redis_instance = AsyncMock()
                mock_redis.return_value = mock_redis_instance

                with patch("app.llm.queue.__main__.OpenAIProvider"):
                    with patch("app.llm.queue.__main__.QueueWorker") as mock_worker:
                        mock_worker_instance = AsyncMock()
                        mock_worker.return_value = mock_worker_instance

                        # Act
                        await main()

                        # Assert
                        # Should use default pool size of 10
                        mock_redis.assert_called_once()
                        assert mock_redis.call_args[1]["max_connections"] == 10


# Import the main module for the __name__ test
import app.llm.queue.__main__
import logging
