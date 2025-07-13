#!/usr/bin/env python3
"""Simple HTTP server for Claude health checks."""

import asyncio
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from app.claude_auth_manager import ClaudeAuthManager


class ClaudeHealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for Claude health checks."""

    def do_GET(self):  # noqa: N802
        """Handle GET requests."""
        parsed_path = urlparse(self.path)

        if parsed_path.path == "/health":
            self._handle_health()
        elif parsed_path.path == "/auth":
            self._handle_auth_status()
        else:
            self._send_error(404, "Not Found")

    def _handle_health(self):
        """Handle /health endpoint."""
        try:
            manager = ClaudeAuthManager()
            status = asyncio.run(manager.check_status())

            self._send_json_response(status)
        except Exception as e:
            self._send_error(500, f"Health check failed: {e}")

    def _handle_auth_status(self):
        """Handle /auth endpoint."""
        try:
            manager = ClaudeAuthManager()
            status = asyncio.run(manager.check_status())
            config = manager.check_config_files()
            test = asyncio.run(manager.test_simple_request())

            response = {
                "authentication": status,
                "configuration": config,
                "test_request": test,
            }

            self._send_json_response(response)
        except Exception as e:
            self._send_error(500, f"Auth status check failed: {e}")

    def _send_json_response(self, data):
        """Send JSON response."""
        response_json = json.dumps(data, indent=2)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_json)))
        self.end_headers()
        self.wfile.write(response_json.encode())

    def _send_error(self, code, message):
        """Send error response."""
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(message.encode())

    def log_message(self, format, *args):
        """Override to reduce log noise."""
        pass


def run_server(port=8080):
    """Run the health check server."""
    server = HTTPServer(("127.0.0.1", port), ClaudeHealthHandler)  # nosec B104
    print(f"🏥 Claude Health Server running on port {port}")
    print(f"   Health check: http://localhost:{port}/health")
    print(f"   Auth status:  http://localhost:{port}/auth")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down health server")
        server.shutdown()


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
