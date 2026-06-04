# HSDS Federation in PPR Core — Design of Record

**Status**: design of record (v2.1, post-adversarial-review of both design and plan). Approved direction (brainstorm 2026-06-03); not yet a ticket. Companion implementation plan: [`../plans/2026-06-03-hsds-federation-core.md`](../plans/2026-06-03-hsds-federation-core.md).
**Date**: 2026-06-03
**Supersedes (home only)**: [`2026-05-22-network-of-lighthouses.md`](2026-05-22-network-of-lighthouses.md) — that doc picked the protocol primitives but scoped the build into the `ppr-lighthouse` plugin. This doc **re-homes the same protocol into PPR core (`app/`)**, scopes a concrete v1, makes the wire format normative, and aligns every decision to [`constitution.md`](../../../constitution.md). For wire-level details the 05-22 examples are **superseded**; §8 here is authoritative. The 05-22 protocol *rationale* (why each primitive beat its alternatives) remains the reference.
**Research behind it**: [`opr-report.md`](../research/2026-05-22-federation/opr-report.md), [`activitypub-report.md`](../research/2026-05-22-federation/activitypub-report.md), [`adjacent-protocols-report.md`](../research/2026-05-22-federation/adjacent-protocols-report.md).

## Review log

- **v1 → v2 (2026-06-03)**: incorporated a four-lens adversarial review (constitution audit, completeness/gaps, non-PPR partner implementability, threat model). Eleven blockers and the majors are folded in. The biggest corrections: the "no new logic" claim was **false** and is replaced by an explicit, tested reconciler-integration spec (§12); the reconciler has **no single transaction** to hook, so federation_log is an **outbox** with a safe-high-water sequence (§6.2, §6.3); `is_active` does not exist — Delete derives from `is_canonical=FALSE` (§9); a normative wire section with one pinned signing profile and a federation_id grammar now exists (§8); SSRF, confidence-gaming, LLM-cost amplification, prompt-injection, rogue-peer recovery, the validator veracity gap, and PII amplification are now first-class v1 requirements (§11). "Plain HSDS publisher participates with no new software" was overstated and is corrected (§6.6a).
- **v2 → v2.1 (2026-06-04, plan review)**: a second adversarial pass (on the implementation plan) found a blocker that also corrects this design — PPR's reconciler Tier-3 path is *prevent-on-ingest* and performs **no** soft-delete, so the `Delete` hook site moves to the offline dedup backfill scripts (§6.2, §9); the `federation_log` advisory lock is scoped to just the sequence append to preserve reconciler parallelism (§6.2); cold-start rebuilds the aggregate from raw tables, not the lossy `location_master` view (§6.3, §13); the thin enqueuer loads the aligner schema/prompt statically so the `LLMJob` is consumable (§6.5a); the `Date` wire format and the §15 run-command heading are pinned; and the companion-plan link is fixed.
- **Open decisions flagged for owner review**: see §21.

---

## 1. Purpose and goals

Make every PPR deployment a **federating node** in an open network of HSDS food-resource endpoints: it ingests from peers it is told about, publishes its own canonical data, and tells peers when that data changes. Modeled on OPR and the Mastodon/fediverse server-to-server model, exchanging data as HSDS.

