"""Unit tests for Claude authentication manager."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock the ClaudeProvider and ClaudeConfig imports at module level
with patch("app.claude_auth_manager.ClaudeProvider", None):
    with patch("app.claude_auth_manager.ClaudeConfig", None):
        from app.claude_auth_manager import ClaudeAuthManager


class TestClaudeAuthManager:
    """Test suite for ClaudeAuthManager."""

    def test_init_without_dependencies(self) -> None:
        """Test initialization without full dependencies."""
        # Force the fallback path by mocking the imports
        with patch("app.claude_auth_manager.ClaudeProvider", None):
            with patch("app.claude_auth_manager.ClaudeConfig", None):
                manager = ClaudeAuthManager()
                assert manager.config is None
                assert manager.provider is None

    @pytest.mark.asyncio
    async def test_check_status_without_dependencies(self) -> None:
        """Test status check without dependencies."""
        # Force the fallback path by creating a manager with None provider
        manager = ClaudeAuthManager()
        manager.provider = None  # Simulate missing dependencies

        status = await manager.check_status()

        assert status["provider"] == "claude"
        assert status["status"] == "unhealthy"
        assert status["authenticated"] is False
        assert "Dependencies not available" in status["error"]
        assert status["message"] == "Please run inside container"

    @pytest.mark.asyncio
    async def test_check_status_with_mocked_provider(self) -> None:
        """Test status check with mocked provider."""
        mock_config = MagicMock()
        mock_provider = AsyncMock()
        mock_provider.health_check.return_value = {
            "provider": "claude",
            "status": "healthy",
            "authenticated": True,
            "model": "claude-sonnet-4-20250514",
            "message": "Ready",
        }

        manager = ClaudeAuthManager()
        manager.config = mock_config
        manager.provider = mock_provider

        status = await manager.check_status()
        assert status["provider"] == "claude"
        assert status["status"] == "healthy"
        assert status["authenticated"] is True
        assert status["model"] == "claude-sonnet-4-20250514"

    def test_setup_interactive_success(self) -> None:
        """Test successful interactive setup."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        manager = ClaudeAuthManager()

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            with patch("sys.stdin"), patch("sys.stdout"), patch("sys.stderr"):
                result = manager.setup_interactive()

        assert result == 0
        mock_run.assert_called_once()
        # Verify the command was called with correct arguments
        call_args = mock_run.call_args[0][0]
        assert call_args == ["claude"]

    def test_setup_interactive_failure(self) -> None:
        """Test failed interactive setup."""
        mock_result = MagicMock()
        mock_result.returncode = 1

        manager = ClaudeAuthManager()

        with patch("subprocess.run", return_value=mock_result):
            with patch("sys.stdin"), patch("sys.stdout"), patch("sys.stderr"):
                result = manager.setup_interactive()

        assert result == 1

    def test_setup_interactive_keyboard_interrupt(self) -> None:
        """Test interactive setup with keyboard interrupt."""
        manager = ClaudeAuthManager()

        with patch("subprocess.run", side_effect=KeyboardInterrupt()):
            with patch("sys.stdin"), patch("sys.stdout"), patch("sys.stderr"):
                result = manager.setup_interactive()

        assert result == 1

    def test_setup_interactive_exception(self) -> None:
        """Test interactive setup with exception."""
        manager = ClaudeAuthManager()

        with patch("subprocess.run", side_effect=Exception("Test error")):
            with patch("sys.stdin"), patch("sys.stdout"), patch("sys.stderr"):
                result = manager.setup_interactive()

        assert result == 1

    def test_check_config_files_exists(self) -> None:
        """Test config file checking when directory exists."""
        manager = ClaudeAuthManager()

        test_files = ["config.json", "auth.txt"]

        with patch("os.environ.get", return_value="/test/home"):
            with patch("os.path.exists", return_value=True):
                with patch("os.listdir", return_value=test_files):
                    config = manager.check_config_files()

        assert config["home_directory"] == "/test/home"
        assert config["config_directory"] == "/test/home/.config/claude"
        assert config["config_exists"] is True
        assert config["files"] == test_files

    def test_check_config_files_not_exists(self) -> None:
        """Test config file checking when directory doesn't exist."""
        manager = ClaudeAuthManager()

        with patch("os.environ.get", return_value="/test/home"):
            with patch("os.path.exists", return_value=False):
                config = manager.check_config_files()

        assert config["home_directory"] == "/test/home"
        assert config["config_directory"] == "/test/home/.config/claude"
        assert config["config_exists"] is False
        assert config["files"] == []

    def test_check_config_files_permission_error(self) -> None:
        """Test config file checking with permission error."""
        manager = ClaudeAuthManager()

        with patch("os.environ.get", return_value="/test/home"):
            with patch("os.path.exists", return_value=True):
                with patch(
                    "os.listdir", side_effect=PermissionError("Permission denied")
                ):
                    config = manager.check_config_files()

        assert config["config_exists"] is True
        assert "error" in config
        assert "Permission denied" in config["error"]

    @pytest.mark.asyncio
    async def test_test_simple_request_success(self) -> None:
        """Test successful simple request."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (
            b'{"result": "Hello", "is_error": false}',
            b"",
        )

        manager = ClaudeAuthManager()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch(
                "asyncio.wait_for",
                return_value=(b'{"result": "Hello", "is_error": false}', b""),
            ):
                result = await manager.test_simple_request()

        assert result["success"] is True
        assert result["return_code"] == 0
        assert result["parsed_response"]["result"] == "Hello"

    @pytest.mark.asyncio
    async def test_test_simple_request_failure(self) -> None:
        """Test failed simple request."""
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b"", b"Error message")

        manager = ClaudeAuthManager()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(b"", b"Error message")):
                result = await manager.test_simple_request()

        assert result["success"] is False
        assert result["return_code"] == 1

    @pytest.mark.asyncio
    async def test_test_simple_request_timeout(self) -> None:
        """Test simple request timeout."""
        manager = ClaudeAuthManager()

        with patch("asyncio.create_subprocess_exec"):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                result = await manager.test_simple_request()

        assert result["success"] is False
        assert "timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_test_simple_request_exception(self) -> None:
        """Test simple request with exception."""
        manager = ClaudeAuthManager()

        with patch(
            "asyncio.create_subprocess_exec", side_effect=Exception("Test error")
        ):
            result = await manager.test_simple_request()

        assert result["success"] is False
        assert result["error"] == "Test error"

    @pytest.mark.asyncio
    async def test_test_simple_request_json_parse_error(self) -> None:
        """Test simple request with JSON parse error."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"Invalid JSON", b"")

        manager = ClaudeAuthManager()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(b"Invalid JSON", b"")):
                result = await manager.test_simple_request()

        assert result["success"] is True  # Non-JSON but successful return code
        assert result["return_code"] == 0
        assert "parsed_response" not in result


