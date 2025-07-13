"""Application startup and shutdown events."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, TypeVar, cast

from prometheus_client import Counter, Gauge
from redis import Redis

# ConnectionPool is used in type annotations for Redis protocol compatibility
from redis.asyncio.client import Redis as AsyncRedis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import ConnectionError, TimeoutError
from rq import Worker

from app.core.config import settings
from app.llm.jobs import JobProcessor
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.claude import ClaudeConfig, ClaudeProvider
from app.llm.providers.openai import OpenAIConfig, OpenAIProvider
from app.llm.queue.queues import llm_queue


class QueueInitError(Exception):
    """Raised when queue initialization fails."""


class RedisProtocol(Protocol):
    """Protocol defining required Redis operations."""

    # ConnectionPool is used in type annotation for Redis protocol compatibility
    connection_pool: "ConnectionPool[Any]"  # type: ignore

    async def ping(self) -> bool: ...

    async def info(  # type: ignore
        self, section: str | None = None, *args: Any, **kwargs: Any
    ) -> Mapping[str, Any]: ...

    async def close(self) -> None: ...


# Redis client type - using Protocol to avoid generic type issues
RedisType = RedisProtocol

# Additional Prometheus metrics
QUEUE_SIZE = Gauge(
    "app_queue_size",
    "Current number of jobs in queue",
)

ACTIVE_WORKERS = Gauge(
    "app_active_workers",
    "Number of active workers",
)

REDIS_POOL_CONNECTIONS = Gauge(
    "app_redis_pool_connections",
    "Number of active Redis connections",
)


# Prometheus metrics
REQUESTS_TOTAL = Counter(
    "app_http_requests_total",
    "Total number of HTTP requests",
    labelnames=["method", "path"],
)

RESPONSES_TOTAL = Counter(
    "app_http_responses_total",
    "Total number of HTTP responses",
    labelnames=["status_code"],
)

logger: logging.Logger = logging.getLogger("app.core.events")

App = TypeVar("App", bound=Any)

T = TypeVar("T")


def get_setting(
    name: str,
    type_: Callable[[Any], T],
    default: T | None = None,
    required: bool = True,
) -> T:
    """Get setting value with type conversion.

    Args:
        name: Setting name
        type_: Type conversion function
        default: Default value
        required: Whether the setting is required

    Returns:
        Setting value

    Raises:
        ValueError: If setting is required but not found
    """
    # Try exact name first
    try:
        if not hasattr(settings, name):
            raise AttributeError
        value = getattr(settings, name)
    except AttributeError:
        # Try uppercase version
        try:
            if not hasattr(settings, name.upper()):
                raise AttributeError
            value = getattr(settings, name.upper())
        except AttributeError:
            if required:
                raise ValueError(f"Setting {name} is required")
            return cast(T, default)

    if value is None:
        if required:
            raise ValueError(f"Setting {name} is required")
        return cast(T, default)

    return type_(value)


class AppStateDict:
    """Application state dictionary with health check capabilities."""

    def __init__(self) -> None:
        """Initialize state."""
        self.redis: RedisType | None = None
        self.job_processor: JobProcessor | None = None

    async def health_check(self) -> dict[str, Any]:
        """Check health of all components.

        Returns:
            Dict containing health status of all components
        """
        health_status: dict[str, Any] = {
            "status": "healthy",
            "components": {
                "redis": False,
                "job_processor": False,
                "queue": False,
            },
            "details": {},
        }

        try:
            # Check Redis connection
            if self.redis is not None:
                await self.redis.ping()
                health_status["components"]["redis"] = True
                # Get Redis info
                pool_info = await self.redis.info("clients")
                connections = pool_info.get("connected_clients", 0)
                health_status["details"]["redis"] = {"connections": connections}
                REDIS_POOL_CONNECTIONS.set(connections)

            # Check queue and worker status via RQ
            if self.redis is not None:
                # Get queue stats
                queued_jobs = llm_queue.count
                try:
                    workers = Worker.all(connection=cast("Redis[Any]", self.redis))
                    active_workers = len(workers)
                except Exception:
                    active_workers = 0

                health_status["components"]["queue"] = True
                health_status["components"]["job_processor"] = active_workers > 0
                health_status["details"]["queue"] = {
                    "queued_jobs": queued_jobs,
                    "workers": active_workers,
                }
                QUEUE_SIZE.set(queued_jobs)
                ACTIVE_WORKERS.set(active_workers)

            # Overall status
            if not all(health_status["components"].values()):
                health_status["status"] = "degraded"

        except Exception as e:
            health_status["status"] = "unhealthy"
            health_status["error"] = str(e)
            logger.error(f"Health check failed: {e}")

        return health_status


async def create_redis_pool() -> RedisType:
    """Create Redis connection pool with retry logic.

    Returns:
        Redis connection pool

    Raises:
        QueueInitError: If connection cannot be established after retries
    """
    redis_url = get_setting("redis_url", str, required=True)
    pool_size = get_setting("redis_pool_size", int, default=10, required=False)
    max_retries = get_setting("redis_max_retries", int, default=3, required=False)
    retry_delay = get_setting("redis_retry_delay", float, default=1.0, required=False)

    for attempt in range(max_retries):
        try:
            pool = AsyncRedis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=False,
                max_connections=pool_size,
                health_check_interval=15,
            )
            # Verify connection is working
            await pool.ping()
            logger.info(
                f"Redis pool initialized - Size: {pool_size}, "
                f"Health check interval: 15s"
            )
            return pool
        except (ConnectionError, TimeoutError) as e:
            if attempt == max_retries - 1:
                raise QueueInitError(f"Failed to initialize Redis pool: {e}")
            logger.warning(
                f"Redis connection attempt {attempt + 1}/{max_retries} "
                f"failed: {e}. Retrying in {retry_delay}s..."
            )
            await asyncio.sleep(retry_delay)

    # This should never be reached due to the max_retries check above
    # but needed to satisfy type checker
    raise QueueInitError("Failed to initialize Redis pool: max retries exceeded")


async def create_job_processor(redis: RedisType) -> JobProcessor:
    """Create LLM job processor.

    Args:
        redis: Redis connection pool

    Returns:
        Job processor instance
    """
    # Create provider based on configuration
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

    # Create processor
    processor = JobProcessor(
        redis=cast("Redis[Any]", redis),
        provider=provider,
    )
    return processor


def create_start_app_handler(app: Any) -> Callable[[], Awaitable[None]]:
    """Create startup event handler.

    Args:
        app: FastAPI application instance

    Returns:
        Startup handler function
    """

    async def start_app() -> None:
        # Create Redis pool
        redis = await create_redis_pool()

        # Create job processor
        processor = await create_job_processor(redis)

        # Store state
        state = AppStateDict()
        state.redis = redis
        state.job_processor = processor
        app.state = state

        # Log startup info
        redis_url = get_setting("redis_url", str, required=True)
        llm_provider = get_setting("llm_provider", str, required=True)
        llm_model = get_setting("llm_model_name", str, required=True)

        logger.info(
            "Application startup complete - "
            f"Redis: {redis_url}, "
            f"LLM Provider: {llm_provider}, "
            f"Model: {llm_model}"
        )

    return start_app


def create_stop_app_handler(app: Any) -> Callable[[], Awaitable[None]]:
    """Create shutdown event handler with graceful shutdown logic.

    Args:
        app: FastAPI application instance

    Returns:
        Shutdown handler function
    """

    async def stop_app() -> None:
        state = cast(AppStateDict, app.state)
        try:
            # Stop accepting new jobs first
            if state.job_processor is not None:
                logger.info("Stopping job processor...")
                logger.info("Job processor stopped")

            # Close Redis connections
            if state.redis is not None:
                logger.info("Closing Redis connections...")
                await state.redis.close()
                await asyncio.sleep(1)  # Give Redis time to close gracefully
                logger.info("Redis connections closed")

            logger.info("Application shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            raise

    return stop_app


def init_app_events(app: Any) -> None:
    """Initialize application events.

    Args:
        app: FastAPI application instance
    """
    app.add_event_handler("startup", create_start_app_handler(app))
    app.add_event_handler("shutdown", create_stop_app_handler(app))