Three drivers (owner's words) and their architectural consequences:

1. **Richer, fresher data.** Peers are an upstream acquisition channel; an ingested peer record is *another source* feeding the existing reconciler. **Consequence (corrected in v2):** this requires real, tested reconciler plumbing — the corroboration model does **not** count `federated_node` sources today (§12).
2. **Resilience / decentralization** (the Mastodon ethos). The dataset survives any single node dying, including ours. **Consequence:** no central registry, allow-list-per-node trust, signed verifiable records, identity that survives a host change.
3. **"Build more doors, not more lock."** An explicit rejection of PPR-as-central-hub. **Consequence:** federation lives in **OSS core, on by default, gated by nothing**. The protocol is small enough that a non-PPR partner can implement a useful tier in days (§20 defines tiers honestly), and a plain HSDS publisher can be *consumed from* with the caveats in §6.6a.

Peer model: **hybrid** — a mesh of PPR/PPR-compatible nodes speaking the full protocol, plus the ability to *consume* plain third-party HSDS endpoints as read-only upstreams (with the real limitations in §6.6a).

## 2. Non-goals

No central registry/directory; no JSON-LD context expansion (`@context` is a version tag, validated by Pydantic against HSDS, never a JSON-LD processor); no client-to-server protocol (federation is strictly server-to-server); no transactional offer lifecycle (`accept`/`reserve`/`reject`); no single-author-per-record rule (multi-source is a feature); no O(followers) fan-out optimization. **v1 defers**: `Verify` (VC-backed trust + `verified_by='network'` — needs an external issuer), Region/Group actors (FEP-1b12 + HAARRRvest-as-relay), `Flag`, `Move`, LD object-integrity signatures for relay-forwarding, standalone `Organization`/`Service`/`service_at_location` federation (v1 federates the **Location aggregate** — §9), HSDS cross-version negotiation beyond reject-on-mismatch (§8), and full GDPR per-field redaction (but **not** the v1 PII-amplification minimums — §11.8).

## 3. Core insight: directory federation is not social federation

PPR is **reference-data exchange** (FHIR Bulk + VhDir, IATI, OSM diffs) — slowly-changing facts about real entities, multiple authorities asserting their own ids/values for the same logical thing — not transactional offer exchange (OPR) or social messaging (ActivityPub). **We are FHIR-for-public-charitable-food.** Three settled structural decisions: identity unit = the node/Organization (not the user); content unit = the HSDS resource (here, the **Location aggregate**, §9), optimized for incremental sync not real-time fan-out; multiple actors asserting facts about one Location simultaneously is correct, carrying both *authoritative* `Update`s and *corroborating* `Announce`s.

## 4. Why core (`app/`), not a plugin

"On by default for every deployment, gated by nothing" is the maximal form of driver 3; a plugin is a door that can be shut. Architecturally, the one new core-pipeline seam (the federation **outbox** write near the reconciler commit) must live in `app/reconciler/` regardless. Interop requires a documented HSDS Profile a non-PPR partner implements against — a plugin-private contract is not a standard. What changes vs. the 05-22 framing: wire endpoints on the **core API**; onboarding via **`./bouy federation` + a `federation_peer` table** (not a Next.js wizard); neutral naming (a *peer*; `/.well-known/hsds-federation`) because a self-explanatory name is the lowest adoption barrier and "Lighthouse"/"Beacon" are taken.

## 5. Architecture overview

A node has identity `did:web:<domain>` (raw org-URL accepted as fallback). It serves `/.well-known/hsds-federation`, `/.well-known/did.json`, WebFinger, an org actor, and an HSDS-typed activity stream of `Update`, `Announce`, `Delete` activities over the **Location aggregate**. Peers exchange those two ways: a **bulk pull path** (`GET /federation/export?_since=<seq>` → keyset-paginated, sequence-numbered NDJSON; default; cold-start served from a pre-built snapshot, §6.3/§13) and a **push path** (signed-body webhook `POST /federation/inbox`) for active mutual peers. Trust is an explicit per-node **allow-list of peer DIDs**. Discovery is mention-driven. Conflict resolution reuses PPR's confidence/`location_source` model **plus the specific new plumbing in §12**. Every component has a defined Docker and AWS realization (§13; Principle XV).

```
  peers ─pull /export─►  ┌── PPR node (app/) ─────────────────────────────────────────────┐
  peers ─push /inbox─►   │ Discovery (did.json, .well-known/hsds-federation, webfinger)      │
                         │ Inbound /inbox: HARDENED-FETCH-FREE verify (pinned key) ─► allow- │
                         │   list ─► attributedTo ─► (actor,seq) dedup ─► per-peer budget ─►  │
                         │ Federation ingest enqueuer (thin; emits LLMJob, no ScraperUtils)  │
                         │   └► Content Store ─► LLM(aligner, untrusted-delimited) ─► Validator│
                         │       ─► Reconciler  (source_type='federated_node',                │
                         │            scraper_id='federation:<peer-did>')                     │
                         │            • Announce → +corroboration counted per DISTINCT DID     │
                         │            • Update   → merge_location, NEVER overwrites human row  │
                         │            • un-corroborated single-peer Location → NOT served yet   │
                         │  reconciler commit ─► federation_log OUTBOX (seq, type, fed_id, …)  │
                         │            │  (safe-high-water sequence; fires on dedup soft-delete │
                         │            │   and SubmarineLocationHandler too)                    │
                         │            ├─► GET /federation/export (keyset, snapshot from S3)    │
                         │            └─► Outbound sender ─► peers' /inbox (signed, DLQ'd)      │
                         └──────────────────────────────────────────────────────────────────┘
```

## 6. Components

All new code under `app/federation/` (Principle IX: ≤600 lines/file, cyclomatic ≤15). Proposed modules: `identity.py` (DID/`did.json`/actor/WebFinger), `discovery.py` (`.well-known/hsds-federation`), `signing.py` (the pinned Ed25519 HTTP-Signature profile, §8.3), `fetch.py` (**the single hardened egress helper**, §11.1 — every outbound HTTP in federation goes through it), `activities.py` (envelope + `Update`/`Announce`/`Delete` Pydantic models; validates `object` against unmodified HSDS models), `log.py` (`federation_log` outbox: append, safe-high-water sequence, retention prune, export/state/history queries), `peers.py` (`federation_peer` allow-list + cached pinned key + per-peer cursor/budget), `enqueue.py` (**the thin federation-ingest enqueuer**, §6.5a), `ingest.py` (pull consumer + inbox activity router), `outbound.py` (push sender). API routes in `app/api/v1/federation/` wired into `app/main.py`, `app/api/lambda_app.py` (read), and the separate inbox Lambda (write, §13).

### 6.1 Identity & discovery
`did:web:<domain>` → `https://<domain>/.well-known/did.json` (Ed25519 verification key(s) + `alsoKnownAs`→actor URL). `/.well-known/hsds-federation` advertises DID, key location, supported HSDS version + Profile URI, `export`/`inbox`/`history` URLs, allow-list policy, retention SLA, contact. WebFinger resolves `acct:<slug>@<domain>`→actor URL. Implementations MUST accept `did:web:…` and `https://…` as one identity. All discovery fetches use the §11.1 hardened helper.

### 6.2 `federation_log` (the outbox) and the reconciler hook
**Corrected (B3, M5):** `process_job_result` issues *many* independent commits per job; there is no single enclosing transaction. So federation_log is an **outbox**, not a same-transaction guarantee: the log row is appended in the **same `commit()` that writes the canonical row** for that resource, making the pair atomic *per resource* while accepting that the log is a **strict subset** of committed canonical state, never a superset. Row shape: `(sequence BIGSERIAL, type, federation_id, object_json JSONB, published_at, origin_did, content_hash)`.

**Hook sites (named, not hand-waved):** the matched-Location branch and the new-Location branch in `app/reconciler/job_processor.py` (the corroboration/merge commit, vicinity of the `merge_location`/`create_location` calls); the **dedup soft-delete sites in the offline backfill scripts** `scripts/dedupe_near_duplicate_locations.py` / `scripts/dedupe_same_org_locations.py`, at the `is_canonical=FALSE` UPDATE + `dedup_run_audit` insert (emit a `Delete` with `redirectTo`=survivor `federation_id`, §9) — **correction (plan review):** the reconciler's inline Tier-3 path (`find_matching_location_with_lock`) is *prevent-on-ingest* (it merges the incoming scrape into the survivor and creates no soft-delete), so it is NOT a `Delete` source; PPR's only `is_canonical=FALSE` writes live in those scripts, which run outside the reconciler worker (`./bouy exec` / `./bouy run-script --aws`), so the append must work in a script context and no new inline-reconciler soft-delete is introduced in v1; and `app/reconciler/submarine_location_handler.py:update_location` (Submarine enrichment is canonical content peers want — it emits `Update`). The append is implemented as a small tested helper in `app/federation/log.py` called from these sites (Principle IX: extension, not accretion into the 1892-line file — §16).

**Sequence safety under concurrency (M5):** PPR runs concurrent reconciler workers; BIGSERIAL is unique but **not commit-order monotonic** (worker A may grab seq 100, worker B seq 101, B commits first). A naïve consumer at `_since=99` would see 101, advance, and **permanently miss 100**. Fix (throughput-aware): the lock is scoped to **only the `federation_log` sequence allocation + INSERT** (a short critical section), **not** the reconciler's resource commit, so the parallel canonical write path is preserved and only the tiny append serializes. `state.txt`/`X-Federation-Sequence` expose a **safe high-water** = the top of the gap-free committed prefix; gaps are normal and the safe high-water never advances past an in-flight row. (For high volume, a single-writer relay assigning sequences off the hot path is the load-test-gated alternative; the M5 test asserts ordering AND that the reconciler's per-resource commit is not globally serialized.)

