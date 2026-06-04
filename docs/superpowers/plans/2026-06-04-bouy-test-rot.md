# bouy Test-Rot Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the remaining pre-existing bouy test rot found during the 1Password work: two failing `test_bouy_deploy.py` tests (one a real bouy bug), the unsafe `prompt_with_default` drift, five environment-dependent tests, a non-executable shell-test fixture — and close the CI loop so all 8 bouy suites run in CI.

**Architecture:** Pure test-infrastructure and small bash fixes, folded directly into `feat/bouy-1password-secrets` (the pending 1Password PR) at the operator's request. Each task is independent and committed separately.

**Tech Stack:** Bash (`bouy`, `bouy-functions.sh`), pytest (`tests/bouy_tests/`, host-run via `poetry run python run_bouy_tests.py`), GitHub Actions (`.github/workflows/ci.yml`).

**Branch:** `feat/bouy-1password-secrets` (folded into the pending PR). Worktree: `/Users/bryanmoran/code/for-the-greater-good/pantry-pirate-radio-1pw`.

**Ground truth (verified at origin/main `f92d286`):** `test_bouy_deploy.py` fails 2/11 at main with the SAME two tests as on the feature branch — `test_scraper_aws_requires_aws_cli` and `test_scraper_aws_no_name_shows_usage`. Everything below is pre-existing rot, not feature fallout.

---

## Task 1: `scraper --aws` validates the scraper name BEFORE the state-machine lookup

**Bug:** `bouy:1729-1740` runs `aws stepfunctions list-state-machines` unconditionally after arg-stripping; with no scraper name the user gets `State machine '...' not found` instead of usage. The `""` usage case at `bouy:~1779-1788` is unreachable for this path. The failing test `test_bouy_deploy.py::TestBouyScraperAwsArgParsing::test_scraper_aws_no_name_shows_usage` already asserts the desired behavior — it IS the red TDD test.

