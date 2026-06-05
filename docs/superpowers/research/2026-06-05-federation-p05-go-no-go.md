# HSDS Federation P0.5 — De-risking Spike Go/No-Go Memo

**Date:** 2026-06-05
**Phase issue:** #521 (P0.5 — De-risking spike, HARD GATE)
**Branch:** `spike/federation-p05` (throwaway; deleted after this memo — only this memo survives)
**Decision required:** owner accepts/declines GO before P1 (#522) is unblocked. P1–P7 carry `blocked:hard-gate` until this is accepted.

## Recommendation: **GO** — build P1 on the in-place dense-sequence verifiable-log substrate (design §6.2). No escalation to the §6.2f single-writer-relay / CDC-LSN fallback is warranted.

This GO is **machine-confirmed by two independent agents**: a build agent that implemented + measured the four proofs, and an adversarial verifier that read the spike code, proved the assertions non-vacuous, independently reasoned and *constructed* the failure scenarios, and re-reproduced the critical result. The owner is not asked to verify concurrency or crypto — only to accept the recommendation.

## What was proven (real measurements, project Postgres test DB, committed P0 primitives)

### Proof 1 — Dense sequencer under genuine concurrency (rank-1 risk) — PASS
Append assigns a gapless sequence under `pg_advisory_xact_lock(KEY)` scoped to **only** `SELECT COALESCE(MAX(sequence),0)+1 → INSERT → COMMIT` (lock released at commit); the reconciler's resource commit is **outside** this lock.
- **Gapless + skip-free under real parallelism:** 8 and 16 independent OS processes (spawn multiprocessing, separate connection each) × up to 400 appends = up to 6,400 rows → sequences exactly `1..N`, no gaps, no duplicates, consumer observed every sequence once in order, **0 skips**. The no-skip/gapless assertions were shown non-vacuous (an injected gap is caught).
- **M5 hazard (higher seq visible before lower commits) is impossible** — proven by construction: a higher sequence cannot even be *allocated* until the lock holder (lower sequence) commits and releases. Verified against rollback-mid-append, connection-death-before-commit, and a live consumer advancing `_since` during concurrent writes (6,707 reads, 0 skip events). The `SELECT MAX` *inside* the lock window is the load-bearing invariant (and why a plain SERIAL/SEQUENCE — which gaps on rollback — was correctly rejected).
- **Resource commits are NOT globally serialized:** 8 × 0.2 s resource steps completed in 0.43 s wall (vs 1.80 s if serialized) — only the tiny append serializes.
- **Contention/throughput:** append p99 ≈ 9–10 ms; **~1,600–1,800 appends/s** sustained, stable as workers double (a single-lock serialized ceiling, not a collapse).

### Proof 2 — Cold-start aggregate parity from RAW tables — PASS
A Location aggregate rebuilt from the raw normalized tables is `jcs_bytes`-identical to the live `BeaconSyncService` aggregate for all shared content (incl. **both** of two distinct schedules, both languages) and a faithful **superset** (it additionally carries service_at_location→service). The `location_master` materialized view is confirmed **lossy** (`DISTINCT ON` drops a schedule; `STRING_AGG`s phones/languages) — cold-start must rebuild from raw tables, not the view (design §6.3/Task 8 already mandates this).

### Proof 3 — Two-node loop — PASS
Node A appends a signed `Update` envelope (`jcs_bytes` content-address + Ed25519 `proof`); Node B pulls by sequence, verifies the object signature, lands a `source_type='federated_node'` `location_source` row; idempotent on re-pull; a tampered envelope fails verification.

### Proof 4 — Verifiable-substrate write cost — PASS (≈20–40× under budget)
Inline hot-path total (JCS canonicalize + sha256 leaf + Ed25519 sign + O(log n) Merkle frontier append) p99 ≈ **0.18–0.24 ms** (budget was low-single-digit ms). The frontier append produces a root **byte-identical to the canonical RFC-6962 MTH at all sizes 1..2048** and scales logarithmically (≈2.4 µs at 1k leaves → ≈3.9 µs at 1M). **Checkpoint signing does NOT need to be coalesced off the commit path.**

## Caveats (the verifier flagged these; none change the GO)
1. **Throughput is a single-lock serialized ceiling (~1,600–1,800/s on local Docker Postgres), not a fleet-scaling number, and ">> PPR's write rate" is reasoned, not measured** (the local DB is empty). It is ~2–3 orders above PPR's realistic change rate (a low-hundreds-of-thousands-of-locations corpus on scraper cadence). **P1 action:** re-confirm 1c throughput on Aurora with representative volume; the §6.2f relay/CDC escalation remains the documented answer if a future workload ever approaches ~10k writes/s.
2. **Proof 2 parity is normalizer-vs-normalizer** (raw rebuild vs a re-normalized BeaconLocation), not against Beacon's literal serialized wire bytes — fair for proving rebuild *fidelity*; P1's golden parity test should compare to the actual `/export` aggregate.
3. **Cold-start *scale*** (replaying the whole corpus) was not timed — only per-Location rebuild fidelity. P1 concern.
4. Disposable-only nuances: the thread-variant 1b sleep was too short to show overlap (cite only the multiprocessing 1b); the disposable `append_log` leaf used `repr()` not real JCS, but Proof 4 measured the real JCS+sign+Merkle cost separately (correctly scoped, not double-counted).

## Incidental findings (independent of federation — file separately)
The spike surfaced two real production **Beacon** bugs while reusing `BeaconSyncService`: (1) `BeaconPhone.extension` typed `Optional[str]` vs a numeric DB column → any phone *with an extension* raises a Pydantic error and the **entire location is silently dropped** from the Beacon sync output (`beacon_transform_failed`); (2) `_q_accessibility`'s `LIMIT 1` is batch-wide, so in a multi-location page at most one location gets accessibility data. Worth a separate ticket.

## If accepted
P1 (#522) is unblocked: build the design-§6.2 verifiable log with the in-place dense-sequence append proven here; carry the four caveats into P1's expansion (Aurora throughput re-measure; golden parity vs real `/export`; cold-start scale). The spike branch is deleted; this memo is the durable record.