**federation_log lives in the canonical Postgres/Aurora DB in both environments and is written ONLY by these reconciler hooks** (nit m11). Only `federation_peer_cursor` is dual-backend (Postgres local / DynamoDB AWS).

**Publish-side echo suppression (m7):** the hook checks origin. A commit driven *solely* by a `federated_node` source (no PPR-origin assertion) appends **nothing** in v1 (PPR does not re-publish peer data under its own DID). Outbound `Announce`-of-peer-data is deferred with §9's authority simplification.

**Retention (m8):** a scheduled prune (EventBridge cadence, like the publisher) deletes `federation_log` rows older than the SLA; `retention_horizon_sequence = min(sequence)` of surviving rows, exposed in `state.txt`. Pruning a Location's last log row while keeping the canonical record is allowed (`_since` below the horizon → `410`, forcing a re-snapshot).

### 6.3 Publish / read path
- `GET /federation/export?_since=<seq>&format=ndjson` → **keyset-paginated** NDJSON (not a single unbounded stream): bounded page size, `X-Federation-Next-Cursor`, `X-Federation-Sequence` (safe high-water), `X-Federation-Retention`. `_since` below the retention horizon → `410 Gone`. Reuses Beacon's `is_canonical=TRUE` + confidence serve gate (§12 extends this gate to un-corroborated peer-only Locations).
- **Cold-start `_since=0` (M8):** served from a **pre-built snapshot artifact** (reuse the HAARRRvest daily SQLite/S3 export, already public and CDN-friendly), NOT a live full-DB scan on the read Lambda (15-min/6-MB/memory ceilings). The live endpoint serves incremental `_since=<N>` deltas. The snapshot **rebuilds the §8.2 Location aggregate from the raw normalized tables** in that export (location/schedule/phone/address/language/accessibility/service_at_location/service), **not** the lossy `location_master` materialized view (which collapses schedules via `DISTINCT ON` and string-aggregates phones/languages); a round-trip parity test asserts the snapshot aggregate equals the live `/export` aggregate for the same `federation_id`.
- `GET /federation/state.txt` → `sequence` (safe high-water), `timestamp`, `retention_horizon_sequence`.
- `GET /federation/history/{federation_id}` → per-aggregate activity history (retention per discovery; default 1yr). Rate-limited/edge-throttled like Beacon (§11.9).

### 6.5 Inbound push (`POST /federation/inbox`)
Verify the §8.3 Ed25519 signature using the **pinned key already cached in `federation_peer`** (the hot inbox path does **no attacker-directed network I/O** — closes the pre-auth SSRF, §11.1) → `actor` ∈ allow-list → for `Update`/`Delete`, `actor == attributedTo` (authoritative-source rule) → `(actor, sequence)` dedup with per-actor **strictly-increasing** sequence (§10) → per-peer **ingest budget** check (§11.3) → route to the thin enqueuer (§6.5a) → `202`. Per-DID rate-limited; anomalous-volume alarms (§11.6).

### 6.5a The federation-ingest enqueuer (B2 — the dual-env write seam)
**Corrected:** there is no "Redis ingest" queue, and `ScraperUtils.queue_for_processing` drags in `REDIS_URL` + the HSDS schema CSV + the aligner prompt + a `SchemaConverter` — exactly what the slim read Lambda excludes. So both the inbox and the pull consumer funnel through a **thin `app/federation/enqueue.py`** that constructs the same **`LLMJob` envelope** the scrapers produce and writes it to the queue backend (`QUEUE_BACKEND`: Redis locally, SQS on AWS) **without instantiating `ScraperUtils`**. Content-store SHA-256 dedup (Principle VIII) is applied here. The enqueuer loads the HSDS schema CSV and the aligner prompt **once at module import** (static files, not Redis), so the enqueued `LLMJob` carries the `format`+`prompt` the aligner worker requires and is genuinely consumable; already-structured plain-HSDS peer records may instead take the cheaper alignment path (§6.6a/§11.5) rather than full free-form alignment. Dual-env: locally the inbox route runs in the app container with `REDIS_URL`; on AWS the inbox is its **own (non-slim) Lambda** that writes to the ingest SQS — mirroring how `ppr-write-api` separates its write path from the read-only API Lambda. The read Lambda (`lambda_app.py`) gains only the **read-only** federation routes and the root-level `.well-known/*`+actor routes (m2), and the federation identity/discovery modules import with **no Redis/LLM dependency** so the slim image stays slim.

### 6.6 Pull ingest consumer
Polls each configured peer on a schedule. **PPR/compatible peer:** `/federation/export?_since=<cursor>` (keyset). Records funnel through the §6.5a enqueuer → Content Store → LLM (untrusted-delimited, §11.5) → Validator → Reconciler as `source_type='federated_node'`, `scraper_id='federation:<peer-did>'`. **Shared idempotency (M7):** inbound pull and inbound push share **one** `(actor, sequence)` key in one `federation_peer_cursor` row, checked before enqueue regardless of transport, so the same change via both transports is processed once and corroborates once.

