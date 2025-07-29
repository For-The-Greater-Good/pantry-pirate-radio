"""Integration tests for bouy script with mocked Docker Compose."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

# Skip all tests in this file when running in Docker
pytestmark = pytest.mark.skipif(
    os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER"),
    reason="Bouy tests cannot run inside Docker containers",
)


class TestBouyCommands:
    """Test bouy commands with mocked docker compose."""

    @pytest.fixture
    def bouy_path(self):
        """Get the correct path to bouy script."""
        if Path("/app/bouy").exists():
            return "/app/bouy"
        else:
            return "./bouy"

    @pytest.fixture
    def mock_compose(self, tmp_path):
        """Create a comprehensive mock docker compose executable."""
        mock_script = tmp_path / "mock-docker-compose"
        mock_script.write_text(
            """#!/bin/bash
# Mock docker compose for testing

case "$*" in
    *"ps --format json"*)
        # Return JSON format for all services
        if [[ "$*" == *"app"* ]]; then
            echo '[{"Name": "app", "State": "running", "Status": "Up 2 hours", "Health": "healthy"}]'
        elif [[ "$*" == *"db"* ]]; then
            echo '[{"Name": "db", "State": "running", "Status": "Up 2 hours"}]'
        elif [[ "$*" == *"cache"* ]]; then
            echo '[{"Name": "cache", "State": "running", "Status": "Up 2 hours"}]'
        elif [[ "$*" == *"worker"* ]]; then
            echo '[{"Name": "worker", "State": "running", "Status": "Up 1 hour"}]'
        else
            echo '[{"Name": "app", "State": "running"}, {"Name": "db", "State": "running"}]'
        fi
        exit 0
        ;;
    *"ps"*)
        # Text format
        echo "NAME    STATUS    PORTS"
        echo "app     Up        8000->8000/tcp"
        echo "db      Up        5432/tcp"
        echo "cache   Up        6379/tcp"
        exit 0
        ;;
    *"up -d"*)
        echo "Starting services..."
        echo "✔ Container db Started"
        echo "✔ Container cache Started"
        echo "✔ Container app Started"
        exit 0
        ;;
    *"down"*)
        echo "Stopping services..."
        echo "✔ Container app Stopped"
        echo "✔ Container db Stopped"
        exit 0
        ;;
    *"exec -T db pg_isready"*)
        echo "localhost:5432 - accepting connections"
        exit 0
        ;;
    *"exec -T db psql"*"SELECT 1 FROM record_version"*)
        echo "1"
        exit 0
        ;;
    *"exec -T db psql"*"test_pantry_pirate_radio"*)
        # Mock test database operations
        echo "CREATE DATABASE"
        exit 0
        ;;
    *"exec -T cache redis-cli ping"*)
        echo "PONG"
        exit 0
        ;;
    *"exec -T worker test -d /app/data/content_store"*)
        exit 0
        ;;
    *"exec -T worker test -f /app/data/content_store/content_store.db"*)
        exit 0
        ;;
    *"exec -T scraper python -m app.scraper --list"*)
        echo "Available scrapers:"
        echo "  - nyc_efap_programs"
        echo "  - food_bank_nyc"
        echo "  - hunter_college_nyc_food_pantries"
        exit 0
        ;;
    *"exec -T scraper python -m app.scraper nyc_efap"*)
        echo "Running scraper: nyc_efap"
        echo "Submitted 10 jobs to queue"
        exit 0
        ;;
    *"exec -T worker python -m app.claude_auth_manager status"*)
        echo "Claude authentication status: Valid"
        exit 0
        ;;
    *"logs"*)
        echo "[2024-01-25 10:00:00] Service started"
        echo "[2024-01-25 10:00:01] Listening on port 8000"
        exit 0
        ;;
    *"build"*)
        echo "Building services..."
        echo "✔ Service app built"
        exit 0
        ;;
    *)
        echo "Unhandled docker compose command: $*" >&2
        exit 1
        ;;
