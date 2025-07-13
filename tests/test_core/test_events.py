"""Tests for application startup and shutdown events."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.asyncio.client import Redis
from redis.exceptions import ConnectionError, TimeoutError

from app.core.events import (
    AppStateDict,
    QueueInitError,
    create_job_processor,
    create_redis_pool,
    create_start_app_handler,
    create_stop_app_handler,
    get_setting,
)


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis client."""
    redis = AsyncMock(spec=Redis)
    redis.ping = AsyncMock(return_value=True)
    redis.info = AsyncMock(return_value={"connected_clients": 5})
    redis.close = AsyncMock()
    return redis


@pytest.fixture
def mock_job_processor() -> AsyncMock:
    """Mock job processor."""
    processor = AsyncMock()
    return processor


@pytest.fixture
def app_state(mock_redis: AsyncMock, mock_job_processor: AsyncMock) -> AppStateDict:
    """Mock application state."""
    state = AppStateDict()
    state.redis = mock_redis
    state.job_processor = mock_job_processor
    return state


@pytest.mark.asyncio
async def test_get_setting() -> None:
    """Test get_setting function."""
    # Test required setting
    with patch("app.core.events.settings") as mock_settings:
        mock_settings.test_setting = "test_value"
        assert get_setting("test_setting", str) == "test_value"

    # Test optional setting with default
    with patch("app.core.events.settings", spec=[]) as mock_settings:
        assert (
            get_setting("test_setting", str, required=False, default="default")
            == "default"
        )

    # Test required setting missing
    with patch("app.core.events.settings") as mock_settings:
        mock_settings.test_setting = None
        with pytest.raises(ValueError):
            get_setting("test_setting", str)


@pytest.mark.asyncio
async def test_create_redis_pool_success(mock_redis: AsyncMock) -> None:
    """Test successful Redis pool creation."""
    with patch("app.core.events.AsyncRedis") as mock_redis_class, patch(
        "app.core.events.settings"
    ) as mock_settings:
        mock_settings.redis_url = "redis://localhost:6379"
        mock_redis_class.from_url.return_value = mock_redis
        redis = await create_redis_pool()
        assert redis == mock_redis
        mock_redis.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_redis_pool_retry(mock_redis: AsyncMock) -> None:
    """Test Redis pool creation with retries."""
    with patch("app.core.events.AsyncRedis") as mock_redis_class, patch(
        "app.core.events.settings"
    ) as mock_settings:
        mock_settings.redis_url = "redis://localhost:6379"
        mock_redis_class.from_url.return_value = mock_redis

        # First two attempts fail
        mock_redis.ping.side_effect = [ConnectionError(), TimeoutError()]
        with pytest.raises(QueueInitError):
            await create_redis_pool()

        # Reset mock for next test
        mock_redis.ping.reset_mock()
        mock_redis.ping.side_effect = None
        mock_redis.ping.return_value = True

        # Third attempt succeeds
        redis = await create_redis_pool()
        assert redis == mock_redis
        assert mock_redis.ping.await_count == 1


@pytest.mark.asyncio
async def test_create_redis_pool_failure(mock_redis: AsyncMock) -> None:
    """Test Redis pool creation failure after retries."""
    with patch("app.core.events.AsyncRedis") as mock_redis_class, patch(
        "app.core.events.settings"
    ) as mock_settings:
        mock_settings.redis_url = "redis://localhost:6379"
        mock_redis_class.from_url.return_value = mock_redis
        mock_redis.ping.side_effect = ConnectionError()
        with pytest.raises(QueueInitError):
            await create_redis_pool()


@pytest.mark.asyncio
async def test_create_job_processor(mock_redis: AsyncMock) -> None:
    """Test job processor creation."""
    with patch("app.core.events.JobProcessor") as mock_processor_class, patch(
        "app.core.events.settings"
    ) as mock_settings:
        mock_settings.llm_provider = "openai"
        mock_settings.llm_model_name = "google/gemini-2.0-flash-001"
        mock_settings.llm_temperature = 0.7
        mock_settings.llm_max_tokens = 1000
        mock_processor = AsyncMock()
        mock_processor_class.return_value = mock_processor
        processor = await create_job_processor(mock_redis)
        assert processor == mock_processor


@pytest.mark.asyncio
async def test_app_state_health_check(app_state: AppStateDict) -> None:
    """Test application state health check."""
    with patch("app.core.events.Worker") as mock_worker_class, patch(
        "app.core.events.llm_queue"
    ) as mock_queue:
        mock_worker_class.all.return_value = [MagicMock(), MagicMock()]  # 2 workers
        mock_queue.count = 5  # 5 queued jobs

        health = await app_state.health_check()
        assert health["status"] == "healthy"
        assert health["components"]["redis"] is True
        assert health["components"]["job_processor"] is True
        assert health["components"]["queue"] is True
        assert health["details"]["redis"]["connections"] == 5
        assert health["details"]["queue"]["queued_jobs"] == 5
        assert health["details"]["queue"]["workers"] == 2


@pytest.mark.asyncio
async def test_app_state_health_check_degraded(app_state: AppStateDict) -> None:
    """Test health check with degraded state."""
    with patch("app.core.events.Worker") as mock_worker_class, patch(
        "app.core.events.llm_queue"
    ) as mock_queue:
        mock_worker_class.all.return_value = []  # No workers
        mock_queue.count = 5  # 5 queued jobs

        health = await app_state.health_check()
        assert health["status"] == "degraded"


@pytest.mark.asyncio
async def test_app_state_health_check_error(app_state: AppStateDict) -> None:
    """Test health check with error."""
    mock_redis = app_state.redis
    assert isinstance(mock_redis, AsyncMock)
    mock_redis.ping.side_effect = ConnectionError()
    health = await app_state.health_check()
    assert health["status"] == "unhealthy"
    assert "error" in health


@pytest.mark.asyncio
async def test_startup_handler() -> None:
    """Test application startup handler."""
    mock_app = MagicMock()
    handler = create_start_app_handler(mock_app)

    with patch("app.core.events.create_redis_pool") as mock_create_redis, patch(
        "app.core.events.create_job_processor"
    ) as mock_create_processor, patch("app.core.events.settings") as mock_settings:
        mock_settings.redis_url = "redis://localhost:6379"
        mock_settings.llm_provider = "openai"
        mock_settings.llm_model_name = "google/gemini-2.0-flash-001"

        mock_redis = AsyncMock()
        mock_processor = AsyncMock()

        mock_create_redis.return_value = mock_redis
        mock_create_processor.return_value = mock_processor

        await handler()

        mock_create_redis.assert_awaited_once()
        mock_create_processor.assert_awaited_once_with(mock_redis)

        assert mock_app.state.redis == mock_redis
        assert mock_app.state.job_processor == mock_processor


@pytest.mark.asyncio
async def test_shutdown_handler(app_state: AppStateDict) -> None:
    """Test application shutdown handler."""
    mock_app = MagicMock()
    mock_app.state = app_state
    handler = create_stop_app_handler(mock_app)

    await handler()

    mock_redis = app_state.redis
    assert isinstance(mock_redis, AsyncMock)
    assert mock_redis.close.await_count == 1