### 6.6a Consuming a plain (non-PPR) HSDS upstream — the honest mechanism (B8, M10, M11)
**Corrected:** the claim "a plain HSDS publisher participates with no new software via `modified_after`" was false. HSDS's HTTP API has **no `/locations` list endpoint** (Locations are nested under `/services`/`/service_at_locations`), **no `last_modified` on `location.json`** (only on `service.json`, and it's optional/not-required), and **offset pagination** that page-drifts under concurrent writes. Therefore:
- A plain upstream yields **Service-level deltas at best** (`GET /services?modified_after=<wm>&minimal=true` → fetch full), and **only if** it implements optional `modified_after` and populates optional `last_modified`. Location-level incremental sync from a plain publisher is **not possible** via the HSDS API.
- The real mechanism for plain upstreams is **periodic full-snapshot reconciliation**: pull the full dataset, diff against the last-seen id set, synthesize local tombstones for absent records — with a **Principle VI safety rule**: never delete a vulnerable-population Location on a *single* missing pull (require N consecutive absences or admin review).
- Offset pagination is consumed safely with `modified_after` + stable sort, bounded duplicate reads (idempotent via SHA-256), and full re-pull when `total_items` changes mid-walk. This fragility is *why* PPR-to-PPR uses the sequence-numbered `/export`.

### 6.7 Trust / allow-list & onboarding
`federation_peer` (DID, actor URL, **pinned public key + fetched-at**, policy, enabled, retention-seen, notes) is the source of truth. `./bouy federation peer-add <did>` fetches discovery (via the hardened helper), shows key fingerprint + retention + a **sample of recent records** (not just a fingerprint — the review bar matters, §11.7), prompts to approve; `peer-remove` (triggers the §11.6 recovery procedure), `peer-list`, `status`.

## 7. Data model

New tables (SQLAlchemy mirrors HSDS-adjacent structure; these are **provenance metadata**, not HSDS-schema invention — Principle II): `federation_log` (§6.2); `federation_peer` (§6.7); `federation_peer_cursor` (one row per peer: shared inbound `(actor, last_sequence)` idempotency high-water, outbound push high-water, per-peer budget counters; Postgres local / DynamoDB AWS; **note:** this is a *new* schema, not literally `ptf_broker_sync_state` which is keyed `PRIMARY KEY(location_id)` — m12). New values: `location_source.source_type` += `federated_node`; `caller_context.source_type` += `federated_update`/`federated_announce`. `verified_by='network'` reserved, **not issued in v1**.

**federation_id & attributedTo live in the activity ENVELOPE, not inside the HSDS object (m1):** the `object` validates against **unmodified** HSDS Pydantic models. Grammar (M14): `federation_id = <publisher-prefix> ":" <internal-id>`; `<publisher-prefix>` is the **`did:web` method-specific identifier** (the host, e.g. `northjerseyfoodbank.org`), while the envelope's `attributedTo` carries the **full DID**; `<internal-id>` is `unreserved` chars only (a node with `:` in internal ids percent-encodes it); equality is byte-exact after lowercasing the host and stripping a trailing dot. Outbound `federation_id = <our-host>:<location.id>`.

**Inbound federation_id → local mapping (m9):** the consumer first does an **exact lookup** on a stored `(source_type='federated_node', federation_id)` index *before* falling back to coordinate/name tiers, so a peer's stable `federation_id` pins to **one** local Location across coordinate drift (>165 m moves that would otherwise create a duplicate). New index on `location_source(source_type, federation_id)`.

**HSDS Profile (M12 — corrected):** an HSDS Profile is a **multi-file** artifact per `docs/HSDS/docs/hsds/profiles.md`: one RFC-7386 JSON-Merge-Patch per modified schema (`location.json`, `service.json` for `confidence_score`/`verified_by`/`sources[]`), **an `openapi.json` patch that adds the `/federation/*` endpoints**, and a pre-compiled `/schema` dir. These are permitted modifications (new *optional* properties not overlapping HSDS terms). P0 replaces the router's generic `profile` URI (`docs.openhumanservices.org/hsds/`) with one that resolves to this Profile. One canonical host is used for both `@context` and the Profile URI (m13).

## 8. Wire protocol (NORMATIVE — §8 is authoritative; 05-22 examples superseded)

### 8.1 Envelope (push body AND each NDJSON export row are this exact shape)
Envelope key is **`type`** (the 05-22 `activity` key is dropped — B6). The NDJSON export row **is** the full envelope.

```json
{ "@context": "https://hsds.openreferral.org/3.1.1",
  "type": "Update",
  "actor": "did:web:northjerseyfoodbank.org",
  "attributedTo": "did:web:northjerseyfoodbank.org",
  "federation_id": "northjerseyfoodbank.org:abc-123",
  "object": { /* unmodified HSDS Location aggregate; NO federation_id/attributedTo inside */ },
  "published": "2026-06-03T18:33:11Z",
  "sequence": 4730 }
```

