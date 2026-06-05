# bouy 1Password Secrets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `bouy` source per-environment configuration from 1Password (never writing secrets to disk) while a `.env` on disk, when present, always wins.

**Architecture:** A new `load_environment` orchestration replaces the unconditional `.env`-export block in `bouy`. It detects the mode (dev/test/prod), and for that mode either loads the on-disk override file (`.env`/`.env.test`/`.env.prod`) exactly as today, or — only for container-using commands when no file exists — fetches the matching field (`dev`/`test`/`prod`) from a 1Password item via `op read`, parses it in memory, and `export`s it into bouy's process environment. Containers receive the values by name through a runtime-generated, **names-only** Docker Compose passthrough overlay (`environment: [KEY, …]`); service `env_file` directives are made `required: false` so they are skipped when absent. The test runner uses valueless `docker run -e KEY` flags instead of a temp env file.

**Tech Stack:** Bash (the `bouy` script + `bouy-functions.sh` test shim), Docker Compose, the 1Password CLI (`op` 2.x, desktop-app biometric integration), pytest (the existing `tests/bouy_tests/` suite run via `run_bouy_tests.py`).

---

## Shared interfaces (defined once; full code appears in the referenced task)

New shell functions live in **both** `bouy` and `bouy-functions.sh` (the existing duplication pattern — `bouy-functions.sh` is the curated, unit-testable copy sourced by pytest). Signatures (authoritative — keep names identical across tasks):

| Function | Defined in | Contract |
|---|---|---|
| `load_env_lines` | Task 1 | Reads `KEY=value` lines from **stdin**; exports valid keys; appends each key to global `BOUY_ENV_KEYS`. No subshell (callers use `<<<` / `<`, never a pipe). |
| `detect_mode "$@"` | Task 2 | Echoes `dev`\|`test`\|`prod`. `--prod`/`--test` flag wins; else first positional `test` ⇒ `test`; else `dev`. |
| `override_file_for_mode <mode>` | Task 2 | Echoes `.env` (dev), `.env.test` (test), or `.env.prod` (prod). |
| `resolve_op_pointer` | Task 3 | Sets globals `OP_ACCOUNT`/`OP_VAULT`/`OP_ITEM` from env > `config/op.conf` > built-in defaults. |
| `op_cli` | Task 4 | Runs the `op` binary: `"${BOUY_OP_CMD:-op}" "$@"`. Single mockable seam. |
| `onepassword_available` | Task 4 | Returns 0 iff `op` is installed and signed into `$OP_ACCOUNT`. |
| `load_env_from_1password <field>` | Task 5 | `op_cli read "op://$OP_VAULT/$OP_ITEM/<field>"` → `load_env_lines`. Returns non-zero on failure. |
| `command_needs_env <cmd>` | Task 6 | Returns 1 (skip) for `setup`/`op`/`version`/`help`/empty/`-h`/`--help`/`--version`; else 0. |
| `load_environment "$@"` | Task 6 | Full precedence algorithm; sets `BOUY_ENV_SOURCE` = `file`\|`1password`\|`none`. |
| `write_passthrough_overlay <outfile> <keys_csv> <svc...>` | Task 8 | Writes a names-only compose overlay (`environment: ["KEY", …]` per service). Pure/testable. |
| `op_status` / `op_pull` / `op_push` | Task 9 | `bouy op` subcommands. |

Global vars introduced: `BOUY_ENV_KEYS`, `BOUY_ENV_SOURCE`, `OP_ACCOUNT`, `OP_VAULT`, `OP_ITEM`, `OP_PASSTHROUGH_ADDED`. Test seam env vars: `BOUY_OP_CMD` (override `op` binary), reusing existing `BOUY_TEST_MODE`/`BOUY_TEST_COMPOSE_CMD`.

Built-in pointer defaults: `OP_ACCOUNT=plentiful.1password.com`, `OP_VAULT=Pantry Pirate Radio`, `OP_ITEM=bouy-env`.

A reusable **mock `op`** stub (used by many tests) is created in Task 1, Step 1.

---

## Task 1: Refactor the `.env` export loop into `load_env_lines` (behavior-preserving)

Extract the inline `.env` parser at `bouy:96-110` into a stdin-reading function so the same logic serves both the file path and the 1Password blob, and have it record loaded keys.

**Files:**
- Modify: `bouy:96-110`
- Modify: `bouy-functions.sh` (add the function next to `parse_mode`)
- Create: `tests/bouy_tests/test_bouy_onepassword.py`
- Create: `tests/bouy_tests/op_mock.sh` (reusable mock `op` for later tasks)

- [ ] **Step 1: Create the reusable mock `op` stub**

Create `tests/bouy_tests/op_mock.sh`:

```bash
#!/bin/bash
# Mock 1Password CLI for bouy tests. Behavior is driven by env vars so each
# test can script responses without a real vault.
#   OP_MOCK_LOG       : file to append the raw argv of each call (for assertions)
#   OP_MOCK_READ_OUT  : stdout to emit for `op read ...`
#   OP_MOCK_READ_RC   : exit code for `op read ...` (default 0)
#   OP_MOCK_SIGNED_IN : "1" => `op account get`/`op whoami` succeed (default "1")
[ -n "$OP_MOCK_LOG" ] && printf '%s\n' "$*" >> "$OP_MOCK_LOG"
case "$1" in
  read)
    printf '%s' "$OP_MOCK_READ_OUT"
    exit "${OP_MOCK_READ_RC:-0}"
    ;;
  account|whoami)
    [ "${OP_MOCK_SIGNED_IN:-1}" = "1" ] && exit 0 || exit 1
    ;;
  item)
    exit "${OP_MOCK_ITEM_RC:-0}"
    ;;
  *)
    exit 0
    ;;
esac
```

```bash
chmod +x tests/bouy_tests/op_mock.sh
```

- [ ] **Step 2: Write the failing test for `load_env_lines`**

Create `tests/bouy_tests/test_bouy_onepassword.py`:

```python
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
```

- [ ] **Step 3: Run the test, verify it fails**

Run: `python run_bouy_tests.py test_bouy_onepassword.py::test_load_env_lines_exports_and_tracks_keys`
Expected: FAIL (`load_env_lines: command not found`).

- [ ] **Step 4: Add `load_env_lines` to `bouy-functions.sh`**

Insert after `parse_mode` (after `bouy-functions.sh:96`):

```bash
# Parse KEY=value lines from stdin, export valid ones, and record their names
# in BOUY_ENV_KEYS. Must be called WITHOUT a pipe (use <<< or < file) so the
# exports land in the current shell, not a subshell.
load_env_lines() {
    local key value
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        if [[ ! "$key" =~ ^[[:space:]]*# ]] && [[ -n "$key" ]]; then
            key=$(echo "$key" | xargs)
            if [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
                export "$key=$value"
                BOUY_ENV_KEYS="${BOUY_ENV_KEYS:+$BOUY_ENV_KEYS }$key"
            fi
        fi
    done
}
```

- [ ] **Step 5: Run the test, verify it passes**

Run: `python run_bouy_tests.py test_bouy_onepassword.py::test_load_env_lines_exports_and_tracks_keys`
Expected: PASS.

- [ ] **Step 6: Rewrite `bouy:96-110` to use the function (behavior-preserving)**

Replace the block:

```bash
# Export .env variables if the file exists
if [ -f .env ]; then
    # Use a safer method that handles special characters properly
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        if [[ ! "$key" =~ ^[[:space:]]*# ]] && [[ -n "$key" ]]; then
            # Remove leading/trailing whitespace from key
            key=$(echo "$key" | xargs)
            # Export the variable if it's a valid name
            if [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
                export "$key=$value"
            fi
        fi
    done < .env
fi
```

with the function definition + a temporary call that preserves current behavior (the full orchestration replaces this call in Task 6):

```bash
# Parse KEY=value lines from stdin, export valid ones, and record their names
# in BOUY_ENV_KEYS. Must be called WITHOUT a pipe (use <<< or < file).
load_env_lines() {
    local key value
    while IFS='=' read -r key value; do
        if [[ ! "$key" =~ ^[[:space:]]*# ]] && [[ -n "$key" ]]; then
            key=$(echo "$key" | xargs)
            if [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
                export "$key=$value"
                BOUY_ENV_KEYS="${BOUY_ENV_KEYS:+$BOUY_ENV_KEYS }$key"
            fi
        fi
    done
}

# Export .env variables if the file exists (replaced by load_environment in Task 6)
if [ -f .env ]; then
    load_env_lines < .env
fi
```

- [ ] **Step 7: Verify nothing regressed**

Run: `python run_bouy_tests.py test_bouy_unit.py test_bouy_simplified.py`
Expected: PASS (the `.env` path is unchanged).

- [ ] **Step 8: Commit**

```bash
git add bouy bouy-functions.sh tests/bouy_tests/test_bouy_onepassword.py tests/bouy_tests/op_mock.sh
git commit -m "refactor(bouy): extract .env parsing into load_env_lines

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Mode detection and override-file mapping

**Files:**
- Modify: `bouy-functions.sh` (add both functions after `load_env_lines`)
- Modify: `bouy` (add the same two functions next to `load_env_lines`)
- Modify: `tests/bouy_tests/test_bouy_onepassword.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/bouy_tests/test_bouy_onepassword.py`:

```python
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
```

- [ ] **Step 2: Run, verify fail**

Run: `python run_bouy_tests.py test_bouy_onepassword.py::test_detect_mode`
Expected: FAIL (`detect_mode: command not found`).

- [ ] **Step 3: Implement both functions (in `bouy-functions.sh` AND `bouy`)**

```bash
# Determine the active environment from CLI args: explicit --prod/--test flag
# wins; otherwise the `test` command implies test mode; default dev.
detect_mode() {
    local mode="dev" arg
    for arg in "$@"; do
        case "$arg" in
            --prod) echo "prod"; return 0 ;;
            --test) echo "test"; return 0 ;;
        esac
    done
    if [ "$1" = "test" ]; then
        mode="test"
    fi
    echo "$mode"
}

