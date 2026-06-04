# HSDS Federation in PPR Core — Design of Record

**Status**: design of record (v3, post steelman/reinforcement pass). Approved direction (brainstorm 2026-06-03); not yet a ticket. Companion implementation plan: [`../plans/2026-06-03-hsds-federation-core.md`](../plans/2026-06-03-hsds-federation-core.md).
**Date**: 2026-06-03 (v3: 2026-06-04)
**Supersedes (home only)**: [`2026-05-22-network-of-lighthouses.md`](2026-05-22-network-of-lighthouses.md) — that doc picked the protocol primitives but scoped the build into the `ppr-lighthouse` plugin. This doc **re-homes the same protocol into PPR core (`app/`)**, scopes a concrete v1, makes the wire format normative, and aligns every decision to [`constitution.md`](../../../constitution.md). For wire-level details the 05-22 examples are **superseded**; §8 here is authoritative.
**Research behind it**: [`opr-report.md`](../research/2026-05-22-federation/opr-report.md), [`activitypub-report.md`](../research/2026-05-22-federation/activitypub-report.md), [`adjacent-protocols-report.md`](../research/2026-05-22-federation/adjacent-protocols-report.md).

## Review log

- **v1 → v2 (2026-06-03)**: four-lens adversarial review (constitution, completeness, partner-implementability, threat model); 11 blockers folded in. Biggest corrections: "no new logic" was false → explicit reconciler-integration spec (§12); reconciler has no single transaction → outbox + safe-high-water (§6.2); `is_active` doesn't exist → Delete derives from `is_canonical=FALSE` (§9); normative wire section (§8); SSRF / confidence-gaming / LLM-cost / prompt-injection / rogue-recovery / veracity-gap / PII-amplification became v1 requirements (§11); "plain HSDS just works" corrected (§6.6a).
- **v2 → v2.1 (2026-06-04, plan review)**: the `Delete` hook site moved to the offline dedup scripts (reconciler Tier-3 is *prevent-on-ingest*, no soft-delete); advisory lock scoped to the sequence append only; cold-start rebuilds from raw tables, not `location_master`; enqueuer loads aligner schema/prompt statically; signing `host` contract fixed.
- **v3 → v3.1 (2026-06-04, ecosystem-signals research)**: a live four-agent scan of the HSDS/Open Referral world confirmed **no competing federation protocol exists** — PPR is first-mover on the wire (zero hits for federation/sync/replication/delta/signed across the spec repo, org repos, forum, and FHIR worlds; the federation conversation, Bloom's forum thread 601, has been dormant since 2025-05). The community is converging on the *prerequisites* (provenance #558/#553/#508; external identifiers #485) — align, don't duplicate. Corrections folded in: the HSDS baseline is **v3.2.3** (the vendored submodule; 3.1.1 was stale — §8.1 fixed; Profile/fixtures pin the 3.2 line); the envelope vocabulary will be **crosswalked to the in-flight BODS-inspired publisher/steward/source model + org-id.guide identifiers** before HSDS-FX extraction (§7, §8.5); an **engagement sub-plan with named targets + a governance annex** added to §8.5; **complementary positioning** vs the United Way NDP hub (~90% of 211s, centralized) and the Resource Record-Matcher (Open Referral's offline batch dedup answer, which explicitly disclaims federation) added to §1.1; **Service Net** (the prior multi-party sync attempt, dead of dormancy 2022) cited as the precedent validating impl-first; watch items recorded in §21.
- **v2.1 → v3 (2026-06-04, steelman/reinforcement pass)**: seven expert lenses (protocol, architecture-challenger, security/trust, ecosystem/standards, data-quality, implementation, adoption) + synthesis, explicitly steelmanning rather than bug-hunting. **Owner decisions:** (1) the federation log becomes a **fully verifiable substrate** — content-addressed, origin-signed activity objects in a Merkle-committed append-only log with signed checkpoints, inclusion/consistency proofs, and a witness-cosigning mesh as a committed later phase (the owner chose the full substrate over the lenses' staged-minimal recommendation; rationale in §21); (2) signing profile flipped to **RFC 9421** (from expired Cavage-12); (3) **equity floor adopted in v1** — a plausibly-real single-source low-density Location is served *with a visible caveat* rather than gated invisible; (4) spec stewardship = **impl-first, donate to Open Referral in parallel** (§8.5). Also folded in: P0.5 de-risking spike; `FEDERATION_ENABLED` kill switch; Feeding America's live HSDS feed as zero-recruitment node #2; HSDS-FX spec extraction + conformance suite; corroboration **origin-dedup** (the citogenesis fix) + CvRDT formalization; version-fracture inoculation; recovery-key hierarchy; review-queue scaling + `Flag` pulled to P4; provenance-weighted freshness-decayed corroboration (later-phase, designed now); reference second-node fixture + golden journey tests.

---

## 1. Purpose and goals

Make every PPR deployment a **federating node** in an open network of HSDS food-resource endpoints: it ingests from peers it is told about, publishes its own canonical data, and tells peers when that data changes — and any consumer can **verify, not merely trust**, what any node (including ours) has published. Modeled on OPR and the fediverse for shape, on Certificate Transparency for accountability, exchanging data as HSDS.

Three drivers (owner's words) and their architectural consequences:

1. **Richer, fresher data.** Peers are an upstream acquisition channel; an ingested peer record is *another source* feeding the existing reconciler. Requires real reconciler plumbing — corroboration does not count `federated_node` sources today (§12) — and corroboration must be **origin-deduplicated** so re-ingested echoes never masquerade as independent confirmation (§12.1).
2. **Resilience / decentralization.** The dataset survives any single node dying, including ours. No central registry; allow-list-per-node trust; identity that survives host changes; and — v3 — **cryptographic non-equivocation**: a node cannot silently rewrite or back-date its published history without breaking proofs a consumer already holds.
3. **"Build more doors, not more lock."** Federation lives in **OSS core, on by default, gated by nothing**; the protocol is small enough that a partner can implement a useful tier in days (§20); and "no node is special, including ours" is enforced **by math, not by promise** (§6.2). The wire spec is extracted as a neutrally-named, separately-governed candidate community standard (§8.5).

**Equity charter (Principle VI corollary):** federation must not worsen coverage for hard-to-reach communities (rural, informal, undocumented-serving pantries) — and this is *measured*, not assumed. The serve-gate carries an explicit equity floor (§11.6a); the PII heuristic flags rather than auto-suppresses informal pantries (§11.8).

Peer model: **hybrid** — a mesh of PPR/PPR-compatible nodes speaking the full protocol, plus consuming plain third-party HSDS endpoints as read-only upstreams (§6.6a — which is also the **adoption spearhead**, not a fallback: Feeding America's live HSDS feed is node #2 on day one, §1.1).

### 1.1 Incentive ledger and flywheel (why anyone joins)

| Partner archetype | They GET on day one | They GIVE | Tier (§20) | Proof use-case |
|---|---|---|---|---|
| **Feeding America** (live HSDS 3.0 feed, ~200 banks / 60k pantries) | corroboration + freshness signal on their own data; attribution-preserving national reach | a feed they already publish (zero build) | Tier 0 (consumed-only) | the v1 acceptance test: PPR ingests + corroborates the live FA feed |
| **A 211 / United Way node** | fresher, corroborated, deduped records for their coverage area; deltas instead of nightly dumps — **feeding and reading the National 211 Data Platform hub, never bypassing it** | their existing HSDS publication | Tier 0→1 | regional freshness uplift |
| **Vivery / FreshTrak** | their listings corroborated + enriched, surfaced with provenance to PPR-network consumers | an `/export` shim over data they already serve | Tier 1 | "your data, verified by N independent orgs" |
| **A county GIS / static dump** | their dataset alive in a national network without running software | a file | Tier 0 | rural coverage |
| **A single food bank (own node)** | authoritative control of their own record (`Update` authority), instant network-wide corrections | running a Tier-3 node (or using Lighthouse) | Tier 3 | origin authority demo |
| **Plentiful** | the same Beacon/PTF data via an open standard instead of a bilateral contract | webhook consumption | Tier 2→3 | the existing sync, generalized |

**Flywheel:** each new node adds corroboration votes → confidence and freshness of *everyone's* served data rises → the "independently confirmed by N orgs" signal (§11.9) becomes more valuable → more reasons to join. Consumption is free and verifiable from day one (Tier 0 costs nothing), so the funnel starts at zero friction.

## 2. Non-goals

No central registry/directory; no JSON-LD context expansion (`@context` is a version tag, validated by Pydantic, never a JSON-LD processor); no client-to-server protocol; no transactional offer lifecycle (`accept`/`reserve`/`reject`); no single-author-per-record rule; no O(followers) fan-out optimization. **Explicit declines (steelman-reviewed):** Solid/LDN (JSON-LD-native, pod-per-owner mismatch); an OPR Transfer-API bridge (project frozen since 2022; offer-lifecycle is the wrong shape — *reserved* as a possible read-only bridge, not adopted); CRDT/vector-clock machinery beyond §12.1's CvRDT formalization of the existing model; real-Mastodon rendering interop (HSDS-typed objects don't render as social posts — bridging is a possible later `Announce`-bot, out of scope). **Reserved (named, not built):** a lightweight `/federation/stream` JSON delta lane without proofs (Jetstream pattern) alongside the verifiable `/export`. **v1 defers** (each with a designed-now interface): the witness-cosigning mesh (§6.2c), `Verify`+VCs (§17 P5), Region/Group actors + relay (§17 P6), `Move`, RBSR anti-entropy (§17 P7), public-log anchoring (§17 P7), full HSDS version negotiation (§8.4 inoculates now), full GDPR per-field redaction (but not the §11.8 v1 PII minimums).

## 3. Core insight: directory federation is not social federation

PPR is **reference-data exchange** (FHIR Bulk + VhDir, IATI, OSM diffs) — slowly-changing facts about real entities, multiple authorities asserting their own ids/values for the same logical thing — not transactional offer exchange (OPR) or social messaging (ActivityPub). **We are FHIR-for-public-charitable-food, with Certificate-Transparency-grade accountability.** Three settled structural decisions: identity unit = the node/Organization; content unit = the HSDS **Location aggregate** (§9), optimized for incremental sync; multiple actors asserting facts about one Location simultaneously is correct — carrying both *authoritative* `Update`s and *corroborating* `Announce`s, merged by a deterministic, order-independent function (§12.1).

## 4. Why core (`app/`), not a plugin

"On by default, gated by nothing" is the maximal form of driver 3; a plugin is a door that can be shut. The new core-pipeline seam (the verifiable-log append at the canonical-commit points) must live in `app/` regardless. Interop requires a documented standard a non-PPR partner implements against (§8.5) — a plugin-private contract is not a standard. Versus the 05-22 framing: wire endpoints on the **core API**; onboarding via **`./bouy federation`** + a `federation_peer` table; neutral naming (a *peer*; `/.well-known/hsds-federation`).

## 5. Architecture overview

A PPR node has identity `did:web:<domain>` (raw org-URL accepted as fallback) with a **recovery-key hierarchy** (§6.1a). It publishes discovery documents and an HSDS-typed activity stream of `Update`/`Announce`/`Delete` activities over the Location aggregate. **v3 substrate:** every published activity is a **content-addressed, origin-signed object** (JCS-canonical bytes → SHA-256 id → Ed25519 object signature) appended to a **Merkle-committed, append-only `federation_log`** whose **signed checkpoint** (origin DID, tree size, root hash, timestamp; C2SP signed-note format) is published in `state.txt` and `/federation/checkpoint`. Consumers verify three things, not one: the **object signature** (who asserted it — survives any relay hop), the **inclusion proof** (it is genuinely in the log the publisher signed), and the **consistency proof** (the new head is an append-only extension of the head they saw last — a rewritten or forked history is detected, not suspected). A **witness-cosigning mesh** (allow-listed peers + HAARRRvest cosign each other's checkpoints) is a committed later phase whose format is fixed now.

The **canonical Postgres DB remains the operational source of truth for serving** — the *app-view*, in AT-Protocol terms: reconciler, dedup, confidence, the read API all unchanged in role. The verifiable log is the source of truth **for federation**: what was published, by whom, in what order, provably. The served Location is a deterministic projection (a CvRDT merge, §12.1) of the verified assertion set.

Exchange happens two ways: a **bulk pull path** (`GET /federation/export?_since=<seq>` → keyset-paginated NDJSON of signed objects + inclusion proofs; cold-start from a **verifiable snapshot** artifact) and a **push path** (RFC-9421-signed webhook `POST /federation/inbox`). Trust is an explicit per-node **allow-list of peer DIDs**; verification is cryptographic. Discovery is mention-driven. Every component has a Docker and an AWS realization (§13; Principle XV), and the whole publish surface sits behind a tested **`FEDERATION_ENABLED` kill switch** (§6.2d).

```
            ┌────────────────────────── PPR node (app/ core) ───────────────────────────┐
 peers ───► │ Discovery: did.json (+recovery keys), .well-known/hsds-federation, webfinger │
  pull      │                                                                              │
 /export ◄──│  VERIFIABLE LOG (append-only, never destroyed)                               │
 +proofs    │   signed objects ── Merkle tree ── signed checkpoint (state.txt /checkpoint)  │
 /checkpoint│        ▲ append at canonical-commit hooks (kill-switch guarded):              │
            │        │  job_processor matched/new-Location · dedup scripts (Delete+redirect)│
            │        │  · submarine enrichment · — dense sequence under short append lock   │
            │  ┌─────┴──────────── canonical Postgres = APP-VIEW (serving) ──────────────┐  │
            │  │ reconciler · 3-tier dedup · confidence (origin-deduped corroboration,    │  │
            │  │ CvRDT merge) · read API · Beacon/PTF · HAARRRvest                        │  │
            │  └───────────────▲──────────────────────────────────────────────────────────┘  │
            │                  │ Content Store → LLM (delimited) → Validator → Reconciler     │
            │  Ingest: verify object sig + inclusion + checkpoint consistency → allow-list    │
            │  → budget → thin enqueuer ──┘   (pull consumer + /inbox share one idempotency)  │
            └──────────────────────────────────────────────────────────────────────────────┘
```

## 6. Components

All new code under `app/federation/` (Principle IX). Modules: `identity.py` (DID/`did.json`/actor/WebFinger, recovery-key hierarchy), `discovery.py`, `canonical.py` (**JCS / RFC 8785 canonicalization** — the normative byte form for hashing and signing, with fixture vectors), `signing.py` (RFC 9421 HTTP Message Signatures + Ed25519 **object** signatures), `fetch.py` (the single hardened egress helper, §11.1), `activities.py` (envelope + verb models; validates `object` against unmodified HSDS models), `log.py` (**the verifiable log engine**: append, dense sequencing, Merkle tree state, checkpoint signing, inclusion/consistency proofs, archive tiering, export/state/history queries), `peers.py` (allow-list + pinned keys + per-peer cursor/budget + cached peer checkpoints), `enqueue.py` (thin consumable LLMJob enqueuer, §6.5a), `ingest.py` (pull consumer + inbox router, verification-before-enqueue), `outbound.py` (push sender). API routes in `app/api/v1/federation/` + root-level `.well-known/*` (§13).

### 6.1 Identity & discovery
`did:web:<domain>` → `https://<domain>/.well-known/did.json`; `/.well-known/hsds-federation` advertises DID, key material, supported HSDS version**s** (plural — §8.4), Profile URI, endpoint URLs, allow-list policy, retention/archive policy, checkpoint location, contact. WebFinger resolves `acct:` handles. Implementations MUST accept `did:web:…` and `https://…` as one identity. All discovery fetches use §11.1's hardened helper.

### 6.1a Recovery-key hierarchy (v3; did:plc-inspired)
`did.json`'s `verificationMethod` is an **ordered list with explicit priority**: the day-to-day Ed25519 signing key (online) plus one or more higher-priority **recovery keys** (held offline). Verify-side rule: a key-change is honored only if signed by a key of ≥ priority of the key being replaced; a recovery key can repudiate a lower-priority key's assertions within a bounded window. `peer-add` displays and pins the **recovery-key fingerprint**, not just the signing key — so a domain takeover (did:web's structural weakness: DNS is trust-on-first-use) becomes a detectable, recoverable event instead of silent identity forgery. Compromise-revocation is tied to the checkpoint sequence (§6.2b) so a rotated-in key cannot retroactively re-sign old history. Schema + verify-side priority check ship in v1 (forward-compatible); the full recovery ceremony is later-phase.

### 6.2 The verifiable log (v3 — the substrate)

**(a) Signed, content-addressed objects.** Every published activity envelope is serialized to **JCS (RFC 8785) canonical bytes**; `id = sha256(canonical bytes)` (content address); the origin signs those bytes with its Ed25519 key → a `proof` field on the envelope (object-integrity signature — survives relays, mirrors, and snapshots; a consumer can verify origin from an S3 archive with no network). The object hash is the Merkle **leaf**.

**(b) Append-only Merkle log + signed checkpoints.** `federation_log` stores `(sequence, id/leaf_hash, type, federation_id, object_canonical JSONB/bytes, published_at, origin_did)`. **Sequence is dense and gapless**: assigned under a **short advisory lock scoped to ONLY the sequence allocation + INSERT** (never the reconciler's resource commit — the parallel canonical write path is preserved; this v2.1 insight stands). Dense sequence = Merkle leaf index, so the tree needs no gap handling. An RFC-6962-style tree over the committed prefix (tlog-tiles/Tessera storage pattern as the reference layout) yields a **checkpoint** `(origin_did, tree_size = head sequence, root_hash, timestamp)`, Ed25519-signed in **C2SP signed-note format**, published in `state.txt` and `GET /federation/checkpoint`, re-issued on append (coalesced) and at a heartbeat interval. `/export` rows carry **inclusion proofs** (leaf hash + audit path to a signed checkpoint); consumers cache the last checkpoint per peer and verify a **consistency proof** on every pull (the new tree is an append-only extension of the head they already saw). A rewritten, forked, or truncated history breaks the proof and is **provable**, not alleged — this is what makes the §11.4 rogue-peer recovery story sound, and it is "no node is special, including ours" enforced by math.

**(c) Witness cosigning — committed later phase, format fixed now.** Allow-listed peers act as mutual **witnesses** (C2SP tlog-witness/tlog-cosignature): each cosigns the largest consistent checkpoint it has observed for a peer, making split-view/equivocation (showing different histories to different consumers) detectable **mesh-wide**, not just bilaterally. **HAARRRvest is recast from privileged relay to the network's first, lowest-trust witness.** The v1 checkpoint format is witness-compatible from day one so the mesh is an extension, not a flag-day rewrite.

**(d) Kill switch (Principle XI).** `FEDERATION_ENABLED=False` makes the append helper a **hard no-op checked at every hook site before any work**; the pull consumer and inbox short-circuit identically. Ingest is **independently killable** (a second flag + the per-peer `enabled` column) so the attacker-facing inbound surface can be cut without killing the publish path. Test: with the flag off, a canonical commit appends zero rows and the reconciler path is **byte-identical to today**. A redeploy-free operator runbook ships with P1.

**(e) Hook sites (v2.1 corrections preserved).** The matched-Location and new-Location commit branches in `app/reconciler/job_processor.py`; the **offline dedup backfill scripts** (`scripts/dedupe_near_duplicate_locations.py` / `dedupe_same_org_locations.py`) at the `is_canonical=FALSE` UPDATE + `dedup_run_audit` insert (emit `Delete` + `redirectTo` — the reconciler's Tier-3 path is *prevent-on-ingest* and is NOT a Delete source; the scripts run outside the reconciler worker, so the append helper takes a plain DB session and the **signing key must be available in script context** too); and `app/reconciler/submarine_location_handler.py:update_location` (enrichment → `Update`). **Publish-side echo suppression:** a commit driven solely by `federated_node` sources appends nothing. The append helper lives in `app/federation/log.py` (Principle IX: extraction, not accretion).

**(f) Sequencing escalation path.** If the P0.5 spike shows append-lock contention, escalate to a named alternative: a **single-writer relay** assigning dense sequence off the hot path, or **CDC/logical-replication** (Debezium/LSN pattern) feeding that relay. The M5 test asserts ordering AND that the reconciler's per-resource commit is never globally serialized.

**(g) Retention = ARCHIVE, never destruction (v3 coherence).** An append-only verifiable log cannot prune leaves without breaking proofs. So: the **live Postgres window** is bounded by the SLA; older objects + tile hashes are **archived to S3** (cheap; still origin-verifiable from the archive with no network trust); the tree state is retained so checkpoints and consistency proofs remain valid **forever**. `_since` below the live window → redirect to the verifiable snapshot/archive (or `410` with the archive pointer). `state.txt` advertises the live-window floor and archive location. This **replaces** v2.1's prune-and-410 semantics and strengthens "no row is ever destroyed" into a network property.

### 6.3 Publish / read path
- `GET /federation/export?_since=<seq>` → keyset-paginated NDJSON of **signed objects + inclusion proofs**; headers `X-Federation-Next-Cursor`, `X-Federation-Sequence` (= signed checkpoint tree_size), `X-Federation-Retention`. Reuses Beacon's `is_canonical` + confidence serve gate, as modified by §11.6/§11.6a.
- `GET /federation/checkpoint` and `state.txt` → the current **C2SP signed checkpoint** (+ live-window floor, archive pointer).
- **Cold-start `_since=0`:** a **verifiable snapshot** artifact (objects + proofs + the checkpoint they verify against), built by **rebuilding the §8.2 Location aggregate from the raw normalized tables** in the HAARRRvest export — **not** the lossy `location_master` view — served from S3/CDN, never a live Lambda full scan. A round-trip **parity test** asserts snapshot aggregate ≡ live `/export` aggregate.
- `GET /federation/history/{federation_id}` → per-aggregate activity history, now **proof-backed** (each activity carries its inclusion proof) — the moderation/audit surface. Rate-limited/edge-throttled like Beacon (§11.9).
- *Path convention:* `/federation/*` paths here are shorthand for **advertised absolute URLs** (OPR-style — the discovery doc is authoritative); in PPR they mount at `/api/v1/federation/*`, while the `.well-known/*` docs are necessarily root-level. Partners never hard-code the prefix.

### 6.5 Inbound push (`POST /federation/inbox`)
Verification order: **RFC 9421 transport signature** against the **pinned** `federation_peer` key (zero attacker-directed I/O, §11.1) → **object signature** (origin authenticity — independent of the delivering hop) → `actor` ∈ allow-list → `actor == attributedTo` for `Update`/`Delete` → `(actor, sequence)` strictly-increasing dedup → **checkpoint consistency** (a stale/forked advertised checkpoint → reject + `federation_consistency_failed` alarm: possible equivocation) → per-peer budget (§11.3) → thin enqueuer → `202`. Per-DID rate-limited.

### 6.5a The federation-ingest enqueuer (v2.1 preserved)
Both inbox and pull consumer funnel through thin `app/federation/enqueue.py`, which constructs the same **`LLMJob` envelope** scrapers produce — loading the HSDS schema CSV and aligner prompt **once at module import** (static files, not Redis) so the job is genuinely consumable — and writes to the queue backend (`QUEUE_BACKEND`: Redis local / SQS AWS) **without instantiating `ScraperUtils`**. Content-store SHA-256 dedup (Principle VIII) applies here. Already-structured plain-HSDS records take the cheaper alignment path (§6.6a/§11.5). Dual-env: locally a route in the app container; on AWS the inbox is its **own non-slim Lambda** → ingest SQS (mirrors `ppr-write-api`). The slim read Lambda gains only read-only routes + root-level `.well-known/*` and imports no Redis/LLM.

### 6.6 Pull ingest consumer
Polls each configured peer: **PPR/compatible peers** via `/export?_since=<cursor>` with **proof verification before enqueue** (object signature, inclusion, consistency against the cached checkpoint); **plain HSDS endpoints** via §6.6a. Pull and push share **one** `(actor, sequence)` idempotency key in one `federation_peer_cursor` row, checked before enqueue regardless of transport.

### 6.6a Plain-HSDS upstreams — the honest mechanism, and the adoption SPEARHEAD
The facts stand (v2.1): HSDS's API has **no `/locations` list endpoint**, **no `last_modified` on Location**, and offset pagination — so a plain publisher yields Service-level deltas at best, and the real mechanism is **periodic full-snapshot reconciliation** (diff against last-seen ids; synthesize tombstones only after N consecutive absences — Principle VI safety; bounded duplicate reads are idempotent via SHA-256; full re-pull when `total_items` shifts mid-walk). **v3 re-narration:** this path is not an apology — it is the **go-to-market spearhead**. The most valuable node #2 already exists and is consumable today with zero recruitment: **Feeding America's live HSDS 3.0 feed (~200 banks / 60k pantries, nightly)**. P2's acceptance test is concretely: *PPR ingests the live FA feed end-to-end via this path and corroborates it against existing scraper sources.* The network has a living, valuable first edge the day P2 ships.

### 6.7 Trust / allow-list & onboarding
`federation_peer` (DID, actor URL, **pinned signing-key + recovery-key fingerprints**, cached peer checkpoint, policy, enabled, trust-tier field reserved for §11.9 weighting, retention-seen, notes). `./bouy federation peer-add <did>`: hardened fetch of discovery → display signing **and recovery** fingerprints + retention/archive policy + **a sample of recent records** (the review bar, §11.7) → approve. `peer-remove` triggers §11.4 recovery. `peer-list`, `status` round it out.

## 7. Data model

Tables: **`federation_log`** (§6.2 — verifiable, append-only, archive-tiered); **`federation_peer`** (§6.7); **`federation_peer_cursor`** (one row per peer: shared inbound `(actor, last_sequence)` idempotency high-water, outbound push high-water, budget counters, cached peer checkpoint; Postgres local / DynamoDB AWS behind an explicit **`CursorStore` dual-backend protocol** mirroring `ContentStoreBackend` — *not* `ptf_broker_sync_state`'s shape, which is `PRIMARY KEY(location_id)` and only a pattern reference). New values: `location_source.source_type` += `federated_node`; `caller_context.source_type` += `federated_update`/`federated_announce`; `verified_by='network'` reserved (P5).

**Envelope identity (v3):** the envelope gains `id` (the JCS-canonical SHA-256 content address) and `proof` (the origin's Ed25519 object signature over the same bytes). `federation_id`/`attributedTo`/`origin` stay in the **envelope**, never inside the HSDS `object`, which validates against **unmodified** HSDS Pydantic models. Grammar (unchanged from v2.1): `federation_id = <publisher-host> ":" <internal-id>`; `attributedTo` carries the full DID; equality = byte-exact after host lowercasing/trailing-dot strip; `unreserved` charset with percent-encoding for `:`.

**Inbound mapping:** exact lookup on `(source_type='federated_node', federation_id)` (new index) **before** coordinate/name tiers, so a peer's stable id pins to one local Location across coordinate drift.

**HSDS Profile:** multi-file per `docs/HSDS/docs/hsds/profiles.md` — per-schema RFC-7386 merge patches (`location.json`, `service.json` for `confidence_score`/`verified_by`/`sources[]`/the §11.9 confirmation signal), an `openapi.json` patch adding `/federation/*`, a pre-compiled `/schema` dir; P0 replaces the router's generic profile URI; one canonical host for `@context` + Profile (hosted on the neutral spec domain, §8.5). **Baseline (v3.1):** the vendored spec is **HSDS v3.2.3** (the router currently advertises 3.1.1 — P0 verifies what the code actually implements and sets the advertised version accordingly); the Profile, fixtures, and `@context` pin the **3.2 line**, which also shipped the `GET /` `publisher`/`data_guide` block and the `modified_after`/`format=ndjson` read primitives our catch-up paths reuse. **Vocabulary crosswalk:** before HSDS-FX extraction, the envelope's `actor`/`attributedTo`/`origin` are crosswalked to Open Referral's in-flight BODS-inspired **publisher / steward / source** role model (issues #558/#553/#508) and `org-id.guide` identifiers are carried alongside `did:web` — so the donated spec speaks the community's field names from day one.

## 8. Wire protocol (NORMATIVE; 05-22 examples superseded)

### 8.1 Envelope (push body AND each NDJSON export row)
Envelope key is **`type`**. The export row is the full envelope **plus its inclusion proof**.

```json
{ "@context": "https://hsds.openreferral.org/3.2",
  "id": "sha256:9f2c…",                      // content address over JCS bytes (v3)
  "type": "Update",
  "actor": "did:web:northjerseyfoodbank.org",
  "attributedTo": "did:web:northjerseyfoodbank.org",
  "origin": "did:web:northjerseyfoodbank.org",   // carried through Announce — §12.1 origin-dedup
  "federation_id": "northjerseyfoodbank.org:abc-123",
  "object": { /* unmodified HSDS Location aggregate */ },
  "published": "2026-06-04T18:33:11Z",
  "sequence": 4730,
  "proof": { "type": "ed25519-jcs-2026", "verificationMethod": "did:web:…#main-key", "signature": "…" } }
```

Required per verb as in v2.1; additionally `id`+`proof` are REQUIRED on every published envelope, and **`Announce` MUST carry the original `origin`** (the asserting authority it is corroborating), not just its own `actor`. `Delete` object = `{ "type": "Tombstone", "federation_id": "…", "redirectTo": "<survivor|null>" }`. A normative JSON Schema + `fixtures/` corpus (including JCS canonicalization vectors and a worked proof) ship with P1.

### 8.2 The Location aggregate
One composed HSDS document per Location (Location + embedded schedules/phones/addresses/languages/accessibility/services-at-location) — what Beacon/PTF already shape.

### 8.3 Signing (RESOLVED v3: RFC 9421)
**Transport:** **RFC 9421 HTTP Message Signatures** with **RFC 9530 `Content-Digest`**, Ed25519 (`alg` agility explicit), covering `@method @target-uri content-digest created`; `created`/`expires` parameters give the replay window (**±300 s**). The expired Cavage-draft-12 profile is dropped (no fediverse-interop debt exists to honor; an ad-hoc Date-format deviation dies with it). **Object:** the `proof` signature over JCS bytes (§6.2a) is the origin-authenticity layer and survives relays/mirrors/archives. **Canonicalization:** **JCS / RFC 8785** is normative for every byte that is hashed or signed, pinned with fixture vectors — the fediverse's signature-interop graveyard is canonicalization ambiguity; we pin it on day one. `keyId`/`verificationMethod` host MUST equal the `actor` DID host; the inbox verifies against the **pinned** key (no fetch on the hot path).

### 8.4 Version handling (fracture inoculation — doc-only-now, binding)
`@context` is matched as **set-membership against the discovery doc's advertised supported-versions list**, not exact-string equality. Receivers **MUST ignore unknown fields, never reject on them**; a reserved `ext` namespace carries experimental fields. The only hard failure is a major-version mismatch (→ `422` + `federation_inbox_rejected_version`). Full content negotiation stays deferred (P7), but these two rules are what let a v1 node and a v5 node still talk in 2036 — permissive-on-read, conservative-on-write, from day one.

### 8.5 Spec extraction & stewardship (RESOLVED v3: impl-first, donate in parallel)
§8 (envelope, aggregate, signing profile, `federation_id` grammar, endpoints, checkpoint format, JSON Schema, fixtures) is extracted into a **separately-versioned, neutrally-named spec artifact — working name "HSDS-FX" (HSDS Federation Exchange)** — implementable with zero reference to `app/`. Governance: its own SemVer; a public issue tracker; HSDS-style backwards-compat rule; **no normative change without a fixture + conformance test**; hosted on one neutral, non-PPR-branded domain (also serving `@context` + Profile + `/schema`); **stated intent to donate stewardship to Open Referral** as the missing incremental, signed, multi-source *exchange* profile above the read-only HSDS API. The fixtures double as: PPR's CI conformance gate, a **public hosted "Federation Readiness Checker"** (paste your `/export` URL → tier report), and a **copy-paste static-feed generator** so Tier 1 is genuinely an afternoon. Sequencing: build the running reference first; bring the fait-accompli-with-proof to Open Referral's TC in parallel.

**Engagement sub-plan (v3.1 — named targets, phase-timed).** *Wedge (now, pre-P1):* contribute to spec issue **#558** (source-of-records; maintainer mrshll1001 is reaching for OpenLineage) and **#553/#508** (publisher/steward/source metadata) — donate HSDS-FX's per-aggregate attribution + identity model aligned to their vocabulary; propose the two low-controversy PRs the community demonstrably needs: **extend `last_modified` beyond `service`** (it exists nowhere else — PR #375's orphan) and **tombstone/Delete semantics** (no deletion-propagation exists in HSDS at all). *Reveal (at P2):* revive Greg Bloom's federation thread (forum 601, dormant since 2025-05) with the running reference + the live-FA-feed corroboration test as proof; Bloom is now at Inform USA/AIRS — the 211-institutional tie — so the pitch is **complementary to the United Way NDP hub** (a verifiable feed into and between hubs and independents, never a bypass) and **complementary to the Resource Record-Matcher** (we are the live attributed exchange layer that feeds clean aggregates into their offline dedup; consider co-presenting with the Record-Matcher coalition — Connect211/ServiceNet/Do Good Data). *Format:* the TC runs rough-consensus + 2-week RFC with Open Data Services as Technical Steward; also engage Mike Thacker (ORUK steward, and the one person who has said "federated sources" in the repo, #485). *Lead the pitch with Tier 0/1* (plain NDJSON `/export` + `state.txt`, no crypto required to participate — §20) and present signed checkpoints/proofs as the optional verifiability tier tied to the provenance work the TC already accepts: the community has zero crypto precedent and the substrate must read as additive integrity, not a prerequisite. *Bring a governance annex, not just a wire spec* — network membership, key/recovery management (§6.1a), deletion authority (§9 Delete), dispute/refutation (§11.12), rogue-peer recovery (§11.4): the community's own open questions ("who controls a federated entity?") make governance the real battleground. *Cite Service Net* — the only prior multi-party sync attempt, dead of dormancy Dec 2022 despite sound tech — as why a running, adopted reference precedes committee stewardship.

## 9. Activity semantics (v1)

Unit = the **Location aggregate**; `federation_id`/`attributedTo` per-Location; standalone `Organization`/`Service` federation deferred. Schedules are embedded read-only aggregate data — only the origin writes hours; peer `Announce`s never touch schedule rows.

| Verb | Authorization | Receiver effect |
|---|---|---|
| `Update` | only `attributedTo` | **Not a blind replace.** Routes through Validator + `merge_location` + the **`HUMAN_VERIFIED_SOURCES` guard**; can never overwrite `verified_by ∈ {admin,source,claimed}`. Federated origin authority is subordinate to local human curation; a brand-new peer cannot overwrite an established multi-source value without corroboration. |
| `Announce` | any allow-listed peer; **MUST carry the original `origin`** | Corroboration → a `location_source` row; counts per **distinct ORIGIN** (§12.1 — N peers re-announcing origin X = 1 vote). Never overwrites fields. |
| `Delete` | only `attributedTo` | Tombstone (`is_canonical=FALSE` semantics) + `redirectTo` survivor — produced on PPR's side by the **offline dedup scripts** (§6.2e), never the reconciler. Receiver re-points to the survivor. |

**v1 authority simplification (owner-reviewed):** PPR is the asserting authority for its own canonical rows; everything PPR publishes is an `Update` attributed to PPR's DID. PPR records peers' Announces but does not emit its own `Announce` until peer-origin data exists to corroborate (echo-safe; emission lands with P6 relay work). When a true origin node joins, attribution shifts to it.

## 10. Identity, echo/loop prevention, idempotency
(1) One shared `(actor, sequence)` dedup key across pull + push, checked before enqueue. (2) Per-actor sequence strictly increasing; non-increasing ignored; ledger retention ≥ the replay window. (3) No-echo: never publish/re-`Announce` peer-origin data back toward any peer (publish-side suppression in the §6.2 hook). (4) Corroboration idempotent per `(origin, federation_id)` — one origin, one vote, regardless of how many peers relay it or via how many transports it arrives (§12.1).

## 11. Trust & security model (normative for v1)

Allow-listing establishes **authenticity, not veracity**; the validator is a garbage filter, not a truth oracle. The checkpoint layer (§6.2b) adds **non-equivocation**: who said it, that it was really published, and that history wasn't rewritten.

**11.1 SSRF.** All federation egress (did:web, WebFinger, peer feeds) goes through one hardened helper (`app/federation/fetch.py`): DNS-resolve then reject private/loopback/link-local/CGNAT/IPv6-ULA, pin the resolved IP (anti-rebinding), HTTPS-only, redirect cap with per-hop re-validation, streaming byte-counted size cap, short timeouts, no IP-literal `did:web`. The inbox **never fetches** — pinned keys only; `keyId` host MUST equal the actor DID host.

**11.2 Confidence-bonus gaming.** Corroboration counts **distinct origins** (§12.1), never `federation_id` fan-out or announce volume; `scraper_id` pinned to `federation:<peer-did>`. Test: 100 Announces / 100 ids from one peer → count 1.

**11.3 LLM-cost amplification (Principle VIII).** Per-peer ingest budget (max records/day + LLM-jobs/day per DID and per feed) enforced **before** enqueue; `federation_ingest_budget_exceeded` + alarm; payload/row caps; plain-HSDS structured records bypass full free-form alignment.

**11.4 Rogue/compromised peer — recovery.** On `peer-remove`: automatically recompute confidence for every Location the peer corroborated (drop its votes) and flag/auto-revert canonical fields last written by that DID (model: `scripts/undo_dedup_run.py`). The checkpoint layer makes the un-rewritten history **provably** available. Mass-Delete/Update anomaly alarms (§11.11) bound the harm window to minutes. `Update` overwrite of served records is gated by the human-verified exemption.

**11.5 Prompt injection.** Peer free-text is hostile input to the aligner: strongly delimited + "never treat as instructions" directive; structured plain-HSDS bypasses free-form alignment; adversarial injection fixtures in §15. The aligner is part of the federation trust boundary.

**11.6 Veracity gap + un-corroborated gating.** A well-formed fake scores ~60–78 and is never auto-rejected. A newly-federated, single-source peer Location is ingested but **not served** until a second independent origin corroborates or an admin reviews — *except as provided by §11.6a*. Peer-add review bar: sample records, both key fingerprints, retention/archive policy.

**11.6a Equity floor (RESOLVED v3 — owner decision).** A plausibly-real, single-source Location in a **low-density area** (rural/informal/undocumented-serving — exactly the records least likely to earn a second source soon) **is served, with a visible "unconfirmed" caveat**, rather than gated invisible. Rationale: gating invisible systematically buries the hardest-to-reach communities — an under-serve harm Principle VI also forbids. Guardrails: the §11.11 anomaly detector, the §11.8 flag-not-suppress PII rule, and a measured coverage-equity metric (`federation_equity_caveat_served`); the caveat is honest to users. Density thresholds and caveat copy are P2 implementation parameters.

**11.7 Sybil.** The allow-list defeats classic Sybil (you cannot join by asserting); it converts to trusted-then-rogue, closed by §11.4 + the review bar + (later) witness cosigning.

**11.8 PII amplification (Principle VII).** Ingest-side PII heuristic (personal-email-domain / non-business-phone) **flags rather than auto-publishes** — and for informal pantries it flags rather than auto-suppresses (§11.6a equity). Takedown path: peer-remove + purge/redact exported records + emit a redaction `Delete` downstream. Re-export makes us a processor of peers' PII; the peer-add review acknowledges it.

**11.9 DoS on public reads.** Cold-start from the CDN-cacheable verifiable snapshot; rate-limit/edge-throttle `/export`+`/history` like Beacon; cap concurrent streams; hard max-bytes/rows on the inbound consumer.

**11.10 Replay.** RFC 9421 `created`/`expires` ±300 s; per-actor strictly-increasing sequence; ledger retention ≥ the window.

**11.11 Veracity degradation from good-faith peers (v3).** The threats that need no attacker: **stale corroboration** (a 14-month-old echo counted like a fresh confirmation — answered later-phase by freshness decay, §12.2), **re-ingestion transitivity** (answered in v1 by origin-dedup, §12.1), **single-wrong-field** (a peer with great hours and a wrong phone — answered by field-level provenance in §12.2's evolution), and **coverage inequity** (§11.6a). v1 ships **field-change anomaly detection**: a coordinate jump >2 km, or a contact/hours flip that contradicts standing corroboration, is **demoted-and-flagged** (Wikidata deprecated-rank pattern), never blindly accepted — `federation_anomalous_field_change` + alarm.

**11.12 Review at scale + fast refutation (designed now, built P4).** The review queue is **prioritized by served-population-impact × uncertainty × staleness** (reuse the population weighting in `pick_next_scraper_task.py`), never FIFO, with auto-expiry so nothing is silently stuck. The existing **Lighthouse claim/verify flow is a corroboration tier**: an owner-claim or source-confirm immediately satisfies the §11.6 gate. A minimal **`Flag`/dispute verb is pulled forward to P4** so refutation can un-serve a bad record as fast as corroboration serves one, with retraction propagated mesh-wide (downstream `Delete`/redirect) and a published, instrumented **time-to-correct SLA**. A wrong record harms every hour it is served; the network must retract at least as fast as it publishes.

General: parameterized queries only; API errors leak no internals; every federation decision logged with reasoning (Principles VI/VII/XII).

## 12. Conflict resolution — the model, formalized, plus the required plumbing

We reuse the confidence *model* (every assertion is a row, confidence aggregates rows, no row destroyed) — and v3 makes its convergence guarantee **explicit**.

### 12.1 The merge is a CvRDT, and corroboration dedups by ORIGIN (v1)
The served Location is a **deterministic function of the grow-only assertion-row set**, with a **commutative, associative, idempotent** merge — i.e., a state-based CRDT in all but name, which is why no vector clocks are needed. Two normative rules make it real: (1) every "most-recent-wins" field (coordinates) breaks ties by the **total order `(published, sequence, actor_did)`** so simultaneity never produces node-dependent output; (2) **corroboration deduplicates by ORIGIN** — the envelope's carried `origin`, not the announcing `actor` — so peers B and C re-announcing origin A's record count as **one** vote, not three (the *citogenesis* trap that would otherwise let re-ingested echoes manufacture false confidence and quietly defeat the §11.6 gate). A **Hypothesis property test** is normative: shuffling the arrival order of a fixed activity set across N simulated peers MUST produce a byte-identical canonical Location.

### 12.2 Designed evolution (later-phase, interfaces reserved now)
**Provenance-weighted, freshness-decayed corroboration**: a freshness multiplier (full weight ≤30 d, decaying to a floor by ~180 d) and a per-peer trust tier on `federation_peer` (own-scrapers/human-verification 1.0; pure aggregators 0.5), applied before the ladder — the Overture/OSM/Wikidata answer to good-faith staleness. Its product, **"independently confirmed by N orgs in the last M days,"** is promoted to a first-class served field on the aggregate and the Beacon/PTF surfaces (optional Profile properties) — the network's multi-source nature made visible, and the single strongest trust artifact federation can hand a user. Field-level provenance (per-field origin attribution) rides the same evolution.

### 12.3 The required reconciler plumbing (v2 corrections, unchanged)
- Widen `merge_location`'s corroboration query (today `source_type IN ('scraper', NULL)`) to count `federated_node` **origins** under §12.1; pin `scraper_id='federation:<peer-did>'`.
- Add the missing partial unique index + `ON CONFLICT` target for `source_type='federated_node'` (today undefined).
- The matched-branch `Update` owner-guard: federated `Update`s never overwrite `verified_by ∈ {admin,source,claimed}` (separate code path from the Tier-3 merge exemption).
- `VALIDATOR_ENABLED`: federated ingest inherits the same routing as scraped data; confidence scoring is mandatory for `federated_node` either way (Principle VI).
- Conflicting origin attributions → `federation_conflicting_attribution`, dedup heuristics, demote lower-confidence side, admin queue (prioritized per §11.12).

## 13. Dual-environment design (Principle XV, NON-NEGOTIABLE)

| Concern | Docker (`./bouy up`) | AWS |
|---|---|---|
| Read endpoints + `.well-known/*` + `/federation/checkpoint` | Uvicorn routes (`app/main.py`) | slim Lambda (`lambda_app.py`) + new root-level routes |
| Cold-start `_since=0` | verifiable snapshot file (raw-table aggregates) | HAARRRvest S3/CDN verifiable snapshot |
| `/federation/inbox` (write) | app-container route via the §6.5a enqueuer | **own non-slim Lambda** → ingest SQS |
| Verifiable log + Merkle state + checkpoints | canonical Postgres (reconciler/script-written only) | canonical Aurora (same) |
| Log archive tier (§6.2g) | local filesystem path | S3 (lifecycle: none — never destroyed) |
| Outbound push sender | bouy worker/loop | EventBridge Lambda + DLQ |
| Pull consumer | bouy worker/loop | EventBridge Lambda/Fargate → ingest SQS |
| `federation_peer_cursor` | Postgres | DynamoDB (via the `CursorStore` protocol) |
| Signing + checkpoint keys | `.env` secrets | Secrets Manager (reconciler, scripts, AND checkpoint signer need access) |
| **Kill switch** | `FEDERATION_ENABLED` env | same; redeploy-free runbook |

## 14. Observability (Principles XII & XIV)

- **structlog**: the v2 taxonomy plus `federation_checkpoint_published`, `federation_proof_failed`, `federation_consistency_failed` (**alarmed — possible equivocation**), `federation_anomalous_field_change`, `federation_equity_caveat_served`, `federation_killswitch_active`, `federation_archive_tiered`. Each carries actor/origin DID, sequence, federation_id. CLAUDE.md gets the grep targets per phase (Principle XIII).
- **Metrics** namespace `PantryPirateRadio/Federation/*`: inbox accept/reject by reason, export rows/proofs served, checkpoint age, push latency/failures, ingest by peer, budget rejections, anomaly count, equity-caveat count, time-to-correct (§11.12 SLA).
- **CloudWatch (XIV — not deferrable past introduction):** the phase that first creates a Lambda/SQS/DynamoDB adds its alarms + dashboard widgets + `infra/tests/` assertions in that same phase, routed to `pantry-pirate-radio-alerts-{env}`. Enumerated per phase in the plan (P1: prune/archive Lambda; P2: pull-consumer Lambda + ingest SQS + DLQ + budget alarm; P3: inbox + outbound Lambdas + DLQs + DynamoDB + anomaly alarms).

## 15. Testing strategy (Principle III — TDD, red-first; single-file via `./bouy exec app pytest`, full gate via `./bouy test`)

Everything from v2.1 stands (signing incl. tampered/expired/wrong-key/host-mismatch; hardened fetch; export keyset; inbox guard chain per rejection reason; `@context` handling; HSDS-validation of objects; `federation_id` round-trip; the §12.3 reconciler tests — 100-announces-from-one-peer→1, `ON CONFLICT`, owner-guard, lone-peer-not-served, peer-remove recovery; idempotency one-touch; federation_id-pin-across-drift; publish-side echo; prompt-injection fixtures; PII flagging; N-consecutive-absence tombstones; fictional data only). **v3 additions:** JCS canonicalization fixture **vectors**; object-signature + **inclusion/consistency proof verification including a tampered-log case** (a rewritten leaf breaks the proof); the §12.1 **order-shuffle convergence property test** (Hypothesis); the **kill-switch byte-identical-reconciler test**; cold-start **verifiable-snapshot parity**; equity-caveat serve path; anomaly demote-and-flag. **Golden journey tests** (one black-box `@pytest.mark.integration` per phase, the literal phase gate): P1 concurrent-append→pull→proof-verify→parity→archive boundary; P2 publish→`federated_node`→origin-dedup→lone-peer-gated/equity-caveat→FA-feed ingest; P3 signed-push+concurrent-pull→one touch→peer-remove reverts. All driven against the **in-repo reference second node** (a minimal fixture peer serving `/export`+`state.txt`+signed `/inbox` from the fixtures corpus) — the external "a feed to point at"/"a partner accepting webhooks" dependencies become internal fixtures, and the reference node doubles as the P7 clone-able example.

## 16. File-size & complexity discipline (Principle IX — RESOLVED)
`job_processor.py` is **1892 lines** (constitution table says 1568 — stale; fix it in the same PR). **Decision: decompose** — P1 Task 0 extracts the matched/new-Location commit branch into a focused sub-module (<600 lines, tests green) before the hooks land; P2 Task 0 does the same gate for `merge_strategy.py` (888) and `location_creator.py` (968), with the written-exception fallback per Governance only if extraction proves disproportionate. New `app/federation/` modules stay ≤600/cyclomatic ≤15 by construction.

## 17. Rollout — the living roadmap (each phase independently useful; PRs update CLAUDE.md)

| Phase | Outcome | External dep |
|---|---|---|
| **P0 Foundations** | `app/federation/` skeleton; discovery + `did.json` (recovery-key schema, §6.1a) + WebFinger + actor in both envs; **JCS canonicalization module + vectors**; **RFC 9421 signing**; hardened fetch; multi-file Profile + router URI. | none |
| **P0.5 De-risking spike (HARD GATE)** | Throwaway branch (deleted after; nothing merged) proving: (a) dense-sequence append under genuinely concurrent reconciler commits (no skipped rows, no global serialization); (b) cold-start aggregate parity from raw tables; (c) a two-node loop on disposable code; (d) **JCS+sign+Merkle write-path cost** in the reconciler hot path. Deliverable: a one-page go/no-go memo; contention → escalate to the §6.2f relay/CDC fallback **before** P1. | none |
| **P1 Verifiable publish** | The §6.2 substrate: signed content-addressed objects, Merkle log, **signed checkpoints** (`state.txt` + `/federation/checkpoint`), inclusion/consistency proofs; `/export`+`history`; hooks (job_processor, dedup scripts `Delete`+`redirectTo`, submarine); **kill switch**; cold-start verifiable snapshot; archive tiering; **HSDS-FX spec extraction + fixtures/conformance suite + Readiness Checker + static-feed generator + reference second node + golden test**; P1 Task 0 decomposition. | none |
| **P2 Pull ingest** | Thin enqueuer; consumer (PPR peers w/ proof-verify; plain-HSDS §6.6a); the §12.3 corrections + **§12.1 origin-dedup + CvRDT property test**; un-corroborated gating + **§11.6a equity caveat**; budget; injection hardening; shared idempotency; **acceptance: ingest + corroborate the live Feeding America HSDS feed**; P2 observability. **Closes the loop, with a real node #2.** | none (FA feed is live) |
| **P3 Push** | RFC-9421 inbox (own Lambda, pinned-key + object-sig + consistency verify) + outbound sender (DLQ) + per-DID limits + **anomaly alarms** + **peer-remove recovery**; full XIV enumeration. | a partner accepting webhooks (PPR-to-PPR works via the reference node) |
| **P4 Trust UX, PII & review-at-scale** | `./bouy federation` peer-add/remove/list/status (both fingerprints, sample records); PII heuristic + takedown; **minimal `Flag` verb**; **Lighthouse claim/verify as a corroboration tier**; **prioritized review queue + auto-expiry + time-to-correct SLA** (§11.12). | none |
| **P5 VC trust** *(deferred)* | `Verify`, VC verification, `verified_by='network'`; replaces `fano_allowlist.tsv`. | an issuer (FA) |
| **P6 Witness mesh + Regions/relay** *(committed)* | **Witness cosigning** (peers + HAARRRvest as first witness, §6.2c); Region/Group actors; `Announce` relay (object signatures make origin survive hops natively); outbound `Announce` emission; §12.2 provenance/freshness weighting + the surfaced confirmation signal. | 2+ peers |
| **P7 Hardening** *(deferred)* | RBSR anti-entropy (Negentropy) for divergence repair; optional public-log anchoring (Sigsum/Rekor); full version negotiation; `Move`; recovery-key ceremony; full GDPR redaction; a non-PPR reference implementation validating HSDS-FX. | partner-driven |

## 18. Composition with existing PPR (concrete seams)

`ScraperUtils.queue_for_processing` semantics reproduced by the thin enqueuer (`app/scraper/utils.py` → `app/federation/enqueue.py`); `ContentStoreBackend` (`app/content_store/backend.py`) and the new `CursorStore` protocol modeled on it; corroboration/merge (`app/reconciler/merge_strategy.py:merge_location` — **edited per §12.3**); 3-tier match + human-verified exemption (`app/reconciler/location_creator.py:find_matching_location_with_lock`, `dedup.py`); the federation-log hook sites (`job_processor.py` matched/new-Location commit; the offline dedup scripts `scripts/dedupe_*.py` for `Delete`+`redirectTo`; `submarine_location_handler.py:update_location`); `dedup_run_audit` survivor chain + Beacon `_resolve_terminal` (`app/api/v1/partners/beacon/services.py`); cursor/`updated_since` read precedent (`BeaconSyncService`); outbound-webhook *pattern* (`plugins/ppr-ptf-sync/` — pattern only); read endpoints both envs (`app/api/v1/router.py`, `app/api/lambda_app.py`); Profile/version advertisement (`router.py:362`); validator routing + scoring (`app/llm/queue/processor.py`, `app/validator/scoring.py:HUMAN_VERIFIED_SOURCES`); population weighting for the review queue (`scripts/feeding-america/pick_next_scraper_task.py`); rollback model (`scripts/undo_dedup_run.py`); config (`config/defaults.yml`, `app/core/config.py`, `infra/shared_config.py`); CDK + `MonitoringStack` (`infra/`); bouy core commands.

## 19. Glossary
**Node/peer** — a PPR/compatible deployment, identified by a DID. **Location aggregate** — the v1 unit of content. **Object `id`** — SHA-256 over JCS-canonical envelope bytes (content address; Merkle leaf). **`proof`** — the origin's Ed25519 object signature; survives relays/mirrors. **Checkpoint** — the signed `(origin, tree_size, root_hash, timestamp)` head (C2SP signed-note). **Inclusion / consistency proof** — Merkle proofs that an object is in, and a new head extends, the signed log. **Witness** — a peer cosigning another's checkpoint (P6). **App-view** — the canonical Postgres serving layer; a deterministic CvRDT projection of verified assertions. **Origin-dedup** — corroboration counts distinct asserting origins, not relaying actors. **Allow-list** — the per-node trust gate. **Equity caveat** — the §11.6a served-with-"unconfirmed" path.

## 20. Minimum viable peer (interop tiers — honest)
- **Tier 0 — Consumed-only** (build nothing): publish any HSDS feed or dump; PPR ingests via §6.6a. You get corroboration/freshness/attribution in the network for free. *This is the FA on-ramp and the funnel's mouth.*
- **Tier 1 — Read-only publisher** (an afternoon with the static-feed generator; "a week" hand-rolled): serve `/export` NDJSON + `state.txt` (+ checkpoint when ready) + the Profile. No DID, no signing required to be *consumed*; signing unlocks verifiability.
- **Tier 2 — Push emitter**: adds `did.json` + RFC-9421 signing to deliver into peers' inboxes.
- **Tier 3 — Full peer**: adds `/inbox` + verification + allow-list + checkpoint/witness participation.
Mapping: county GIS/static dump → Tier 0; Vivery/FreshTrak → Tier 0→1; a 211 → Tier 1; Plentiful → Tier 2→3; a sister PPR node → Tier 3.

## 21. Decisions — resolved (v3) and remaining

**Resolved by the owner (2026-06-04 steelman review):**
1. **Verifiable substrate: FULL.** Content-addressed signed objects + Merkle-committed log + signed checkpoints + proofs are the v1 substrate, with the witness mesh committed at P6 — the owner chose this over the lenses' staged-minimal recommendation ("signed head only, substrate later"), accepting the larger P1 for the strongest end-state: a network being built for the 3+-mutually-distrusting-nodes world from day one. Guardrails retained: canonical Postgres stays the serving source of truth (app-view); the log is still an outbox written at the same hooks; **the P0.5 spike gates everything** (a verifiable log over an unproven sequencer verifies the wrong thing).
2. **Signing: RFC 9421** + RFC 9530 + JCS (Cavage-12 dropped; no interop debt existed).
3. **Equity floor: serve-with-caveat in v1** (§11.6a) — gating invisible buries the communities federation should serve.
4. **Stewardship: impl-first, donate in parallel** (§8.5) — build the running reference, bring proof to Open Referral's TC.
5. **Corroboration**: strengthened default confirmed (lone peer never self-promotes) + **origin-dedup** (§12.1).
6. **Principle IX: decompose** (§16), exception only as documented fallback.
7. **Naming: neutral** (`/.well-known/hsds-federation`, "peer"; spec artifact "HSDS-FX") — incumbent-adoption neutrality beats the metaphor.

**Remaining open (decide at the phase that needs them):** witness-set composition + minimum cosigner count (P6); archive live-window length + S3 layout (P1 expansion); FA outreach timing relative to P2 (consume-first is permissionless; when to *tell* them); whether `/federation/stream` (the no-proofs lane) ships in P3 or waits for demand.

**Standing watch items (v3.1 — the only credible paths to a competing standard):** the **CMS/HL7 FHIR Connectathon (2026-07-14..16)** and any move by the FHIR Human-Services-Directory IG to lift its explicit federation out-of-scope and adopt NDH v2's `$export`+Subscriptions directory-exchange patterns (NDH is the one real directory-to-directory protocol in the adjacent world — and it chose Subscriptions over signed feeds, which both de-risks our bulk-NDJSON shape and leaves verifiability as our differentiation). Everything inside pure-HSDS is provenance-field discussion PPR is ahead of and aligned with (first-mover status confirmed by live scan, 2026-06-04).

## 22. Bottom line

Four traditions gave us the primitives; two adversarial passes made the design honest; the steelman pass made it ambitious in the one way that compounds: **verifiability**. v3 is the strongest form of the thesis — every PPR deployment a node, on by default, in core; every published assertion content-addressed, origin-signed, and committed to an append-only log whose history *no one* — including us — can rewrite undetected; corroboration that cannot be gamed by echoes; an equity floor so the network lifts the communities hardest to reach; a wire spec extracted as a community standard with a conformance suite, pointed at Open Referral; and a first edge (the live Feeding America feed) that makes the network real the day P2 ships. The build is still phased, still TDD, still constitution-governed, still killable by one flag — and each phase still stands on its own. "Build more doors, not more lock," enforced by math.