Required per verb: `@context` (REQUIRED, exact-string match against the single supported version; mismatch → `422` + `federation_inbox_rejected_version` — m13), `type`, `actor`, `federation_id`, `published` (RFC 3339 UTC), `sequence` (sender's monotonic watermark). `Update`/`Announce` require `object`; `Update`/`Delete` require `attributedTo == actor`. `Delete` object is `{ "type":"Tombstone", "federation_id":"…", "redirectTo":"<survivor federation_id|null>" }` (§9). A normative JSON Schema + a `fixtures/` directory of canonical example activities ship with P1 so partners test against bytes, not prose.

### 8.2 The Location aggregate (§9) is the `object`
One composed HSDS document per Location: the Location plus its embedded `schedules`, `phones`, `addresses`, `languages`, `accessibility`, and the `services` delivered at it (as embedded HSDS objects). This is what Beacon/PTF already shape and what consumers actually need.

### 8.3 Signing profile (PINNED — B7)
**Draft-Cavage-12 HTTP Signatures, Ed25519** (v1 choice; RFC 9421 reconsideration noted in §21). `Signature: keyId="<actor-did>#<key-id>", algorithm="ed25519", headers="(request-target) host date digest", signature="<base64>"`. Signing string: the listed headers as lowercase `name: value` lines joined by `\n`; `(request-target)` = `lowercase(method) + " " + path` (path only, **no query string**). `Digest: SHA-256=base64(sha256(body))`, recomputed and rejected on mismatch. `Date` skew window **±300 s** (m15); the signature MUST cover `date`. PPR's federation profile uses an **RFC-3339/ISO-8601 `Date`** value — a deliberate, normative deviation from Cavage's HTTP-date format — pinned byte-exactly in the `fixtures/` so partners match it. `keyId` host **MUST equal** the `actor` DID host; resolution prefers the **pinned `federation_peer.public_key`** (no network I/O on the hot path — §11.1). A worked byte-level example ships in `fixtures/`.

## 9. Activity semantics (v1)

Unit = the **Location aggregate** (§8.2); `federation_id`/`attributedTo` are per-Location; standalone `Organization`/`Service`/`service_at_location` federation is **deferred** (M6). Schedules are embedded read-only data of the aggregate — only the origin/`attributedTo` writes hours; peer `Announce`s never touch schedule rows (resolves the recurrence-identity collision, m10).

| Verb | Direction | Authorization | Receiver effect |
|---|---|---|---|
| `Update` | origin → peers | only `attributedTo` | **Not a blind replace (M3).** Routes through the same Validator + `merge_location` + **`HUMAN_VERIFIED_SOURCES` guard** as any source; **can never overwrite a row whose `verified_by ∈ {admin,source,claimed}`**. Federated origin authority is **subordinate to local human curation**. A brand-new peer does not overwrite an established multi-source canonical value without corroboration (§11.6). |
| `Announce` | any allow-listed peer | publisher ∈ allow-list | Corroboration → a `location_source` row; counts toward the bonus **per DISTINCT peer DID** (§12), never per `federation_id`/volume. Never overwrites fields. |
| `Delete` | origin → peers | only `attributedTo` | **Derived from PPR's real lifecycle (B4):** PPR emits no upstream deletes; the only PPR-originated `Delete` is a **dedup soft-delete** (`is_canonical=FALSE`) produced by the **offline dedup backfill scripts** (not the reconciler — §6.2 correction), carrying `redirectTo` = the survivor's `federation_id` (from the `dedup_run_audit` survivor chain, reusing Beacon's transitive cycle/depth-guarded `_resolve_terminal`). Receiver sets its copy non-canonical and re-points to the survivor. `is_active` does **not** exist; all references corrected to `is_canonical`. |

**v1 authority simplification (owner-reviewed):** PPR is the asserting authority for its own canonical rows; everything PPR *publishes* is an `Update` attributed to PPR's DID. Cross-publisher `Announce` *emission* is inbound-only in v1 (we record peers' Announces; we do not re-broadcast peer data under our DID — §6.2 echo suppression). When a true origin node joins later, attribution shifts to it.

## 10. Identity, echo/loop prevention, idempotency
(1) Dedup every received activity on `(actor, sequence)` — **one** shared key across pull and push (M7). (2) Per-actor sequence MUST be **strictly increasing**; non-increasing → ignored (replay + loop safety, m15); the dedup-ledger retention ≥ the Date window so within-window replays are always caught. (3) No-echo: never publish/re-`Announce` peer-origin data back toward any peer (publish-side suppression in the §6.2 hook). (4) Corroboration is idempotent per `(peer DID, federation_id)` so one peer asserting one fact via two transports cannot inflate the bonus.

## 11. Trust & security model (rewritten — the v1 threat model is normative, not advisory)

Allow-listing establishes **authenticity, not veracity**; the validator is a **garbage filter, not a truth oracle** (M17). The following are **v1 design-of-record requirements**, not deferrals.

**11.1 SSRF (B9).** Four paths fetch attacker-influenceable HTTPS URLs (`did:web` resolution, WebFinger, `keyId`, the pull feed) and the inbox `keyId` fetch would be **pre-auth**. All federation egress goes through **one hardened helper** (`app/federation/fetch.py`): resolve DNS, **reject** any IP in private/loopback/link-local/CGNAT/IPv6-ULA ranges, **pin the resolved IP** and connect to it (defeats DNS-rebinding/TOCTOU), HTTPS-only, redirect cap with per-hop re-validation, hard response-size cap, short timeouts, forbid IP-literal `did:web` domains. The inbox **never** fetches a key — it uses the **pinned `federation_peer.public_key`** (verification does zero attacker-directed I/O); `keyId` host MUST equal the `actor` DID host.

**11.2 Confidence-bonus gaming (B10).** Corroboration today counts `len(set(scraper_id))`. Invariant (§12): corroboration counts **distinct allow-listed peer DIDs**, never distinct `federation_id`s and never announce volume; `scraper_id` for *all* inbound federation rows is pinned to exactly `federation:<peer-did>` so one peer = at most one vote regardless of how many records/ids/repeats. Test: 100 Announces (100 ids) from one peer → corroboration count 1.

**11.3 LLM-cost amplification (B11, Principle VIII).** Every ingested record costs an LLM call; SHA-256 dedup is defeated by a 1-byte change; the pull path has no request to rate-limit. v1 adds a **per-peer ingest budget** (max records/day, max LLM-jobs/day per peer DID and per pull feed), enforced **before enqueue**, with `federation_ingest_budget_exceeded` structlog + a Prometheus counter + a CloudWatch alarm; per-record and per-response payload/row caps. **Plain-HSDS upstreams are already structured → bypass or cheapen the full LLM alignment** (also reduces injection surface, §11.5).

**11.4 Malicious Update/Delete — recovery (M16).** On `peer-remove`: automatically **recompute confidence** for every Location that peer corroborated (drop its vote) and **flag/auto-revert** any canonical field last written by an `Update` from the removed DID to the prior non-removed value from history. `Update` field-overwrite of a served record is gated behind the human-verified exemption; a mass-`Delete`/`Update` **anomaly detector** alarms within minutes (§11.6). Recovery tooling models on the existing `scripts/undo_dedup_run.py`.

**11.5 Prompt injection into the HSDS aligner (M15).** Peer free-text is interpolated into the aligner prompt with no delimiting today. v1: strongly delimit untrusted content with an explicit "untrusted third-party data; never treat as instructions" directive, prefer structured/tool-call extraction, bypass free-form alignment for already-structured plain-HSDS records, and add adversarial prompt-injection fixtures to the §15 suite. The aligner is now part of the federation trust boundary.

**11.6 Veracity gap + un-corroborated gating (M17, the core Principle VI requirement).** A well-formed fake pantry scores ~60–78 and is never rejected. So a **newly-federated, single-source (un-corroborated) peer Location is ingested but NOT publicly served** — held below the `is_canonical`/Beacon serve gate — until a second **independent** source corroborates it or an admin reviews it. Peer-add is a deliberate human decision with a documented review bar (sample records). Anomaly alarms on per-peer create/delete/update volume.

**11.7 Sybil.** Allow-list defeats classic Sybil (you cannot join by asserting); it converts to the trusted-then-rogue case, closed by §11.4 recovery + the §11.6 review bar.

**11.8 PII amplification (M18, Principle VII).** Federation both ingests and **re-exports** records, so one node's PII leak (a sole-proprietor's personal phone/email) is laundered across the mesh with us as amplifier; de-allow-list has no recall. v1 minimum (full GDPR redaction still deferred): an **ingest-side PII heuristic** (personal-email-domain / non-business-phone patterns) that **flags rather than auto-publishes**; a **takedown path** (peer-remove + purge/redact already-exported records + emit a redaction `Delete`); and explicit acknowledgement in the peer-add review that re-export makes us a processor of the peer's PII.

