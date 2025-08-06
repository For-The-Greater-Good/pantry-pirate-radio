"""Authentication and quota state management for Claude workers."""

import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from enum import Enum

import redis
from app.core.logging import get_logger

logger = get_logger().bind(module="auth_state")


class AuthStatus(Enum):
    """Authentication status types."""

    HEALTHY = "healthy"
    AUTH_FAILED = "auth_failed"
    QUOTA_EXCEEDED = "quota_exceeded"


class AuthStateManager:
    """Manages Claude authentication and quota state across workers."""

    def __init__(self, redis_client: redis.Redis):
        """Initialize auth state manager.

        Args:
            redis_client: Redis client for state storage
        """
        self.redis = redis_client
        self.auth_key = "claude:auth:status"
        self.quota_key = "claude:quota:status"
        self.last_check_key = "claude:last:check"

    def set_auth_failed(self, message: str, retry_after: int = 300) -> None:
        """Mark authentication as failed.

        Args:
            message: Error message describing the auth failure
            retry_after: Seconds to wait before retrying (default 5 minutes)
        """
        state = {
            "status": AuthStatus.AUTH_FAILED.value,
            "message": message,
            "timestamp": time.time(),
            "retry_at": time.time() + retry_after,
            "retry_after": retry_after,
        }

        # Store with TTL slightly longer than retry time
        self.redis.setex(
            self.auth_key, retry_after + 60, json.dumps(state)  # Extra minute buffer
        )

        logger.warning(
            f"Auth state set to FAILED: {message}. "
            f"Will retry in {retry_after} seconds"
        )

    def set_quota_exceeded(self, message: str, retry_after: int = 3600) -> None:
        """Mark quota as exceeded.

        Args:
            message: Error message describing the quota issue
            retry_after: Seconds to wait before retrying (default 1 hour)
        """
        state = {
            "status": AuthStatus.QUOTA_EXCEEDED.value,
            "message": message,
            "timestamp": time.time(),
            "retry_at": time.time() + retry_after,
            "retry_after": retry_after,
        }

        # Store with TTL slightly longer than retry time
        self.redis.setex(
            self.quota_key, retry_after + 60, json.dumps(state)  # Extra minute buffer
        )

        logger.warning(
            f"Quota state set to EXCEEDED: {message}. "
            f"Will retry in {retry_after} seconds ({retry_after/3600:.1f} hours)"
        )

    def set_healthy(self) -> None:
        """Mark authentication and quota as healthy."""
        # Clear any error states
        self.redis.delete(self.auth_key)
        self.redis.delete(self.quota_key)

        # Update last successful check
        self.redis.setex(
            self.last_check_key,
            3600,  # Keep for 1 hour
            json.dumps({"timestamp": time.time(), "status": "healthy"}),
        )

        logger.info("Auth state set to HEALTHY")

    def is_healthy(self) -> tuple[bool, Optional[Dict[str, Any]]]:
        """Check if auth and quota are healthy.

        Returns:
            Tuple of (is_healthy, error_details)
            If healthy, error_details is None
            If unhealthy, error_details contains status info
        """
        # Check auth status
        auth_data = self.redis.get(self.auth_key)
        if auth_data:
            auth_state = json.loads(auth_data)
            if auth_state.get("retry_at", 0) > time.time():
                # Add retry_in_seconds for convenience
                auth_state["retry_in_seconds"] = max(
                    0, int(auth_state.get("retry_at", 0) - time.time())
                )
                return False, auth_state

        # Check quota status
        quota_data = self.redis.get(self.quota_key)
        if quota_data:
            quota_state = json.loads(quota_data)
            if quota_state.get("retry_at", 0) > time.time():
                # Add retry_in_seconds for convenience
                quota_state["retry_in_seconds"] = max(
                    0, int(quota_state.get("retry_at", 0) - time.time())
                )
                return False, quota_state

        return True, None

    def get_status(self) -> Dict[str, Any]:
        """Get detailed status information.

        Returns:
            Dictionary with current auth and quota status
        """
        is_healthy, error_details = self.is_healthy()

        # Get last successful check
        last_check_data = self.redis.get(self.last_check_key)
        last_check = json.loads(last_check_data) if last_check_data else None

        status = {
            "healthy": is_healthy,
            "timestamp": time.time(),
            "last_successful_check": last_check,
        }

        if error_details:
            status["error"] = error_details
            status["error_type"] = error_details.get("status")
            status["retry_in_seconds"] = max(
                0, int(error_details.get("retry_at", 0) - time.time())
            )

        return status

    def should_check_auth(self, check_interval: int = 30) -> bool:
        """Determine if we should perform an auth check.

        Args:
            check_interval: Minimum seconds between checks

        Returns:
            True if we should check, False otherwise
        """
        # Always check if we're in an error state
        is_healthy, _ = self.is_healthy()
        if not is_healthy:
            return False  # Don't check while in error state

        # Check if enough time has passed since last check
        last_check_data = self.redis.get(self.last_check_key)
        if last_check_data:
            last_check = json.loads(last_check_data)
            last_timestamp = last_check.get("timestamp", 0)
            if time.time() - last_timestamp < check_interval:
                return False

        return True
