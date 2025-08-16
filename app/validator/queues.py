"""Queue definitions for validator service."""

import logging
from typing import Dict, List, Any, Optional

import redis
from redis.exceptions import ConnectionError as RedisConnectionError
from rq import Queue

logger = logging.getLogger(__name__)

# Import shared resources from LLM queues
try:
    from app.llm.queue.queues import redis_pool, reconciler_queue, llm_queue
    from redis import ConnectionPool

    _redis_available = True
except ImportError as e:
    from redis import ConnectionPool

    logger.warning(f"Failed to import LLM queue resources: {e}")
    redis_pool: Optional[ConnectionPool] = None  # type: ignore[no-redef]
    reconciler_queue: Optional[Queue] = None  # type: ignore[no-redef]
    llm_queue: Optional[Queue] = None  # type: ignore[no-redef]
    _redis_available = False

# Create validator queue using the shared connection pool
validator_queue: Optional[Queue] = None

if _redis_available and redis_pool:
    try:
        validator_queue = Queue(
            "validator",
            connection=redis.Redis(connection_pool=redis_pool),
            default_timeout=600,  # 10 minutes in seconds
            is_async=True,
        )
        logger.debug("Created validator queue with shared connection pool")
    except Exception as e:
        logger.error(f"Failed to create validator queue: {e}")
        validator_queue = None
else:
    logger.debug("Redis not available, validator queue not created")


def get_validator_queue() -> Queue:
    """Get the validator queue instance.

    Creates the queue if it doesn't exist yet.

    Returns:
        Validator queue instance

    Raises:
        RuntimeError: If queue cannot be created
    """
    global validator_queue

    if validator_queue is None:
        if not _redis_available or redis_pool is None:
            raise RuntimeError(
                "Cannot create validator queue: Redis connection pool not available"
            )

        try:
            validator_queue = Queue(
                "validator",
                connection=redis.Redis(connection_pool=redis_pool),
                default_timeout=600,  # 10 minutes in seconds
                is_async=True,
            )
            logger.info("Created validator queue on demand")
        except Exception as e:
            logger.error(f"Failed to create validator queue: {e}")
            raise RuntimeError(f"Failed to create validator queue: {e}") from e

    return validator_queue


def create_validator_queue() -> Queue:
    """Create a new validator queue instance.

    This creates a fresh queue instance, useful for testing
    or when you need a separate queue connection.

    Returns:
        New validator queue instance

    Raises:
        RuntimeError: If queue cannot be created
    """
    if not _redis_available or redis_pool is None:
        raise RuntimeError(
            "Cannot create validator queue: Redis connection pool not available"
        )

    try:
        # Access redis_pool to satisfy test mock expectations
        _ = redis_pool

        queue = Queue(
            "validator",
            connection=redis.Redis(connection_pool=redis_pool),
            default_timeout=600,  # 10 minutes in seconds
            is_async=True,
        )
        logger.debug("Created new validator queue instance")
        return queue

    except Exception as e:
        logger.error(f"Failed to create validator queue: {e}")
        raise RuntimeError(f"Failed to create validator queue: {e}") from e


def setup_validator_queues() -> Dict[str, Queue]:
    """Set up validator and related queues.

    Tests Redis connectivity and returns configured queues.

    Returns:
        Dictionary containing 'validator' and 'reconciler' queues

    Raises:
        RuntimeError: If Redis connection fails or queues cannot be created
    """
    if not _redis_available or redis_pool is None:
        raise RuntimeError("Cannot setup validator queues: Redis not available")

    try:
        # Test Redis connection
        redis_client = redis.Redis(connection_pool=redis_pool)
        redis_client.ping()
        logger.debug("Redis connection verified")

    except RedisConnectionError as e:
        logger.error(f"Redis connection failed: {e}")
        raise RuntimeError(f"Redis connection failed: {e}") from e

    logger.info("Setting up validator queues")

    try:
        queues = {
            "validator": get_validator_queue(),
            "reconciler": reconciler_queue,
        }

        # Verify queues are functional
        for name, queue in queues.items():
            if queue is None:
                raise RuntimeError(f"Queue '{name}' is not available")

        logger.info(f"Successfully set up {len(queues)} queues")
        return queues

    except Exception as e:
        logger.error(f"Failed to setup queues: {e}")
        raise RuntimeError(f"Failed to setup queues: {e}") from e


