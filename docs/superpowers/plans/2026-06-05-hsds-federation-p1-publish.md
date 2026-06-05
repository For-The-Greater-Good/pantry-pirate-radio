# HSDS Federation P1 — Verifiable Publish (bite-sized implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL — implement this plan task-by-task with
> `superpowers:subagent-driven-development` (fresh subagent per task, two-stage review between tasks).
> Every task opens **red-first** (failing test → `run; expect fail` → minimal impl → `run; expect pass` → commit).
> Per-task iteration: `./bouy exec app pytest <path>::<test> -v` (single-file selection — `./bouy test --pytest`
> does not select files well, owner practice). Pre-PR full gate: `./bouy test` (black + ruff + mypy + bandit +
> pytest + coverage ratchet — Principle X). This is a **RED-tier** phase (crypto + concurrency + an append-only
> verifiable log): the PR Gauntlet phases 1–4 are mandatory, and the P1 verifiable-substrate PR is the one place
> the playbook recommends a one-off external security / distributed-systems spot-audit.

## Status (updated 2026-06-05)

- **Task -1 (HSDS version pin): RESOLVED → pin 3.1.1** (owner-confirmed, #522). The models implement 3.1.1, not the submodule's 3.2.3; advertising 3.2 would violate Principle II. Remaining: land the CI guard test (advertised version == the 3.1.1-shaped models) in PR-A.
- **Task 0 (Principle-IX decomposition): DONE → PR-A draft #549.** `job_processor.py` 1892→1328; both commit branches extracted to `app/reconciler/location_commit.py` (531) + `location_match.py` (193), both <600; pure refactor, full suite green, no behavior change. Remaining on PR-A: the Task -1 guard + the PR Gauntlet → mark ready for owner merge.
- **Next:** finish PR-A, then **PR-B** (RED-tier substrate: `FederationLog` + dense-sequence advisory-lock append [proven GO in the P0.5 memo] + RFC-6962 Merkle + C2SP checkpoints + proofs + aggregate + wire spec/fixtures) → **PR-C** (hooks + kill switch + endpoints) → **PR-D** (cold-start + archive + HSDS-FX + reference node + golden test). Entry point: [`../NEXT-SESSION.md`](../NEXT-SESSION.md).

---

**Objective.** Turn PPR from *discoverable* (P0) into ***verifiably readable***. Write a JCS-canonical,
content-addressed, origin-signed activity object into an append-only Merkle log (`federation_log`) at the
canonical-commit hooks; publish the head as a C2SP-signed checkpoint (`state.txt` + `/federation/checkpoint`);
serve sequence-numbered deltas on `/api/v1/federation/export` with inclusion proofs; verify consistency across
pulls. A second process can pull `?_since=<cursor>` and receive exactly the activities committed since, in
order, with **no skips under concurrent reconciler writes**, and a rewritten/forked/truncated history is
*provably* detectable. "No node is special, including ours," enforced by math.

**Design of record (AUTHORITATIVE — cite §-numbers, do not re-derive):**
[`../specs/2026-06-03-hsds-federation-core-design.md`](../specs/2026-06-03-hsds-federation-core-design.md) —
esp. **§5, §6.2 (a–g), §6.3, §8 (8.1–8.5), §9, §12.1, §14, §16, §20, §21**.
**Living plan / roadmap:** [`2026-06-03-hsds-federation-core.md`](2026-06-03-hsds-federation-core.md)
(the **P1 roadmap row**, the **"v3 DELTA (binding)"** block, the provisional Task 0–12 list). The roadmap row +
v3 DELTA are authoritative over the older task text.
**Spike memo (binding outcome):**
[`../research/2026-06-05-federation-p05-go-no-go.md`](../research/2026-06-05-federation-p05-go-no-go.md).
**Operating model:** [`../federation-ai-build-playbook.md`](../federation-ai-build-playbook.md).
**Epic body:** [`../federation-github-epic.md`](../federation-github-epic.md) → the `### \`P1\`` section (issue #522).

---

## Binding context for P1 (the decisions this plan executes — do not relitigate)

### The v3 DELTA, summarized (design §6.2/§17; plan "v3 DELTA (binding)"; epic #522)

1. **Verifiable substrate, not a plain delta feed.** Every appended activity is a JCS-canonical (RFC 8785),
   content-addressed (`id = sha256(jcs_bytes(envelope))`), **origin-signed** (`proof`, Ed25519) object. The
   object hash is the Merkle **leaf**; a consumer verifies origin from an S3 archive with zero network trust.
2. **Dense sequence under a short append lock** (= Merkle leaf index), assigned under an advisory lock scoped to
   **ONLY** `SELECT MAX(sequence)+1 → INSERT → COMMIT` — never the reconciler's per-resource commit.
   `safe-high-water` = top of the gap-free committed prefix.
3. **C2SP signed checkpoints** `(origin_did, tree_size, root_hash, timestamp)` over an RFC-6962 tree of the
   committed prefix, in C2SP signed-note format, published in `state.txt` + `GET /federation/checkpoint`.
4. **Inclusion proofs on `/export` rows; consistency proofs across pulls.** A rewritten / forked / truncated
   history breaks a proof — *provable*, not alleged.
5. **Archive tiering (NEVER destroy — §6.2g).** Live Postgres window bounded by SLA; older objects + tile hashes
   archived to S3 (still origin-verifiable); tree state retained forever; `_since` below the live window →
   redirect to verifiable snapshot/archive (or `410` + archive pointer).
6. **Kill switch (§6.2d, Principle XI).** `FEDERATION_ENABLED=False` = hard no-op at **every** hook site before
   any work + the **byte-identical-reconciler test**.
7. **Cold-start `_since=0`** covers **ALL** pre-existing canonical rows, built by rebuilding the §8.2 aggregate
   from the **RAW normalized tables** in the HAARRRvest export — NOT the lossy `location_master` view.
8. **HSDS-FX extraction + ecosystem artifacts:** normative wire spec + JSON Schema + `fixtures/federation/`
   (JCS vectors + worked proof + RFC-3339 fixture); conformance suite / hosted Readiness Checker /
   static-feed generator (DRY with fixtures); in-repo reference second node; golden P1 journey test.
9. **Vocabulary crosswalk (v3.1)** before HSDS-FX freezes field names: `actor`/`attributedTo`/`origin` →
   Open Referral's publisher/steward/source model (#558/#553/#508); `org-id.guide` alongside `did:web`.

### The P0.5 spike returned **GO** (binding — `research/2026-06-05-federation-p05-go-no-go.md`)

- **GO on the in-place dense-sequence advisory-lock append.** `pg_advisory_xact_lock(KEY)` scoped to ONLY
  `SELECT COALESCE(MAX(sequence),0)+1 → INSERT → COMMIT` (lock released at commit); the resource commit is
  **outside** the lock. **NO escalation** to the §6.2f single-writer-relay / CDC-LSN fallback.
- **Proven:** gapless + skip-free under 8/16 concurrent OS processes (0 skips, 6,707 live-consumer reads);
  resource commits not globally serialized (0.43s vs 1.80s serialized); append p99 ≈ 9–10 ms, ~1,600–1,800
  appends/s; cold-start raw-table rebuild `jcs_bytes`-identical to the Beacon aggregate (incl. both schedules,
  both languages); two-node loop lands a `federated_node` `location_source`; verifiable-substrate write cost
  p99 ≈ 0.18–0.24 ms (≈20–40× under budget) — **checkpoint signing need NOT be coalesced off the commit path**;
  the frontier root is byte-identical to the canonical RFC-6962 MTH at all sizes 1..2048.
- **Three caveats carried into P1 as explicit tasks/notes** (memo §Caveats):
  - **(a)** Append throughput is a single-lock serialized ceiling measured on empty local Docker Postgres;
    ">> PPR's write rate" is reasoned, not measured. **→ re-confirm on Aurora with representative volume** (Task 2 note + Task 10/13 runbook).
  - **(b)** Proof-2 parity was normalizer-vs-normalizer. **→ the golden parity test must compare to the REAL
    `/export` aggregate**, not normalizer-vs-normalizer (Task 8).
  - **(c)** Cold-start *scale* (whole-corpus replay timing) was untimed. **→ time it; note + guardrail** (Task 8).
- **Incidental (file separately, NOT P1 scope but a fidelity risk for Tasks 3/8):** the spike surfaced two real
  Beacon bugs — `BeaconPhone.extension` typed `Optional[str]` vs a numeric column silently drops any location
  with a phone extension; `_q_accessibility`'s `LIMIT 1` is batch-wide. P1 reuses Beacon *shaping*; if these
  bleak into the aggregate the parity test (Task 8) and the conformance fixtures (Task 11) will catch them. Open
  a separate ticket; do not let P1 inherit the bug.

### Live-code anchors verified against the current branch (write tasks against these REAL signatures)

- `app/reconciler/job_processor.py` — **1892 lines** (Task 0 decomposition target). The hook sites inside the
  one giant `JobProcessor.process_job_result` method (lines 337–~1300):
  - **Matched-Location branch** ≈ L908–L1092: `if match_id:` → org fill-only UPDATE + `self.db.commit()` (≈L1013) →
    `VersionTracker.create_version(...)` (≈L1024) → `location_creator.create_location_source(...)` (≈L1042) →
    `merge_strategy.merge_location(str(location_id), loc_confidence_score)` wrapped in try/except (≈L1079).
    The submarine sub-branch (`if is_submarine:` ≈L942) calls `submarine_handler.update_location(...)`.
  - **New-Location branch** ≈ L1093+: `location_creator.create_location(...)` returns a str id (≈L1150).
- `app/reconciler/merge_strategy.py` (888), `location_creator.py` (968), `submarine_location_handler.py` (248) —
  `submarine_location_handler.update_location(location_id, location, org_id)` is the submarine `Update` hook.
- `scripts/dedupe_near_duplicate_locations.py` (966) + `scripts/dedupe_same_org_locations.py` (373) — the **real
  `Delete` hook site**: `soft_delete_duplicate(...)` (near_duplicate L540) flips `is_canonical=FALSE` (L562) and
  calls `_log_audit(..., action="soft_delete", ...)` (L571) into `dedup_run_audit`. Scripts use a **plain sync
  SQLAlchemy `Session`** (`sessionmaker`). NOT the reconciler Tier-3 path (prevent-on-ingest).
- `app/api/v1/partners/beacon/services.py` (603) — `BeaconSyncService` (`_transform`, `_batch_lookups`,
  `_q_phones/_q_schedules/_q_languages/_q_accessibility/_q_sources`) is the Location-aggregate shaping to reuse;
  `BeaconRedirectService._resolve_terminal` (L537) + `_load_soft_delete_chain` (L519) is the survivor-chain
  resolver for `Delete.redirectTo` (`dedup_run_audit`, `DISTINCT ON (row_id) ... ORDER BY row_id, created_at DESC`,
  cycle/depth-guarded at `_MAX_SURVIVOR_CHAIN_DEPTH = 25`).
- `app/database/models.py` (394) — ORM declares `from .base import Base`; tables `organization/location/service/
  schedule/service_at_location/address` (phone/language/accessibility queried raw in Beacon). **`FederationLog`
  lands here.** Cold-start rebuilds from these RAW tables, NOT `location_master`.
- `app/federation/{canonical,signing,identity}.py` (P0, merged) — reuse `jcs_bytes` for the object `id` + the
  envelope `proof`; reuse `Ed25519PrivateKey.sign` / `.verify` (exposed via `signing.py`) for checkpoint signing.
  `identity.public_key_multibase` / `build_did_document` already ship the recovery-key schema.
- `app/api/v1/router.py` (519) — `router.include_router(...)` block L335–L350 (add the federation data router);
  `router.py:362` reads `settings.FEDERATION_PROFILE_URI`. `app/api/lambda_app.py` (70) already calls
  `register_federation_public_routes(app)` (L70) and `app.include_router(v1_router, prefix=...)` (L67) — the new
  read-only `/api/v1/federation/*` routes ride the slim Lambda for free **iff** they import no Redis/LLM.
- `app/core/config.py` — federation settings merged in P0 (L244–L275). **`FEDERATION_HSDS_VERSIONS` defaults to
  `["3.1.1"]`** and `FEDERATION_PROFILE_URI` is set. This is the seam of the HSDS-version conflict (Task -1).
- Migrations are **hand-authored Python modules** in `app/database/migrations/` (e.g. `add_schedule_location_index.py`)
  + raw DDL in `app/database/init_scripts/*.sql` — **there is no alembic `versions/` chain**; follow the
  existing pattern for the `federation_log` migration (Task 1).
- `infra/stacks/monitoring_stack.py` + `infra/stacks/submarine_stack.py` (EventBridge-Lambda precedent) +
  `infra/tests/` (pytest CDK assertions) — the archive/prune Lambda's alarms land here (Task 10).
- Constitution `constitution.md` §IX — **two stale `1568` references (L198 table row + L206 rationale)** → fix to
  `1892` in Task 0.

### Conflict surfaced and resolved in this plan: the **HSDS version pin** (OWNER DECISION REQUIRED)

The design (§7, §8.5, plan v3.1 DELTA, epic #522) says pin `@context` / Profile / fixtures to the **3.2 line**
(vendored submodule baseline v3.2.3). But P0 verified — and the live code confirms — that the **Pydantic models
implement 3.1.1, not 3.2.3**: `LocationResponse` (and the schedule/service models) **lack** `additional_websites`,
`additional_urls`, `attributes`, and `metadata`, and `FEDERATION_HSDS_VERSIONS` defaults to `["3.1.1"]`. **These
conflict.** Per Principle II (NON-NEGOTIABLE), federated objects MUST validate against *unmodified* HSDS Pydantic
models — so the advertised `@context` must match what the models actually emit. **Task -1** is an explicit early
decision task that surfaces this for owner sign-off and recommends a default; **nothing in P1 freezes the
`@context`/Profile/fixtures until Task -1 resolves.** This plan's default recommendation: **(b) pin HSDS-FX /
Profile / `@context` to 3.1.1 honestly** for P1 (smaller, truthful, unblocks the substrate), and file 3.2 model
implementation as a separate follow-up — see Task -1.

### PR-splitting strategy (P1 is large — ship as 4 Gauntlet-able sub-PRs, not one)

The playbook permits splitting a phase that exceeds reviewable/Gauntlet-able size; P1 plainly does (a 1892-line
decomposition + a Merkle/crypto substrate + endpoints + cold-start + archive + a whole spec artifact). Each
sub-PR is independently `./bouy test`-green and Gauntlet-able; each updates `CLAUDE.md` for its own surface
(Principle XIII). The golden P1 journey test (Task 12) is the literal phase gate and lands in **PR-D**.

- **PR-A — Decomposition + decision gate (Tasks -1, 0).** Owner-facing HSDS-version decision; `job_processor.py`
  1892 → focused sub-module; constitution §IX fix. Pure refactor + a doc decision; no behavior change. *GREEN/
  YELLOW tier.* Merges first so the hooks land cleanly.
- **PR-B — The verifiable substrate (Tasks 1, 2, 3, 11-fixtures-core).** `FederationLog` + migration; the
  advisory-lock append + Merkle/checkpoint engine; the §8.2 aggregate serializer; JCS vectors + worked-proof
  fixtures + JSON Schema. **RED tier — Gauntlet phases 1–4 mandatory + the external spot-audit lands here.**
  No hooks fire yet (`FEDERATION_ENABLED` can stay effectively dormant until PR-C wires the hooks); ships the
  crypto/concurrency core in isolation so it can be hammered.
- **PR-C — Hooks + kill switch + endpoints (Tasks 4, 5, 6, 7).** The three `Update`/`Delete` hooks; the
  byte-identical-reconciler kill-switch test; `/export`+`state.txt`+`/checkpoint`+`history`. *YELLOW/RED tier.*
- **PR-D — Cold-start + archive + observability + ecosystem + golden test (Tasks 8, 9, 10, 11-extraction, 12).**
  Cold-start raw-table parity; archive tiering (dual-env) + Principle XIV alarms; HSDS-FX extraction + Readiness
  Checker + static-feed generator + reference second node; the golden P1 journey test; docs. *YELLOW + RED
  (golden test) tier.*

STD-1 (vocabulary crosswalk #558/#553/#508) and STD-2 (upstream `last_modified`/tombstone PRs) are permissionless
and run in parallel during P1; STD-1's crosswalk **must land before Task 11 freezes the envelope field names**.

---

## Tasks

> Format per task: **Files** (create/modify/test) · **Red-first failing test** (concrete assertions / sketch) ·
> **Run; expect fail** · **Minimal implementation outline** · **Run; expect pass** · **Commit**.
> Task ordering: `-1` and `0` first (PR-A), then `1..12`. Task 0 is a **BINARY gate** — no hooks land until resolved.

---

### Task -1 (DECISION GATE, FIRST in PR-A): resolve the HSDS version pin for `@context` / Profile / fixtures

**Files:**
- Create: `docs/superpowers/research/2026-06-05-federation-hsds-version-pin.md` (one-page decision memo).
- Modify (only if the owner picks option a): nothing in this task — this task *records the decision*; the chosen
  `FEDERATION_HSDS_VERSIONS` value + `@context` host are then consumed by Tasks 3, 7, 11.

**Why this is a task, not a footnote.** Principle II is NON-NEGOTIABLE: federated `object`s validate against the
*unmodified* HSDS Pydantic models (`app/models/hsds/response.py`). Those models implement **3.1.1** (no
`additional_websites`/`additional_urls`/`attributes`/`metadata`), and `config.py` advertises `["3.1.1"]`. The
design wants the **3.2 line**. Emitting `@context: .../3.2` over a 3.1.1-shaped object is a lie a conformance
fixture (Task 11) would have to either ignore (defeating its purpose) or fail on.

**Red-first check (a failing assertion that pins the decision before code consumes it):**

```python
# tests/test_federation/test_hsds_version_pin.py
from app.core.config import Settings
from app.models.hsds.response import LocationResponse

def test_advertised_hsds_version_matches_model_shape():
    """The advertised @context line MUST match what the Pydantic models emit.
    Option (b) — pin 3.1.1 — is the default until 3.2 fields are implemented."""
    s = Settings()
    fields = set(LocationResponse.model_fields)
    has_32_fields = {"additional_websites", "additional_urls", "attributes"} <= fields
    if has_32_fields:
        assert any(v.startswith("3.2") for v in s.FEDERATION_HSDS_VERSIONS)
    else:
        # models are 3.1.1: we must NOT advertise 3.2 over a 3.1.1 object
        assert all(not v.startswith("3.2") for v in s.FEDERATION_HSDS_VERSIONS)
```

**Run; expect:** PASS *today* (models are 3.1.1, config advertises 3.1.1 — they already agree). This test is the
**guard** that keeps the agreement true; it fails the moment someone bumps `@context` to 3.2 without implementing
the fields. Commit it as the regression lock.

**Recommended default (flag for owner sign-off):** **option (b) — pin HSDS-FX / Profile / `@context` to 3.1.1
honestly for P1.** It is smaller, truthful, and unblocks the substrate now; implementing the 3.2 model fields is a
clean separate follow-up (and aligns with STD-2's upstream work). Option (a) — implement `additional_websites`/
`additional_urls`/`attributes`/`metadata` on the models first — is the design's literal intent but expands P1 and
mixes HSDS-modeling work into a crypto-substrate phase. The memo presents both; **the owner signs off before
Task 11 freezes fixtures.**

**Commit:** `docs(federation): P1 HSDS version-pin decision memo (3.1.1 default, owner sign-off) + regression guard`

---

### Task 0 (BINARY GATE, do FIRST after -1): decompose `job_processor.py` (1892 → <600) + fix the stale §IX entry

**Files:**
- Create: `app/reconciler/location_commit.py` (or similar focused name) — the extracted matched/new-Location
  commit branch as a cohesive unit the `Update` hooks can call into.
- Modify: `app/reconciler/job_processor.py` (delegate the two commit branches to the new module).
- Modify: `constitution.md` (§IX: `1568` → `1892` at **both** L198 and L206).
- Test: extend `tests/test_reconciler/` (existing reconciler tests must stay green — this is a behavior-preserving
  extraction); add a size-guard test.

**Red-first failing test:**

```python
# tests/test_reconciler/test_file_size_discipline.py
from pathlib import Path
def test_job_processor_under_600_lines():
    p = Path("app/reconciler/job_processor.py")
    assert len(p.read_text().splitlines()) < 600, "Principle IX: decompose before the hooks land"
```

**Run; expect fail:** `./bouy exec app pytest tests/test_reconciler/test_file_size_discipline.py -v` → FAIL (1892 lines).

**Minimal implementation outline.** Extract the matched-Location commit branch (≈L908–L1092: org fill-only UPDATE,
version tracking, `create_location_source`, `merge_location` call, submarine sub-branch) and the new-Location
branch (≈L1093–~L1300: `create_location`, addresses/phones/accessibility creation) into the new module as
functions/a small class taking `(db, location, job_result, org_id, location_creator, merge_strategy,
service_creator, submarine_handler, ...)`. `process_job_result` calls into them. **Behavior-preserving** — the
full reconciler test suite is the safety net; do NOT change commit ordering or the `merge_location` semantics.
Keep the new module <600 and cyclomatic ≤15 (split helpers if needed). Recommended over the written-exception
fallback (design §16: "Decision: decompose"); the fallback (author `federation-principle-ix-exception.md`) is
permitted only if extraction proves disproportionate — it will not here.

**Run; expect pass:** `./bouy exec app pytest tests/test_reconciler/ -v` (all green) + the size guard passes.

**Commit:** `refactor(reconciler): extract location-commit branches from job_processor (Principle IX, 1892→<600)`
and a second commit `docs(constitution): correct stale §IX job_processor line count (1568→1892)`.

---

### Task 1 (PR-B): `FederationLog` model + migration

**Files:**
- Modify: `app/database/models.py` (`+ class FederationLogModel(Base)`).
- Create: `app/database/migrations/add_federation_log.py` (follow the hand-authored migration pattern of
  `add_schedule_location_index.py`; raw DDL acceptable per the repo convention — there is no alembic chain).
- Test: `tests/test_federation/test_log_model.py`.

**Columns (design §6.2b, epic file-map):** `sequence` (BIGINT, dense, gapless, **unique**, the Merkle leaf index),
`id` / `leaf_hash` (the `sha256:` content address), `type` (`Update`/`Announce`/`Delete`), `federation_id`,
`object_canonical` (the JCS bytes / JSONB of the full envelope), `published_at`, `origin_did`. **Index on
`sequence`** (the keyset-pagination + safe-high-water key). Consider an index on `federation_id` for `history`.

**Red-first failing test:**

```python
# tests/test_federation/test_log_model.py
from app.database.models import FederationLogModel

def test_federation_log_columns_present():
    cols = set(FederationLogModel.__table__.columns.keys())
    assert {"sequence", "leaf_hash", "type", "federation_id",
            "object_canonical", "published_at", "origin_did"} <= cols

def test_sequence_is_indexed_and_unique():
    seq = FederationLogModel.__table__.columns["sequence"]
    assert seq.unique or any("sequence" in {c.name for c in ix.columns}
                             for ix in FederationLogModel.__table__.indexes)
```

**Run; expect fail:** module/class missing.

**Minimal implementation outline.** Declare `FederationLogModel(Base)` with the columns above; `sequence`
`unique=True, index=True`; `object_canonical` as `JSONB` (Postgres) or `LargeBinary` for raw JCS bytes — pick
JSONB for queryability but store the canonical form so `id` re-derivation is exact. Write the migration module
creating the table + indexes idempotently (`CREATE TABLE IF NOT EXISTS`). No append logic yet.

**Run; expect pass.** **Commit:** `feat(federation): FederationLog model + migration (§6.2b)`

---

### Task 2 (PR-B, RED): the append helper — dense-sequence advisory-lock append + Merkle/checkpoint engine

**Files:**
- Create: `app/federation/log.py` (`append(session, *, type, federation_id, object_dict, origin_did) -> int`;
  Merkle frontier state; `signed_checkpoint(...)`; `safe_high_water(session) -> int`; proof builders).
- Test: `tests/test_federation/test_log_append.py`, `tests/test_federation/test_log_merkle.py`,
  `tests/test_federation/test_log_append_concurrency.py` (Hypothesis/multiprocessing property test).

**The spike-proven design (memo Proof 1 + Proof 4 — implement EXACTLY this):** the append takes a **plain DB
session** (so the dedup scripts can call it — Task 5), and the critical section is **only**:
`pg_advisory_xact_lock(KEY)` → `SELECT COALESCE(MAX(sequence),0)+1` → build envelope (`id=sha256(jcs_bytes(env))`,
Ed25519 `proof`) → INSERT → COMMIT (lock auto-released at commit). The reconciler's resource commit is **outside**
this lock. `safe_high_water` = top of the gap-free committed prefix (because the lock makes the sequence dense
and gapless, this equals `MAX(sequence)` of committed rows). The Merkle tree is an **RFC-6962 frontier** (the
spike proved the root byte-identical to the canonical MTH at all sizes 1..2048, O(log n)).

**Red-first failing tests:**

```python
# tests/test_federation/test_log_append_concurrency.py  (the rank-1 RED test)
def test_concurrent_appends_are_gapless_and_skip_free():
    """8+ independent OS processes each appending N rows -> sequences exactly
    1..total, no gaps, no duplicates; a consumer advancing _since observes
    every sequence exactly once, in order, 0 skips (the M5 hazard)."""
    # spawn multiprocessing workers (separate connection each), then assert:
    seqs = fetch_all_sequences()
    assert seqs == list(range(1, len(seqs) + 1))          # dense, gapless
    assert len(seqs) == len(set(seqs))                     # no dup
    assert consumer_skip_count == 0                        # no late-row skip

def test_resource_commit_is_not_globally_serialized():
    """N workers each doing a ~0.2s resource step + an append complete in
    ~max(step) wall, not N*step — only the tiny append serializes."""
    assert wall_time < serialized_lower_bound  # e.g. < 0.6s for 8x0.2s
```

```python
# tests/test_federation/test_log_merkle.py
def test_frontier_root_matches_rfc6962_mth():
    leaves = [bytes([i]) for i in range(1, 2049)]
    for n in (1, 2, 3, 100, 1024, 2048):
        assert frontier_root(leaves[:n]) == reference_rfc6962_mth(leaves[:n])

def test_append_assigns_content_address_and_proof(db_session, signing_key):
    seq = append(db_session, type="Update", federation_id="example.com:1",
                 object_dict={"@context": "...", "object": {...}}, origin_did="did:web:example.com")
    row = fetch(seq)
    assert row.leaf_hash == "sha256:" + sha256(jcs_bytes(envelope_of(row))).hexdigest()
    assert verify_proof_signature(row)  # Ed25519 proof over jcs_bytes
```

**Run; expect fail:** `app/federation/log.py` missing.

**Minimal implementation outline.** Implement `append` with the exact lock scope above (reuse the spike's proven
shape). Build the envelope per §8.1 (`@context`, `id`, `type`, `actor`, `attributedTo`, `origin`, `federation_id`,
`object`, `published` RFC-3339, `sequence`, `proof`); `id = "sha256:" + sha256(jcs_bytes(envelope_without_id_or_proof?)).hexdigest()`
— **pin the exact pre-image in a fixture (Task 11)** so the content-address is unambiguous. Sign with the Ed25519
key loaded via `app/federation/identity.load_signing_key(settings.FEDERATION_SIGNING_KEY)`. The Merkle frontier:
maintain the running frontier so checkpoint issuance is O(log n); `signed_checkpoint` returns the C2SP signed-note
`(origin_did, tree_size=safe_high_water, root_hash, timestamp)` Ed25519-signed via `signing.py`'s raw sign. Add
inclusion-proof + consistency-proof builders (audit path / RFC-6962 consistency path).

> **Caveat-a note (memo §Caveat 1) — carry into the task body and the operator runbook (Task 12):** the spike's
> ~1,600–1,800 appends/s ceiling was measured on empty local Docker Postgres; ">> PPR's write rate" is reasoned,
> not measured. **Re-confirm append throughput on Aurora with representative volume during P1** (a load step in
> the PR-B Gauntlet or a staging measurement). The §6.2f relay/CDC escalation remains the documented answer if a
> future workload ever approaches ~10k writes/s — but the spike says no escalation now.

**Run; expect pass** (the concurrency test runs the multiprocessing harness from the spike). **Commit:**
`feat(federation): dense-sequence advisory-lock append + RFC-6962 Merkle/checkpoint engine (§6.2a/b)`

---

### Task 3 (PR-B): the §8.2 Location aggregate serializer

**Files:**
- Create: `app/federation/aggregate.py` (`build_location_aggregate(session, location_id) -> dict` — the HSDS
  `object`; and `build_envelope(aggregate, *, type, actor, attributed_to, origin, federation_id, sequence,
  published) -> dict`).
- Test: `tests/test_federation/test_aggregate.py`.

**Design refs §8.2 / §7 / §5.** One composed HSDS document per Location (Location + embedded schedules / phones /
addresses / languages / accessibility / services-at-location) — exactly what Beacon/PTF shape. **Reuse
`BeaconSyncService`'s query+shape logic** (`_batch_lookups`, `_q_*`, `_transform`) rather than re-deriving SQL.
**Critical (m1, Principle II):** `federation_id` / `attributedTo` / `origin` live in the **envelope**, NEVER inside
the HSDS `object`, which validates against the *unmodified* `app/models/hsds/response.py` models.

**Red-first failing test:**

```python
# tests/test_federation/test_aggregate.py
from app.models.hsds.response import LocationResponse

async def test_object_validates_against_unmodified_hsds_model(db_session, seeded_location):
    env = build_envelope(await build_location_aggregate(db_session, seeded_location.id),
                         type="Update", actor="did:web:example.com",
                         attributed_to="did:web:example.com", origin="did:web:example.com",
                         federation_id="example.com:%s" % seeded_location.id, sequence=1,
                         published="2026-06-05T00:00:00Z")
    # envelope carries identity fields; object does NOT
    assert {"federation_id", "attributedTo", "origin"} <= set(env)
    assert "federation_id" not in env["object"]
    assert "attributedTo" not in env["object"]
    LocationResponse.model_validate(env["object"])  # MUST NOT raise (Principle II)

async def test_aggregate_embeds_all_subentities(db_session, location_with_two_schedules):
    obj = await build_location_aggregate(db_session, location_with_two_schedules.id)
    assert len(obj["schedules"]) == 2          # spike Proof 2: don't collapse via DISTINCT ON
```

**Run; expect fail.**

**Minimal implementation outline.** Factor the Beacon batch-lookup queries into a reusable shaping path (either
import/compose `BeaconSyncService` internals or lift the SQL into `aggregate.py`). Emit the HSDS object with
embedded sub-entities (do NOT use `location_master` — it collapses schedules). `build_envelope` wraps it with the
§8.1 envelope fields; `published` is RFC-3339 (pin byte-exactly in Task 11). **Guard against the spike's incidental
Beacon bugs** (phone-extension type, accessibility `LIMIT 1`) — they would silently drop sub-entities; the
two-schedule + phone-with-extension cases in the test catch them.

**Run; expect pass.** **Commit:** `feat(federation): §8.2 Location aggregate serializer + envelope wrapper (Beacon-shaped)`

---

### Task 4 (PR-C): hook the matched/new-Location commit sites in `job_processor.py` → `Update` (echo-suppressed, kill-switch-guarded)

**Files:**
- Modify: `app/reconciler/location_commit.py` (the Task-0 module) to call `app/federation/log.append(...)` after
  the matched-Location commit (≈ post-L1013/L1079 equivalent) and after `create_location` in the new-Location
  branch.
- Test: `tests/test_federation/test_hook_job_processor.py`.

**Design refs §6.2d/e, m7.** Append an `Update` for the just-committed canonical Location. **Publish-side echo
suppression:** a commit driven **solely** by `federated_node` sources appends nothing (look at the job's
`source_type` / the location's source set — a pure-federated commit is a re-echo and must not republish, §10
no-echo). **Kill switch:** `if not settings.FEDERATION_ENABLED: return` is the FIRST line of the append call site
(hard no-op before any work — design §6.2d).

**Red-first failing test:**

```python
# tests/test_federation/test_hook_job_processor.py
def test_ppr_origin_commit_appends_update(processed_scraper_job, db_session):
    rows = fetch_federation_log(db_session)
    assert any(r.type == "Update" and r.federation_id.endswith(processed_scraper_job.location_id)
               for r in rows)

def test_pure_federated_commit_appends_nothing(processed_federated_only_job, db_session):
    assert fetch_federation_log(db_session) == []   # echo suppression (m7)

def test_killswitch_off_appends_nothing(monkeypatch, processed_scraper_job, db_session):
    monkeypatch.setattr(settings, "FEDERATION_ENABLED", False)
    assert fetch_federation_log(db_session) == []   # §6.2d hard no-op
```

**Run; expect fail.**

**Minimal implementation outline.** In the Task-0 commit module, after the canonical write is committed, build the
aggregate (Task 3) and call `log.append(...)` with `type="Update"`, `origin=settings.FEDERATION_DID`. Compute the
`federation_id = "<publisher-host>:<location-uuid>"` (§7 grammar). Skip when `FEDERATION_ENABLED` is off OR the
commit's sources are all `federated_node`. Wrap in try/except logging `federation_append_failed` so a federation
failure never aborts the reconciler job (Principle XI — mirror the existing `merge_location_failed` pattern).

**Run; expect pass.** **Commit:** `feat(federation): append Update at reconciler matched/new-Location commits (echo-suppressed, kill-switch-guarded)`

---

### Task 5 (PR-C): `Delete` derivation at the REAL site — the offline dedup scripts

**Files:**
- Modify: `scripts/dedupe_near_duplicate_locations.py` (`soft_delete_duplicate` ≈L540) and
  `scripts/dedupe_same_org_locations.py` (its soft-delete site) to append a `federation_log` `Delete` after the
  `is_canonical=FALSE` UPDATE + `_log_audit` insert.
- Modify (maybe): `app/federation/log.py` — confirm `append` already takes a plain `Session` (Task 2 contract).
- Test: `tests/test_federation/test_hook_dedup_delete.py`.

**Design refs §6.2e, §9 Delete.** The Tombstone object is `{ "type": "Tombstone", "federation_id": "<dead>",
"redirectTo": "<survivor federation_id | null>" }`. `redirectTo` resolves through the `dedup_run_audit` survivor
chain — **reuse Beacon `_resolve_terminal`** (`app/api/v1/partners/beacon/services.py:537`) to follow
dead→survivor to the terminal still-canonical row. The reconciler's inline Tier-3 path is prevent-on-ingest (no
soft-delete) — do **NOT** hook it. The scripts run **outside the reconciler worker** with a plain sync `Session`,
so the signing key MUST be available in script context (`settings.FEDERATION_SIGNING_KEY` / Secrets Manager in
AWS — design §13 "scripts AND checkpoint signer need access"). Kill-switch-guard the append.

**Red-first failing test:**

```python
# tests/test_federation/test_hook_dedup_delete.py
def test_soft_delete_emits_delete_with_resolved_redirect(dedup_run_with_chain, db_session):
    """dead_a -> survivor_b -> survivor_c (terminal canonical). The Delete for
    dead_a must redirectTo c's federation_id (terminal), not b's."""
    rows = [r for r in fetch_federation_log(db_session) if r.type == "Delete"]
    delete = next(r for r in rows if r.federation_id.endswith(dead_a_id))
    assert delete.object_canonical["object"]["type"] == "Tombstone"
    assert delete.object_canonical["object"]["redirectTo"].endswith(terminal_c_id)

def test_killswitch_off_no_delete(monkeypatch, dedup_run_with_chain, db_session):
    monkeypatch.setattr(settings, "FEDERATION_ENABLED", False)
    assert [r for r in fetch_federation_log(db_session) if r.type == "Delete"] == []
```

**Run; expect fail.**

**Minimal implementation outline.** In `soft_delete_duplicate`, after `rowcount > 0` and the audit insert, build a
`Tombstone` envelope and call `log.append(db, type="Delete", ...)`. Resolve `redirectTo` via a script-local copy
of the terminal-survivor walk (import/replicate `_resolve_terminal`'s logic against the same `dedup_run_audit`
chain query, cycle/depth-guarded). Only fire on `--apply` (never dry-run) and only when `FEDERATION_ENABLED`.

**Run; expect pass.** **Commit:** `feat(federation): emit Delete+redirectTo at dedup-script soft-delete (§9, survivor-chain resolved)`

---

### Task 6 (PR-C): hook submarine enrichment → `Update`

**Files:**
- Modify: `app/reconciler/submarine_location_handler.py` (`update_location` ≈ append after the dynamic UPDATE)
  OR the Task-0 commit module's submarine sub-branch — wherever the submarine commit lands.
- Test: `tests/test_federation/test_hook_submarine.py`.

**Design refs §6.2e.** Submarine enrichment is an `Update` (it fills missing hours/phone/email/description on an
existing canonical row). Kill-switch-guarded; echo-suppressed (submarine is never `federated_node`-sourced, so
echo suppression is a no-op here but apply the same guard for uniformity).

**Red-first failing test:**

```python
# tests/test_federation/test_hook_submarine.py
def test_submarine_enrichment_emits_update(processed_submarine_job, db_session):
    rows = fetch_federation_log(db_session)
    assert any(r.type == "Update" and r.federation_id.endswith(processed_submarine_job.location_id)
               for r in rows)
```

**Run; expect fail. Minimal impl:** after `update_location` persists, build the aggregate + `log.append(type="Update")`.
**Run; expect pass.** **Commit:** `feat(federation): append Update on submarine enrichment (§6.2e)`

---

### Task 7 (PR-C): `/api/v1/federation/{export, state.txt, checkpoint, history}` (both envs — Principle XV)

**Files:**
- Create: `app/api/v1/federation/__init__.py`, `app/api/v1/federation/router.py` (the data router — imports only
  `app/federation/{log,aggregate}` + DB; **no Redis/LLM** so the slim Lambda stays slim).
- Modify: `app/api/v1/router.py` (`router.include_router(federation_router)` in the L335–L350 block).
- Test: `tests/test_federation/test_export_endpoints.py`.

**Design refs §6.3.** `GET /export?_since=<seq>` → keyset-paginated NDJSON of signed objects **+ inclusion proofs**;
headers `X-Federation-Next-Cursor`, `X-Federation-Sequence` (= signed-checkpoint tree_size = safe-high-water),
`X-Federation-Retention`. `_since < live-window floor` → redirect to verifiable snapshot/archive (or `410` +
archive pointer) — Task 9 fills the archive side; in PR-C the boundary returns the `410`/redirect with the floor.
`GET /checkpoint` + `state.txt` → the current C2SP signed checkpoint (+ live-window floor, archive pointer).
`GET /history/{federation_id}` → per-aggregate activity history, each carrying its inclusion proof. Reuse the
Beacon `is_canonical` + confidence serve gate (`_BASE_WHERE`). Consumers verify a **consistency proof** on every
pull — the endpoint serves the proof material; the verify side is exercised by the reference node (Task 11/12).

**Red-first failing test:**

```python
# tests/test_federation/test_export_endpoints.py
def test_export_returns_signed_objects_with_inclusion_proofs(client, seeded_log):
    r = client.get("/api/v1/federation/export?_since=0")
    assert r.status_code == 200
    rows = [json.loads(l) for l in r.text.splitlines() if l]
    assert all("proof" in row and "inclusion_proof" in row for row in rows)
    assert int(r.headers["X-Federation-Sequence"]) == safe_high_water(seeded_log)

def test_delta_pull_returns_only_newer(client, seeded_log):
    r = client.get(f"/api/v1/federation/export?_since={mid_seq}")
    rows = [json.loads(l) for l in r.text.splitlines() if l]
    assert all(row["sequence"] > mid_seq for row in rows)

def test_below_window_floor_returns_410_or_redirect(client, archived_log):
    r = client.get("/api/v1/federation/export?_since=1", follow_redirects=False)
    assert r.status_code in (301, 302, 410)
    # archive pointer present in body or Location header

def test_checkpoint_and_state_txt_signed(client, seeded_log):
    cp = client.get("/api/v1/federation/checkpoint").json()
    assert {"origin", "tree_size", "root_hash", "timestamp", "signature"} <= set(cp)
    assert verify_checkpoint_signature(cp)

def test_consistency_proof_detects_rewritten_log(client, seeded_log):
    """A tampered (rewritten-leaf) log fails the consistency proof a consumer
    holding the prior checkpoint computes — provable, not alleged."""
    old_cp = client.get("/api/v1/federation/checkpoint").json()
    rewrite_a_committed_leaf(seeded_log)              # adversary mutates history
    new_cp = client.get("/api/v1/federation/checkpoint").json()
    assert not verify_consistency_proof(old_cp, new_cp, fetch_consistency_proof())
```

**Run; expect fail.**

**Minimal implementation outline.** Build the router with the four routes; stream NDJSON for `export`; build
inclusion proofs from the frontier/tree state (Task 2); serve the C2SP checkpoint from `log.signed_checkpoint`.
Wire into the v1 router; confirm it reaches the slim Lambda (the lambda already includes `v1_router`). Reuse
Beacon's `_BASE_WHERE` gate to exclude non-canonical/low-confidence/rejected rows from `export`.

**Run; expect pass.** **Commit:** `feat(federation): export/state.txt/checkpoint/history endpoints with inclusion+consistency proofs (§6.3, dual-env)`

---

### Task 8 (PR-D): cold-start `_since=0` from the HAARRRvest snapshot, rebuilt from RAW tables — parity vs the REAL `/export`

**Files:**
- Create: `app/federation/coldstart.py` (`build_snapshot_aggregate(raw_source, location_id) -> dict` reading the
  raw normalized tables in the HAARRRvest SQLite/S3 export).
- Test: `tests/test_federation/test_coldstart_parity.py`.

**Design refs §6.3, spike Proof 2 + Caveats (b)/(c).** `_since=0` MUST cover **ALL** pre-existing canonical rows,
served as a verifiable snapshot (objects + proofs + the checkpoint they verify against) from S3/CDN — never a live
Lambda full scan. **Rebuild the §8.2 aggregate from the RAW tables** (location + schedule + phone + address +
language + accessibility + service_at_location + service) — NOT `location_master` (it collapses schedules via
`DISTINCT ON` and string-aggregates phones/languages — confirmed lossy by the spike).

**Red-first failing test (memo Caveat (b) — compare to the REAL `/export`, not normalizer-vs-normalizer):**

```python
# tests/test_federation/test_coldstart_parity.py
async def test_coldstart_aggregate_byte_equals_live_export(db_session, raw_export, location_id):
    """The cold-start raw-table rebuild must be jcs_bytes-identical to the
    object the LIVE /export endpoint serves for the same federation_id —
    a flattened-view shortcut fails CI (spike Caveat b)."""
    live_obj = (await live_export_object(db_session, location_id))["object"]
    cold_obj = build_snapshot_aggregate(raw_export, location_id)["object"]
    assert jcs_bytes(cold_obj) == jcs_bytes(live_obj)

async def test_coldstart_covers_all_canonical_rows(db_session, raw_export):
    canonical_ids = await all_canonical_location_ids(db_session)
    snapshot_ids = snapshot_location_ids(raw_export)
    assert canonical_ids <= snapshot_ids        # no row left behind
```

**Run; expect fail.**

**Minimal implementation outline.** Read the raw tables from the export; rebuild the aggregate with the **same**
shaping path as Task 3 (DRY — the parity test enforces it). Generate the snapshot artifact (objects + inclusion
proofs + checkpoint) for S3/CDN. Serve `_since=0` as a redirect to the snapshot artifact (or stream it), per §13.

> **Caveat-c note (untimed cold-start scale):** the spike timed per-Location rebuild fidelity, not whole-corpus
> replay. **Add a timing measurement** (e.g. a `@pytest.mark.slow` or a one-off staging run) of full-corpus
> snapshot generation and record it in the operator runbook (Task 12); guardrail the snapshot build so it cannot
> run as a live Lambda full scan (design §6.3/§11.9).

**Run; expect pass.** **Commit:** `feat(federation): cold-start _since=0 raw-table snapshot + parity-vs-export test (§6.3)`

---

### Task 9 (PR-D): archive tiering (NOT prune) — dual-env, Principle XV (§6.2g)

**Files:**
- Create: `app/federation/archive.py` (tier objects + tile hashes to S3 / local-fs; retain tree state; advertise
  the live-window floor + archive location in `state.txt`).
- Modify: `app/api/v1/federation/router.py` (`state.txt` advertises floor + archive pointer; `_since < floor`
  redirect target).
- Create: a bouy-invoked worker entry (Docker) + the AWS EventBridge Lambda is added in `infra/` (Task 10).
- Test: `tests/test_federation/test_archive_tiering.py`.

**Design refs §6.2g (the v3 correction over v2.1's prune-and-410).** An append-only verifiable log **cannot prune
leaves without breaking proofs** — so this is *archive*, not destroy: the live Postgres window is bounded by the
SLA (`FEDERATION_RETENTION_DAYS`); older objects + tile hashes are archived to S3 (still origin-verifiable from the
archive with no network trust); **tree state is retained so checkpoints + consistency proofs stay valid forever.**
`_since` below the live window → redirect to the verifiable snapshot/archive (or `410` + archive pointer).
`state.txt` advertises the live-window floor + archive location. Dual-env: AWS EventBridge Lambda (HAARRRvest-
publisher cadence); Docker bouy worker/loop.

**Red-first failing test:**

```python
# tests/test_federation/test_archive_tiering.py
def test_archived_objects_still_origin_verifiable(archive_store, signing_key):
    """An object tiered to the archive verifies its Ed25519 proof with zero
    network — origin-verifiable from the archive (§6.2g)."""
    obj = archive_store.fetch(some_old_federation_id)
    assert verify_proof_signature(obj)

def test_consistency_proof_holds_across_archive_boundary(seeded_then_archived_log):
    """A consumer who held an old checkpoint can still verify the new head is
    an append-only extension AFTER older leaves were tiered out of Postgres."""
    assert verify_consistency_proof(old_cp, current_cp, fetch_consistency_proof())

def test_state_txt_advertises_floor_and_archive_pointer(client, archived_log):
    state = client.get("/api/v1/federation/state.txt").text
    assert "live_window_floor" in state and "archive" in state
```

**Run; expect fail. Minimal impl:** move rows older than the SLA to the archive store (S3 prefix / local path),
keep the tree/frontier state and the per-leaf hashes in Postgres (or in the archived tiles), update the floor;
serve archived `_since` via redirect. The tree is **never** rebuilt from a truncated set — consistency must hold.

**Run; expect pass.** **Commit:** `feat(federation): archive tiering (never destroy) — live window + S3 archive, proofs hold forever (§6.2g)`

---

### Task 10 (PR-D, Principle XIV — NON-NEGOTIABLE): observability for the P1 archive Lambda

**Files:**
- Create/Modify: `infra/stacks/federation_stack.py` (the archive/prune EventBridge Lambda — model on
  `infra/stacks/submarine_stack.py`'s EventBridge-Lambda precedent).
- Modify: `infra/stacks/monitoring_stack.py` (the Lambda's Error alarm + a dashboard widget on
  `PantryPirateRadio-{env}`, routed to `pantry-pirate-radio-alerts-{env}`).
- Test: `infra/tests/test_federation_stack.py` (CDK assertions — model on `infra/tests/test_submarine_stack.py`).

**Design refs §14 (XIV — not deferrable past introduction).** P1 is the phase that first creates a federation
Lambda (the archive tiering Lambda), so its alarm + widget + `infra/tests/` assertion land **in P1**. (The
pull-consumer Lambda + ingest SQS + DLQ alarms are P2's — do NOT add them here.)

**Red-first failing test:**

```python
# infra/tests/test_federation_stack.py
def test_archive_lambda_has_error_alarm(synth_template):
    synth_template.has_resource_properties("AWS::CloudWatch::Alarm", {
        "MetricName": "Errors", "Namespace": "AWS/Lambda",
        # alarm action -> the pantry-pirate-radio-alerts-{env} SNS topic
    })

def test_archive_lambda_scheduled(synth_template):
    synth_template.resource_count_is("AWS::Events::Rule", 1)
```

**Run; expect fail. Minimal impl:** define the Lambda + EventBridge schedule in `federation_stack.py`; add the
Errors alarm wired to the alerts topic + a dashboard widget; assert in `infra/tests/`.
**Run; expect pass.** **Commit:** `feat(federation): archive Lambda + EventBridge schedule + XIV alarm/widget/infra-test (§14)`

---

### Task 11 (PR-B core + PR-D extraction): normative wire spec + JSON Schema + `fixtures/federation/` + HSDS-FX

**Files:**
- Create: `fixtures/federation/` — canonical activity examples (`update.json`, `announce.json`, `delete.json`),
  the normative **JSON Schema** (`envelope.schema.json`), **JCS canonicalization vectors** (input → expected
  bytes), a **worked proof** (envelope → `jcs_bytes` → `id` → `proof` → inclusion proof, all pinned), and the
  **RFC-3339 `published` fixture** (byte-exact).
- Create (PR-D): the HSDS-FX spec artifact (`docs/hsds-fx/` or a separate repo per STD-3) + governance section +
  Readiness Checker + static-feed generator (DRY with `fixtures/`).
- Test: `tests/test_federation/test_fixtures_conform.py`, `tests/test_federation/test_jcs_vectors.py`.

**Design refs §8 (NORMATIVE), §8.4, §8.5, STD-3.** Envelope key is `type`; `id` + `proof` REQUIRED on every
published envelope; `@context` matched as **set-membership against the advertised supported-versions list** (major
mismatch → `422`, NOT exact-string equality — §8.4 fracture inoculation). `published` is RFC-3339, pinned
byte-exactly. The fixtures serve **triple duty** (§8.5): PPR CI conformance gate, hosted Readiness Checker, and a
copy-paste static-feed generator — keep them DRY. **Vocabulary crosswalk (v3.1, STD-1 feeds this):** before
freezing field names, align `actor`/`attributedTo`/`origin` to the publisher/steward/source model (#558/#553/#508)
and carry `org-id.guide` alongside `did:web`. **Pin per Task -1's decision** (default: 3.1.1).

**Red-first failing test:**

```python
# tests/test_federation/test_jcs_vectors.py
import json, pathlib
from app.federation.canonical import jcs_bytes
def test_jcs_vectors_pin_byte_exactly():
    for vec in json.loads(pathlib.Path("fixtures/federation/jcs_vectors.json").read_text()):
        assert jcs_bytes(vec["input"]) == vec["expected"].encode("utf-8")

# tests/test_federation/test_fixtures_conform.py
def test_all_fixtures_validate_against_envelope_schema():
    schema = load("fixtures/federation/envelope.schema.json")
    for f in ("update.json", "announce.json", "delete.json"):
        env = load(f"fixtures/federation/{f}")
        jsonschema.validate(env, schema)            # MUST pass
        assert {"type", "id", "proof"} <= set(env)  # §8.1 required

def test_worked_proof_reproduces():
    wp = load("fixtures/federation/worked_proof.json")
    assert ("sha256:" + sha256(jcs_bytes(wp["envelope_preimage"])).hexdigest()) == wp["id"]

def test_context_set_membership_rejects_major_mismatch():
    assert is_acceptable_context("...3.1...", advertised=["3.1.1"])
    assert not is_acceptable_context("...4.0...", advertised=["3.1.1"])  # -> 422 upstream
```

**Run; expect fail. Minimal impl:** author the fixtures, schema, vectors, and worked proof; implement
`is_acceptable_context` set-membership (consumed by the inbox in P3, but the rule + test live here). Stand up the
HSDS-FX artifact + governance annex (STD-3 scope — DRY with `fixtures/`). The conformance tests are the gate.
**Run; expect pass.** **Commit:** `feat(federation): normative wire spec + JSON Schema + JCS vectors + worked proof + HSDS-FX extraction (§8, §8.5)`

---

### Task 11b (PR-D): in-repo reference second node + golden P1 journey test

**Files:**
- Create: `tests/test_federation/reference_node/` (a minimal fixture peer serving `/export` + `state.txt` +
  `/checkpoint` from the fixtures corpus — also the P7 clone-able example).
- Create: `tests/test_federation/test_golden_journey_p1.py` (`@pytest.mark.integration` — the literal phase gate).
- Test: itself.

**Design refs §15.** The golden P1 journey, against the in-repo reference node:
**concurrent-append → pull `/export?_since=<cursor>` → proof-verify (object signature + inclusion + checkpoint
consistency) → cold-start parity → archive boundary, INCLUDING a tampered-log case** that breaks the consistency
proof and is detected.

**Red-first failing test (sketch):**

```python
# tests/test_federation/test_golden_journey_p1.py
@pytest.mark.integration
def test_golden_p1_journey(reference_node, db_session):
    concurrent_append_N_activities(db_session)                  # under real concurrency
    rows = reference_node.pull_export(since=0)
    assert all(verify_object_signature(r) for r in rows)        # origin auth
    assert all(verify_inclusion_proof(r, checkpoint) for r in rows)
    assert verify_consistency_proof(prev_cp, current_cp, proof) # append-only extension
    assert coldstart_parity_holds()                             # _since=0 == live /export
    assert archive_boundary_redirects_and_proofs_hold()
    # tampered-log MUST be detected:
    rewrite_a_committed_leaf(db_session)
    assert not verify_consistency_proof(prev_cp, reference_node.checkpoint(), proof)
```

**Run; expect fail. Minimal impl:** build the reference node (a small ASGI app or in-process client serving the
fixtures). Wire the journey end-to-end. **Run; expect pass.** **Commit:**
`test(federation): in-repo reference second node + golden P1 journey (concurrent→proof→parity→archive→tamper)`

---

### Task 12 (PR-D, Principle XIII): docs + the redeploy-free kill-switch runbook + full gate

**Files:**
- Modify: `CLAUDE.md` (the Federation subsection — the export/checkpoint contract; the `federation_*` structlog
  grep targets per design §14; the kill-switch operator runbook).
- Modify: the memory file `project_federation.md` (operational state).
- Test: the full gate `./bouy test`.

**Design refs §14, §6.2d.** Document: the `/api/v1/federation/{export,state.txt,checkpoint,history}` contract;
the `federation_*` structlog grep targets — `federation_checkpoint_published`, `federation_proof_failed`,
`federation_consistency_failed` (**alarmed**), `federation_archive_tiered`, `federation_killswitch_active`,
`federation_append_failed`; the **redeploy-free kill-switch runbook** (`FEDERATION_ENABLED=False` → hard no-op,
byte-identical reconciler); and the Aurora-throughput re-measure result + cold-start scale timing (Tasks 2/8 notes).

**Run the full gate:** `./bouy test` (black + ruff + mypy + bandit + pytest + coverage ratchet). Fix failures.
**Commit:** `docs(federation): P1 export/checkpoint contract + federation_* grep targets + kill-switch runbook`

---

## Self-review (every design § → a task; NON-NEGOTIABLEs covered; spike GO + caveats reflected; conflict surfaced)

**Every design § maps to a task:**
- §5 (architecture / verifiable substrate) → Tasks 2, 7. §6.2a (signed content-addressed objects) → Task 2/11.
  §6.2b (Merkle log + signed checkpoints) → Task 2, 7. §6.2c (witness format fixed now) → checkpoint format is
  C2SP/witness-compatible in Task 2 (mesh itself is P6, out of scope — epic #522 "Out of scope"). §6.2d (kill
  switch) → Tasks 4/5/6 guards + Task 4 byte-identical test + Task 12 runbook. §6.2e (hook sites) → Tasks 4/5/6.
  §6.2f (escalation) → **NOT taken** (spike GO); carried as the Task 2 contention-escalation note only. §6.2g
  (archive, never destroy) → Task 9. §6.3 (publish/read + cold-start) → Tasks 7, 8. §8.1 envelope → Tasks 2, 11.
  §8.2 aggregate → Task 3. §8.3 signing (object `proof`) → Task 2 (reuses P0 `signing.py`/`canonical.py`). §8.4
  version handling (set-membership) → Task 11. §8.5 HSDS-FX → Task 11 + STD-3. §9 Delete (Tombstone+redirectTo) →
  Task 5. §12.1 (CvRDT/origin-dedup) → **P2, not P1** (no ingest here) — flagged out-of-scope. §14 (observability)
  → Tasks 10, 12. §16 (file-size) → Task 0. §20 (interop tiers) → Task 11 (Tier 0/1 = no-crypto NDJSON). §21
  (open decisions) → surfaced below + Task -1.
- **NON-NEGOTIABLEs:** **II** (HSDS compliance) → Task 3 object-validates-against-unmodified-models test + Task -1
  version honesty. **III** (TDD red-first) → every task opens with a failing test + run-and-expect-fail. **IX**
  (file-size) → Task 0 binary gate (decompose, recommended) + §IX stale-entry fix. **XIV** (AWS observability) →
  Task 10 (archive Lambda alarm + widget + infra test, in-phase). **XV** (dual-env) → Task 7 (export on Uvicorn +
  slim Lambda; the data router imports no Redis/LLM), Task 8 (cold-start via S3), Task 9 (dual-env archive). Also
  **XI** (no silent loss) → all hooks try/except-logged so federation never aborts a reconciler/dedup job.
- **Spike GO + caveats reflected:** Task 2 implements the exact proven advisory-lock-scope append + frontier
  (Proof 1 + 4); Task 2 carries Caveat (a) (Aurora throughput re-measure); Task 8 carries Caveat (b) (parity vs
  REAL `/export`, not normalizer-vs-normalizer) and Caveat (c) (time cold-start scale); the incidental Beacon bugs
  are flagged as a Task 3/8 fidelity risk + a separate ticket. **No §6.2f escalation** (binding GO).
- **HSDS-version conflict surfaced:** Task -1 is an explicit decision gate with a regression-guard test and a
  recommended default (3.1.1), blocking Task 11's fixture freeze until owner sign-off.

## Open decisions for the owner

1. **HSDS version pin (Task -1) — DECIDE FIRST.** Design says pin the 3.2 line; the Pydantic models implement
   3.1.1 (no `additional_websites`/`additional_urls`/`attributes`/`metadata`) and config advertises `["3.1.1"]`.
   **Recommended default: (b) pin 3.1.1 honestly for P1**, file 3.2 model implementation as a separate follow-up.
   Alternative: (a) implement the 3.2 fields first (expands P1). Sign off before Task 11 freezes fixtures.
2. **Archive live-window length + S3 layout (design §21, epic #522 "Open decision").** How much log stays in live
   Postgres before tiering to S3 (`FEDERATION_RETENTION_DAYS` is the SLA lever, default 365), and the S3 archive
   layout (tlog-tiles / Tessera tile-prefix scheme is the design's reference). Needed by Task 9.
3. **External security / distributed-systems spot-audit of PR-B** (playbook "verify the verifier", item 4): the
   one place "AI reviewed itself" is genuinely insufficient. Recommended (not blocking); alternatively seed a known
   defect and confirm the Gauntlet catches it.
4. **Recovery-key verify-side enforcement** stays scheduled to P3 (playbook pending-decision 2) — P1 only consumes
   the P0 recovery-key *schema* for checkpoint signing; no change requested, noted for completeness.

## Execution handoff

Build via `superpowers:subagent-driven-development`: fresh subagent per task, TDD red-first, two-stage review
between tasks. Group tasks into the four PRs above (A: -1,0 · B: 1,2,3,11-core · C: 4,5,6,7 · D: 8,9,10,11-ext,11b,12).
Run the **PR Gauntlet** per PR; PR-B is RED-tier (phases 1–4 + external spot-audit). The golden P1 journey (Task
11b) is the literal phase gate. Each PR updates `CLAUDE.md` for its own surface (Principle XIII). STD-1/STD-2 run
in parallel; STD-1's crosswalk lands before Task 11 freezes field names.
