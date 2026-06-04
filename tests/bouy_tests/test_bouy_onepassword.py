"""Tests for bouy 1Password secret-loading functions."""

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER"),
    reason="Bouy tests cannot run inside Docker containers",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FUNCTIONS = REPO_ROOT / "bouy-functions.sh"
OP_MOCK = Path(__file__).resolve().parent / "op_mock.sh"


def run_bash(script: str, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {"PATH": os.environ.get("PATH", "")}
    if env:
        full_env.update(env)
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=full_env
    )


def test_load_env_lines_exports_and_tracks_keys():
    result = run_bash(
        f"""
        source {FUNCTIONS}
        BOUY_ENV_KEYS=""
        load_env_lines <<'EOF'
# a comment
ALPHA=one
  BETA = two
INVALID-KEY=skip
GAMMA="three"
EOF
        echo "ALPHA=$ALPHA"
        echo "BETA=$BETA"
        echo "GAMMA=$GAMMA"
        echo "KEYS=$BOUY_ENV_KEYS"
        echo "INVALID=${{INVALID_KEY:-<unset>}}"
        """
    )
    assert result.returncode == 0, result.stderr
    assert "ALPHA=one" in result.stdout
    assert "BETA=two" in result.stdout          # surrounding spaces trimmed
    assert 'GAMMA="three"' in result.stdout      # value preserved verbatim
    assert "ALPHA" in result.stdout and "BETA" in result.stdout and "GAMMA" in result.stdout
    # The dash key is not a valid shell name and must be skipped entirely.
    assert "INVALID-KEY" not in result.stdout.split("KEYS=")[1]


@pytest.mark.parametrize(
    "args,expected",
    [
        ("up", "dev"),
        ("up --prod", "prod"),
        ("up --test", "test"),
        ("test --pytest", "test"),
        ("logs worker", "dev"),
        ("--prod down", "prod"),
    ],
)
def test_detect_mode(args, expected):
    result = run_bash(f"source {FUNCTIONS}; detect_mode {args}")
    assert result.stdout.strip() == expected, result.stderr


@pytest.mark.parametrize(
    "mode,expected",
    [("dev", ".env"), ("test", ".env.test"), ("prod", ".env.prod")],
)
def test_override_file_for_mode(mode, expected):
    result = run_bash(f"source {FUNCTIONS}; override_file_for_mode {mode}")
    assert result.stdout.strip() == expected, result.stderr


def test_resolve_op_pointer_precedence(tmp_path):
    conf = tmp_path / "config"
    conf.mkdir()
    (conf / "op.conf").write_text(
        'OP_ACCOUNT=fromfile.1password.com\nOP_VAULT=FileVault\nOP_ITEM=file-item\n'
    )
    # Built-in default when neither env nor file present (file dir empty here):
    base = run_bash(
        f"cd {tmp_path}; source {FUNCTIONS}; resolve_op_pointer; "
        f'echo "$OP_ACCOUNT|$OP_VAULT|$OP_ITEM"',
    )
    assert base.stdout.strip() == "fromfile.1password.com|FileVault|file-item"

    # Env var overrides the file:
    env_over = run_bash(
        f"cd {tmp_path}; source {FUNCTIONS}; resolve_op_pointer; "
        f'echo "$OP_VAULT"',
        env={"OP_VAULT": "EnvVault"},
    )
    assert env_over.stdout.strip() == "EnvVault"


def test_resolve_op_pointer_builtin_defaults(tmp_path):
    result = run_bash(
        f"cd {tmp_path}; source {FUNCTIONS}; resolve_op_pointer; "
        f'echo "$OP_ACCOUNT|$OP_VAULT|$OP_ITEM"'
    )
    assert result.stdout.strip() == (
        "plentiful.1password.com|Pantry Pirate Radio|bouy-env"
    )