@pytest.mark.asyncio
async def test_main_status_command() -> None:
    """Test main function with status command."""
    mock_manager = AsyncMock()
    mock_manager.check_status.return_value = {
        "provider": "claude",
        "status": "healthy",
        "authenticated": True,
        "model": "claude-sonnet-4-20250514",
        "message": "Ready",
    }

    # Mock argparse to simulate status command
    with patch("argparse.ArgumentParser") as mock_parser:
        mock_args = MagicMock()
        mock_args.command = "status"
        mock_args.json = False
        mock_parser.return_value.parse_args.return_value = mock_args

        with patch(
            "app.claude_auth_manager.ClaudeAuthManager", return_value=mock_manager
        ):
            with patch("builtins.print") as mock_print:
                # Import and run main function
                from app.claude_auth_manager import main

                exit_code = await main()

    assert exit_code == 0
    mock_manager.check_status.assert_called_once()


@pytest.mark.asyncio
async def test_main_status_command_json() -> None:
    """Test main function with status command and JSON output."""
    mock_manager = AsyncMock()
    mock_manager.check_status.return_value = {
        "provider": "claude",
        "status": "healthy",
        "authenticated": True,
        "model": "claude-sonnet-4-20250514",
        "message": "Ready",
    }

    with patch("argparse.ArgumentParser") as mock_parser:
        mock_args = MagicMock()
        mock_args.command = "status"
        mock_args.json = True
        mock_parser.return_value.parse_args.return_value = mock_args

        with patch(
            "app.claude_auth_manager.ClaudeAuthManager", return_value=mock_manager
        ):
            with patch("builtins.print") as mock_print:
                from app.claude_auth_manager import main

                exit_code = await main()

    assert exit_code == 0
    # Verify JSON output was printed
    mock_print.assert_called()
    printed_output = mock_print.call_args[0][0]
    # Should be valid JSON
    json.loads(printed_output)


@pytest.mark.asyncio
async def test_main_setup_command() -> None:
    """Test main function with setup command."""
    mock_manager = MagicMock()
    mock_manager.setup_interactive.return_value = 0

    with patch("argparse.ArgumentParser") as mock_parser:
        mock_args = MagicMock()
        mock_args.command = "setup"
        mock_args.json = False
        mock_parser.return_value.parse_args.return_value = mock_args

        with patch(
            "app.claude_auth_manager.ClaudeAuthManager", return_value=mock_manager
        ):
            from app.claude_auth_manager import main

            exit_code = await main()

    assert exit_code == 0
    mock_manager.setup_interactive.assert_called_once()


@pytest.mark.asyncio
async def test_main_test_command() -> None:
    """Test main function with test command."""
    mock_manager = AsyncMock()
    mock_manager.test_simple_request.return_value = {
        "success": True,
        "return_code": 0,
        "parsed_response": {"result": "Hello"},
    }

    with patch("argparse.ArgumentParser") as mock_parser:
        mock_args = MagicMock()
        mock_args.command = "test"
        mock_args.json = False
        mock_parser.return_value.parse_args.return_value = mock_args

        with patch(
            "app.claude_auth_manager.ClaudeAuthManager", return_value=mock_manager
        ):
            with patch("builtins.print"):
                from app.claude_auth_manager import main

                exit_code = await main()

    assert exit_code == 0
    mock_manager.test_simple_request.assert_called_once()


@pytest.mark.asyncio
async def test_main_config_command() -> None:
    """Test main function with config command."""
    mock_manager = MagicMock()
    mock_manager.check_config_files.return_value = {
        "home_directory": "/test/home",
        "config_directory": "/test/home/.config/claude",
        "config_exists": True,
        "files": ["config.json"],
    }

    with patch("argparse.ArgumentParser") as mock_parser:
        mock_args = MagicMock()
        mock_args.command = "config"
        mock_args.json = False
        mock_parser.return_value.parse_args.return_value = mock_args

        with patch(
            "app.claude_auth_manager.ClaudeAuthManager", return_value=mock_manager
        ):
            with patch("builtins.print"):
                from app.claude_auth_manager import main

                exit_code = await main()

    assert exit_code == 0
    mock_manager.check_config_files.assert_called_once()