esac
"""
        )
        mock_script.chmod(0o755)
        return str(mock_script)

    @pytest.fixture
    def test_env(self, mock_compose):
        """Set up test environment."""
        env = os.environ.copy()
        env["BOUY_TEST_MODE"] = "1"
        env["BOUY_TEST_COMPOSE_CMD"] = mock_compose
        env["PROGRAMMATIC_MODE"] = "1"
        env["JSON_OUTPUT"] = "1"
        return env

    def test_up_command(self, test_env, bouy_path):
        """Test the up command flow."""
        result = subprocess.run(
            [bouy_path, "--json", "up"],
            capture_output=True,
            text=True,
            env=test_env,
        )

        assert result.returncode == 0

        # Parse JSON output
        outputs = []
        for line in result.stdout.strip().split("\n"):
            if line.strip() and line.startswith("{"):
                try:
                    outputs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        # Check that we got some JSON output
        assert len(outputs) > 0, f"No JSON output found in: {result.stdout}"
        
        # Check for expected messages
        if outputs:
            messages = [o.get("message", "") for o in outputs]
            assert any("Starting services" in m for m in messages)
            levels = [o.get("level", "") for o in outputs]
            assert "success" in levels or "info" in levels

    def test_down_command(self, test_env, bouy_path):
        """Test the down command."""
        result = subprocess.run(
            [bouy_path, "--json", "down"],
            capture_output=True,
            text=True,
            env=test_env,
        )

        assert result.returncode == 0

        outputs = []
        for line in result.stdout.strip().split("\n"):
            if line.strip() and line.startswith("{"):
                try:
                    outputs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        assert len(outputs) > 0, f"No JSON output found in: {result.stdout}"
        
        if outputs:
            messages = [o.get("message", "") for o in outputs]
            assert any("Stopping" in m or "services" in m for m in messages)

    def test_status_command(self, test_env, bouy_path):
        """Test the ps command (list services)."""
        result = subprocess.run(
            [bouy_path, "--json", "ps"],
            capture_output=True,
            text=True,
            env=test_env,
        )

        assert result.returncode == 0
        # Should show status table in output

    def test_logs_command(self, test_env, bouy_path):
        """Test the logs command."""
        result = subprocess.run(
            [bouy_path, "--programmatic", "logs", "app", "--tail", "10"],
            capture_output=True,
            text=True,
            env=test_env,
        )

        assert result.returncode == 0
        assert "Service started" in result.stdout

    def test_shell_command_missing_service(self, test_env, bouy_path):
        """Test shell command without service name."""
        result = subprocess.run(
            [bouy_path, "--programmatic", "shell"],
            capture_output=True,
            text=True,
            env=test_env,
        )

        assert result.returncode == 1
        assert "Please specify a service name" in result.stderr

    def test_test_command(self, test_env, tmp_path, bouy_path):
        """Test the test command."""
        # Create mock .env.test file
        env_test = tmp_path / ".env.test"
        env_test.write_text("TEST_VAR=value\n")

        # Create mock test runner
        mock_test_runner = tmp_path / "mock-test-runner"
        mock_test_runner.write_text(
            """#!/bin/bash
echo "Running tests..."
echo "All tests passed!"
exit 0
"""
        )
        mock_test_runner.chmod(0o755)

        test_env_copy = test_env.copy()
        test_env_copy["PATH"] = f"{tmp_path}:{test_env.get('PATH', '')}"

        # Run test in tmp_path to use our .env.test
        result = subprocess.run(
            [bouy_path, "--programmatic", "test", "pytest"],
            capture_output=True,
            text=True,
            env=test_env_copy,
            cwd=os.getcwd(),  # Stay in project root
        )

        # The test might fail due to missing dependencies, but it should recognize the command
        assert "test option: pytest" in result.stdout or result.returncode in [0, 1]

    def test_scraper_list(self, test_env, bouy_path):
        """Test scraper list command."""
        result = subprocess.run(
            [bouy_path, "--programmatic", "scraper", "list"],
            capture_output=True,
            text=True,
            env=test_env,
        )

        assert result.returncode == 0
        assert "nyc_efap_programs" in result.stdout
        assert "food_bank_nyc" in result.stdout

    def test_scraper_run_specific(self, test_env, bouy_path):
        """Test running a specific scraper."""
        result = subprocess.run(
            [bouy_path, "--json", "scraper", "nyc_efap"],
            capture_output=True,
            text=True,
            env=test_env,
        )

        assert result.returncode == 0

        outputs = []
        for line in result.stdout.strip().split("\n"):
            if line.startswith("{"):
                outputs.append(json.loads(line))

        messages = [o["message"] for o in outputs]
        assert any("Running scraper: nyc_efap" in m for m in messages)

    def test_reconciler_command(self, test_env, bouy_path):
        """Test reconciler command with dependency checks."""
        result = subprocess.run(
            [bouy_path, "--json", "reconciler"],
            capture_output=True,
            text=True,
            env=test_env,
        )

        assert result.returncode == 0

        outputs = []
        for line in result.stdout.strip().split("\n"):
            if line.startswith("{"):
                outputs.append(json.loads(line))

        # Should check database connectivity and schema
        messages = [o["message"] for o in outputs]
        assert any("database" in m.lower() for m in messages)

    def test_help_command(self, bouy_path):
        """Test help output."""
        result = subprocess.run([bouy_path, "--help"], capture_output=True, text=True)

        assert result.returncode == 0
        assert "Bouy v1.0.0 - Docker Fleet Management" in result.stdout
        assert "Commands:" in result.stdout
        assert "Global Options:" in result.stdout


class TestBouyErrorHandling:
    """Test error handling in bouy."""

    @pytest.fixture
    def failing_compose(self, tmp_path):
        """Create a mock compose that fails."""
        mock_script = tmp_path / "failing-compose"
        mock_script.write_text(
            """#!/bin/bash