# Map a mode to its on-disk override file (which always wins over 1Password).
override_file_for_mode() {
    case "$1" in
        test) echo ".env.test" ;;
        prod) echo ".env.prod" ;;
        *)    echo ".env" ;;
    esac
}
```

- [ ] **Step 4: Run, verify pass**

Run: `python run_bouy_tests.py test_bouy_onepassword.py::test_detect_mode test_bouy_onepassword.py::test_override_file_for_mode`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bouy bouy-functions.sh tests/bouy_tests/test_bouy_onepassword.py
git commit -m "feat(bouy): add detect_mode and override_file_for_mode

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 1Password pointer resolution + committed defaults

**Files:**
- Create: `config/op.conf` (committed; names only, no secrets)
- Modify: `bouy-functions.sh` and `bouy` (add `resolve_op_pointer`)
- Modify: `tests/bouy_tests/test_bouy_onepassword.py`

- [ ] **Step 1: Create `config/op.conf`**

```bash
# 1Password pointer for bouy (names only — NOT secrets). Override any value via
# the matching OP_* environment variable. Delete this file to fall back to the
# built-in defaults in bouy.
OP_ACCOUNT=plentiful.1password.com
OP_VAULT=Pantry Pirate Radio
OP_ITEM=bouy-env
```

- [ ] **Step 2: Write the failing test (precedence: env > op.conf > builtin)**

Append:

```python
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
```

- [ ] **Step 3: Run, verify fail**

Run: `python run_bouy_tests.py test_bouy_onepassword.py::test_resolve_op_pointer_precedence`
Expected: FAIL.

- [ ] **Step 4: Implement `resolve_op_pointer` (in `bouy-functions.sh` AND `bouy`)**

```bash
# Resolve the 1Password pointer into OP_ACCOUNT/OP_VAULT/OP_ITEM.
# Precedence: existing environment variable > config/op.conf > built-in default.
resolve_op_pointer() {
    local file_account="" file_vault="" file_item=""
    if [ -f config/op.conf ]; then
        # shellcheck disable=SC1091
        file_account=$(grep -E '^OP_ACCOUNT=' config/op.conf | cut -d= -f2-)
        file_vault=$(grep -E '^OP_VAULT=' config/op.conf | cut -d= -f2-)
        file_item=$(grep -E '^OP_ITEM=' config/op.conf | cut -d= -f2-)
    fi
    OP_ACCOUNT="${OP_ACCOUNT:-${file_account:-plentiful.1password.com}}"
    OP_VAULT="${OP_VAULT:-${file_vault:-Pantry Pirate Radio}}"
    OP_ITEM="${OP_ITEM:-${file_item:-bouy-env}}"
    export OP_ACCOUNT OP_VAULT OP_ITEM
}
```

- [ ] **Step 5: Run, verify pass**

Run: `python run_bouy_tests.py test_bouy_onepassword.py::test_resolve_op_pointer_precedence test_bouy_onepassword.py::test_resolve_op_pointer_builtin_defaults`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add config/op.conf bouy bouy-functions.sh tests/bouy_tests/test_bouy_onepassword.py
git commit -m "feat(bouy): resolve 1Password pointer (env > config/op.conf > default)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `op` CLI wrapper + availability check

**Files:**
- Modify: `bouy-functions.sh` and `bouy` (add `op_cli` and `onepassword_available`)
- Modify: `tests/bouy_tests/test_bouy_onepassword.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
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
```

- [ ] **Step 2: Run, verify fail**

Run: `python run_bouy_tests.py test_bouy_onepassword.py::test_onepassword_available_true_when_signed_in`
Expected: FAIL.

- [ ] **Step 3: Implement (in `bouy-functions.sh` AND `bouy`)**

```bash
# Single mockable seam for the 1Password CLI. Tests set BOUY_OP_CMD to a stub.
op_cli() {
    "${BOUY_OP_CMD:-op}" "$@"
}

# True iff the op binary exists and is signed into the configured account.
onepassword_available() {
    local bin="${BOUY_OP_CMD:-op}"
    command -v "$bin" >/dev/null 2>&1 || return 1
    op_cli account get --account "$OP_ACCOUNT" >/dev/null 2>&1
}
```

Note: the mock's `account` branch ignores the `get`/`--account` args and keys off `OP_MOCK_SIGNED_IN`, so these tests exercise the success/failure paths without a real vault.

- [ ] **Step 4: Run, verify pass**

Run: `python run_bouy_tests.py test_bouy_onepassword.py -k onepassword_available`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add bouy bouy-functions.sh tests/bouy_tests/test_bouy_onepassword.py
git commit -m "feat(bouy): add op_cli wrapper and onepassword_available check

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Fetch + parse a blob from 1Password

**Files:**
- Modify: `bouy-functions.sh` and `bouy` (add `load_env_from_1password`)
- Modify: `tests/bouy_tests/test_bouy_onepassword.py`

- [ ] **Step 1: Write the failing tests (success + failure + no-disk)**

Append:

```python
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
```

- [ ] **Step 2: Run, verify fail**

Run: `python run_bouy_tests.py test_bouy_onepassword.py -k load_env_from_1password`
Expected: FAIL.

- [ ] **Step 3: Implement (in `bouy-functions.sh` AND `bouy`)**

```bash
# Fetch the blob for <field> (dev|test|prod) from 1Password and export it.
# Reads the whole field with a single op call; the value lives only in memory.
load_env_from_1password() {
    local field="$1" blob
    blob=$(op_cli read "op://$OP_VAULT/$OP_ITEM/$field" --account "$OP_ACCOUNT") || return 1
    [ -n "$blob" ] || return 1
    load_env_lines <<< "$blob"
}
```

- [ ] **Step 4: Run, verify pass**

Run: `python run_bouy_tests.py test_bouy_onepassword.py -k load_env_from_1password`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add bouy bouy-functions.sh tests/bouy_tests/test_bouy_onepassword.py
git commit -m "feat(bouy): load_env_from_1password fetches+parses a field blob

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `load_environment` orchestration + wire into `bouy`

This replaces the temporary `if [ -f .env ]; then load_env_lines < .env; fi` from Task 1 and moves env loading below flag-parsing so it can use `output` and see the parsed command/flags.

**Files:**
- Modify: `bouy-functions.sh` and `bouy` (add `command_needs_env` + `load_environment`)
- Modify: `bouy:96-110` region (remove the temporary loader call; keep the function defs) and `bouy:~605` (call `load_environment` before `case "$1"`)
- Modify: `tests/bouy_tests/test_bouy_onepassword.py`

- [ ] **Step 1: Write the failing tests (precedence + flags + skip-list)**

Append:

```python
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
```

- [ ] **Step 2: Run, verify fail**

Run: `python run_bouy_tests.py test_bouy_onepassword.py -k load_environment`
Expected: FAIL.

- [ ] **Step 3: Implement `command_needs_env` + `load_environment` (in `bouy-functions.sh` AND `bouy`)**

```bash
# Commands that never need the application environment (must NOT trigger a
# 1Password biometric prompt when no override file exists).
command_needs_env() {
    case "$1" in
        ""|setup|op|version|help|-h|--help|--version) return 1 ;;
        *) return 0 ;;
    esac
}

