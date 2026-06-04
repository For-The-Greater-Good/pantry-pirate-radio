# Design: bouy secrets from 1Password (no `.env` on disk)

- **Date:** 2026-06-03
- **Status:** Approved (design); pending implementation plan
- **Branch:** `feat/bouy-1password-secrets`
- **Author:** Jolly (with Claude Code)

## 1. Summary

Let `bouy` source its environment configuration from **1Password** instead of a
plaintext `.env` on disk, mirroring the approach used in `gitgat/claysmasher`'s
`trapper` script. Secrets are fetched at runtime, held only in the process
environment, and injected into containers without ever writing a secrets file to
disk. A `.env` on disk, when present, **always wins** and 1Password is not
consulted — preserving the workflow of OSS contributors who do not have access to
the vault, and giving the operator a local override escape hatch.

The gating factor for access becomes **1Password biometric auth** (the `op` CLI's
desktop-app integration), not any secret typed on a command line or stored in a
file. This is deliberately "agent-friendly": an automation can run `./bouy up` and
the only interactive step is a Touch ID approval.

## 2. Goals / Non-goals

### Goals
- Operator can run `bouy` with **no `.env` on disk**; all config comes from 1Password.
- **Secrets never touch the disk** — not via `.env`, not via a temp env file.
- **`.env` (per environment) overrides 1Password** when present (whole-file precedence).
- **Zero disruption for OSS contributors**: the classic `.env` path keeps working with no flag.
- **Per-environment** config: `dev` / `test` / `prod` are distinct sets.
- The only thing *required* on disk is the 1Password pointer, and that is defaulted
  in `bouy` itself (so in practice nothing extra is required — just be signed in).
- bouy's existing test suite is extended to cover the new behavior and continues to pass.

### Non-goals (explicitly out of scope)
- **CI / GitHub Actions is unchanged.** It already injects GitHub Secrets as
  `environment:` vars and does not rely on a real `.env` on disk
  (`.github/workflows/ci.yml` derives `.env.test` from `.env.example` via `sed`).
- **Claude-CLI authentication is untouched.** It lives in the `claude_config` Docker
  volume (`/root/.config/claude`), orthogonal to env secrets.
- **AWS deployment / Secrets Manager is untouched.** `DATABASE_SECRET_ARN` and the
  CDK secrets path (`infra/shared_config.py`) are independent of local `bouy` env loading.
- **No per-key layering** in v1 (see Open Questions). `.env` precedence is whole-file.
- No change to `config/defaults.yml` semantics (it remains the shared pipeline-config
  source of truth read by Python/CDK).

## 3. Reference pattern (claysmasher `trapper`)

For grounding, `gitgat/claysmasher`:
- Uses **`op read "op://Vault/Item/field"`** (and `op document get` for binary files)
  to pull secrets into the process environment at runtime — **never** writing a
  resolved secrets file to disk.
- One vault ("Clay Smasher"), one item ("Fastlane"), one field per secret.
- Selects the account via an `OP_ACCOUNT` env var (defaulted in-script).
- Provides a `--no-1password` fallback to local `.env.local` files.
- Caches "secrets loaded" in-process to avoid re-querying on parallel invocations.

This design adapts that pattern to bouy's needs. The key difference: claysmasher
injects into a single subprocess (Fastlane); bouy must inject into **many Docker
containers**, which is the one genuinely new piece of engineering (Section 6).

## 4. Current state (what we're changing)

| Concern | Today | File:line |
|---|---|---|
| bouy reads `.env` at shell level | `if [ -f .env ]` → `while IFS='='` export loop | `bouy:96-110` |
| Containers get env | every service has `env_file: ../../.env` | `.docker/compose/base.yml` (e.g. :12,34,56,79,98), `docker-compose.prod.yml`, plugin overlays |
| Mode selection | `parse_mode` appends a compose file per `--dev/--prod/--test` | `bouy-functions.sh:66-96` |
| Setup writes secrets | wizard copies `.env.example` → `.env`, `sed`-injects values, timestamped backup | `bouy:607-725` |
| Test runner env | builds `.env.test.tmp` merge, `docker run --env-file` | `bouy:~1128-1271` |
| Test hooks | `BOUY_TEST_MODE` / `BOUY_TEST_COMPOSE_CMD` override the compose command | `bouy:112-115` |