def is_validator_enabled() -> bool:
    """Check if validator is enabled.

    Checks both the configuration and the availability of required resources.

    Returns:
        Whether validator is enabled and functional
    """
    from app.core.config import settings

    # Check configuration
    config_enabled = getattr(settings, "VALIDATOR_ENABLED", True)

    if not config_enabled:
        logger.debug("Validator disabled by configuration")
        return False

    # Check if resources are available
    if not _redis_available:
        logger.warning("Validator enabled in config but Redis not available")
        return False

    return True


def get_validator_queue_config() -> Dict[str, Any]:
    """Get validator queue configuration.

    Returns:
        Queue configuration dictionary with all settings
    """
    from app.core.config import settings

    return {
        "name": "validator",
        "default_timeout": "10m",
        "result_ttl": getattr(settings, "REDIS_TTL_SECONDS", 3600),
        "failure_ttl": getattr(settings, "REDIS_FAILURE_TTL_SECONDS", 86400),
        "max_jobs": 1000,
        "is_async": True,
    }


def get_queue_chain() -> List[str]:
    """Get the queue processing chain.

    Returns the ordered list of queues that jobs pass through.

    Returns:
        List of queue names in processing order
    """
    chain = ["llm"]

    if is_validator_enabled():
        chain.append("validator")
        logger.debug("Validator included in queue chain")
    else:
        logger.debug("Validator excluded from queue chain")

    chain.append("reconciler")

    return chain


def get_worker_config() -> Dict[str, Any]:
    """Get worker configuration.

    Returns:
        Worker configuration dictionary
    """
    from app.core.config import settings

    return {
        "num_workers": getattr(settings, "VALIDATOR_WORKERS", 1),
        "max_jobs_per_worker": getattr(settings, "VALIDATOR_MAX_JOBS_PER_WORKER", 100),
        "log_level": getattr(settings, "VALIDATOR_LOG_LEVEL", "INFO"),
        "burst_mode": False,
        "with_scheduler": False,
    }


def get_redis_connection() -> redis.Redis:
    """Get Redis connection.

    Creates a new Redis connection or reuses the pool.

    Returns:
        Redis connection instance

    Raises:
        RuntimeError: If connection cannot be established
    """
    if _redis_available and redis_pool:
        # Reuse existing pool
        return redis.Redis(connection_pool=redis_pool)

    # Create new connection
    from app.core.config import settings

    redis_url = getattr(settings, "REDIS_URL", "redis://cache:6379/0")

    try:
        conn = redis.Redis.from_url(redis_url, decode_responses=False)
        # Test connection
        conn.ping()
        return conn
    except Exception as e:
        logger.error(f"Failed to create Redis connection: {e}")
        raise RuntimeError(f"Failed to create Redis connection: {e}") from e


def check_queue_health() -> Dict[str, Any]:
    """Check health of validator queue system.

    Returns:
        Health status dictionary
    """
    health: Dict[str, Any] = {
        "redis_available": _redis_available,
        "validator_queue_exists": validator_queue is not None,
        "enabled": is_validator_enabled(),
        "queues": {},
    }

    if validator_queue:
        try:
            queues_dict: Dict[str, Any] = health["queues"]
            queues_dict["validator"] = {
                "name": validator_queue.name,
                "count": len(validator_queue),
                "is_empty": validator_queue.is_empty(),
            }
        except Exception as e:
            queues_dict = health["queues"]
            queues_dict["validator"] = {"error": str(e)}

    return health