# Resolve the environment for this invocation.
# Sets BOUY_ENV_SOURCE = file | 1password | none.
# Precedence: override file on disk wins; otherwise (for env-needing commands)
# 1Password; otherwise a hard error. --no-1password forces the file-only path;
# --1password forces the vault path even if a file exists.
load_environment() {
    local args=("$@") cmd="$1" mode file force="auto" arg
    for arg in "${args[@]}"; do
        case "$arg" in
            --no-1password) force="off" ;;
            --1password) force="on" ;;
        esac
    done
    [ "${USE_1PASSWORD:-}" = "false" ] && force="off"
    [ "${USE_1PASSWORD:-}" = "true" ] && force="on"

    resolve_op_pointer
    mode=$(detect_mode "${args[@]}")
    file=$(override_file_for_mode "$mode")
    # prod falls back to .env when .env.prod is absent
    if [ "$mode" = "prod" ] && [ ! -f "$file" ] && [ -f .env ]; then
        file=".env"
    fi
    BOUY_ENV_SOURCE="none"

    if [ "$force" != "on" ] && [ -f "$file" ]; then
        load_env_lines < "$file"
        BOUY_ENV_SOURCE="file"
        return 0
    fi

    if [ "$force" = "off" ]; then
        command_needs_env "$cmd" || return 0
        output error "No $file found and --no-1password set. Run './bouy setup' to create it."
        return 1
    fi

    command_needs_env "$cmd" || return 0

    if onepassword_available; then
        if load_env_from_1password "$mode"; then
            BOUY_ENV_SOURCE="1password"
            return 0
        fi
        output error "Failed to read op://$OP_VAULT/$OP_ITEM/$mode. Try './bouy op status'."
        return 1
    fi

    output error "No $file on disk and 1Password is unavailable."
    output error "Sign in (op signin --account $OP_ACCOUNT) or run './bouy setup' to create $file."
    return 1
}
```

- [ ] **Step 4: Run, verify pass**

Run: `python run_bouy_tests.py test_bouy_onepassword.py -k load_environment`
Expected: PASS.

- [ ] **Step 5: Wire into `bouy` — remove the temporary loader call**

In `bouy`, the block from Task 1 Step 6 currently ends with:

```bash
# Export .env variables if the file exists (replaced by load_environment in Task 6)
if [ -f .env ]; then
    load_env_lines < .env
fi
```

Delete those 4 lines (keep all the function definitions above them).

- [ ] **Step 6: Wire into `bouy` — call `load_environment` before dispatch**

Immediately before `# Main command handling` / `case "$1" in` (around `bouy:605`), add:

```bash
# Resolve environment from .env (wins) or 1Password (no file present).
load_environment "$@"
```

- [ ] **Step 7: Verify the `.env` path still works end-to-end + no regressions**

Run: `python run_bouy_tests.py test_bouy_unit.py test_bouy_simplified.py test_bouy_integration.py test_bouy_docker.py test_bouy_setup.py`
Expected: PASS. Also smoke-test manually with a real `.env` present:
Run: `./bouy --programmatic ps` → Expected: no errors, same as before.

- [ ] **Step 8: Commit**

```bash
git add bouy bouy-functions.sh tests/bouy_tests/test_bouy_onepassword.py
git commit -m "feat(bouy): load_environment with .env-wins precedence and 1Password fallback

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Make compose `env_file` optional + ignore `.env.prod`

So containers don't fail when no `.env` file exists (1Password mode supplies values via the Task 8 overlay).

**Files:**
- Modify: `.docker/compose/base.yml` (12 occurrences)
- Modify: `.docker/compose/docker-compose.prod.yml` (10 occurrences)
- Modify: `plugins/ppr-lighthouse/.docker/compose.yml` (1)
- Modify: `plugins/ppr-beacon/.docker/compose.yml` (1)
- Modify: `.gitignore`
- Modify: `tests/bouy_tests/test_bouy_onepassword.py`

- [ ] **Step 1: Write the failing guard test**

Append:

```python
COMPOSE_FILES_WITH_ENVFILE = [
    REPO_ROOT / ".docker/compose/base.yml",
    REPO_ROOT / ".docker/compose/docker-compose.prod.yml",
    REPO_ROOT / "plugins/ppr-lighthouse/.docker/compose.yml",
    REPO_ROOT / "plugins/ppr-beacon/.docker/compose.yml",
]


def test_env_file_directives_are_optional():
    """No bare `env_file: ../../.env`; all must be the required:false long form."""
    for path in COMPOSE_FILES_WITH_ENVFILE:
        text = path.read_text()
        assert "env_file: ../../.env" not in text, f"bare env_file remains in {path}"
        if "../../.env" in text:
            assert "required: false" in text, f"{path} missing required:false"


def test_env_prod_is_gitignored():
    gi = (REPO_ROOT / ".gitignore").read_text().splitlines()
    assert ".env.prod" in gi
```

- [ ] **Step 2: Run, verify fail**

Run: `python run_bouy_tests.py test_bouy_onepassword.py -k "env_file_directives or env_prod"`
Expected: FAIL.

- [ ] **Step 3: Rewrite the `env_file` directives**

Apply this replacement to each of the four files (all occurrences are the identical 4-space-indented line):

```bash
for f in .docker/compose/base.yml .docker/compose/docker-compose.prod.yml \
         plugins/ppr-lighthouse/.docker/compose.yml plugins/ppr-beacon/.docker/compose.yml; do
  perl -0pi -e 's/^(?<i> *)env_file: \.\.\/\.\.\/\.env$/$+{i}env_file:\n$+{i}  - path: ..\/..\/.env\n$+{i}    required: false/mg' "$f"
done
```

This turns each `    env_file: ../../.env` into:

```yaml
    env_file:
      - path: ../../.env
        required: false
