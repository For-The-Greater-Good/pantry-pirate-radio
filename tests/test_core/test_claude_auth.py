"""Tests for Claude authentication manager."""

import pytest
import asyncio
import json
import os
from unittest.mock import MagicMock, AsyncMock, patch

from app.claude_auth_manager import ClaudeAuthManager


class TestClaudeAuthManager:
    """Test cases for ClaudeAuthManager."""

    @pytest.fixture
    def auth_manager(self):
        """Create a ClaudeAuthManager instance."""
        # Mock the ClaudeProvider and ClaudeConfig to avoid import issues
        with patch("app.claude_auth_manager.ClaudeProvider"):
            with patch("app.claude_auth_manager.ClaudeConfig"):
                return ClaudeAuthManager()

    def test_initialization(self, auth_manager):
        """Test ClaudeAuthManager initialization."""
        assert auth_manager is not None
        assert hasattr(auth_manager, "check_status")
        assert hasattr(auth_manager, "setup_interactive")
        assert hasattr(auth_manager, "check_config_files")
        assert hasattr(auth_manager, "test_simple_request")

    @pytest.mark.asyncio
    async def test_check_status_with_provider(self, auth_manager):
        """Test checking status with provider configured."""
        mock_provider = MagicMock()
        mock_provider.health_check = AsyncMock(
            return_value={
                "provider": "claude",
                "status": "healthy",
                "authenticated": True,
                "model": "claude-3-opus",
                "message": "All good",
            }
        )
        auth_manager.provider = mock_provider

        status = await auth_manager.check_status()
        assert status["provider"] == "claude"
        assert status["status"] == "healthy"
        assert status["authenticated"] is True

    @pytest.mark.asyncio
    async def test_check_status_without_provider(self):
        """Test checking status without provider configured."""
        # Create manager without mocking providers
        with patch("app.claude_auth_manager.ClaudeProvider", None):
            with patch("app.claude_auth_manager.ClaudeConfig", None):
                auth_manager = ClaudeAuthManager()

        status = await auth_manager.check_status()
        assert status["provider"] == "claude"
        assert status["status"] == "unhealthy"
        assert status["authenticated"] is False
        assert "Dependencies not available" in status["error"]

    @patch("app.claude_auth_manager.subprocess.run")
    def test_setup_interactive_success(self, mock_run, auth_manager):
        """Test successful interactive setup."""
        mock_run.return_value = MagicMock(returncode=0)

        result = auth_manager.setup_interactive()
        assert result == 0
        mock_run.assert_called_once()

    @patch("app.claude_auth_manager.subprocess.run")
    def test_setup_interactive_failure(self, mock_run, auth_manager):
        """Test failed interactive setup."""
        mock_run.return_value = MagicMock(returncode=1)

        result = auth_manager.setup_interactive()
        assert result == 1

    @patch("app.claude_auth_manager.subprocess.run")
    def test_setup_interactive_exception(self, mock_run, auth_manager):
        """Test interactive setup with exception."""
        mock_run.side_effect = Exception("Command not found")

        result = auth_manager.setup_interactive()
        assert result == 1

    def test_check_config_files_exists(self, auth_manager):
        """Test checking config files when they exist."""
        with patch("os.path.exists", return_value=True):
            with patch("os.listdir", return_value=["config.json", "auth.json"]):
                config_info = auth_manager.check_config_files()

                assert config_info["config_exists"] is True
                assert "config.json" in config_info["files"]
                assert "auth.json" in config_info["files"]

    def test_check_config_files_not_exists(self, auth_manager):
        """Test checking config files when they don't exist."""
        with patch("os.path.exists", return_value=False):
            config_info = auth_manager.check_config_files()

            assert config_info["config_exists"] is False
            assert config_info["files"] == []

    def test_check_config_files_error(self, auth_manager):
        """Test checking config files with error."""
        with patch("os.path.exists", return_value=True):
            with patch("os.listdir", side_effect=PermissionError("Access denied")):
                config_info = auth_manager.check_config_files()

                assert config_info["config_exists"] is True
                assert "error" in config_info

    @pytest.mark.asyncio
    async def test_test_simple_request_success(self, auth_manager):
        """Test simple request success."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(
                json.dumps({"result": "Hello!", "is_error": False}).encode("utf-8"),
                b"",
            )
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await auth_manager.test_simple_request()

            assert result["success"] is True
            assert result["return_code"] == 0
            assert "parsed_response" in result

    @pytest.mark.asyncio
    async def test_test_simple_request_failure(self, auth_manager):
        """Test simple request failure."""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"Error occurred"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await auth_manager.test_simple_request()

            assert result["success"] is False
            assert result["return_code"] == 1

    @pytest.mark.asyncio
    async def test_test_simple_request_timeout(self, auth_manager):
        """Test simple request timeout."""
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await auth_manager.test_simple_request()

            assert result["success"] is False
            assert "timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_test_simple_request_exception(self, auth_manager):
        """Test simple request with exception."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=Exception("Failed to create process"),
        ):
            result = await auth_manager.test_simple_request()

            assert result["success"] is False
            assert "Failed to create process" in result["error"]
