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


def test_onepassword_available_true_when_signed_in():
    result = run_bash(
        f"source {FUNCTIONS}; resolve_op_pointer; "
        f"if onepassword_available; then echo YES; else echo NO; fi",
        env={"BOUY_OP_CMD": str(OP_MOCK), "OP_MOCK_SIGNED_IN": "1"},
    )
    assert result.stdout.strip() == "YES", result.stderr


def test_onepassword_available_false_when_not_signed_in():
    result = run_bash(
        f"source {FUNCTIONS}; resolve_op_pointer; "
        f"if onepassword_available; then echo YES; else echo NO; fi",
        env={"BOUY_OP_CMD": str(OP_MOCK), "OP_MOCK_SIGNED_IN": "0"},
    )
    assert result.stdout.strip() == "NO", result.stderr


def test_onepassword_available_false_when_op_missing():
    result = run_bash(
        f"source {FUNCTIONS}; resolve_op_pointer; "
        f"if onepassword_available; then echo YES; else echo NO; fi",
        env={"BOUY_OP_CMD": "/nonexistent/op"},
    )
    assert result.stdout.strip() == "NO", result.stderr


def test_load_env_from_1password_exports_blob():
    blob = "POSTGRES_PASSWORD=fromvault\nLLM_PROVIDER=claude\n"
    result = run_bash(
        f"source {FUNCTIONS}; resolve_op_pointer; BOUY_ENV_KEYS=''; "
        f"load_env_from_1password dev; "
        f'echo "PW=$POSTGRES_PASSWORD"; echo "LLM=$LLM_PROVIDER"; echo "KEYS=$BOUY_ENV_KEYS"',
        env={"BOUY_OP_CMD": str(OP_MOCK), "OP_MOCK_READ_OUT": blob},
    )
    assert result.returncode == 0, result.stderr
    assert "PW=fromvault" in result.stdout
    assert "LLM=claude" in result.stdout
    assert "POSTGRES_PASSWORD" in result.stdout and "LLM_PROVIDER" in result.stdout


def test_load_env_from_1password_passes_correct_reference():
    log = "/tmp/op_mock_ref.log"
    Path(log).unlink(missing_ok=True)
    run_bash(
        f"source {FUNCTIONS}; resolve_op_pointer; load_env_from_1password prod",
        env={"BOUY_OP_CMD": str(OP_MOCK), "OP_MOCK_LOG": log, "OP_MOCK_READ_OUT": "X=1\n"},
    )
    logged = Path(log).read_text()
    assert "read op://Pantry Pirate Radio/bouy-env/prod" in logged
    Path(log).unlink(missing_ok=True)


def test_load_env_from_1password_returns_nonzero_on_read_failure():
    result = run_bash(
        f"source {FUNCTIONS}; resolve_op_pointer; "
        f"if load_env_from_1password dev; then echo OK; else echo FAIL; fi",
        env={"BOUY_OP_CMD": str(OP_MOCK), "OP_MOCK_READ_RC": "1"},
    )
    assert result.stdout.strip() == "FAIL", result.stderr


def test_load_env_from_1password_writes_no_file(tmp_path):
    blob = "SECRET_TOKEN=abc123\n"
    result = run_bash(
        f"cd {tmp_path}; source {FUNCTIONS}; resolve_op_pointer; load_env_from_1password dev",
        env={"BOUY_OP_CMD": str(OP_MOCK), "OP_MOCK_READ_OUT": blob},
    )
    assert result.returncode == 0, result.stderr
    # No file in the working dir should contain the secret value.
    leaked = [p for p in tmp_path.rglob("*") if p.is_file() and "abc123" in p.read_text(errors="ignore")]
    assert leaked == [], f"secret leaked to disk: {leaked}"


def test_load_environment_file_wins_and_skips_1password(tmp_path):
    (tmp_path / ".env").write_text("FROM_FILE=yes\n")
    log = str(tmp_path / "op.log")
    result = run_bash(
        f"cd {tmp_path}; source {FUNCTIONS}; resolve_op_pointer; "
        f'PROGRAMMATIC_MODE=1; JSON_OUTPUT=0; QUIET=1; NO_COLOR=1; '
        f"load_environment up; "
        f'echo "VAL=$FROM_FILE"; echo "SRC=$BOUY_ENV_SOURCE"',
        env={"BOUY_OP_CMD": str(OP_MOCK), "OP_MOCK_LOG": log, "OP_MOCK_READ_OUT": "FROM_VAULT=yes\n"},
    )
    assert "VAL=yes" in result.stdout
    assert "SRC=file" in result.stdout
    assert not Path(log).exists(), "op must not be called when .env exists"


def test_load_environment_uses_1password_when_no_file(tmp_path):
    result = run_bash(
        f"cd {tmp_path}; source {FUNCTIONS}; resolve_op_pointer; "
        f'PROGRAMMATIC_MODE=1; JSON_OUTPUT=0; QUIET=1; NO_COLOR=1; '
        f"load_environment up; "
        f'echo "VAL=$FROM_VAULT"; echo "SRC=$BOUY_ENV_SOURCE"',
        env={"BOUY_OP_CMD": str(OP_MOCK), "OP_MOCK_READ_OUT": "FROM_VAULT=yes\n", "OP_MOCK_SIGNED_IN": "1"},
    )
    assert "VAL=yes" in result.stdout
    assert "SRC=1password" in result.stdout


def test_load_environment_skips_for_help(tmp_path):
    # No .env, op available, but `help` doesn't need env => no prompt/fetch.
    log = str(tmp_path / "op.log")
    result = run_bash(
        f"cd {tmp_path}; source {FUNCTIONS}; resolve_op_pointer; "
        f'PROGRAMMATIC_MODE=1; QUIET=1; NO_COLOR=1; '
        f"load_environment help; echo \"SRC=$BOUY_ENV_SOURCE\"",
        env={"BOUY_OP_CMD": str(OP_MOCK), "OP_MOCK_LOG": log, "OP_MOCK_READ_OUT": "X=1\n"},
    )
    assert "SRC=none" in result.stdout
    assert not Path(log).exists()


def test_load_environment_no_file_no_op_errors(tmp_path):
    result = run_bash(
        f"cd {tmp_path}; source {FUNCTIONS}; resolve_op_pointer; "
        f'PROGRAMMATIC_MODE=1; QUIET=0; NO_COLOR=1; JSON_OUTPUT=0; '
        f"load_environment up; echo RC=$?",
        env={"BOUY_OP_CMD": "/nonexistent/op"},
    )
    assert "RC=1" in result.stdout or result.returncode == 1
    assert "1Password" in result.stderr or "setup" in result.stderr


def test_load_environment_no_1password_flag_forces_file_path(tmp_path):
    # --no-1password with no file present => error, never touches op.
    log = str(tmp_path / "op.log")
    result = run_bash(
        f"cd {tmp_path}; source {FUNCTIONS}; resolve_op_pointer; "
        f'PROGRAMMATIC_MODE=1; QUIET=0; NO_COLOR=1; JSON_OUTPUT=0; '
        f"load_environment up --no-1password; echo RC=$?",
        env={"BOUY_OP_CMD": str(OP_MOCK), "OP_MOCK_LOG": log, "OP_MOCK_READ_OUT": "X=1\n"},
    )
    assert not Path(log).exists()
    # Must hard-error, not silently succeed: the user forced the file path
    # and no file exists.
    assert "RC=1" in result.stdout
    assert "no-1password" in result.stderr or "setup" in result.stderr