```

- [ ] **Step 4: Add `.env.prod` to `.gitignore`**

Add after the `.env` line (`.gitignore:53`):

```
.env.prod
```

- [ ] **Step 5: Validate compose still parses (with and without .env)**

Run (with a `.env` present — normal dev): `docker compose -f .docker/compose/base.yml -f .docker/compose/docker-compose.dev.yml config >/dev/null && echo OK`
Expected: `OK`.
Run (simulate no .env): `mv .env .env.bak && docker compose -f .docker/compose/base.yml config >/dev/null && echo OK_NO_ENV; mv .env.bak .env`
Expected: `OK_NO_ENV` (no "env file not found" error).

- [ ] **Step 6: Run guard tests, verify pass**

Run: `python run_bouy_tests.py test_bouy_onepassword.py -k "env_file_directives or env_prod"`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add .docker/compose/base.yml .docker/compose/docker-compose.prod.yml \
  plugins/ppr-lighthouse/.docker/compose.yml plugins/ppr-beacon/.docker/compose.yml \
  .gitignore tests/bouy_tests/test_bouy_onepassword.py
git commit -m "feat(compose): make env_file optional; gitignore .env.prod

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Passthrough overlay (names-only) + hook into `parse_mode`

**Files:**
- Modify: `bouy-functions.sh` and `bouy` (add `write_passthrough_overlay`, `get_active_services`, `maybe_add_passthrough_overlay`; call the last at the end of `parse_mode`)
- Modify: `tests/bouy_tests/test_bouy_onepassword.py`

- [ ] **Step 1: Write the failing tests for the writer**

Append:

```python
def test_write_passthrough_overlay_names_only(tmp_path):
    out = tmp_path / "overlay.yml"
    result = run_bash(
        f"source {FUNCTIONS}; "
        f'write_passthrough_overlay "{out}" "ALPHA BETA" app worker',
    )
    assert result.returncode == 0, result.stderr
    text = out.read_text()
    assert "app:" in text and "worker:" in text
    assert "ALPHA" in text and "BETA" in text
    # Crucially: variable NAMES only, never `NAME=value` pairs.
    assert "=" not in text


def test_maybe_add_passthrough_overlay_only_when_1password(tmp_path):
    # source=file => no overlay, COMPOSE_FILES unchanged.
    result = run_bash(
        f"source {FUNCTIONS}; "
        f'COMPOSE_CMD="echo"; COMPOSE_FILES="-f base.yml"; '
        f'BOUY_ENV_SOURCE="file"; BOUY_ENV_KEYS="ALPHA"; '
        f"maybe_add_passthrough_overlay; echo \"CF=$COMPOSE_FILES\"",
    )
    assert result.stdout.strip() == "CF=-f base.yml"
```

- [ ] **Step 2: Run, verify fail**

Run: `python run_bouy_tests.py test_bouy_onepassword.py -k passthrough`
Expected: FAIL.

- [ ] **Step 3: Implement (in `bouy-functions.sh` AND `bouy`)**

```bash
# Write a names-only Docker Compose overlay that passes BOUY env vars through to
# each given service. Contains variable NAMES only — never secret values.
#   $1 = output file, $2 = space-separated keys, $3.. = service names
write_passthrough_overlay() {
    local outfile="$1" keys="$2"; shift 2
    local svc key
    {
        echo "services:"
        for svc in "$@"; do
            echo "  $svc:"
            echo "    environment:"
            for key in $keys; do
                echo "      - \"$key\""
            done
        done
    } > "$outfile"
}

# Service names in the currently-assembled compose configuration.
get_active_services() {
    $COMPOSE_CMD $COMPOSE_FILES config --services 2>/dev/null
}

# When running from 1Password, generate the passthrough overlay once and append
# it to COMPOSE_FILES. No-op for the .env (file) path.
maybe_add_passthrough_overlay() {
    [ "$BOUY_ENV_SOURCE" = "1password" ] || return 0
    [ -n "$OP_PASSTHROUGH_ADDED" ] && return 0
    local services overlay
    services=$(get_active_services)
    [ -n "$services" ] || return 0
    overlay=$(mktemp -t bouy-op-passthrough.XXXXXX.yml)
    # shellcheck disable=SC2086
    write_passthrough_overlay "$overlay" "$BOUY_ENV_KEYS" $services
    COMPOSE_FILES="$COMPOSE_FILES -f $overlay"
    CLEANUP_TEMP_FILES="$CLEANUP_TEMP_FILES $overlay"
    OP_PASSTHROUGH_ADDED=1
}
```

- [ ] **Step 4: Hook into `parse_mode` (in `bouy-functions.sh` AND `bouy`)**

At the very end of `parse_mode` (after the `case $mode in … esac`, before the closing `}`), add:

```bash
    maybe_add_passthrough_overlay
```

(The `BOUY_ENV_SOURCE` guard makes this a no-op for the `.env` path and in unit tests where the var is unset.)

- [ ] **Step 5: Run, verify pass + no regression in parse_mode tests**

Run: `python run_bouy_tests.py test_bouy_onepassword.py -k passthrough`
Expected: PASS.
Run: `python run_bouy_tests.py test_bouy_unit.py -k parse_mode`
Expected: PASS (guard keeps `parse_mode` unchanged when `BOUY_ENV_SOURCE` is unset).

- [ ] **Step 6: Commit**

```bash
git add bouy bouy-functions.sh tests/bouy_tests/test_bouy_onepassword.py
git commit -m "feat(bouy): names-only passthrough overlay for 1Password mode

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: `bouy op` subcommands (status / pull / push)

**Files:**
- Modify: `bouy` (add `op)` to the dispatch `case "$1"`; add `op_status`/`op_pull`/`op_push`)
- Modify: `bouy-functions.sh` (add the three functions for testability)
- Modify: `bouy` `usage()` (document `op`)
- Modify: `tests/bouy_tests/test_bouy_onepassword.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_op_status_reports_pointer_and_signin(tmp_path):
    result = run_bash(
        f"cd {tmp_path}; source {FUNCTIONS}; "
        f'PROGRAMMATIC_MODE=1; QUIET=0; NO_COLOR=1; JSON_OUTPUT=0; '
        f"op_status",
        env={"BOUY_OP_CMD": str(OP_MOCK), "OP_MOCK_SIGNED_IN": "1", "OP_MOCK_READ_OUT": "X=1\n"},
    )
    assert "plentiful.1password.com" in (result.stdout + result.stderr)
    assert "bouy-env" in (result.stdout + result.stderr)


def test_op_push_invokes_item_with_field_assignment(tmp_path):
    (tmp_path / ".env").write_text("A=1\nB=2\n")
    log = str(tmp_path / "op.log")
    run_bash(
        f"cd {tmp_path}; source {FUNCTIONS}; resolve_op_pointer; "
        f'PROGRAMMATIC_MODE=1; QUIET=1; NO_COLOR=1; JSON_OUTPUT=0; '
        f"op_push --field dev",
        env={"BOUY_OP_CMD": str(OP_MOCK), "OP_MOCK_LOG": log, "OP_MOCK_ITEM_RC": "0"},
    )
    logged = Path(log).read_text()
    assert "item" in logged and "dev[text]=" in logged
```