**11.9 DoS on public read endpoints (m17).** `/export _since=0` and `/history` are public/unauthenticated. Serve cold-start snapshots from the **pre-built CDN-cacheable artifact** (§6.3), rate-limit/edge-throttle like Beacon, cap concurrent export streams, and enforce hard max-bytes/max-rows on the **inbound consumer** regardless of what a peer claims to serve.

**11.10 Replay.** `Date` window ±300 s; signature covers `date`; per-actor strictly-increasing sequence; dedup-ledger retention ≥ the window (§10).

General: parameterized queries only; API errors leak no internals; all federation decisions logged with reasoning (Principles VI/VII/XII).

## 12. Conflict resolution — reuses the MODEL, requires specific new plumbing (corrected)

The "no new logic" claim was false. We reuse the confidence *model* (every assertion a row, confidence aggregates rows, no row destroyed) but the following **new, tested reconciler code** is required:

- **Corroboration query widening** — `merge_location` counts corroboration over `source_type IN ('scraper', NULL)` today; it must count **distinct `federated_node` peer DIDs** as well, under the §11.2 invariant (one peer = one vote). Decision (§21): whether a federated `Announce` feeds the **same** +5/+10 ladder as an independent scraper, or a **weaker** ladder, given a peer may itself have ingested the record from a third node. v1 default: a peer Announce counts as corroboration **only when it agrees with ≥1 independent (non-federated) source or another distinct peer DID** — a lone peer never self-promotes a Location to served (ties to §11.6).
- **New `location_source` upsert target** — the partial unique indexes target `submarine` vs `scraper/NULL`; `federated_node` matches neither `ON CONFLICT` target, so a new partial unique index + `ON CONFLICT` target is required (today the upsert is undefined/erroring for `federated_node`).
- **`Update` owner-protection** — the matched-branch field overwrite in `job_processor.py` must reject federated `Update`s against `verified_by ∈ {admin,source,claimed}` (a separate code path from the Tier-3 *merge* exemption — M3).
- **VALIDATOR_ENABLED (M4)** — federated ingest inherits the same `VALIDATOR_ENABLED` routing as scraped data; confidence scoring is **mandatory** for `federated_node` (Principle VI). Federation does not assume the validator is unconditionally present; with it off, federated records take the same default scoring path (which still enforces the rejection threshold).
- Conflicting origin attributions → `federation_conflicting_attribution` (structlog), fall back to dedup heuristics, demote lower-confidence side, surface to admin queue.

## 13. Dual-environment design (Principle XV, NON-NEGOTIABLE)

| Concern | Docker (`./bouy up`) | AWS |
|---|---|---|
| Read endpoints (`export`/`state`/`history`/`.well-known/*`/actor) | Uvicorn routes in `app/main.py` (Redis/LLM-free) | `app/api/lambda_app.py` (Mangum slim image) **+ new root-level `.well-known/*`+actor routes** (m2) |
| Cold-start `_since=0` | pre-built snapshot file (aggregate rebuilt from raw tables) | HAARRRvest SQLite/S3 export (CDN), aggregate rebuilt from raw normalized tables not `location_master`, not a live Lambda scan (§6.3) |
| `/federation/inbox` (write) | route in app container (`REDIS_URL`), via the §6.5a enqueuer | **own non-slim Lambda** → ingest SQS (mirrors `ppr-write-api`) |
| Federation-ingest enqueuer | `QUEUE_BACKEND=redis` | `QUEUE_BACKEND=sqs` |
| Outbound sender | bouy-invoked worker/loop reading `federation_log` | EventBridge Lambda; **own DLQ** for poison/undeliverable (m3) |
| Pull consumer | bouy-invoked worker/loop | EventBridge Lambda/Fargate → ingest SQS |
| `federation_log` | canonical Postgres | canonical Aurora (same; reconciler-written only) |
| `federation_peer_cursor` | Postgres | DynamoDB |
| Signing key | `.env` secret (never committed) | Secrets Manager |

