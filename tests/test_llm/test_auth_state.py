"""Tests for authentication state management."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from app.llm.queue.auth_state import AuthStateManager, AuthStatus


class TestAuthStateManager:
    """Tests for AuthStateManager."""

    def test_init(self):
        """Test AuthStateManager initialization."""
        mock_redis = MagicMock()
        manager = AuthStateManager(mock_redis)

        assert manager.redis == mock_redis
        assert manager.auth_key == "claude:auth:status"
        assert manager.quota_key == "claude:quota:status"
        assert manager.last_check_key == "claude:last:check"

    def test_set_auth_failed(self):
        """Test setting authentication as failed."""
        mock_redis = MagicMock()
        manager = AuthStateManager(mock_redis)

        with patch("time.time", return_value=1000.0):
            manager.set_auth_failed("Invalid credentials", retry_after=600)

        # Verify Redis call
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args

        assert call_args[0][0] == "claude:auth:status"
        assert call_args[0][1] == 660  # 600 + 60 buffer

        stored_data = json.loads(call_args[0][2])
        assert stored_data["status"] == AuthStatus.AUTH_FAILED.value
        assert stored_data["message"] == "Invalid credentials"
        assert stored_data["timestamp"] == 1000.0
        assert stored_data["retry_at"] == 1600.0  # 1000 + 600
        assert stored_data["retry_after"] == 600

    def test_set_quota_exceeded(self):
        """Test setting quota as exceeded."""
        mock_redis = MagicMock()
        manager = AuthStateManager(mock_redis)

        with patch("time.time", return_value=2000.0):
            manager.set_quota_exceeded("Rate limit exceeded", retry_after=7200)

        # Verify Redis call
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args

        assert call_args[0][0] == "claude:quota:status"
        assert call_args[0][1] == 7260  # 7200 + 60 buffer

        stored_data = json.loads(call_args[0][2])
        assert stored_data["status"] == AuthStatus.QUOTA_EXCEEDED.value
        assert stored_data["message"] == "Rate limit exceeded"
        assert stored_data["timestamp"] == 2000.0
        assert stored_data["retry_at"] == 9200.0  # 2000 + 7200
        assert stored_data["retry_after"] == 7200

    def test_set_healthy(self):
        """Test setting authentication and quota as healthy."""
        mock_redis = MagicMock()
        manager = AuthStateManager(mock_redis)

        with patch("time.time", return_value=3000.0):
            manager.set_healthy()

        # Verify Redis calls
        mock_redis.delete.assert_any_call("claude:auth:status")
        mock_redis.delete.assert_any_call("claude:quota:status")

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args

        assert call_args[0][0] == "claude:last:check"
        assert call_args[0][1] == 3600  # 1 hour

        stored_data = json.loads(call_args[0][2])
        assert stored_data["timestamp"] == 3000.0
        assert stored_data["status"] == "healthy"

    def test_is_healthy_when_healthy(self):
        """Test is_healthy returns True when no error states exist."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        manager = AuthStateManager(mock_redis)

        is_healthy, error_details = manager.is_healthy()

        assert is_healthy is True
        assert error_details is None

    def test_is_healthy_with_active_auth_failure(self):
        """Test is_healthy returns False when auth failure is still active."""
        mock_redis = MagicMock()
        manager = AuthStateManager(mock_redis)

        # Mock auth failure that's still active (retry time in future)
        auth_state = {
            "status": AuthStatus.AUTH_FAILED.value,
            "message": "Auth failed",
            "retry_at": time.time() + 300,  # 5 minutes from now
        }

        def mock_get(key):
            if key == "claude:auth:status":
                return json.dumps(auth_state)
            return None

        mock_redis.get.side_effect = mock_get

        is_healthy, error_details = manager.is_healthy()

        assert is_healthy is False
        assert error_details is not None
        assert error_details["status"] == AuthStatus.AUTH_FAILED.value
        assert "retry_in_seconds" in error_details
        assert error_details["retry_in_seconds"] > 0

    def test_is_healthy_with_expired_auth_failure(self):
        """Test is_healthy returns True when auth failure has expired."""
        mock_redis = MagicMock()
        manager = AuthStateManager(mock_redis)

        # Mock auth failure that has expired (retry time in past)
        auth_state = {
            "status": AuthStatus.AUTH_FAILED.value,
            "message": "Auth failed",
            "retry_at": time.time() - 300,  # 5 minutes ago
        }

        def mock_get(key):
            if key == "claude:auth:status":
                return json.dumps(auth_state)
            return None

        mock_redis.get.side_effect = mock_get

        is_healthy, error_details = manager.is_healthy()

        assert is_healthy is True
        assert error_details is None

    def test_is_healthy_with_active_quota_exceeded(self):
        """Test is_healthy returns False when quota exceeded is still active."""
        mock_redis = MagicMock()
        manager = AuthStateManager(mock_redis)

        # Mock quota exceeded that's still active
        quota_state = {
            "status": AuthStatus.QUOTA_EXCEEDED.value,
            "message": "Quota exceeded",
            "retry_at": time.time() + 1800,  # 30 minutes from now
        }

        def mock_get(key):
            if key == "claude:quota:status":
                return json.dumps(quota_state)
            return None

        mock_redis.get.side_effect = mock_get

        is_healthy, error_details = manager.is_healthy()

        assert is_healthy is False
        assert error_details is not None
        assert error_details["status"] == AuthStatus.QUOTA_EXCEEDED.value
        assert "retry_in_seconds" in error_details
        assert error_details["retry_in_seconds"] > 0

    def test_get_status_healthy(self):
        """Test get_status when everything is healthy."""
        mock_redis = MagicMock()
        manager = AuthStateManager(mock_redis)

        # Mock healthy state
        last_check = {"timestamp": 4000.0, "status": "healthy"}

        def mock_get(key):
            if key == "claude:last:check":
                return json.dumps(last_check)
            return None

        mock_redis.get.side_effect = mock_get

        with patch("time.time", return_value=5000.0):
            status = manager.get_status()

        assert status["healthy"] is True
        assert status["timestamp"] == 5000.0
        assert status["last_successful_check"] == last_check
        assert "error" not in status

    def test_get_status_with_error(self):
        """Test get_status when there's an error state."""
        mock_redis = MagicMock()
        manager = AuthStateManager(mock_redis)

        # Mock error state
        error_details = {
            "status": AuthStatus.AUTH_FAILED.value,
            "message": "Auth failed",
            "retry_at": 6000.0,
        }

        def mock_get(key):
            if key == "claude:auth:status":
                return json.dumps(error_details)
            return None

        mock_redis.get.side_effect = mock_get

        with patch("time.time", return_value=5000.0):
            status = manager.get_status()

        assert status["healthy"] is False
        assert status["timestamp"] == 5000.0
        assert status["error"] is not None
        assert status["error_type"] == AuthStatus.AUTH_FAILED.value
        assert status["retry_in_seconds"] == 1000  # 6000 - 5000

    def test_should_check_auth_unhealthy_state(self):
        """Test should_check_auth returns False when in error state."""
        mock_redis = MagicMock()
        manager = AuthStateManager(mock_redis)

        # Mock unhealthy state
        with patch.object(
            manager, "is_healthy", return_value=(False, {"error": "test"})
        ):
            result = manager.should_check_auth()

        assert result is False

    def test_should_check_auth_no_last_check(self):
        """Test should_check_auth returns True when no last check exists."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        manager = AuthStateManager(mock_redis)

        # Mock healthy state
        with patch.object(manager, "is_healthy", return_value=(True, None)):
            result = manager.should_check_auth()

        assert result is True

    def test_should_check_auth_interval_not_passed(self):
        """Test should_check_auth returns False when interval hasn't passed."""
        mock_redis = MagicMock()
        manager = AuthStateManager(mock_redis)

        # Mock recent last check
        last_check = {"timestamp": time.time() - 10}  # 10 seconds ago
        mock_redis.get.return_value = json.dumps(last_check)

        # Mock healthy state
        with patch.object(manager, "is_healthy", return_value=(True, None)):
            result = manager.should_check_auth(check_interval=30)

        assert result is False

    def test_should_check_auth_interval_passed(self):
        """Test should_check_auth returns True when interval has passed."""
        mock_redis = MagicMock()
        manager = AuthStateManager(mock_redis)

        # Mock old last check
        last_check = {"timestamp": time.time() - 60}  # 1 minute ago
        mock_redis.get.return_value = json.dumps(last_check)

        # Mock healthy state
        with patch.object(manager, "is_healthy", return_value=(True, None)):
            result = manager.should_check_auth(check_interval=30)

        assert result is True

    def test_should_check_auth_invalid_last_check_data(self):
        """Test should_check_auth handles invalid last check data gracefully."""
        mock_redis = MagicMock()
        manager = AuthStateManager(mock_redis)

        # Mock invalid last check data
        last_check = {}  # Missing timestamp
        mock_redis.get.return_value = json.dumps(last_check)

        # Mock healthy state
        with patch.object(manager, "is_healthy", return_value=(True, None)):
            result = manager.should_check_auth(check_interval=30)

        # Should return True because timestamp defaults to 0, making the interval passed
        assert result is True


class TestAuthStatus:
    """Tests for AuthStatus enum."""

    def test_auth_status_values(self):
        """Test that AuthStatus enum has expected values."""
        assert AuthStatus.HEALTHY.value == "healthy"
        assert AuthStatus.AUTH_FAILED.value == "auth_failed"
        assert AuthStatus.QUOTA_EXCEEDED.value == "quota_exceeded"