- [ ] **Step 2: Run, verify fail**

Run: `python run_bouy_tests.py test_bouy_onepassword.py -k "op_status or op_push"`
Expected: FAIL.

- [ ] **Step 3: Implement the three functions (in `bouy-functions.sh` AND `bouy`)**

```bash
# Print resolved pointer + sign-in + which fields exist. No secret values shown.
op_status() {
    resolve_op_pointer
    output info "1Password account: $OP_ACCOUNT"
    output info "Vault: $OP_VAULT"
    output info "Item:  $OP_ITEM"
    if onepassword_available; then
        output success "Signed in to $OP_ACCOUNT"
    else
        output warning "Not signed in (run: op signin --account $OP_ACCOUNT)"
        return 0
    fi
    local field
    for field in dev test prod; do
        if op_cli read "op://$OP_VAULT/$OP_ITEM/$field" --account "$OP_ACCOUNT" >/dev/null 2>&1; then
            output info "  field '$field': present"
        else
            output info "  field '$field': missing"
        fi
    done
}

# Print a field blob to stdout (or --out FILE only when explicitly requested).
op_pull() {
    resolve_op_pointer
    local field="dev" out=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --field) field="$2"; shift 2 ;;
            --out) out="$2"; shift 2 ;;
            *) shift ;;
        esac
    done
    local blob
    blob=$(op_cli read "op://$OP_VAULT/$OP_ITEM/$field" --account "$OP_ACCOUNT") || {
        output error "Could not read op://$OP_VAULT/$OP_ITEM/$field"; return 1; }
    if [ -n "$out" ]; then
        printf '%s' "$blob" > "$out"
        output success "Wrote $field to $out"
    else
        printf '%s\n' "$blob"
    fi
}

# Upload local env file(s) into the 1Password item fields. --field dev|test|prod|all
op_push() {
    resolve_op_pointer
    local field="all"
    while [ $# -gt 0 ]; do
        case "$1" in
            --field) field="$2"; shift 2 ;;
            *) shift ;;
        esac
    done
    local fields=()
    case "$field" in
        all) fields=(dev test prod) ;;
        *) fields=("$field") ;;
    esac
    # Ensure the item exists (create empty Secure Note if missing).
    op_cli item get "$OP_ITEM" --vault "$OP_VAULT" --account "$OP_ACCOUNT" >/dev/null 2>&1 || \
        op_cli item create --category "Secure Note" --title "$OP_ITEM" \
            --vault "$OP_VAULT" --account "$OP_ACCOUNT" >/dev/null 2>&1 || true
    local f src content
    for f in "${fields[@]}"; do
        src=$(override_file_for_mode "$f")
        [ "$f" = "prod" ] && [ ! -f "$src" ] && [ -f .env ] && src=".env"
        if [ ! -f "$src" ]; then
            output warning "Skipping '$f': $src not found"
            continue
        fi
        content=$(cat "$src")
        if op_cli item edit "$OP_ITEM" --vault "$OP_VAULT" --account "$OP_ACCOUNT" \
            "$f[text]=$content" >/dev/null 2>&1; then
            output success "Pushed $src -> field '$f'"
        else
            output error "Failed to push field '$f'"
        fi
    done
}
```

- [ ] **Step 4: Add the `op)` dispatch branch in `bouy`**

In the main `case "$1" in` (starts `bouy:606`), add a branch (e.g. right after the `setup)` branch's `;;`):

```bash
    op)
        shift
        case "$1" in
            status) op_status ;;
            pull)   shift; op_pull "$@" ;;
            push)   shift; op_push "$@" ;;
            *) output error "Usage: bouy op {status|pull|push}"; exit 1 ;;
        esac
        ;;
```

- [ ] **Step 5: Document `op` in `usage()`**

In `usage()` (near `bouy:149`, the Commands list), add after the `setup` line:

```bash
    echo "  op [status|pull|push] Manage secrets in 1Password (status/pull/push)"
```

- [ ] **Step 6: Run, verify pass + help shows op**

Run: `python run_bouy_tests.py test_bouy_onepassword.py -k "op_status or op_push"`
Expected: PASS.
Run: `./bouy --help | grep -E "^\s+op "`
Expected: the `op` line prints.

- [ ] **Step 7: Commit**

```bash
git add bouy bouy-functions.sh tests/bouy_tests/test_bouy_onepassword.py
git commit -m "feat(bouy): add 'bouy op' status/pull/push subcommands

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: `bouy setup` — optional "Configure 1Password" branch

**Files:**
- Modify: `bouy` (in the `setup)` handler, `bouy:607-725`)
- Modify: `tests/bouy_tests/test_bouy_setup.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/bouy_tests/test_bouy_setup.py` (inside `class TestBouySetup`):

```python
    def test_setup_can_write_op_conf(self, test_env, bouy_path, temp_dir):
        """Answering 'y' to the 1Password prompt writes config/op.conf (no secrets)."""
        # Feed: overwrite? (no .env so skipped) -> db pass -> provider 1 -> key ->
        # haarrrvest skip -> configure 1Password? y -> account -> vault -> item
        answers = "\n".join(
            ["pirate", "1", "test_key", "skip", "y",
             "plentiful.1password.com", "Pantry Pirate Radio", "bouy-env"]
        ) + "\n"
        result = subprocess.run(
            [bouy_path, "setup"],
            input=answers, capture_output=True, text=True,
            cwd=temp_dir, env=test_env,
        )
        op_conf = Path(temp_dir) / "config" / "op.conf"
        assert op_conf.exists(), result.stdout + result.stderr
        body = op_conf.read_text()
        assert "OP_ACCOUNT=plentiful.1password.com" in body
        assert "OP_ITEM=bouy-env" in body
        # No secret values in op.conf
        assert "test_key" not in body and "pirate" not in body