Identical contracts; configuration-driven differences; neither environment may break the other (Principle XV).

## 14. Observability (Principles XII & XIV, XIV NON-NEGOTIABLE)

- **structlog taxonomy**: `federation_log_appended`, `federation_export_served`, `federation_inbox_received`, `federation_inbox_rejected_{signature,allowlist,attribution,replay,version}`, `federation_ingest_enqueued`, `federation_ingest_budget_exceeded`, `federation_push_delivered`, `federation_push_failed`, `federation_peer_added/removed`, `federation_peer_removed_recovery`, `federation_conflicting_attribution`, `federation_echo_suppressed`, `federation_anomalous_volume`, `federation_pii_flagged`. Each carries actor DID, sequence, federation_id where applicable. CLAUDE.md gets the "Grep CloudWatch for …" entries (Principle XIII, §17).
- **Prometheus / CloudWatch metric namespace** `PantryPirateRadio/Federation/*` (m6): inbox accept/reject by reason, export rows/bytes, push latency/failures, ingest by peer, budget rejections, conflicting-attribution, anomalous-volume.
- **CloudWatch (XIV)**: enumerate the concrete queues — **ingest SQS + its DLQ**, **outbound-sender DLQ** (m3) — each with DLQ-depth + queue-depth alarms; Error+Throttle alarms on each new Lambda (inbox, outbound sender, pull consumer); throttle+system-error alarms on the DynamoDB cursor table; **the §11.6 mass-anomaly and §11.3 budget alarms**; all route to `pantry-pirate-radio-alerts-{env}`; dashboard widgets on `PantryPirateRadio-{env}`; `infra/tests/` assert alarm+widget existence. Core `MonitoringStack` (not a plugin stack).

## 15. Testing strategy (Principle III, NON-NEGOTIABLE — TDD, red-first; single-file via `./bouy exec app pytest`, full gate via `./bouy test`)

Unit: Ed25519 sign/verify (tampered body, expired `Date`, wrong key, `keyId`-host-mismatch); the **hardened fetch helper** (rejects private/loopback/CGNAT/ULA, DNS-rebinding pin, redirect cap, size cap); `federation_log` safe-high-water under simulated out-of-order commits; export keyset/`410`; inbox guards (bad sig, non-allow-listed, `actor≠attributedTo`, replayed/non-increasing sequence, budget exceeded); `@context` mismatch→422; activity Pydantic validation against **unmodified** HSDS models; `federation_id` ABNF round-trip + equality. **Reconciler (the §12 corrections):** corroboration counts distinct peer DIDs (100 Announces from 1 peer → 1); `federated_node` `ON CONFLICT` upsert; federated `Update` cannot overwrite `verified_by ∈ {admin,source,claimed}`; un-corroborated single-peer Location is NOT served; `peer-remove` recomputes confidence + reverts that DID's fields. **Idempotency:** same activity via pull AND push → exactly one `location_source` touch. **Mapping:** peer re-publishes same `federation_id` with moved coordinates → updates the same local Location (no duplicate). **Echo:** a commit driven solely by `federated_node` appends no `federation_log` row. **Security:** adversarial prompt-injection fixtures; PII-heuristic flagging. **Deletion:** dedup soft-delete emits `Delete` with correct `redirectTo`; prune+`410` boundary; plain-HSDS N-consecutive-absence tombstone safety. Property (Hypothesis): HSDS object validation. Integration (`@pytest.mark.integration`): the **two-node loop** (A appends → B pulls *and* receives push → B reconciles as `federated_node` → corroboration fires and is observable) + a generic-HSDS-upstream snapshot-diff ingest test. Fictional data only (Principle VII).

## 16. File-size & complexity discipline (Principle IX)