Notable: the `.env` export loop at `bouy:96-110` runs at **script top, before any
mode flag is parsed**. Today that is fine (dev and prod both use `.env`). Our
mode-specific fields require **mode detection to move earlier** (Section 6.4).

## 5. 1Password structure

- **Account (default):** `plentiful.1password.com` (the org account; this is a work project).
- **Vault (default):** `Pantry Pirate Radio`
- **Item (default):** `bouy-env`
- **Fields:** three multiline fields — `dev`, `test`, `prod` — each holding the
  full contents of the corresponding env file (`.env`, `.env.test`, `.env.prod`)
  verbatim, in `KEY=value` lines (same format bouy already parses).

A multiline **field** is chosen over a 1Password **document** because fields are
inline-editable in the 1Password UI; documents would require re-upload to change a
single value. (`op document get` remains a viable alternative; noted in Open Questions.)

### Pointer resolution (the "only required on-disk value")
Resolved in this order, first hit wins:
1. Environment variables `OP_ACCOUNT`, `OP_VAULT`, `OP_ITEM`.
2. An optional committed `config/op.conf` (shell `KEY=value`, **contains no secrets** —
   only account/vault/item names).
3. Built-in defaults in `bouy` (the values above).

Because (3) exists, **nothing must be added to disk** for the operator's machine —
being signed into the right 1Password account is sufficient.

## 6. Design

### 6.1 Mode → override file + 1Password field

| Mode | CLI | Override file (wins if present on disk) | 1Password field |
|---|---|---|---|
| dev (default) | _(none)_ / `--dev` | `.env` | `dev` |
| test | `--test` | `.env.test` | `test` |
| prod | `--prod` | `.env.prod` → falls back to `.env` if absent | `prod` |

`.env.prod` is **new**. For backward compatibility, prod mode falls back to `.env`
when `.env.prod` is absent (today prod uses `.env`).

### 6.2 Selection & precedence algorithm (whole-file)

```
mode      = detect_mode("$@")            # dev | test | prod  (see 6.4)
file      = override_file_for(mode)      # .env | .env.test | .env.prod(→.env)
field     = op_field_for(mode)           # dev | test | prod

if file exists on disk:
    load env from file (existing export loop)      # 1Password NOT consulted
    source = "file"
elif use_1password_enabled (auto-detect or --1password):
    require op installed && signed in (else clear error)
    blob = op read "op://$OP_VAULT/$OP_ITEM/$field" --account "$OP_ACCOUNT"
    load env by parsing blob in memory (reuse the export loop on the blob)
    source = "1password"
else:
    error: no $file and 1Password unavailable → run `./bouy setup` or `op signin`
```

**Auto-detect** (no flag needed):
- `--no-1password` (or `USE_1PASSWORD=false`) → never use 1Password.
- `--1password` (or `USE_1PASSWORD=true`) → force 1Password even if a file exists
  (useful for testing the path); error if `op` unavailable.
- Default: file-if-present-else-1Password-if-available. If neither, the clear error above.

### 6.3 Never-on-disk injection into containers

The blob is parsed **in memory** (reusing the `bouy:96-110` key=value loop) and the
variables are `export`ed into bouy's own process environment. Containers then receive
them **by name**, with values flowing only through the process environment:

- **Compose path (`up`, `logs`, `exec`, scraper, etc.):**
  - Each service's `env_file: ../../.env` becomes optional via the long-form
    `env_file: [{ path: ../../.env, required: false }]`, so it is silently skipped
    when the file is absent. (Small, backward-compatible change across `base.yml`,
    `docker-compose.dev.yml`, `docker-compose.prod.yml`, and the three plugin
    overlays under `plugins/ppr-*/.docker/compose.yml`.)
  - bouy generates a **names-only passthrough overlay** at runtime (temp file,
    removed via the existing cleanup trap) that adds `environment: [KEY1, KEY2, …]`
    (bare names — Docker Compose passthrough) to each **active** service. Variable
    *names are not secret*, so this temp file carries no secret values. The key list
    comes from the parsed blob, so it can never drift from the actual config. Service
    list is derived from the active compose set (`docker compose … config --services`
    after the env is exported, so interpolation resolves).
  - This overlay is appended to `$COMPOSE_FILES` only on the 1Password path; the
    `.env` path is unchanged.
- **Test path (`docker run`):** bouy builds value-less `-e KEY1 -e KEY2 …` flags
  (Docker passes the current value of each named var through from bouy's env), so
  **no temp env file is created** — this also sidesteps the existing `.env.test.tmp`
  race condition.

### 6.4 Integration seam: mode detection must precede env load

The env load at `bouy:96-110` runs before args are parsed. Introduce a lightweight
`detect_mode "$@"` (scans args for `--test`/`--prod`, defaults `dev`) that runs
*before* the load block, so the correct override file and 1Password field are chosen.
The existing unconditional `.env` block at `bouy:96-110` is replaced by the
Section 6.2 algorithm. (Implementation note for the plan: keep the export loop body
identical so behavior for the `.env` path is byte-for-byte unchanged.)

### 6.5 Auth (biometric, two accounts signed in)

- Uses the `op` CLI's **desktop-app integration** (biometric unlock). No service
  account token, no secret on the command line.
- Two accounts are signed in on the operator's machine
  (`plentiful.1password.com`, `bryanandcaroline.1password.com`); all `op` calls pass
  `--account "$OP_ACCOUNT"` to disambiguate.
- bouy detects and reports clearly when: `op` is not installed; not signed in;
  the account/vault/item/field cannot be read.

### 6.6 New `bouy op` subcommands + setup integration

- `./bouy op status` — print resolved account/vault/item, sign-in state, and which
  fields (`dev`/`test`/`prod`) exist. No secrets printed.
- `./bouy op push [--field dev|test|prod|all]` — read local `.env` / `.env.test` /
  `.env.prod` and write them into the corresponding field(s) via `op item create`
  (first time) / `op item edit`. **This is the one-command migration** from existing
  `.env` files into the vault.
- `./bouy op pull [--field dev]` — print a field to **stdout** for inspection;
  writes a file only with an explicit `--out PATH`.
- `./bouy setup` gains an optional "Configure 1Password" branch that writes
  `config/op.conf` and offers to `op push` the current `.env`. The classic `.env`
  wizard remains the default for contributors.

## 7. Failure modes & messages

| Condition | Behavior |
|---|---|
| No override file, `op` not installed | Error: install 1Password CLI or run `./bouy setup` to create `.env`. |
| No override file, `op` installed but not signed in | Error: `op signin --account $OP_ACCOUNT` (or unlock desktop app). |
| `op read` fails (missing vault/item/field) | Error naming the exact `op://` path that failed; suggest `./bouy op status`. |
| `--1password` forced but `op` unavailable | Hard error (no silent fallback to `.env`). |
| Blob parse yields zero valid keys | Error: field exists but is empty/malformed. |

No silent fallbacks that could mask a misconfiguration (Constitution XI — pipeline
resilience / no silent data loss applied to config).

## 8. Security considerations

- `config/op.conf` (if used) and the generated passthrough overlay contain **only
  names**, never secret values — safe to commit / write to disk.
- Secret values exist only in bouy's process environment and the containers it
  launches; nothing is written to a file.
- `.gitignore` must continue to ignore `.env*`; add `config/op.conf` as a tracked
  file (names only) and ensure no generated temp overlay path is committable.
- bandit/safety unaffected (no Python secret handling added).

## 9. Testing plan (integral — bouy has a real suite)

bouy's tests are pytest modules under `tests/bouy_tests/` driven by
`run_bouy_tests.py`, plus `tests/test_bouy.sh`; CI runs them at
`.github/workflows/ci.yml:631-641`. Testable shell functions are mirrored into
`bouy-functions.sh` and exercised by sourcing that file in a subprocess with mocked
commands (e.g. `COMPOSE_CMD="echo docker compose"`).

**Approach (TDD — tests written first, must fail, then implementation):**

1. **Mirror functions** for testability: every new shell function
   (`detect_mode`, `resolve_op_pointer`, `load_env_from_1password`,
   `build_passthrough_overlay`, `op_status`/`op_push`/`op_pull`) is added to **both**
   `bouy` and `bouy-functions.sh`, matching the existing duplication pattern.
2. **Mock `op`**: add a `BOUY_OP_CMD` test override (parallel to
   `BOUY_TEST_COMPOSE_CMD`) so tests inject a stub `op` that returns canned blobs /
   exit codes without a real vault. Default is the real `op`.
3. **New module** `tests/bouy_tests/test_bouy_onepassword.py` covering:
   - `detect_mode` returns dev/test/prod for the right flags (and default).
   - Pointer resolution precedence: env vars > `config/op.conf` > built-in defaults.
   - Precedence: when override file exists, `op` is **never invoked** (assert the
     mock records zero calls); when absent, the blob is fetched and parsed.
   - Blob parsing produces the same exported vars as the equivalent `.env` file
     (parity with the existing export loop).
   - Passthrough overlay contains the blob's **keys only** and **no values**.
   - **No-disk guarantee**: after a simulated 1Password-mode run, assert no
     `.env*` file and no secrets-bearing file was created in the working dir
     (temp overlay, if present, contains only names).
   - Failure modes from Section 7 emit the documented errors / exit codes.
   - `op push`/`pull`/`status` invoke the mocked `op` with the expected args.
4. **Setup-branch test** in `tests/bouy_tests/test_bouy_setup.py`: the new
   "Configure 1Password" path writes `config/op.conf` and does not write secrets.
5. **Regression**: the entire existing bouy suite
   (`test_bouy_unit`, `test_bouy_simplified`, `test_bouy_integration`,
   `test_bouy_docker`, `test_bouy_setup`, `test_bouy_deploy`) must still pass
   unchanged — the `.env` path is behavior-preserving.
6. **CI wiring**: add `test_bouy_onepassword.py` to the unit batch in
   `.github/workflows/ci.yml` (alongside `test_bouy_unit.py test_bouy_simplified.py`).
7. Run via `python run_bouy_tests.py test_bouy_onepassword.py` during development
   and the full `./tests/test_bouy.sh` + `run_bouy_tests.py …` before completion.
   (Note: per project memory, bouy tests run on the host, not inside the Docker test
   container — they `skipif` under `/.dockerenv`.)

## 10. Documentation

- Update `CLAUDE.md` (Environment Configuration / setup sections) to document the
  1Password path, `bouy op` subcommands, and the precedence rules (Constitution XIII).
- Update `.env.example` header and/or `README` setup notes to mention the optional
  1Password path and that `.env` always wins.

## 11. Open questions / future enhancements

- **Per-key layering** (deferred): load 1Password as a base and let a *partial*
  `.env` override only the keys it defines. More powerful but always prompts for
  biometrics; v1 uses whole-file precedence per the approved design.
- **Document vs field** storage in 1Password: fields chosen for inline editability;
  `op document get` is a drop-in alternative if blobs grow unwieldy.
- **Account default**: defaulted to `plentiful.1password.com`; trivially changed via
  `OP_ACCOUNT` / `config/op.conf` if the personal account is preferred.
- **Caching**: claysmasher caches "loaded" in-process; bouy is a single short-lived
  invocation per command, so a single `op read` per run is sufficient (no cache needed).