```

Note: the `bouy_path` fixture copies `bouy` + `.env.example` to a temp dir; this test also needs the dir to allow creating `config/`. Add to the fixture (or the test) a `mkdir -p config` is unnecessary — the implementation creates it.

- [ ] **Step 2: Run, verify fail**

Run: `python run_bouy_tests.py test_bouy_setup.py::TestBouySetup::test_setup_can_write_op_conf`
Expected: FAIL (no `config/op.conf` written).

- [ ] **Step 3: Implement the branch**

In `bouy`, just before `output success ".env file created successfully!"` (`bouy:715`), insert:

```bash
        echo ""
        echo "=== 1Password (optional) ==="
        echo "Store secrets in 1Password instead of relying on .env on disk?"
        read -p "Configure 1Password pointer now? (y/N): " want_op
        if [[ "$want_op" =~ ^[Yy]$ ]]; then
            prompt_with_default "1Password account" "plentiful.1password.com" "SETUP_OP_ACCOUNT"
            prompt_with_default "Vault" "Pantry Pirate Radio" "SETUP_OP_VAULT"
            prompt_with_default "Item" "bouy-env" "SETUP_OP_ITEM"
            mkdir -p config
            cat > config/op.conf <<EOF
# 1Password pointer for bouy (names only — NOT secrets).
OP_ACCOUNT=$SETUP_OP_ACCOUNT
OP_VAULT=$SETUP_OP_VAULT
OP_ITEM=$SETUP_OP_ITEM
EOF
            output success "Wrote config/op.conf"
            echo "Next: run './bouy op push' to upload your .env into the vault,"
            echo "then you can delete .env to load secrets from 1Password."
        fi
```

- [ ] **Step 4: Run, verify pass**

Run: `python run_bouy_tests.py test_bouy_setup.py::TestBouySetup::test_setup_can_write_op_conf`
Expected: PASS.

- [ ] **Step 5: Run the full setup suite (no regression)**

Run: `python run_bouy_tests.py test_bouy_setup.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add bouy tests/bouy_tests/test_bouy_setup.py
git commit -m "feat(bouy): optional 1Password configuration in setup wizard

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Test runner — 1Password support (no temp env file)

When `.env.test` is absent but the `test` field is available, the test runner must use the env already exported by `load_environment` (mode `test`), injecting it with valueless `docker run -e KEY` flags instead of `--env-file`.

**Files:**
- Modify: `bouy:1116-1121` (relax the hard `.env.test` requirement)
- Modify: `bouy:1263-1272` (branch the env injection)
- Modify: `tests/bouy_tests/test_bouy_onepassword.py`

- [ ] **Step 1: Write the failing test for the `-e` flag builder**

We isolate the flag-building into a tiny function so it is unit-testable. Append:

```python
def test_build_env_flags_from_keys():
    result = run_bash(
        f"source {FUNCTIONS}; build_env_flags ALPHA BETA",
    )
    assert result.stdout.split() == ["-e", "ALPHA", "-e", "BETA"], result.stdout
```

- [ ] **Step 2: Run, verify fail**

Run: `python run_bouy_tests.py test_bouy_onepassword.py::test_build_env_flags_from_keys`
Expected: FAIL.

- [ ] **Step 3: Add `build_env_flags` (in `bouy-functions.sh` AND `bouy`)**

```bash
# Emit valueless `-e KEY` flags so docker run passes each var through from the
# current environment (used by the 1Password test path; no temp file needed).
build_env_flags() {
    local k
    for k in "$@"; do
        printf -- '-e %s ' "$k"
    done
}
```

- [ ] **Step 4: Run, verify pass**

Run: `python run_bouy_tests.py test_bouy_onepassword.py::test_build_env_flags_from_keys`
Expected: PASS.

- [ ] **Step 5: Relax the `.env.test` hard requirement (`bouy:1116-1121`)**

Replace:

```bash
        # Use test environment file
        if [ ! -f .env.test ]; then
            output error ".env.test file not found!"
            output error "Please ensure .env.test exists with proper test database configuration."
            exit 1
        fi
```

with:

```bash
        # Use test environment file, OR the env already loaded from 1Password.
        if [ ! -f .env.test ] && [ "$BOUY_ENV_SOURCE" != "1password" ]; then
            output error ".env.test file not found!"
            output error "Provide .env.test, or sign into 1Password (it will read the 'test' field)."
            exit 1
        fi
```

- [ ] **Step 6: Branch the docker run env injection (`bouy:1263-1272`)**

Replace the `docker run` invocation:

```bash
        docker run --rm $TTY_FLAG \
            -v "$(pwd)":/app:cached \
            -w /app \
            --network "$NETWORK_NAME" \
            --env-file "$ENV_FILE_TO_USE" \
            -e PYTHONUNBUFFERED=1 \
            -e RUNNING_IN_DOCKER=1 \
            -e CONTENT_STORE_PATH=/tmp/test_content_store \
            "$TEST_IMAGE_TAG" \
            bash -c "$test_cmd"
```

with:

```bash
        # In 1Password mode there is no .env.test file: pass the already-exported
        # test vars through as valueless -e flags. Otherwise use the env file.
        ENV_INJECT_ARGS=()
        if [ "$BOUY_ENV_SOURCE" = "1password" ]; then
            # shellcheck disable=SC2046
            ENV_INJECT_ARGS=( $(build_env_flags $BOUY_ENV_KEYS) )
        else
            ENV_INJECT_ARGS=( --env-file "$ENV_FILE_TO_USE" )
        fi

        docker run --rm $TTY_FLAG \
            -v "$(pwd)":/app:cached \
            -w /app \
            --network "$NETWORK_NAME" \
            "${ENV_INJECT_ARGS[@]}" \
            -e PYTHONUNBUFFERED=1 \
            -e RUNNING_IN_DOCKER=1 \
            -e CONTENT_STORE_PATH=/tmp/test_content_store \
            "$TEST_IMAGE_TAG" \
            bash -c "$test_cmd"
```

- [ ] **Step 7: Verify the `.env.test` path still works**

Run (with `.env.test` present, as in CI/dev): `./bouy --programmatic test --mypy app/core/config.py`
Expected: runs as before (uses `--env-file .env.test`). If Docker isn't available in your environment, skip this manual check and rely on CI.

- [ ] **Step 8: Commit**

```bash
git add bouy bouy-functions.sh tests/bouy_tests/test_bouy_onepassword.py
git commit -m "feat(bouy): test runner reads 1Password 'test' field via -e passthrough

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Wire new tests into CI + full suite green

**Files:**
- Modify: `.github/workflows/ci.yml:631` (add the new module to the unit batch)
- Modify: `tests/test_bouy.sh` (only if it enumerates modules; otherwise no change)

- [ ] **Step 1: Add the module to the CI unit batch**

In `.github/workflows/ci.yml`, change the "Run bouy unit tests" step (around line 631):

```yaml
          poetry run python run_bouy_tests.py test_bouy_unit.py test_bouy_simplified.py
```

to:

```yaml
          poetry run python run_bouy_tests.py test_bouy_unit.py test_bouy_simplified.py test_bouy_onepassword.py
```

- [ ] **Step 2: Run the entire bouy suite locally exactly as CI does**

Run:
```bash
python run_bouy_tests.py test_bouy_unit.py test_bouy_simplified.py test_bouy_onepassword.py
python run_bouy_tests.py test_bouy_integration.py test_bouy_docker.py
python run_bouy_tests.py test_bouy_setup.py test_bouy_deploy.py
./tests/test_bouy.sh
```
Expected: all PASS.

- [ ] **Step 3: Confirm no secret ever lands on disk during a 1Password-mode run**

This is already asserted by `test_load_env_from_1password_writes_no_file` and `test_write_passthrough_overlay_names_only`. Additionally grep the working tree after the suite:
Run: `git status --porcelain | grep -E '\.env(\.|$)' || echo "no stray env files"`
Expected: `no stray env files`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run test_bouy_onepassword in the bouy unit batch

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Documentation

**Files:**
- Modify: `CLAUDE.md` (Environment Configuration / Initial Setup sections)
- Modify: `.env.example` (header comment)

- [ ] **Step 1: Document the 1Password path in `CLAUDE.md`**

Under "Environment Configuration", add a subsection:

```markdown
### 1Password secret loading (no `.env` on disk)

bouy can source per-environment config from 1Password instead of a `.env` file:

- **A `.env` (or `.env.test`/`.env.prod`) on disk always wins** — 1Password is not
  consulted, so OSS contributors are unaffected.
- With no override file, container-using commands read the matching field
  (`dev`/`test`/`prod`) from a 1Password item via `op read` and inject the values
  into containers through a runtime, names-only passthrough overlay. **Secrets are
  never written to disk.** Auth is the `op` desktop-app biometric integration.
- Pointer defaults: account `plentiful.1password.com`, vault `Pantry Pirate Radio`,
  item `bouy-env`. Override via `OP_ACCOUNT`/`OP_VAULT`/`OP_ITEM` or `config/op.conf`.
- `--no-1password` / `USE_1PASSWORD=false` force the file path; `--1password` forces the vault.

Commands:
- `./bouy op status` — show pointer, sign-in state, which fields exist.
- `./bouy op push [--field dev|test|prod|all]` — upload local `.env*` into the vault (migration).
- `./bouy op pull [--field dev] [--out FILE]` — print/inspect a field.

CI and AWS are unchanged (GitHub Secrets and Secrets Manager respectively).
```

- [ ] **Step 2: Add a pointer in `.env.example` header**

At the top of `.env.example`, add a comment:

```bash
# bouy can also load this configuration from 1Password (see CLAUDE.md →
# "1Password secret loading"). A .env on disk always overrides 1Password.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md .env.example
git commit -m "docs(bouy): document 1Password secret loading and bouy op commands

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (run after Task 13)

- [ ] Full bouy suite green (Task 12 Step 2 commands).
- [ ] `./bouy --help` lists `op`; `./bouy op status` prints pointer (signing in optional).
- [ ] With a real `.env` present, `./bouy up` / `./bouy test` behave exactly as before (`BOUY_ENV_SOURCE=file`, no `op` calls).
- [ ] Manual 1Password smoke test (requires the vault): `./bouy op push --field dev`, then `mv .env /tmp/`, then `./bouy --programmatic ps` → biometric prompt, services resolve config from the vault; restore `.env`.
- [ ] `git status` shows no `.env*` or other secret-bearing files created by any run.

## Notes for the implementer

- **Mirror every new function into BOTH `bouy` and `bouy-functions.sh`.** The pytest
  suite sources `bouy-functions.sh`; the real behavior lives in `bouy`. They must stay
  identical (this is the established pattern, e.g. `parse_mode`, `prompt_with_default`).
- **Never pipe into `load_env_lines`** (`cmd | load_env_lines`) — the exports would be
  lost in the subshell. Always `load_env_lines <<< "$blob"` or `load_env_lines < file`.
- `bouy` runs under `set -e`; call functions that may return non-zero only inside `if`/`||`.
- Per project memory: bouy tests run on the host (they `skipif` under `/.dockerenv`); run
  them with `python run_bouy_tests.py …`, not `./bouy test`.
