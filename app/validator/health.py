"""Health check for validator service."""

import logging
from typing import Dict, Any

from app.validator.queues import get_validator_queue

logger = logging.getLogger(__name__)


def check_health() -> Dict[str, Any]:
    """Check health of validator service.

    Returns:
        Health status dictionary
    """
    try:
        queue = get_validator_queue()

        # Check Redis connection
        queue.connection.ping()

        # Get queue statistics
        queue_size = len(queue)

        return {
            "status": "healthy",
            "queue_size": queue_size,
            "redis": "connected",
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
        }
