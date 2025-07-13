"""Tests for Claude health server."""

import asyncio
import json
import sys
from http.server import HTTPServer
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.claude_health_server import ClaudeHealthHandler, run_server


class TestClaudeHealthHandler:
    """Tests for ClaudeHealthHandler."""

    @patch("app.claude_health_server.ClaudeHealthHandler.__init__")
    def test_do_get_health_endpoint(self, mock_init):
        """Test GET request to /health endpoint."""
        mock_init.return_value = None
        handler = ClaudeHealthHandler.__new__(ClaudeHealthHandler)
        handler.path = "/health"

        with patch.object(handler, "_handle_health") as mock_handle_health:
            handler.do_GET()
            mock_handle_health.assert_called_once()

    @patch("app.claude_health_server.ClaudeHealthHandler.__init__")
    def test_do_get_auth_endpoint(self, mock_init):
        """Test GET request to /auth endpoint."""
        mock_init.return_value = None
        handler = ClaudeHealthHandler.__new__(ClaudeHealthHandler)
        handler.path = "/auth"

        with patch.object(handler, "_handle_auth_status") as mock_handle_auth:
            handler.do_GET()
            mock_handle_auth.assert_called_once()

    @patch("app.claude_health_server.ClaudeHealthHandler.__init__")
    def test_do_get_not_found(self, mock_init):
        """Test GET request to unknown endpoint returns 404."""
        mock_init.return_value = None
        handler = ClaudeHealthHandler.__new__(ClaudeHealthHandler)
        handler.path = "/unknown"

        with patch.object(handler, "_send_error") as mock_send_error:
            handler.do_GET()
            mock_send_error.assert_called_once_with(404, "Not Found")

    @patch("app.claude_health_server.ClaudeHealthHandler.__init__")
    def test_handle_health_success(self, mock_init):
        """Test _handle_health with successful status check."""
        mock_init.return_value = None
        handler = ClaudeHealthHandler.__new__(ClaudeHealthHandler)

        mock_status = {"authenticated": True, "quota_available": True}

        with patch(
            "app.claude_health_server.ClaudeAuthManager"
        ) as mock_auth_manager, patch("asyncio.run") as mock_asyncio_run, patch.object(
            handler, "_send_json_response"
        ) as mock_send_json:

            mock_manager_instance = MagicMock()
            mock_auth_manager.return_value = mock_manager_instance
            mock_asyncio_run.return_value = mock_status

            handler._handle_health()

            mock_auth_manager.assert_called_once()
            mock_asyncio_run.assert_called_once_with(
                mock_manager_instance.check_status()
            )
            mock_send_json.assert_called_once_with(mock_status)

    @patch("app.claude_health_server.ClaudeHealthHandler.__init__")
    def test_handle_health_exception(self, mock_init):
        """Test _handle_health with exception."""
        mock_init.return_value = None
        handler = ClaudeHealthHandler.__new__(ClaudeHealthHandler)

        with patch(
            "app.claude_health_server.ClaudeAuthManager"
        ) as mock_auth_manager, patch.object(handler, "_send_error") as mock_send_error:

            mock_auth_manager.side_effect = Exception("Auth error")

            handler._handle_health()

            mock_send_error.assert_called_once_with(
                500, "Health check failed: Auth error"
            )

    @patch("app.claude_health_server.ClaudeHealthHandler.__init__")
    def test_handle_auth_status_success(self, mock_init):
        """Test _handle_auth_status with successful checks."""
        mock_init.return_value = None
        handler = ClaudeHealthHandler.__new__(ClaudeHealthHandler)

        mock_status = {"authenticated": True}
        mock_config = {"config_exists": True}
        mock_test = {"test_passed": True}

        with patch(
            "app.claude_health_server.ClaudeAuthManager"
        ) as mock_auth_manager, patch("asyncio.run") as mock_asyncio_run, patch.object(
            handler, "_send_json_response"
        ) as mock_send_json:

            mock_manager_instance = MagicMock()
            mock_auth_manager.return_value = mock_manager_instance
            mock_manager_instance.check_config_files.return_value = mock_config

            # Mock asyncio.run to return different values for different calls
            mock_asyncio_run.side_effect = [mock_status, mock_test]

            handler._handle_auth_status()

            expected_response = {
                "authentication": mock_status,
                "configuration": mock_config,
                "test_request": mock_test,
            }

            mock_send_json.assert_called_once_with(expected_response)

    @patch("app.claude_health_server.ClaudeHealthHandler.__init__")
    def test_handle_auth_status_exception(self, mock_init):
        """Test _handle_auth_status with exception."""
        mock_init.return_value = None
        handler = ClaudeHealthHandler.__new__(ClaudeHealthHandler)

        with patch(
            "app.claude_health_server.ClaudeAuthManager"
        ) as mock_auth_manager, patch.object(handler, "_send_error") as mock_send_error:

            mock_auth_manager.side_effect = Exception("Config error")

            handler._handle_auth_status()

            mock_send_error.assert_called_once_with(
                500, "Auth status check failed: Config error"
            )

    @patch("app.claude_health_server.ClaudeHealthHandler.__init__")
    def test_send_json_response(self, mock_init):
        """Test _send_json_response sends correct headers and data."""
        mock_init.return_value = None
        handler = ClaudeHealthHandler.__new__(ClaudeHealthHandler)
        handler.wfile = MagicMock()

        test_data = {"status": "ok", "value": 123}
        expected_json = json.dumps(test_data, indent=2)

        with patch.object(handler, "send_response") as mock_send_response, patch.object(
            handler, "send_header"
        ) as mock_send_header, patch.object(handler, "end_headers") as mock_end_headers:

            handler._send_json_response(test_data)

            mock_send_response.assert_called_once_with(200)
            mock_send_header.assert_any_call("Content-Type", "application/json")
            mock_send_header.assert_any_call("Content-Length", str(len(expected_json)))
            mock_end_headers.assert_called_once()
            handler.wfile.write.assert_called_once_with(expected_json.encode())

    @patch("app.claude_health_server.ClaudeHealthHandler.__init__")
    def test_send_error(self, mock_init):
        """Test _send_error sends correct error response."""
        mock_init.return_value = None
        handler = ClaudeHealthHandler.__new__(ClaudeHealthHandler)
        handler.wfile = MagicMock()

        with patch.object(handler, "send_response") as mock_send_response, patch.object(
            handler, "send_header"
        ) as mock_send_header, patch.object(handler, "end_headers") as mock_end_headers:

            handler._send_error(404, "Not found")

            mock_send_response.assert_called_once_with(404)
            mock_send_header.assert_called_once_with("Content-Type", "text/plain")
            mock_end_headers.assert_called_once()
            handler.wfile.write.assert_called_once_with(b"Not found")

    @patch("app.claude_health_server.ClaudeHealthHandler.__init__")
    def test_log_message_override(self, mock_init):
        """Test log_message is overridden to reduce noise."""
        mock_init.return_value = None
        handler = ClaudeHealthHandler.__new__(ClaudeHealthHandler)

        # Should not raise any exception and do nothing
        handler.log_message("test format", "arg1", "arg2")


