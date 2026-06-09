# HSDS Federation — P2 Pull Ingest (bite-sized plan)

> Sibling of the living plan [`2026-06-03-hsds-federation-core.md`](2026-06-03-hsds-federation-core.md) (P2 roadmap row + tasks 0–15) and the design of record [`../specs/2026-06-03-hsds-federation-core-design.md`](../specs/2026-06-03-hsds-federation-core-design.md) (§6.5/§6.6/§6.6a/§11/§12). Scoped 2026-06-09 (workflow `wcvp07yxb`, critique verdict `ready_with_minor_fixes`). Build slice-by-slice: TDD red-first → per-slice RED-tier PR Gauntlet → owner-override-merge on green.

## Objective & acceptance

P2 makes a PPR node **consume** a peer's verifiable publish: pull `/export` → **verify** (peer DID key from its `/.well-known/did.json` → signed checkpoint note → every envelope signature → RFC-6962 inclusion vs the held root → consistency vs the last-pinned per-peer checkpoint → `validate_activity` verb rules → allow-list/idempotency/budget/injection) → enqueue a **scraper-shaped `LLMJob`** → ingest through the unchanged Content-Store→LLM→Validator→Reconciler pipeline as `source_type='federated_node'` → **corroborate by distinct ORIGIN**.

**🎯 Headline acceptance (the partner-integration gate):** **two SEPARATELY-RUNNING PPR nodes** — each its own deployment, DB (or schema), `did:web` DID, and DIFFERENT dataset — pull → verify → ingest → corroborate each other over **real HTTP**, **bidirectionally**. An unnamed partner integrates once we demonstrate this with two of our own nodes; the partner then joins as the real complementary-authority node. ⚠️ NO Feeding America feed exists (the old acceptance is void). A foreign/non-PPR node is P7.