`job_processor.py` is **1892 lines** (the constitution's table says 1568 — stale; update it). Principle IX: "files exceeding limits MUST be refactored before new features are added." The federation outbox append is an **extracted helper** (`app/federation/log.py`) called from the hook sites — but the §12 corrections (corroboration widening, the new `ON CONFLICT` target, the `Update` owner-guard) **necessarily edit `merge_strategy.py` and `location_creator.py` inline**. **Decision (§21):** P1 either (a) carries the constitution-mandated decomposition of `job_processor.py`/`merge_strategy.py` as a prerequisite task, or (b) records an explicit written Principle-IX exception per Governance ("violations MUST be explicitly justified … simpler alternatives documented"). Recommended: (a) for `job_processor.py` (it is the highest-risk file and the hook lands there anyway), (b) acceptable for the small `merge_strategy.py` corroboration edit if scoped tightly.

## 17. Rollout — the living roadmap (each phase independently useful & shippable; PRs update CLAUDE.md per Principle XIII)

| Phase | Outcome | Docs (Principle XIII) | External dep |
|---|---|---|---|
| **P0 Foundations** | `app/federation/` skeleton; `did.json` + `/.well-known/hsds-federation` + WebFinger + actor (both envs, incl. lambda_app root routes); the **multi-file HSDS Profile** + router URI replaced; signing-key handling; the **hardened fetch helper** (§11.1). | CLAUDE.md: federation overview, `.well-known` surface | none |
| **P1 Publish (bulk read)** | `federation_log` outbox + safe-high-water + the named hook sites (incl. Tier-3 soft-delete `Delete`+`redirectTo` and Submarine `Update`); `/export` (keyset) + `state.txt` + `history`; cold-start from S3 snapshot; retention prune; **the normative wire spec §8 + `fixtures/`**. PPR is *readable*. | CLAUDE.md: structlog grep targets, export contract | none |
| **P2 Pull ingest** | the §6.5a thin enqueuer; `FederationPeerConsumer` (PPR `/export` + plain-HSDS snapshot-diff §6.6a); the **§12 reconciler corrections** (corroboration distinct-DID, `ON CONFLICT` target, `Update` owner-guard, VALIDATOR_ENABLED); **un-corroborated gating (§11.6)**; per-peer **ingest budget (§11.3)**; **prompt-injection hardening (§11.5)**; shared idempotency. **Closes the loop.** | CLAUDE.md: `source_type='federated_node'`, budget, gating | a peer/HSDS feed to point at |
| **P3 Push** | outbound signed sender (DLQ) + `/inbox` (own Lambda) + pinned-key verification (no inbox I/O) + per-DID rate-limit + **anomaly alarms (§11.6)** + **peer-remove recovery (§11.4)**. | CLAUDE.md: `./bouy federation` push ops | a partner accepting webhooks |
| **P4 Trust UX & PII** | `./bouy federation` peer-add/remove/list/status with the review bar; **PII ingest heuristic + takedown path (§11.8)**. | CLAUDE.md: peer runbook, PII takedown | none |
| **P5 VC trust** *(deferred)* | `Verify`, VC verification at the FANO gate, `verified_by='network'`; replaces `fano_allowlist.tsv`. | — | an issuer (Feeding America) |
| **P6 Regions/relay** *(deferred)* | Region/Group actors (FEP-1b12), `Announce` relay w/ origin LD-signatures, HAARRRvest as universal Region; outbound `Announce` emission. | — | an aggregator |
| **P7 Hardening** *(deferred)* | HSDS version negotiation, `Move`, full GDPR per-field redaction, a non-PPR reference impl. | — | partner-driven |

## 18. Composition with existing PPR (concrete seams)

`ScraperUtils.queue_for_processing` semantics reproduced by the thin enqueuer (`app/scraper/utils.py` → `app/federation/enqueue.py`); `ContentStoreBackend` (`app/content_store/backend.py`); corroboration/merge (`app/reconciler/merge_strategy.py:merge_location` ~line 233/310; **edited per §12**); 3-tier match + human-verified exemption (`app/reconciler/location_creator.py:find_matching_location_with_lock`, `dedup.py`); the federation_log hook sites (`app/reconciler/job_processor.py` matched/new-Location commit; the offline dedup scripts `scripts/dedupe_*.py` for `Delete`+`redirectTo`; `submarine_location_handler.py:update_location` for enrichment `Update`); `is_canonical` soft-delete + `dedup_run_audit` survivor chain + Beacon `_resolve_terminal` for `Delete`/`redirectTo` (`app/api/v1/partners/beacon/services.py`); cursor/`updated_since` read precedent (`BeaconSyncService`); outbound-webhook + idempotency-ledger *pattern* (`plugins/ppr-ptf-sync/ptf_sync/state.py` — pattern only, schema differs); read endpoints in both envs (`app/api/v1/router.py`, `app/api/lambda_app.py`); Profile/version advertisement (`router.py:362`); validator routing + scoring (`app/llm/queue/processor.py`, `app/validator/scoring.py:HUMAN_VERIFIED_SOURCES`); config (`config/defaults.yml`, `app/core/config.py`, `infra/shared_config.py`); CDK + `MonitoringStack` (`infra/`); rollback model (`scripts/undo_dedup_run.py`); bouy core commands.

## 19. Glossary
**Node/peer** — a PPR/compatible deployment, identified by a DID. **Location aggregate** — a Location + embedded schedules/phones/addresses/languages/accessibility/services-at-location; the v1 unit of content. **`federation_id`** — `<host>:<internal-id>`, globally unique. **Origin/`attributedTo`** — the node authoritative for a record; only it may `Update`/`Delete`. **Announce** — a non-origin corroboration; one vote per peer DID. **Sequence** — the `federation_log` safe-high-water watermark. **Allow-list** — the per-node set of accepted peer DIDs; the trust gate. **Outbox** — `federation_log` as a strict subset of committed canonical state.

## 20. Minimum viable peer (interop tiers — driver 3, honest)
- **Tier 1 — Read-only publisher** (genuinely "a week"): serve `/export` NDJSON + `state.txt` + the Profile. **No DID, no signing.** PPR can consume you.
- **Tier 2 — Push emitter**: adds `did.json` + Ed25519 outbound signing to deliver to peers' inboxes.
- **Tier 3 — Full peer**: adds `/inbox` + signature verification + allow-list + `history`.
Plain HSDS endpoints are **below Tier 1** — consumable only via the §6.6a snapshot-diff mechanism, with the Service-vs-Location and tombstone caveats. Map partners realistically: a county GIS or a static HSDS dump → consume via §6.6a; Vivery/FreshTrak with engineering → Tier 1; a sister PPR node → Tier 3.

## 21. Open decisions flagged for owner review (in the PR)
1. **Signing profile**: pinned to **Cavage-draft-12 + Ed25519** for v1 (consistency with 05-22). Since we have *no* existing-fediverse interop requirement (HSDS-typed activities don't interop with Mastodon anyway), **RFC 9421** (the actual, non-expired standard) is a defensible alternative. Override here if you'd prefer 9421.
2. **Federated corroboration strength** (§12): v1 default — a lone peer never self-promotes; a peer `Announce` counts only alongside ≥1 independent or another distinct peer DID. Alternative: peers feed the same +5/+10 ladder as scrapers (simpler, weaker against a rogue-then-trusted peer).
3. **Principle-IX (§16)**: decompose `job_processor.py` as a P1 prerequisite (recommended) vs. a documented exception.
4. **Naming**: neutral (`/.well-known/hsds-federation`, "peer"). Say the word to keep "Network of Lighthouses" or coin a Pirate-Radio-themed term.

## 22. Bottom line
Four mature traditions solved every primitive; the 05-22 spec picked the right pieces. v2's contribution is to put the result **in core, on by default, for everyone**, with the wire format pinned, the reconciler integration told truthfully, and the federation threat surface (SSRF, confidence-gaming, cost-amplification, prompt-injection, rogue-peer recovery, the veracity gap, PII amplification) treated as v1 requirements rather than deferrals — because this serves food-insecure people and Principle VI is non-negotiable. The network is not planned into existence; it emerges from making each phase useful on its own.