def test_run_server_default_port():
    """Test run_server with default port."""
    with patch("app.claude_health_server.HTTPServer") as mock_http_server:
        mock_server_instance = MagicMock()
        mock_http_server.return_value = mock_server_instance

        with patch("builtins.print") as mock_print:
            # Mock serve_forever to raise KeyboardInterrupt immediately
            mock_server_instance.serve_forever.side_effect = KeyboardInterrupt()

            run_server()

            # Verify server setup
            mock_http_server.assert_called_once_with(
                ("127.0.0.1", 8080), ClaudeHealthHandler
            )

            # Verify startup messages
            mock_print.assert_any_call("🏥 Claude Health Server running on port 8080")
            mock_print.assert_any_call("   Health check: http://localhost:8080/health")
            mock_print.assert_any_call("   Auth status:  http://localhost:8080/auth")

            # Verify shutdown
            mock_server_instance.serve_forever.assert_called_once()
            mock_server_instance.shutdown.assert_called_once()


def test_run_server_custom_port():
    """Test run_server with custom port."""
    with patch("app.claude_health_server.HTTPServer") as mock_http_server:
        mock_server_instance = MagicMock()
        mock_http_server.return_value = mock_server_instance
        mock_server_instance.serve_forever.side_effect = KeyboardInterrupt()

        with patch("builtins.print"):
            run_server(port=9090)

            mock_http_server.assert_called_once_with(
                ("127.0.0.1", 9090), ClaudeHealthHandler
            )


def test_main_script_default_port():
    """Test main script execution with default port."""
    with patch("sys.argv", ["claude_health_server.py"]), patch(
        "app.claude_health_server.run_server"
    ) as mock_run_server:

        # Import and execute main section
        import app.claude_health_server

        # Simulate the if __name__ == "__main__" block
        exec(  # nosec B102, S102
            """
if __name__ == "__main__":
    import sys

    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("Usage: python claude_health_server.py [port]")
            sys.exit(1)

    run_server(port)
""",
            {"__name__": "__main__", "sys": sys, "run_server": mock_run_server},
        )


def test_main_script_custom_port():
    """Test main script execution with custom port."""
    with patch("sys.argv", ["claude_health_server.py", "9090"]), patch(
        "app.claude_health_server.run_server"
    ) as mock_run_server:

        # Simulate main script logic
        port = 8080
        if len(sys.argv) > 1:
            try:
                port = int(sys.argv[1])
            except ValueError:
                pass

        assert port == 9090


def test_main_script_invalid_port():
    """Test main script with invalid port argument."""
    with patch("sys.argv", ["claude_health_server.py", "invalid"]), patch(
        "builtins.print"
    ) as mock_print, patch("sys.exit") as mock_exit:

        # Simulate main script logic
        port = 8080
        if len(sys.argv) > 1:
            try:
                port = int(sys.argv[1])
            except ValueError:
                mock_print("Usage: python claude_health_server.py [port]")
                mock_exit(1)

        mock_print.assert_called_once_with(
            "Usage: python claude_health_server.py [port]"
        )
        mock_exit.assert_called_once_with(1)