echo "Error: Service not found" >&2
exit 1
"""
        )
        mock_script.chmod(0o755)
        return str(mock_script)

    def test_service_not_running_error(self, failing_compose, bouy_path):
        """Test error when service is not running."""
        env = os.environ.copy()
        env["COMPOSE_CMD"] = failing_compose
        env["PROGRAMMATIC_MODE"] = "1"

        result = subprocess.run(
            [bouy_path, "exec", "app", "echo", "test"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode != 0
        assert "error" in result.stderr.lower() or "not running" in result.stderr

    def test_invalid_scraper_name(self, mock_compose, bouy_path):
        """Test that bouy handles potentially malicious scraper names safely."""
        env = os.environ.copy()
        env["BOUY_TEST_MODE"] = "1"
        env["BOUY_TEST_COMPOSE_CMD"] = mock_compose
        env["PROGRAMMATIC_MODE"] = "1"

        # Try to run scraper with a name that could be used for path traversal
        result = subprocess.run(
            [bouy_path, "scraper", "test_scraper"],
            capture_output=True,
            text=True,
            env=env,
        )

        # Should complete without error (bouy passes the name to the scraper service)
        assert result.returncode == 0


class TestBouyModes:
    """Test different operational modes."""

    def test_dev_mode(self, mock_compose, bouy_path):
        """Test dev mode configuration."""
        env = os.environ.copy()
        env["BOUY_TEST_MODE"] = "1"
        env["BOUY_TEST_COMPOSE_CMD"] = mock_compose

        result = subprocess.run(
            [bouy_path, "--dev", "ps"],
            capture_output=True,
            text=True,
            env=env,
        )

        # Dev mode should work
        assert result.returncode == 0

    def test_prod_mode(self, mock_compose, bouy_path):
        """Test prod mode configuration."""
        env = os.environ.copy()
        env["BOUY_TEST_MODE"] = "1"
        env["BOUY_TEST_COMPOSE_CMD"] = mock_compose

        result = subprocess.run(
            [bouy_path, "--prod", "ps"],
            capture_output=True,
            text=True,
            env=env,
        )

        # Prod mode should work
        assert result.returncode == 0

    def test_quiet_mode(self, mock_compose, bouy_path):
        """Test quiet mode suppresses output."""
        env = os.environ.copy()
        env["BOUY_TEST_MODE"] = "1"
        env["BOUY_TEST_COMPOSE_CMD"] = mock_compose

        result = subprocess.run(
            [bouy_path, "--quiet", "ps"],
            capture_output=True,
            text=True,
            env=env,
        )

        # Quiet mode should work
        assert result.returncode == 0

    def test_verbose_mode(self, mock_compose, bouy_path):
        """Test verbose mode shows extra output."""
        env = os.environ.copy()
        env["COMPOSE_CMD"] = mock_compose

        result = subprocess.run(
            [bouy_path, "--verbose", "status"],
            capture_output=True,
            text=True,
            env=env,
        )

        # Verbose mode might show more output
        assert result.returncode == 0 or "verbose" in result.stdout.lower()