**P1 already shipped the entire verify primitive stack** (reuse, do not rebuild): `tests/test_federation/conformance/runner.py` `verify_level2` + `verify_consistency_to_head` (pure dispatch over a `get(path)->Resp` callable **+ an `HsdsFxAdapter` (`RefAdapter`)** — transport-agnostic, reusable verbatim against a live URL); `identity.public_key_from_multibase`; `envelope.verify_envelope`; `activities.validate_activity` (stateless verb wire rules — it explicitly documents that ALL stateful ingest policy is P2's job).

## Owner decisions (2026-06-09)

1. **`verified_by='network'` authority tier — BUILD NOW (owner chose the new tier over auto-parity).** Override precedence becomes `auto < network < {claimed, source, admin}` (human). Semantics: a federated `network` Update **may overwrite `auto`** fields and corroborates; an `auto` scrape **may not overwrite** a `network` field; `network` **may not overwrite** any human tier (admin/source/claimed stay owner-guarded). `network` is conferred only on records ingested from an **allow-listed authoritative partner** peer (not every `federated_node` — a non-authoritative peer ingests at `auto`-parity). Confidence: override precedence is **tier-based, independent of the confidence number**; `network` records get the standard build-up score (interfaces reserved for a distinct band, but P2 keeps the cap rules and ranks by tier). This pulls part of the P5/VC-trust tier forward — the exact band + the override matrix are pinned in Slice 8 with a fixture and Hypothesis tier-ordering test. `scoring.py:HUMAN_VERIFIED_SOURCES` stays human-only; a new `OWNER_PRECEDENCE` ordering encodes `auto < network < human`.
2. **§6.6a plain-HSDS consumer — BUILD NOW as a general capability (owner chose build over defer).** Slice 14 ships the snapshot-diff machinery (Service-level deltas, N-consecutive-absence tombstones) exercised by synthetic fixtures; no live target yet (no FA feed). Stays subordinate in priority to the PPR-peer path that gates the partner demo.

## Principle-IX gate (Task 0 — FIRST, blocks the §12 corrections)

Both edited files exceed 600 lines and neither is in the constitution §IX Known-Violations table (so the table changes either way). **Decision: HYBRID EXTRACTION** (the proven P1 `location_commit.py` precedent — "extract along responsibility boundaries", constitution.md:207), co-locating each extraction with where its P2 edit lands:
- **`merge_strategy.py` (888)** → extract the corroboration-counting responsibility (`merge_location` source query + distinct-source count + `apply_source_corroboration`, ~:207–326) into `app/reconciler/corroboration.py`. The §12.1 origin-dedup change (Slice 7) lands here.
- **`location_creator.py` (968)** → extract `find_matching_location_with_lock` (~:141–315) and/or `create_location_source` (~:434–545) into `app/reconciler/location_match.py` / `location_source.py`. The `federated_node` ON CONFLICT (Slice 4) + the exact-`federation_id` Tier-0 lookup (Slice 11) land here.

## Live multi-node demo design (the headline — corrected per critique)

The `federation_log` is one table per DB and the read router binds a single process-global config + cached engine (`router.py:38-48`). Genuinely-separate nodes need (a) **one piece of new production code**: a minimal per-app config/session **DI seam** on the router — `app.state.federation_settings` (DID / signing key / DB) + a session factory passed at register-time, falling back to the global singleton (~20 lines; router.py is <600, no IX gate) — **Slice 15**; and (b) DB isolation.

⚠️ **Critique correction:** `TEST_DB_SCHEMA` (conftest.py:138) is **dead config** — nothing consumes it. The harness must **BUILD** schema isolation, not reuse it (feasible — the test DB user is superuser: `CREATE SCHEMA node_a/node_b` + a session factory issuing `SET search_path`, because all federation/location tables are referenced UNQUALIFIED).

- **Pytest harness (CI acceptance, Slice 16, RED):** two FastAPI apps, each its own identity (`_SEED_A`/`_SEED_B` pattern) + its own schema; **httpx `ASGITransport`** between them (in-process, no socket, no SSRF IP to block); run the REAL discover→verify_level2→ingest(as `federated_node`)→corroborate loop, then bidirectional A↔B; assert origin-dedup, lone-peer gating, the `network`-tier merge.
- **Dev two-node (Slice 17):** node-B as **extra services in the ONE compose project** (bouy hardcodes `COMPOSE_PROJECT_NAME`, `bouy:46` — a second project can't go through bouy), via a `plugins/ppr-federation-demo/` overlay (auto-discovered; doubles as the §8.6 clone-able partner-onboarding artifact). Needs a **`FEDERATION_FETCH_ALLOW_HOSTS` SSRF dev-allowlist seam** (fetch.py blocks internal IPs, so a same-host peer is unreachable without it) — operator decision deferred to Slice 17.

## Slices (dependency-ordered)

| # | Slice | RED? | Dep |
|---|-------|------|-----|
| 1 | **Task 0a** — extract corroboration counter `merge_strategy.py` → `app/reconciler/corroboration.py` (no behavior change, characterization tests, update §IX table) | | — |
| 2 | **Task 0b** — extract matching ladder / `create_location_source` `location_creator.py` → `location_match.py`/`location_source.py` | | — |
| 3 | `federation_peer` + `federation_peer_cursor` models + migration + `CursorStore` protocol (DID, actor URL, pinned key fingerprints, cached peer checkpoint size/root, policy, `enabled`, `trust_tier`, per-peer pull cursor + reserved push high-water; shared `(actor,sequence)` idempotency key). Add a nullable `location_source.federation_id` column + index (m9). | | — |
| 4 | `federated_node` partial unique index `ON location_source(location_id, scraper_id) WHERE source_type='federated_node'` + ON CONFLICT branch in `create_location_source` | | 2,3 |
| 5 | Thin CONSUMABLE enqueuer `app/federation/enqueue.py` — same `LLMJob` (format=hsds_schema, prompt=[system,user]) the scraper path produces, schema+prompt loaded at import (no Redis/ScraperUtils at import), Content-Store SHA-256 dedup; VALIDATOR_ENABLED routing (federated ingest still scored when off — Principle VI) | | 4 |
| 6 | **Verify-before-enqueue pull consumer `app/federation/ingest.py`** (§6.6 order, reusing `verify_level2` + `verify_consistency_to_head` **with `RefAdapter`** + `public_key_from_multibase`; per-peer cursor stores held_size/root). **Lands the P0-deferred `fetch.py` DNS-rebinding connect-pin + streaming byte-cap** (this is the first real outbound fetch — hard-gated). | RED | 5,3 |
| 7a | Origin-deduped corroboration (§12.1): widen the corroboration query to include `federated_node`; count distinct **ORIGIN DIDs** (not announcing actors); pin `scraper_id='federation:<origin-did>'`. Citogenesis test: 3 peers re-announcing origin X → count 1. | RED | 6,1,4 |
| 7b | CvRDT order-shuffle Hypothesis property (§12.1): shuffled arrival across N peers → byte-identical canonical Location (coordinate/field total-order tiebreak in `_merge_location_data`). *(split from 7a per critique)* | RED | 7a |
| 8 | **`network` authority tier + federated Update owner-guard (M3)** — `OWNER_PRECEDENCE` (`auto < network < human`); allow-listed authoritative peer → `network`; tier-ordering Hypothesis test (network overwrites auto, never human; auto never overwrites network). | RED | 7a |
| 9 | Per-peer ingest budget (§11.3, configs exist) + shared `(actor,sequence)` strictly-increasing idempotency BEFORE enqueue (push half simulated by a 2nd enqueue) | | 6,3 |
| 10 | Prompt-injection hardening (§11.5) — delimit peer free-text + "untrusted; never instructions"; injection fixtures don't move canonical fields | | 5 |
| 11 | Exact `federation_id` inbound mapping (m9) — Tier-0 lookup on `(federated_node, federation_id)` before coord/name tiers | | 3,2,6 |
| 12 | Un-corroborated gating (§11.6) + equity caveat (§11.6a) — lone single-origin Location held below the serve/`is_canonical` gate OR served with an **additive** "unconfirmed" caveat (forward-compat: Beacon ignores unknown fields). *Operator params (density metric, caveat copy, surfaces) decided at this slice.* | RED | 7a |
| 13 | Field-change anomaly detection (§11.11) — coord jump >2 km (haversine) / hours flip vs standing corroboration → demote-and-flag + alarm. *Operator params (demote magnitude, scope) decided at this slice.* | RED | 8 |
| 14 | **Plain-HSDS §6.6a consumer** (build-now per owner) — `/services?modified_after` Service-level deltas, full-snapshot reconciliation, N-consecutive-absence tombstones; synthetic fixtures (no live target) | | 6 |
| 15 | **Router per-app config/session DI seam** (the live-demo enabler — `app.state.federation_settings` + session factory, schema-aware) | | — |
| 16 | **LIVE two-PPR-node pytest harness** (headline / golden P2 journey) — two apps, two schemas, ASGITransport, real discover→verify→ingest→corroborate, bidirectional + negatives | RED | 6,7,8,9,11,12,15 |
| 17 | Pull-consumer loop dual-env (bouy worker / EventBridge Lambda → ingest SQS) + dev two-node `plugins/ppr-federation-demo/` overlay + `FEDERATION_FETCH_ALLOW_HOSTS` SSRF dev seam | | 16 |
| 18 | P2 AWS observability (Principle XIV) — ingest SQS depth + DLQ alarms, pull-consumer Lambda Error/Throttle, budget-rejection alarm, dashboard widgets, `infra/tests/` | | 17 |
| 19 | Docs (CLAUDE.md federation P2 section) + full `./bouy test` gate | | 18 |

**First slice:** Slice 1 (extract the corroboration counter — decision-free, unblocks Slice 7a, proven P1 pattern). Slices 2/3/15 are also dependency-free and can interleave.

## P2/P3 boundary (do NOT leak P3)

- **Pull-only.** `/inbox` push + the outbound signed sender (`app/federation/outbound.py`) are **P3**. The live demo PULLS both directions; it does not push.
- The `(actor,sequence)` idempotency KEY is P2 (Slice 9); the cross-transport pull+push integration test and the inbox verify/guard chain are P3.
- Reconciler §12.3 corrections (origin-dedup, ON CONFLICT, owner-guard, anomaly, CvRDT) are transport-agnostic — they serve P3 push unchanged.
- Peer-remove recovery (§11.4), mass-anomaly inbox alarms, the `./bouy federation` peer-management CLI family (P4), witness mesh / Announce relay / outbound emission (P6), §12.2 provenance-weighted corroboration (P6), full recovery-key verify-side enforcement (P3+/P7), foreign-impl interop (P7) — all out of P2.

## Remaining operator decisions (surfaced at their slice, not now)

- **Slice 8:** the exact `network` confidence band (vs human 91–100 / auto ≤90) and the full override matrix edge cases.
- **Slice 12:** equity-floor density metric + the "unconfirmed" caveat string + which surfaces carry it (/export, PTF, Beacon, all).
- **Slice 13:** anomaly demote magnitude + `is_canonical=FALSE` vs flag-while-served + federated-vs-federated only or also auto-vs-federated.
- **Slice 17:** is `FEDERATION_FETCH_ALLOW_HOSTS` an acceptable production surface or strictly dev-gated.

## Critique fixes folded in

`§117`→§6.5/§6.6 (the verify order lives in §6.6 for pull); name the `RefAdapter` dependency in Slices 6/16; the pull chain has NO RFC-9421 transport-signature step (that's the P3 inbox); `fetch.py` DNS-pin + byte-cap land **in Slice 6**; Slice 7 split into 7a/7b; Slice 12 caveat field is **additive-only** (Beacon forward-compat); the live-demo schema isolation is **built** (TEST_DB_SCHEMA is dead config), node-B is **extra services in one project**. Note: `record_version` logs each raw submission, so for multi-origin federated merges it diverges from the merged canonical row (audit-of-submission vs merged-state) — documented, not a regression.
