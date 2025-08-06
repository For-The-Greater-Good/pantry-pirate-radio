#!/usr/bin/env python3
"""Simple HTTP server for Claude health checks."""

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

import redis

from app.claude_auth_manager import ClaudeAuthManager
from app.llm.queue.auth_state import AuthStateManager


class ClaudeHealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for Claude health checks."""

    def do_GET(self):  # noqa: N802
        """Handle GET requests."""
        parsed_path = urlparse(self.path)

        if parsed_path.path == "/health":
            self._handle_health()
        elif parsed_path.path == "/auth":
            self._handle_auth_status()
        elif parsed_path.path == "/worker-status":
            self._handle_worker_status()
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

    def _handle_worker_status(self):
        """Handle /worker-status endpoint."""
        try:
            # Connect to Redis
            redis_url = os.environ.get("REDIS_URL", "redis://cache:6379")
            redis_client = redis.from_url(redis_url)

            # Get auth state
            auth_manager = AuthStateManager(redis_client)
            auth_status = auth_manager.get_status()

            # Get worker information from RQ
            from rq import Worker

            workers = Worker.all(connection=redis_client)

            worker_info = []
            for worker in workers:
                worker_info.append(
                    {
                        "name": worker.name,
                        "state": worker.state,
                        "current_job": (
                            str(worker.get_current_job_id())
                            if worker.get_current_job_id()
                            else None
                        ),
                        "birth_date": (
                            worker.birth_date.isoformat() if worker.birth_date else None
                        ),
                        "last_heartbeat": (
                            worker.last_heartbeat.isoformat()
                            if worker.last_heartbeat
                            else None
                        ),
                    }
                )

            # Get queue information
            from rq import Queue

            llm_queue = Queue("llm", connection=redis_client)

            queue_info = {
                "name": "llm",
                "count": llm_queue.count,
                "is_empty": llm_queue.is_empty(),
            }

            response = {
                "auth_state": auth_status,
                "workers": {"total": len(workers), "details": worker_info},
                "queue": queue_info,
                "recommendations": [],
            }

            # Add recommendations based on state
            if not auth_status["healthy"]:
                error_type = auth_status.get("error_type", "unknown")
                if error_type == "auth_failed":
                    response["recommendations"].append(
                        "Run: docker compose exec worker python -m app.claude_auth_manager setup"
                    )
                elif error_type == "quota_exceeded":
                    retry_in = auth_status.get("retry_in_seconds", 0)
                    response["recommendations"].append(
                        f"Wait {retry_in} seconds ({retry_in/3600:.1f} hours) for quota reset"
                    )

            self._send_json_response(response)
        except Exception as e:
            self._send_error(500, f"Worker status check failed: {e}")

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
    print(f"   Health check:   http://localhost:{port}/health")
    print(f"   Auth status:    http://localhost:{port}/auth")
    print(f"   Worker status:  http://localhost:{port}/worker-status")

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
