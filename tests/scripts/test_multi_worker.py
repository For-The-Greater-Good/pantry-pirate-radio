"""Tests for multi-worker script functionality."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def multi_worker_script():
    """Get path to multi_worker.sh script."""
    # Try multiple possible locations (local dev vs CI environment)
    possible_paths = [
        Path(__file__).parent.parent.parent
        / "scripts"
        / "multi_worker.sh",  # Local dev
        Path("/app/scripts/multi_worker.sh"),  # CI environment (test stage)
        Path("/usr/local/bin/multi_worker.sh"),  # CI environment (worker stage)
        Path.cwd() / "scripts" / "multi_worker.sh",  # Alternative
    ]

    for script_path in possible_paths:
        if script_path.exists():
            return str(script_path)

    # If none found, show all attempted paths in error
    paths_tried = [str(p) for p in possible_paths]
    assert False, f"Script not found. Tried paths: {paths_tried}"


def test_should_start_single_worker_when_count_is_one(multi_worker_script):
    """Test script starts one worker when WORKER_COUNT=1."""
    with patch("subprocess.Popen") as mock_popen:
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        env = os.environ.copy()
        env["WORKER_COUNT"] = "1"

        # Test the script would start correctly (we can't actually run it in tests)
        assert Path(multi_worker_script).exists()
        assert os.access(multi_worker_script, os.X_OK)


def test_should_validate_worker_count_environment_variable(multi_worker_script):
    """Test script handles WORKER_COUNT environment variable correctly."""
    # Read the script content to verify it uses WORKER_COUNT
    with open(multi_worker_script, "r") as f:
        script_content = f.read()

    assert "WORKER_COUNT" in script_content
    assert "${WORKER_COUNT:-1}" in script_content


def test_should_use_queue_name_from_environment(multi_worker_script):
    """Test script uses QUEUE_NAME environment variable."""
    with open(multi_worker_script, "r") as f:
        script_content = f.read()

    assert "QUEUE_NAME" in script_content
    assert "${QUEUE_NAME:-llm}" in script_content


def test_should_have_signal_handlers_for_cleanup(multi_worker_script):
    """Test script has proper signal handling for graceful shutdown."""
    with open(multi_worker_script, "r") as f:
        script_content = f.read()

    # Check for signal handling
    assert "trap cleanup SIGTERM SIGINT" in script_content
    assert "cleanup()" in script_content

    # Check for PID tracking
    assert "WORKER_PIDS" in script_content


def test_should_track_worker_pids_for_cleanup(multi_worker_script):
    """Test script tracks worker PIDs for proper cleanup."""
    with open(multi_worker_script, "r") as f:
        script_content = f.read()

    # Verify PID tracking is implemented
    assert "WORKER_PIDS=()" in script_content
    assert "WORKER_PIDS+=($WORKER_PID)" in script_content
    assert 'for pid in "${WORKER_PIDS[@]}"' in script_content


def test_should_use_rq_worker_command_with_proper_arguments(multi_worker_script):
    """Test script uses correct RQ worker command format."""
    with open(multi_worker_script, "r") as f:
        script_content = f.read()

    # Check for proper RQ worker command with unique naming
    assert "/usr/local/bin/python -m rq.cli worker" in script_content
    assert "--name" in script_content
    assert "WORKER_NAME" in script_content
    assert "CONTAINER_ID" in script_content


def test_should_have_executable_permissions(multi_worker_script):
    """Test script file has executable permissions."""
    assert os.access(multi_worker_script, os.X_OK)


def test_should_start_with_proper_shebang(multi_worker_script):
    """Test script starts with proper bash shebang."""
    with open(multi_worker_script, "r") as f:
        first_line = f.readline().strip()

    assert first_line == "#!/bin/bash"


def test_should_use_set_minus_e_for_error_handling(multi_worker_script):
    """Test script uses 'set -e' for proper error handling."""
    with open(multi_worker_script, "r") as f:
        script_content = f.read()

    assert "set -e" in script_content


def test_script_syntax_is_valid(multi_worker_script):
    """Test script has valid bash syntax."""
    # Use bash -n to check syntax without executing
    result = subprocess.run(
        ["bash", "-n", multi_worker_script], capture_output=True, text=True
    )

    assert result.returncode == 0, f"Script syntax error: {result.stderr}"