**Files:**
- Modify: `bouy` (the `scraper)` handler's `--aws` branch, region ~1694-1790)

- [ ] **Step 1: Confirm the test fails (red)**

Run: `poetry run python run_bouy_tests.py "test_bouy_deploy.py::TestBouyScraperAwsArgParsing::test_scraper_aws_no_name_shows_usage"`
Expected: FAIL with `State machine ... not found` in the assertion output.

- [ ] **Step 2: Insert the early validation**

In `bouy`, immediately after this line (~1727):

```bash
                set -- "${REMAINING_ARGS[@]}"
```

insert:

```bash
                # Validate input BEFORE any AWS state-machine lookup so a
                # missing scraper name yields usage, not an AWS error.
                if [ -z "${1:-}" ]; then
                    output error "No scraper specified."
                    echo "Usage: ./bouy scraper --aws [--prod|--dev] NAME [NAME2 ...]"
                    echo "       ./bouy scraper --aws [--prod|--dev] --all"
                    echo "       ./bouy scraper --aws [--prod|--dev] scouting-party"
                    echo "       ./bouy scraper --aws [--prod|--dev] --status [EXEC_ARN]"
                    echo "       ./bouy scraper --aws [--prod|--dev] --logs"
                    exit 1
                fi
```

- [ ] **Step 3: Remove the now-dead `"")` case**

In the same handler's `case "${1:-}" in` block (~1779), delete the entire now-unreachable case branch:

```bash
                    "")
                        output error "No scraper specified."
                        echo "Usage: ./bouy scraper --aws [--prod|--dev] NAME [NAME2 ...]"
                        echo "       ./bouy scraper --aws [--prod|--dev] --all"
                        echo "       ./bouy scraper --aws [--prod|--dev] scouting-party"
                        echo "       ./bouy scraper --aws [--prod|--dev] --status [EXEC_ARN]"
                        echo "       ./bouy scraper --aws [--prod|--dev] --logs"
                        exit 1
                        ;;
```

- [ ] **Step 4: Verify (green + no collateral)**

Run: `poetry run python run_bouy_tests.py test_bouy_deploy.py` → expect `1 failed, 10 passed` (only `test_scraper_aws_requires_aws_cli` remains — Task 2).
Run: `bash -n bouy` → clean.

- [ ] **Step 5: Commit**

```bash
git add bouy
git commit -m "fix(bouy): validate scraper name before AWS state-machine lookup

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Repair `test_scraper_aws_requires_aws_cli` (portable symlinks + docker stub)

**Rot (two layers):** (a) the restricted-PATH fixture symlinks tools from a hardcoded `/usr/bin/<cmd>` with a silent `os.path.exists` skip — on macOS `date` lives in `/bin`, so it's silently absent; (b) the scraper path runs bouy's docker check before the AWS-CLI check, and with no `docker` in PATH the run dies with "Docker daemon is not running" instead of reaching `AWS CLI not found`.

**Files:**
- Modify: `tests/bouy_tests/test_bouy_deploy.py` (both restricted-PATH tests, lines ~86-107 and ~195-215; add `shutil` import)

- [ ] **Step 1: Confirm the failure mode (red)**

Run: `poetry run python run_bouy_tests.py "test_bouy_deploy.py::TestBouyScraperAwsArgParsing::test_scraper_aws_requires_aws_cli"`
Expected: FAIL; output contains `date: command not found` and `Docker daemon is not running`.

- [ ] **Step 2: Make both restricted-PATH fixtures portable and stage a docker stub**

Add `import shutil` to the imports at the top of `test_bouy_deploy.py` (if absent). In BOTH tests (`test_deploy_requires_aws_cli` ~line 86 and `test_scraper_aws_requires_aws_cli` ~line 195), replace:

```python
        for cmd in ["dirname", "basename", "xargs", "sed", "grep", "cat", "id", "tput", "cut", "date"]:
            src = f"/usr/bin/{cmd}"
            if os.path.exists(src):
                (fake_bin / cmd).symlink_to(src)
```

with:

```python
        for cmd in ["dirname", "basename", "xargs", "sed", "grep", "cat", "id", "tput", "cut", "date"]:
            src = shutil.which(cmd)
            assert src, f"required tool missing from host: {cmd}"
            (fake_bin / cmd).symlink_to(src)
        # Stage a docker stub that always succeeds so bouy's docker check
        # passes and the flow reaches the AWS CLI check under test.
        fake_docker = fake_bin / "docker"
        fake_docker.write_text("#!/bin/bash\nexit 0\n")
        fake_docker.chmod(0o755)
```

(`shutil.which` + assert replaces the silent skip — a missing tool now fails loudly instead of producing a misleading downstream error.)

- [ ] **Step 3: Verify (green)**

Run: `poetry run python run_bouy_tests.py test_bouy_deploy.py`
Expected: **11 passed** (first time ever).
Lint: `poetry run black --check tests/bouy_tests/test_bouy_deploy.py && poetry run ruff check tests/bouy_tests/test_bouy_deploy.py` → clean (the worktree venv has the CI-pinned versions).

- [ ] **Step 4: Commit**

```bash
git add tests/bouy_tests/test_bouy_deploy.py
git commit -m "test(bouy): portable restricted-PATH fixtures + docker stub for AWS-CLI tests

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Unify `prompt_with_default` (quote-safe via `printf -v`)

**Bug:** `bouy`'s copy (~743-765) assigns via `eval "$var_name='$value'"` — a password containing a single quote aborts the wizard (`unexpected EOF while looking for matching quote`); it also lacks the non-tty stdin branch that `bouy-functions.sh`'s copy (~566-599) has. The two copies have drifted structurally (pre-existing).

**Files:**
- Modify: `bouy` and `bouy-functions.sh` (replace both `prompt_with_default` bodies with one identical implementation)
- Modify: `tests/bouy_tests/test_bouy_setup.py` (add adversarial test)

- [ ] **Step 1: Write the failing adversarial test**

Append inside `class TestBouySetup` in `tests/bouy_tests/test_bouy_setup.py`:

```python
    def test_setup_password_with_single_quote(self, test_env, bouy_path, temp_dir):
        """A password containing a single quote must not abort the wizard."""
        # db password (contains ') -> provider 1 -> API key -> HAARRRvest skip -> no 1Password
        answers = "\n".join(["pir'ate", "1", "test_key", "skip", "n"]) + "\n"
        result = subprocess.run(
            [bouy_path, "setup"],
            input=answers,
            capture_output=True,
            text=True,
            cwd=temp_dir,
            env=test_env,
        )
        env_file = Path(temp_dir) / ".env"
        assert env_file.exists(), result.stdout + result.stderr
        assert "pir'ate" in env_file.read_text()
```

- [ ] **Step 2: Run, verify it fails against current bouy**

Run: `poetry run python run_bouy_tests.py test_bouy_setup.py::TestBouySetup::test_setup_password_with_single_quote`
Expected: FAIL (wizard aborts on the quote, no `.env` written — or `.env` lacks the password).

- [ ] **Step 3: Replace BOTH `prompt_with_default` bodies with this single implementation**

```bash
# Prompt for a value with a default. Reads stdin directly when not a TTY
# (tests/CI). Assignment uses printf -v so the VALUE is never eval'd —
# quotes, backticks, and $() in passwords are safe. Only the validated
# variable NAME passes through eval (export).
prompt_with_default() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    local is_password="${4:-false}"
    local value=""

    if [ ! -t 0 ]; then
        # Non-interactive: read one line; EOF -> default (set -e safe).
        if IFS= read -r value; then
            :
        else
            value=""
        fi
    else
        if [ "$is_password" = "true" ]; then
            echo -n "$prompt [$default]: "
            read -s value || true
            echo  # New line after password input
        else
            read -p "$prompt [$default]: " value || true
        fi
    fi

    if [ -z "$value" ]; then
        value="$default"
    fi

    printf -v "$var_name" '%s' "$value"
    eval "export $var_name"
}
```

In `bouy` this replaces lines ~743-765; in `bouy-functions.sh` lines ~566-599. The bodies must end up byte-identical (verify with `diff <(sed -n '/^prompt_with_default()/,/^}/p' bouy) <(sed -n '/^prompt_with_default()/,/^}/p' bouy-functions.sh)`).

- [ ] **Step 4: Verify (green + full setup suite + adversarial sweep)**

Run: `poetry run python run_bouy_tests.py test_bouy_setup.py` → 10 passed (9 prior + 1 new).
Adversarial sanity in scratch bash (no repo files):

```bash
bash -c '
source /Users/bryanmoran/code/for-the-greater-good/pantry-pirate-radio-1pw/bouy-functions.sh
for v in "pir'"'"'ate" "pa\"ss" "ba\`ck" "\$(touch /tmp/pwn_test_marker)"; do
  printf "%s\n" "$v" | prompt_with_default "p" "d" "OUT"
  echo "OUT=[$OUT]"
done
[ -e /tmp/pwn_test_marker ] && echo "INJECTION!" || echo "NO_INJECTION_OK"'
```

Expected: each `OUT=[...]` echoes the literal input; final line `NO_INJECTION_OK`.

- [ ] **Step 5: Commit**

```bash
git add bouy bouy-functions.sh tests/bouy_tests/test_bouy_setup.py
git commit -m "fix(bouy): unify prompt_with_default; quote-safe assignment via printf -v

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Pin `BOUY_TEST_MODE` in the five env-dependent tests

**Rot:** five tests set `env["COMPOSE_CMD"]` directly, but bouy only honors the override via `BOUY_TEST_MODE=1` + `BOUY_TEST_COMPOSE_CMD` (`bouy:~384-388` — the documented test seam). Without it, the REAL docker compose runs, so the tests pass/fail depending on whether a pantry-pirate-radio stack happens to be up (one currently fails on this machine for exactly that reason).

**Files:**
- Modify: `tests/bouy_tests/test_bouy_integration.py` (`test_service_not_running_error` ~line 397-416, `test_verbose_mode` ~line 488)
- Modify: `tests/bouy_tests/test_bouy_docker.py` (the three tests setting `COMPOSE_CMD` at ~lines 177, 204, 252)

- [ ] **Step 1: Capture the current red state**

Run: `poetry run python run_bouy_tests.py test_bouy_integration.py test_bouy_docker.py`
Expected (with the local stack running): 1 failure — `test_service_not_running_error`. Note the exact failing set for comparison.

- [ ] **Step 2: Fix each of the five tests**

In each, where the test currently does (exact var names vary slightly — locate by the `COMPOSE_CMD` assignment):

```python
        env["COMPOSE_CMD"] = <mock>
```

change to the canonical seam (matching `test_invalid_scraper_name` at ~line 421, which does it correctly):

```python
        env["BOUY_TEST_MODE"] = "1"
        env["BOUY_TEST_COMPOSE_CMD"] = <same mock>
```

(Keep the existing mock value; only the routing changes. Remove the now-unused bare `COMPOSE_CMD` assignment.)

- [ ] **Step 3: Verify robustness BOTH ways**

Run with the local stack up (as it is): `poetry run python run_bouy_tests.py test_bouy_integration.py test_bouy_docker.py` → 0 failures (skips OK).
Lint the two files with black/ruff as in Task 2.

- [ ] **Step 4: Commit**

```bash
git add tests/bouy_tests/test_bouy_integration.py tests/bouy_tests/test_bouy_docker.py
git commit -m "test(bouy): route compose mocks through BOUY_TEST_MODE seam

Five tests set COMPOSE_CMD directly, which bouy ignores without
BOUY_TEST_MODE — so they silently exercised the REAL docker stack and
passed/failed depending on machine state.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Make `mock_compose.sh` executable in git

**Rot:** `tests/shell/fixtures/mock_compose.sh` is mode `100644` in git; CI compensates with an explicit `chmod +x` (`.github/workflows/ci.yml:610`), but local `./tests/test_bouy.sh` runs fail 10/15 because the mock can't execute.

**Files:**
- Modify: git file mode of `tests/shell/fixtures/mock_compose.sh`

- [ ] **Step 1: Fix the mode**

```bash
chmod +x tests/shell/fixtures/mock_compose.sh
git update-index --chmod=+x tests/shell/fixtures/mock_compose.sh
git ls-files -s tests/shell/fixtures/mock_compose.sh   # expect 100755
```

- [ ] **Step 2: Verify the local shell suite improves**

Run: `./tests/test_bouy.sh 2>&1 | tail -5`
Expected: substantially more passes than the prior 5/15 (the suite mocks COMPOSE_CMD, so no real services start). Record the exact count. If stragglers remain, confirm each is the documented docker-compose-version JSON fallback (a warning + plain-text fallback, by design at `bouy:~1228-1236`) and report rather than chasing.
(Leave the CI `chmod` line in place — harmless, defensive.)

- [ ] **Step 3: Commit**

```bash
git add tests/shell/fixtures/mock_compose.sh
git commit -m "test(bouy): track mock_compose.sh as executable

CI chmods it (ci.yml:610) so CI passed while every local run failed 10/15.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Add `test_bouy_deploy.py` to CI (closing 8/8)

**Pre-req:** Tasks 1-2 make the suite 11/11. The suite has no docker/AWS/network dependence (all mocked; verified during investigation).

**Files:**
- Modify: `.github/workflows/ci.yml` ("Run bouy unit tests" step, ~line 631)

- [ ] **Step 1: Edit the batch**

Change:
```yaml
          poetry run python run_bouy_tests.py test_bouy_unit.py test_bouy_simplified.py test_bouy_onepassword.py test_bouy_setup.py
```
to:
```yaml
          poetry run python run_bouy_tests.py test_bouy_unit.py test_bouy_simplified.py test_bouy_onepassword.py test_bouy_setup.py test_bouy_deploy.py
```

- [ ] **Step 2: Run the full CI batch locally**

Run: `poetry run python run_bouy_tests.py test_bouy_unit.py test_bouy_simplified.py test_bouy_onepassword.py test_bouy_setup.py test_bouy_deploy.py`
Expected: **78 passed** (21+36+10+11 — note setup grew to 10 in Task 3).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run test_bouy_deploy — all 8 bouy suites now in CI

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] All suites: the Task 6 batch (78 passed) + `test_bouy_integration.py test_bouy_docker.py` (0 failures with stack up) + `./tests/test_bouy.sh` (improved count from Task 5).
- [ ] `bash -n bouy && bash -n bouy-functions.sh` clean; `prompt_with_default` byte-identical across both files.
- [ ] `git log --oneline feat/bouy-1password-secrets..fix/bouy-test-rot` shows exactly the 5-6 commits above.
- [ ] Dispatch a code-quality review of the full stacked diff before PR.
- [ ] PR: base `feat/bouy-1password-secrets` while that PR is open; retarget main after it merges.

## Notes for the implementer

- Worktree `/Users/bryanmoran/code/for-the-greater-good/pantry-pirate-radio-1pw` must be on `fix/bouy-test-rot` during execution. **Do not touch** `/Users/bryanmoran/code/for-the-greater-good/pantry-pirate-radio`. Never invoke the real `op` CLI. Don't start real docker services (the main tree's stack owns the compose project name).
- bouy tests run on the host: `poetry run python run_bouy_tests.py <args>` from the worktree (venv already has pytest, pytest-cov, and CI-pinned black/ruff).
- `bouy` runs under `set -e`; any new predicate calls go inside `if`/`||`.
- A one-shot timer in the controller session pushes `feat/bouy-1password-secrets` and opens its PR at 6:30pm — work on `fix/bouy-test-rot` does not affect it (different branch; the push targets the branch ref), but the worktree must be back on the feature branch before 6:30pm because the timer sanity-checks `git branch --show-current`.
