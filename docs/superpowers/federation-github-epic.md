# HSDS Federation in PPR Core — GitHub Epic & Issue Bodies

> **Status: DRAFT PLANNING ARTIFACT. Nothing here has been created on GitHub.** This document is the
> proposed epic structure plus ready-to-paste issue bodies for the HSDS-federation epic. It is generated
> from the design of record and the living implementation plan; review it, then we create the issues with
> the (un-run) `gh` recipe below.

**Sources of truth:**
- Design of record (v3.1): [`docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`](specs/2026-06-03-hsds-federation-core-design.md)
- Living implementation plan: [`docs/superpowers/plans/2026-06-03-hsds-federation-core.md`](plans/2026-06-03-hsds-federation-core.md)
- Docs PR: **#518** (DRAFT), branch `docs/hsds-federation-core-design`
- Machine-readable source for the creation step: [`federation-github-epic.issues.json`](federation-github-epic.issues.json)

## What this is

A **3-level issue hierarchy** — 1 epic, 9 phase issues, 9 P0 task issues (P0 is fully decomposed and ready now), and 5 cross-cutting Ecosystem/Standards + Watch issues — **24 issues total.**

## Issue hierarchy

```
[EPIC] HSDS Federation in PPR Core
├── P0    P0 — Foundations
│   ├── P0.1      P0.1 — Federation config + package skeleton
│   ├── P0.2      P0.2 — SSRF-hardened egress helper (§11.1)
│   ├── P0.3      P0.3 — JCS canonicalization + RFC 9421 signing
│   ├── P0.4      P0.4 — Identity: did.json, actor doc, Ed25519 key loading (recovery-key schema §6.1a)
│   ├── P0.5-task P0.5 — Discovery document (.well-known/hsds-federation)
│   ├── P0.6      P0.6 — WebFinger JRD responder
│   ├── P0.7      P0.7 — Wire root-level public routes into both apps
│   ├── P0.8      P0.8 — HSDS Profile files + replace router profile URI
│   └── P0.9      P0.9 — Docs + full gate (phase-closing; open the P0 PR)
├── P0.5  P0.5 — De-risking spike (HARD GATE)
├── P1    P1 — Verifiable publish
├── P2    P2 — Pull ingest
├── P3    P3 — Push
├── P4    P4 — Trust UX & PII
├── P5    P5 — VC trust
├── P6    P6 — Witness mesh + Regions/relay
├── P7    P7 — Hardening
└── Ecosystem & Standards
    ├── STD-1   STD: crosswalk envelope vocabulary to Open Referral provenance model (#558/#553/#508)
    ├── STD-2   STD: propose upstream HSDS PRs — extend last_modified + tombstone/Delete semantics
    ├── STD-3   STD: extract & govern HSDS-FX spec artifact + conformance suite
    ├── STD-4   STD: Open Referral TC engagement — reveal at P2 with the running reference
    └── WATCH-1 WATCH: FHIR Connectathon 2026-07-14..16 + FHIR HSD IG federation scope
```

## Dependency DAG (creation/work order)

```
P0 ─┬─► P0.5 spike (HARD GATE: go/no-go memo) ─► P1 ─► P2 ─► P3 ─► P4
    │                                                 │      └─► P6 (needs 2+ peers)
    │                                                 └─► P5 (needs FA issuer)
    └─► STD-1, STD-2 (permissionless wedge, start now)        P6 ─► P7 (partner-driven)

STD-3 (DRY with P1 Task 11)  •  STD-4 (reveal at P2)  •  WATCH-1 (observe; non-blocking)
```
- **P0** and **STD-1/STD-2** have no dependencies — start immediately.
- **P0.5 is the hard gate**: its accepted go/no-go memo unblocks P1; until then P1–P7 carry `blocked:hard-gate`.
- P1→P2→P3→P4 is the critical path; P5 (FA issuer), P6 (2+ peers), P7 (partner) are externally gated.

## Labels to create (`gh label create`)

| Label | Applies to |
|---|---|
| `blocked:hard-gate` | gated on the P0.5 go/no-go memo |
| `constitution` | NON-NEGOTIABLE-principle-heavy |
| `epic` | the parent tracking issue |
| `federation` | every federation issue |
| `phase:P0` | P0 phase + its tasks |
| `phase:P0.5` | the de-risking spike |
| `phase:P1` | P1 |
| `phase:P2` | P2 |
| `phase:P3` | P3 |
| `phase:P4` | P4 |
| `phase:P5` | P5 |
| `phase:P6` | P6 |
| `phase:P7` | P7 |
| `ready` | decomposed, executable now |
| `type:spike` | throwaway de-risking spike |
| `type:standards` | ecosystem / standards work |
| `type:watch` | external watch item |

## Milestones to create

One per phase + a rolling track: `P0`, `P0.5`, `P1`, `P2`, `P3`, `P4`, `P5`, `P6`, `P7`, `Ecosystem & Standards`.

## Creation recipe (NOT yet run)

> Run these only after the bodies below are approved. Order matters: the epic first (to get its number), then phases as its sub-issues, then P0 tasks under the P0 issue, then the standards/watch track.

```bash
# 0. Auth: this repo pushes as the For-The-Greater-Good account (gitgat is pull-only).
gh auth switch -u For-The-Greater-Good

# 1. Labels
gh label create "blocked:hard-gate" --force
gh label create "constitution" --force
gh label create "epic" --force
gh label create "federation" --force
gh label create "phase:P0" --force
gh label create "phase:P0.5" --force
gh label create "phase:P1" --force
gh label create "phase:P2" --force
gh label create "phase:P3" --force
gh label create "phase:P4" --force
gh label create "phase:P5" --force
gh label create "phase:P6" --force
gh label create "phase:P7" --force
gh label create "ready" --force
gh label create "type:spike" --force
gh label create "type:standards" --force
gh label create "type:watch" --force

# 2. Milestones (gh has no native milestone create; use the API)
gh api repos/:owner/:repo/milestones -f title="P0" >/dev/null 2>&1 || true
gh api repos/:owner/:repo/milestones -f title="P0.5" >/dev/null 2>&1 || true
gh api repos/:owner/:repo/milestones -f title="P1" >/dev/null 2>&1 || true
gh api repos/:owner/:repo/milestones -f title="P2" >/dev/null 2>&1 || true
gh api repos/:owner/:repo/milestones -f title="P3" >/dev/null 2>&1 || true
gh api repos/:owner/:repo/milestones -f title="P4" >/dev/null 2>&1 || true
gh api repos/:owner/:repo/milestones -f title="P5" >/dev/null 2>&1 || true
gh api repos/:owner/:repo/milestones -f title="P6" >/dev/null 2>&1 || true
gh api repos/:owner/:repo/milestones -f title="P7" >/dev/null 2>&1 || true
gh api repos/:owner/:repo/milestones -f title="Ecosystem & Standards" >/dev/null 2>&1 || true

# 3. Issues — bodies live in this doc / federation-github-epic.issues.json.
#    Create the epic first, capture #N, then create children and link them as sub-issues
#    (native sub-issues via the GraphQL addSubIssue mutation, or a task-list in the epic body).
#    A small driver script that reads federation-github-epic.issues.json and calls
#    `gh issue create --title --body-file --label --milestone` is the clean way to do this in one pass.
```

## Consistency & completeness review (automated)

**Verdict:** APPROVE_WITH_FIXES — The set is complete (epic + 9 phases each once + all 9 P0 tasks + STD-1..4 + WATCH-1), parent integrity is sound, labels/milestones are uniform, and every load-bearing citation I spot-checked against the docs is accurate (job_processor.py=1892, merge_strategy.py=888, location_creator.py=968, constitution stale at 1568, router advertises 3.1.1 vs 3.2.3 baseline, Delete derives from the offline dedup scripts not the reconciler Tier-3 path, corroboration dedups by ORIGIN, advisory lock scoped to sequence-append only). One blocking defect: a duplicate `ref` ("P0.5" used by BOTH the spike phase and the discovery-document task) breaks ref uniqueness and must be resolved before assembly. A handful of smaller fidelity/consistency fixes and two missing §21 open-decision homes are noted below.

All 7 review fixes have been applied to the bodies below (blocking `ref` collision resolved: the discovery-document task is now `P0.5-task`; the de-risking spike keeps `P0.5`). The DAG is acyclic, parent integrity holds, and every NON-NEGOTIABLE principle has a home.

### Open decisions surfaced for the owner

These are design §21 *Remaining open* items + one design↔plan divergence, each now homed in its owning issue:

- **Recovery-key verify-side rule (divergence):** design §6.1a says the priority *check* ships in **v1**; the plan sequences enforcement to **P3**. Bodies follow the plan (P3); flagged in **P0.4** for your call.
- **Archive live-window length + S3 layout** → resolve at **P1** expansion (homed in P1).
- **`/federation/stream` no-proofs lane** → ship in **P3** or defer on demand (homed in P3; default: defer).
- **Witness-set composition + min cosigner count** → **P6** (already homed).
- **FA outreach timing** (consume-first is permissionless; *when to tell them*) → **P2 / STD-4**.

---

## Issue bodies

Each body below is verbatim and copy-paste ready (shown in a raw-markdown fence so nested code blocks render correctly). The metadata line above each is for the `gh issue create` flags.

### `epic` — [EPIC] HSDS Federation in PPR Core

**kind:** `epic` · **parent:** `— (root)` · **milestone:** `—` · **labels:** `federation`, `epic`

````markdown
## Summary

Make **every PPR deployment a first-class federating node** in an open network of HSDS food-resource endpoints: it ingests from peers it is told about, publishes its own canonical data, tells peers when that data changes, and — crucially — lets any consumer **verify, not merely trust**, what any node (including ours) has published. The thesis is **"build more doors, not more lock"**: federation lives in **OSS core (`app/`), on by default, gated by nothing** — and "no node is special, including ours" is enforced **by math, not by promise** (a content-addressed, origin-signed, Merkle-committed append-only log with signed checkpoints and inclusion/consistency proofs). The whole publish surface sits behind a tested `FEDERATION_ENABLED` kill switch (Principle XI). The protocol is small enough that a partner can implement a useful tier in days, and the wire spec is extracted as a neutrally-named, separately-governed candidate community standard.

## Why (the three drivers + equity charter)

From the owner's words (design §1):

1. **Richer, fresher data.** Peers are an upstream acquisition channel; an ingested peer record is *another source* feeding the existing reconciler. This requires real reconciler plumbing (corroboration does not count `federated_node` sources today, §12) and corroboration must be **origin-deduplicated** so re-ingested echoes never masquerade as independent confirmation (the *citogenesis* trap, §12.1).
2. **Resilience / decentralization.** The dataset survives any single node dying, including ours. No central registry; allow-list-per-node trust; identity that survives host changes; and **cryptographic non-equivocation** — a node cannot silently rewrite or back-date its published history without breaking proofs a consumer already holds.
3. **"Build more doors, not more lock."** Federation is OSS core, on by default; a partner can implement a useful tier in days (§20); "no node is special, including ours" is enforced by math (§6.2).

**Equity charter (Principle VI corollary):** federation must not worsen coverage for hard-to-reach communities (rural, informal, undocumented-serving pantries) — and this is *measured*, not assumed. The serve-gate carries an explicit **equity floor** (§11.6a): a plausibly-real, single-source low-density Location is served *with a visible "unconfirmed" caveat* rather than gated invisible; the PII heuristic *flags* rather than auto-suppresses informal pantries (§11.8).

### FHIR-for-food / Certificate-Transparency framing (design §3, §5)

PPR is **reference-data exchange** (FHIR Bulk + VhDir, IATI, OSM diffs) — slowly-changing facts about real entities, multiple authorities asserting their own ids/values for the same logical thing — **not** transactional offer exchange (OPR) or social messaging (ActivityPub). **We are FHIR-for-public-charitable-food, with Certificate-Transparency-grade accountability.** Consumers verify three things, not one: the **object signature** (who asserted it — survives any relay hop), the **inclusion proof** (it is genuinely in the log the publisher signed), and the **consistency proof** (the new head is an append-only extension of the head they saw last). The canonical Postgres DB remains the operational source of truth for serving (the *app-view*); the verifiable log is the source of truth **for federation**.

## Design + plan links

- **Design of record (v3.1):** [`docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`](docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md)
- **Living implementation plan:** [`docs/superpowers/plans/2026-06-03-hsds-federation-core.md`](docs/superpowers/plans/2026-06-03-hsds-federation-core.md)
- **Docs PR:** #518 (DRAFT) on branch `docs/hsds-federation-core-design`
- Implementation starts on `feat/federation-p0-foundations` off `main`.

## Phase map (design §17, plan Roadmap)

| Phase | Outcome (one line) | Ext. dep |
|---|---|---|
| **P0 — Foundations** | `app/federation/` skeleton; discovery + `did.json` (recovery-key schema) + WebFinger + actor in both envs; JCS canonicalization + vectors; RFC 9421/Ed25519 signing; SSRF-hardened fetch; multi-file HSDS Profile + router URI. PPR is *discoverable*. | none |
| **P0.5 — De-risking spike (HARD GATE)** | Throwaway branch (deleted; nothing merged) proving: dense-sequence append under concurrent reconciler commits; cold-start aggregate parity from raw tables; a two-node loop; JCS+sign+Merkle write-path cost. Deliverable: a one-page go/no-go memo. | none |
| **P1 — Verifiable publish** | The §6.2 substrate: signed content-addressed objects, Merkle log, signed checkpoints (`state.txt` + `/checkpoint`), inclusion/consistency proofs; `/export`+`history`; hooks (job_processor, dedup scripts `Delete`+`redirectTo`, submarine); kill switch; cold-start verifiable snapshot; archive tiering; HSDS-FX spec extraction + conformance suite + reference second node + golden test. PPR is *verifiably readable*. | none |
| **P2 — Pull ingest** | Thin consumable enqueuer; consumer (PPR peers with proof-verify; plain-HSDS §6.6a); the §12.3 corrections + §12.1 origin-dedup + CvRDT property test; un-corroborated gating + §11.6a equity caveat; per-peer budget; injection hardening. **Acceptance: ingest + corroborate the live Feeding America HSDS feed.** Closes the loop, with a real node #2. | none (FA feed is live) |
| **P3 — Push** | RFC-9421 inbox (own Lambda, pinned-key + object-sig + consistency verify) + outbound sender (DLQ) + per-DID limits + anomaly alarms + peer-remove recovery; full XIV enumeration. | a partner accepting webhooks (PPR-to-PPR via the reference node) |
| **P4 — Trust UX, PII & review-at-scale** | `./bouy federation` peer-add/remove/list/status; PII heuristic + takedown; minimal `Flag` verb; Lighthouse claim/verify as a corroboration tier; prioritized review queue + auto-expiry + time-to-correct SLA. | none |
| **P5 — VC trust** *(deferred)* | `Verify` verb, VC verification at the FANO gate, `verified_by='network'`; replaces `fano_allowlist.tsv`. | an issuer (FA) |
| **P6 — Witness mesh + Regions/relay** *(committed)* | Witness cosigning (peers + HAARRRvest as first witness); Region/Group actors; `Announce` relay; outbound `Announce` emission; §12.2 provenance/freshness weighting + the surfaced "confirmed by N orgs" signal. | 2+ peers |
| **P7 — Hardening** *(deferred)* | RBSR anti-entropy (Negentropy); optional public-log anchoring (Sigsum/Rekor); full version negotiation; `Move`; recovery-key ceremony; full GDPR redaction; a non-PPR reference impl validating HSDS-FX. | partner-driven |
| **Ecosystem / Standards track** | Extend HSDS `last_modified` beyond `service` + tombstone/Delete semantics upstream (the two low-controversy PRs the community needs); contribute to spec issues #558/#553/#508; revive Bloom's federation thread (forum 601) at P2 with the running reference; donate HSDS-FX stewardship to Open Referral; standing watch on the CMS/HL7 FHIR Connectathon + NDH directory-exchange patterns. | community |

**Dependency note (HARD GATE):** P0 and the Ecosystem/Standards wedge have zero dependencies and start now. **P0.5's go/no-go memo gates P1 and everything after it** — a verifiable log over an unproven sequencer verifies the wrong thing. All of P1–P7 are `blocked:hard-gate` until the spike memo is accepted by the owner; contention or a missed-row edge escalates to the §6.2f single-writer-relay / CDC(LSN) fallback **before** P1.

## Incentive flywheel + the Feeding-America spearhead (design §1.1)

Each new node adds corroboration votes → confidence and freshness of *everyone's* served data rises → the "independently confirmed by N orgs" signal (§11.9/§12.2) becomes more valuable → more reasons to join. Consumption is free and verifiable from day one (Tier 0 costs nothing), so the funnel starts at zero friction. **The spearhead is node #2 with zero recruitment:** Feeding America's live HSDS 3.0 feed (~200 banks / 60k pantries, nightly) is consumable today via the plain-HSDS path (§6.6a) — and **P2's concrete acceptance test is: PPR ingests + corroborates the live FA feed end-to-end.** The network has a living, valuable first edge the day P2 ships.

## Child issues (task-list placeholder, grouped by phase)

The assembler turns these human-readable titles into real issue links.

### Phases
- [ ] P0 — Foundations
- [ ] P0.5 — De-risking spike (HARD GATE)
- [ ] P1 — Verifiable publish
- [ ] P2 — Pull ingest
- [ ] P3 — Push
- [ ] P4 — Trust UX, PII & review-at-scale
- [ ] P5 — VC trust
- [ ] P6 — Witness mesh + Regions/relay
- [ ] P7 — Hardening

### P0 tasks (decomposed, ready)
- [ ] P0.1 — Federation config + package skeleton
- [ ] P0.2 — SSRF-hardened egress helper
- [ ] P0.3 — JCS canonicalization + RFC 9421 signing
- [ ] P0.4 — Identity: did.json, actor doc, key loading
- [ ] P0.5(task) [ref `P0.5-task`] — Discovery document (.well-known/hsds-federation)
- [ ] P0.6 — WebFinger
- [ ] P0.7 — Wire root-level public routes into both apps
- [ ] P0.8 — HSDS Profile files + replace router profile URI
- [ ] P0.9 — Docs + full gate

*(Note: the P0.5 in the design/plan is the de-risking **spike**; the "P0.5 — Discovery document" task above is plan Task 0.5 within P0. The spike is the standalone HARD-GATE phase issue.)*

### Ecosystem / Standards track
- [ ] STD: extend HSDS last_modified + tombstone semantics upstream
- [ ] WATCH: FHIR Connectathon + NDH directory-exchange patterns

## Labels / milestones overview

- **Every issue** carries `federation`.
- **This epic** adds `epic` (no milestone).
- **Phase issues** add `phase:P0`..`phase:P7` (`phase:P0.5` for the spike). P0 + its tasks add `ready`; P0.5 adds `type:spike`; P1–P7 add `blocked:hard-gate`.
- **NON-NEGOTIABLE-heavy phases** (e.g. P2, P3) add `constitution`.
- **Standards** issues use `type:standards`; **watch** issues use `type:watch`; both sit in the **Ecosystem & Standards** milestone.
- Phase issues + their tasks use the matching phase milestone (`P0`, `P0.5`, `P1`..`P7`).

## How this epic is tracked

- **Sub-issues:** each phase, P0 task, standards, and watch item is a child issue parented to this epic (P0 tasks parent to the P0 phase issue).
- **Project board with a Phase field:** the board carries a single-select **Phase** field (P0 / P0.5 / P1..P7 / Ecosystem) so progress is visible per phase and the hard-gate state is filterable.
- **Living-plan contract:** P1–P7 are roadmapped at task granularity now and each is expanded into its own bite-sized sibling plan at the start of its session (the binding decisions live in the design doc + roadmap; bite-sized code is written just-in-time). The roadmap row + each phase's "v3 DELTA (binding)" block are authoritative over any older task text.

## Epic acceptance

- [ ] All phase issues (P0, P0.5, P1–P7) closed.
- [ ] PPR **publishes a verifiable log**: content-addressed, origin-signed objects in a Merkle-committed append-only log with signed checkpoints and inclusion/consistency proofs (`/export`, `state.txt`, `/federation/checkpoint`); a rewritten/forked/truncated history is *provably* detected.
- [ ] PPR **ingests + corroborates the live Feeding America HSDS feed** end-to-end as `source_type='federated_node'`, with origin-deduplicated corroboration and the §11.6a equity caveat where applicable (P2 acceptance).
- [ ] A **non-PPR node interoperates** — a reference implementation validating HSDS-FX proves implementation-independence (P7).
- [ ] The whole publish surface is byte-identically a no-op with `FEDERATION_ENABLED=False` (kill-switch test green), and every phase that introduced AWS constructs carries its CloudWatch alarms + `infra/tests/` assertions (Principle XIV).

## Constitution touchpoints

I (Docker-first — all work via `./bouy`), II (HSDS — objects validate against unmodified HSDS Pydantic models; multi-file Profile), III (TDD red-first per task; coverage ratchet), VI (data quality — confidence scoring mandatory for `federated_node`, un-corroborated gating, equity floor), VII (privacy — PII flag-not-suppress, fictional test data only), IX (file-size — `job_processor.py`/`merge_strategy.py`/`location_creator.py` decomposed before hooks land; new modules ≤600 lines), X (gates — black/ruff/mypy/bandit/pytest), XI (resilience — `FEDERATION_ENABLED` kill switch, isolated failures), XIV (AWS observability — alarms in the phase that introduces each Lambda/SQS/DynamoDB), XV (dual-env — every component has a Docker and an AWS realization).

## Notes

- Design §21 records the owner's resolved v3 decisions: **full verifiable substrate** (over staged-minimal), **RFC 9421** signing (Cavage-12 dropped), **serve-with-caveat equity floor** in v1, **impl-first stewardship + donate to Open Referral in parallel**, **origin-deduped corroboration**, **decompose for Principle IX**, and **neutral naming** (`/.well-known/hsds-federation`, "peer", spec artifact "HSDS-FX").
- Design §22 bottom line: every PPR deployment a node, on by default, in core; every published assertion content-addressed, origin-signed, and committed to an append-only log no one — including us — can rewrite undetected; corroboration that cannot be gamed by echoes; an equity floor; a wire spec donated to Open Referral; and a first edge (the live FA feed) that makes the network real the day P2 ships. "Build more doors, not more lock," enforced by math.
````

### `P0` — P0 — Foundations

**kind:** `phase` · **parent:** `epic` · **milestone:** `P0` · **labels:** `federation`, `phase:P0`, `ready`, `constitution`

````markdown
## Summary

P0 makes PPR **discoverable** as a federation node. It lands the `app/federation/` package skeleton and the four primitives every later phase builds on: **identity** (`did:web` document with the ordered recovery-key schema, actor, WebFinger), **discovery** (`.well-known/hsds-federation`), **JCS canonicalization (RFC 8785) + RFC 9421/Ed25519 HTTP Message Signatures**, an **SSRF-hardened egress helper**, and a multi-file **HSDS Profile** replacing the router's generic profile URI. P0 has **zero external dependencies and is executable now** — it is the only fully task-decomposed phase, and the root of the dependency tree.

## Design refs

- Design of record: [`docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`](docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md) — §17 (P0 rollout row), §6.1 (identity & discovery), §6.1a (recovery-key hierarchy), §8.3 (signing: RFC 9421 + RFC 9530 + JCS), §6.3 (path convention), §8.4 (version set-membership), §7 (HSDS Profile + v3.1 baseline note).
- Implementation plan: [`docs/superpowers/plans/2026-06-03-hsds-federation-core.md`](docs/superpowers/plans/2026-06-03-hsds-federation-core.md) — `## P0 — Foundations (fully task-decomposed; execute now)`, Roadmap P0 row.
- Parent epic: `[EPIC] HSDS Federation in PPR Core`.

## Branch

The docs (design + plan) live on `docs/hsds-federation-core-design` (PR #518, DRAFT). Implementation work starts on a fresh branch off `main`: **`feat/federation-p0-foundations`**.

## Deliverables

The nine P0 tasks, each TDD red-first → impl → commit (tracked as the P0.1–P0.9 task issues):

- [ ] **P0.1 — Federation config + package skeleton** — `FEDERATION_ENABLED` (on by default) + skew/retention/budget/page-size settings; `app/federation/__init__.py`.
- [ ] **P0.2 — SSRF-hardened egress helper (§11.1 — blocker)** — `is_blocked_ip` + `hardened_get`: HTTPS-only, internal/loopback/link-local/CGNAT/IPv6-ULA rejection, redirect cap with per-hop revalidation, size cap. (Connect-pin + streaming hard-cap deferred together to P2/P3.)
- [ ] **P0.3 — JCS canonicalization + RFC 9421 signing** — `canonical.py` (`jcs_bytes`, RFC 8785) + `signing.py` (RFC 9421 signature base over `@method @target-uri content-digest created`, RFC 9530 `Content-Digest`, Ed25519 sign/verify, ±skew). Both modules designed so the P1 envelope-object `proof` reuses them.
- [ ] **P0.4 — Identity: did.json, actor doc, key loading** — `build_did_document` / `build_actor` / `load_signing_key`; `verificationMethod` is an **ordered list with explicit `priority`** carrying the online signing key + ≥1 higher-priority offline recovery key (§6.1a; verify-side priority rule ships P3, schema forward-compatible now).
- [ ] **P0.5(task) — Discovery document (`.well-known/hsds-federation`)** — `build_discovery_doc`: `did`, key location, `hsds_versions` (a **list**, §8.4), `profile_uri`, absolute `endpoints.*`, allow-list policy, retention, contact. (Distinct from the P0.5 hard-gate spike.)
- [ ] **P0.6 — WebFinger** — `build_webfinger` JRD responder.
- [ ] **P0.7 — Wire root-level public routes into both apps (Principle XV)** — `register_federation_public_routes(app)` serving `/.well-known/hsds-federation|did.json|webfinger` + actor doc from `app/main.py` (Uvicorn) AND `app/api/lambda_app.py` (slim Lambda); imports only `app.federation.{identity,discovery}` (no Redis/LLM).
- [ ] **P0.8 — HSDS Profile files + replace router profile URI (Principle II)** — RFC-7386 merge-patch `profiles/hsds-ppr/{location,service,openapi}.json` + README (optional `confidence_score`/`verified_by`/`sources` only); set `app/api/v1/router.py:362` profile to the canonical PPR profile URI.
- [ ] **P0.9 — Docs + full gate (Principles XIII, X)** — add a "Federation (core)" subsection to `CLAUDE.md` (the `.well-known` surface, forthcoming `./bouy federation` family, `source_type='federated_node'`, `federation_*` structlog grep placeholder); run `./bouy test` green; open PR.

## Files

- Create: `app/federation/__init__.py`, `app/federation/fetch.py`, `app/federation/canonical.py`, `app/federation/signing.py`, `app/federation/identity.py`, `app/federation/discovery.py`, `app/federation/routes_public.py`.
- Create (Profile): `profiles/hsds-ppr/location.json`, `profiles/hsds-ppr/service.json`, `profiles/hsds-ppr/openapi.json`, `profiles/hsds-ppr/README.md`.
- Modify: `app/core/config.py` (federation Settings block before the `build_database_url_from_components` model_validator), `app/main.py` (after ~line 78), `app/api/lambda_app.py` (after ~line 66), `app/api/v1/router.py:362`, `CLAUDE.md`.
- Test: `tests/test_federation/test_config.py`, `test_fetch.py`, `test_canonical.py`, `test_signing.py`, `test_identity.py`, `test_discovery.py`, `test_public_routes.py`, `test_profile.py`.
- Note: the `app/api/v1/federation/*` data-router package is created in **P1**, not P0.

## Acceptance criteria

Reproduces the plan's **P0 acceptance** block:

- [ ] Discovery, `did.json`, WebFinger, and the actor doc resolve in **both** Uvicorn (`app/main.py`) and the **slim Lambda** (`app/api/lambda_app.py`).
- [ ] `did.json` carries the **ordered recovery-key schema** (signing key + ≥1 higher-priority recovery key, explicit `priority`).
- [ ] JCS canonicalization **vectors pass** (key ordering, whitespace stripping, insertion-order stability, UTF-8).
- [ ] RFC 9421 signing **round-trips and rejects tampering** (recomputed `Content-Digest` mismatch and skew-window enforcement).
- [ ] The fetch helper **blocks internal IPs** (loopback/private/link-local/IMDS 169.254.169.254/CGNAT/IPv6-ULA) and **rejects non-HTTPS**.
- [ ] The PPR **HSDS Profile URI resolves** and `GET /api/v1/` advertises it (no longer the generic `docs.openhumanservices.org/hsds/`); `location.json` adds only optional properties.
- [ ] `./bouy test` is **green** (black + ruff + mypy + bandit + pytest, coverage ratchet).

## Constitution touchpoints

- **II (HSDS, NON-NEGOTIABLE)** — Profile is RFC-7386 merge patches adding only optional props; `hsds_versions` advertised as a set per §8.4.
- **III (TDD, NON-NEGOTIABLE)** — every task opens red-first (`./bouy exec app pytest <path>::<test> -v`; `./bouy test --pytest` does not select files well — owner practice).
- **IX (file size/complexity)** — satisfied **by construction**: new `app/federation/` modules stay ≤600 lines / cyclomatic ≤15.
- **X (quality gates, NON-NEGOTIABLE)** — P0.9 runs the full `./bouy test` gate before PR.
- **XV (dual-env, NON-NEGOTIABLE)** — public routes wired into both Uvicorn and the slim Lambda; `routes_public.py` imports no Redis/LLM so the slim image stays slim.
- **VII (privacy)** — fictional test data only (`555-…`, `example.com`, `h.example`).

## Dependencies / blocked by

- **None** — P0 is the root of the dependency tree (no external dependencies; executable immediately). P0.5 (the hard-gate de-risking spike) and P1–P7 are gated downstream of P0, not the reverse.

## Out of scope

- The `app/federation/log.py` verifiable-log engine, Merkle tree, signed checkpoints, and `/api/v1/federation/export|state.txt|history` data router — all **P1**.
- The verify-side recovery-key **priority enforcement** rule (schema only in P0; enforcement in P3).
- DNS-rebinding connect-pin and streaming byte-counted hard-cap on `hardened_get` (deferred together to P2/P3 when wiring real peer fetches).
- Pull ingest, inbox, enqueuer, CLI — P2/P3/P4.

## Notes

- **HSDS baseline (v3.1):** the vendored spec submodule is **HSDS v3.2.3** while `app/api/v1/router.py:362` currently advertises **3.1.1** (stale). P0 (Tasks 0.5/0.8) **verifies what the code actually implements** and sets the advertised version(s) and Profile/`@context` to the **3.2 line** accordingly — do not hardcode the version string; assert against a `FEDERATION_HSDS_VERSIONS` setting.
- **Endpoint path convention (§6.3):** the `.well-known/*` discovery docs are necessarily **root-level** (`did:web` + WebFinger require it); the data endpoints the design wrote as `/federation/*` mount under the v1 router as **`/api/v1/federation/export|state.txt|history`** and are advertised as **absolute URLs** in the discovery doc (OPR-style — partners never hard-code the prefix). The data router itself is created in P1.
- Per-task constitution gate is inherited verbatim: TDD red-first, files ≤600/cyclomatic ≤15, the same-PR `CLAUDE.md` update (Principle XIII), full `./bouy test` pre-PR.
- Execution handoff: dispatch a fresh subagent per P0 task (superpowers:subagent-driven-development, recommended) or run in-session with checkpoints (superpowers:executing-plans).
````

### `P0.5` — P0.5 — De-risking spike (HARD GATE)

**kind:** `spike` · **parent:** `epic` · **milestone:** `P0.5` · **labels:** `federation`, `phase:P0.5`, `type:spike`, `constitution`

````markdown
## Summary

**NOTE — read first:** this is the standalone **HARD-GATE de-risking spike** (phase milestone `P0.5`). It is distinct from P0 plan-task 0.5, the discovery-document task (issue ref `P0.5-task`, milestone `P0`).

A throwaway, de-risking spike on a **disposable branch (`spike/federation-p05`)** — **nothing merges; the branch is deleted after.** Its sole purpose is to prove the four riskiest federation assumptions on the thinnest possible vertical slice, _before_ they get baked into the real P1/P2 build. This is a **HARD GATE: P1 does not begin until the owner accepts a one-page go/no-go memo** recording a green sequencer result and the chosen path.

Design refs: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md` §17 (P0.5 roadmap row), §6.2f (sequencing escalation path), §21.1 ("the P0.5 spike gates everything"). Plan: `docs/superpowers/plans/2026-06-03-hsds-federation-core.md` → "## P0.5 — De-risking spike (HARD GATE; throwaway by design)".

Parent epic: see ref `epic` ([EPIC] HSDS Federation in PPR Core).

## Why this gates everything

Per design §21.1, the owner chose the **full verifiable substrate** (content-addressed signed objects + Merkle-committed log + signed checkpoints + proofs). The explicit guardrail on that decision: **a verifiable log built over an unproven sequencer verifies the wrong thing.** Without this spike, the plan otherwise first proves its riskiest assumptions _inside_ the real P1/P2 build — entangled with `app/reconciler/job_processor.py` (a 1892-line file; steelman rank-1 risk). De-risk first, on disposable code, so the substrate is built on a sequencer we trust.

## Prove together (thinnest vertical slice)

All four must be demonstrated together on the spike branch:

- [ ] **(1) Sequencer under real concurrency.** Two reconciler workers committing interleaved; a consumer at `_since=N` **never skips a late-committing row** (the M5 hazard) AND the per-resource reconciler commit is **not globally serialized**. **Measure append-lock contention** at realistic write rates.
- [ ] **(2) Cold-start aggregate parity.** Rebuild **one Location aggregate from the RAW normalized tables** in the HAARRRvest SQLite export (location + schedule + phone + address + language + accessibility + service_at_location + service — _not_ the lossy `location_master` view) and **byte-compare** it to the live Beacon-shaped aggregate.
- [ ] **(3) Two-node loop on disposable code.** Process A appends to a `federation_log`; process B pulls `/export` by sequence and lands a `federated_node` `location_source` row.
- [ ] **(4) Verifiable-substrate write cost.** JCS-canonicalize + Ed25519-sign + Merkle-append in the reconciler hot path; **measure added latency per commit. Budget: low single-digit ms.**

## Go / no-go decision rules

- [ ] **Contention or a missed-row edge** → **escalate before P1** to the design §6.2f named fallback: a **single-writer relay** assigning dense sequence off the hot path, or **CDC / logical-replication (Debezium / LSN pattern)** feeding that relay. The M5 test must still assert ordering AND that the reconciler's per-resource commit is never globally serialized.
- [ ] **Write-cost overrun (budget exceeded)** → **coalesce checkpoint signing off the commit path and re-measure.**
- [ ] Record the **chosen sequencer path** in the memo.

## Deliverable

- [ ] A one-page **go/no-go memo** committed to `docs/superpowers/research/`, reviewed and **accepted by the owner before P1 begins**. The memo records the four results, the contention/write-cost measurements, and the chosen sequencer path.

## Files

- Create (throwaway, on `spike/federation-p05` — discarded with the branch): the thinnest disposable slice exercising (1)–(4). None of this code merges to `main`.
- Create (the one artifact that survives): `docs/superpowers/research/<go-no-go-memo>.md` — the go/no-go memo.

## Acceptance criteria

- [ ] The go/no-go memo is committed to `docs/superpowers/research/` and **accepted by the owner**.
- [ ] The memo **records the chosen sequencer path** (in-place dense-sequence append, single-writer relay, or CDC/LSN per §6.2f).
- [ ] **P1 is unblocked only on a green sequencer result** (no skipped rows, no global serialization, contention acceptable; write-cost within budget or coalesced-and-re-measured).
- [ ] The spike branch is **deleted after** the memo is accepted (nothing merges).

## Constitution touchpoints

- **III (TDD)** — the sequencer/parity claims are demonstrated with executable evidence, not assertion.
- **XI (Pipeline resilience)** — the sequencer must preserve the parallel canonical write path (no global serialization) and survive out-of-order commits without data loss.
- **VI (Data quality)** — cold-start parity (2) ensures the federated aggregate is byte-faithful to canonical serving data.

## Dependencies / blocked by

- **Blocks all of P1–P7** (hard gate). The phase issues carry `blocked:hard-gate` pending this memo.
- Builds on P0 foundations (JCS canonicalization module, Ed25519 signing) for the write-cost measurement (4).

## Out of scope

- Any production code, schema migration, or CDK change — this is a disposable spike. The real `federation_log` model, append helper, `/export`, hooks, and substrate land in **P1**.
- Witness cosigning, push/inbox, ingest corroboration — later phases.

## Notes

The spike is throwaway **by design**: its value is the measured go/no-go decision, not reusable code. The plan and design are explicit that contention here re-routes the architecture to a relay/CDC sequencer **before** P1 commits to building the verifiable log on top of it (§6.2f), and that the spike "gates everything" (§21.1).
````

### `P1` — P1 — Verifiable publish

**kind:** `phase` · **parent:** `epic` · **milestone:** `P1` · **labels:** `federation`, `phase:P1`, `blocked:hard-gate`, `constitution`

````markdown
## Summary

P1 turns PPR from *discoverable* (P0) into ***verifiably readable***. Every canonical commit becomes a JCS-canonical, content-addressed, origin-signed activity object appended to an append-only Merkle log (`federation_log`); the head is published as a C2SP-signed checkpoint; `/export` rows carry inclusion proofs and consumers verify a consistency proof on every pull. A second process can pull `/export?_since=<cursor>` and receive exactly the activities committed since, in order, with no skips under concurrent reconciler writes — and a rewritten or truncated history is *provably* detectable, not merely alleged. This is the §6.2 verifiable substrate: "no node is special, including ours," enforced by math.

Parent epic: [EPIC] HSDS Federation in PPR Core.

Design of record: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`
Living implementation plan: `docs/superpowers/plans/2026-06-03-hsds-federation-core.md`

## Design refs

- **§6.2** the verifiable log — (a) signed content-addressed objects, (b) append-only Merkle log + signed checkpoints, (c) witness format fixed now, (d) kill switch, (e) hook sites, (f) sequencing escalation path, (g) archive tiering (never destroy).
- **§6.3** publish / read path (`/export`, `/checkpoint`, `state.txt`, `history`, cold-start verifiable snapshot).
- **§8** wire protocol (NORMATIVE): §8.1 envelope (`type`, `id`, `proof`, `origin`), §8.2 Location aggregate, §8.3 signing (RFC 9421 transport + JCS object `proof`), §8.4 version handling, **§8.5** HSDS-FX spec extraction & stewardship.
- **§9** activity semantics — `Update` / `Announce` / `Delete` (Tombstone + `redirectTo`); Delete produced on PPR's side only by the offline dedup scripts.
- **§16** file-size discipline — decompose `job_processor.py` (1892 lines) before the hooks land (Principle IX, Task 0).
- Roadmap row **P1 Verifiable publish** (plan §Roadmap) — authoritative over the older task text.

## v3 DELTA (binding)

> The roadmap row + design §6.2/§17 are authoritative over the predating task list. P1 builds the **verifiable substrate**, not a plain delta feed:

- **Verifiable substrate.** Every appended activity is a JCS-canonical (RFC 8785), content-addressed (`id = sha256(canonical bytes)`), **origin-signed** (`proof`, Ed25519) object. The object hash is the Merkle **leaf**; a consumer can verify origin from an S3 archive with zero network trust.
- **Dense sequence under a short append lock.** Sequence is dense and gapless (= Merkle leaf index), assigned under an advisory lock scoped to **ONLY** the sequence allocation + INSERT — never the reconciler's per-resource commit, so the parallel canonical write path is preserved. `safe-high-water` = top of the gap-free committed prefix.
- **C2SP signed checkpoints.** An RFC-6962-style tree over the committed prefix yields a checkpoint `(origin_did, tree_size, root_hash, timestamp)`, Ed25519-signed in **C2SP signed-note format**, published in **`state.txt`** + **`GET /federation/checkpoint`**, re-issued on append (coalesced) and at a heartbeat.
- **Inclusion proofs on `/export` rows; consistency proofs across pulls.** Each export row carries leaf hash + audit path to a signed checkpoint; consumers cache the last per-peer checkpoint and verify a **consistency proof** every pull. A rewritten / forked / truncated history breaks the proof — provable, not alleged.
- **Archive tiering (never destroy — §6.2g).** Task 9's old "retention prune" becomes archive tiering: live Postgres window bounded by SLA; older objects + tile hashes archived to S3 (still origin-verifiable, no network); tree state retained so checkpoints + consistency proofs stay valid forever. `_since` below the live window → redirect to the verifiable snapshot/archive (or `410` + archive pointer). `state.txt` advertises the live-window floor + archive location.
- **Kill switch (§6.2d, Principle XI).** `FEDERATION_ENABLED=False` is a hard no-op checked at **every hook site before any work**; pull consumer + inbox short-circuit identically. **Byte-identical-reconciler test:** with the flag off, a canonical commit appends zero rows and the reconciler path is byte-identical to today. Redeploy-free operator runbook ships with P1.
- **HSDS-FX extraction + ecosystem artifacts.** Extract §8 (envelope, aggregate, signing profile, `federation_id` grammar, endpoints, checkpoint format, JSON Schema, fixtures) into the separately-versioned, neutrally-named **"HSDS-FX"** spec (implementable with zero reference to `app/`) with its own governance section (SemVer, public tracker, no normative change without a fixture + conformance test). DRY with `fixtures/`: the same corpus drives PPR's CI **conformance suite**, a hosted **Federation Readiness Checker**, and a copy-paste **static-feed generator**. Ship an **in-repo reference second node** and a **golden P1 journey test** (concurrent-append → pull → proof-verify → parity → archive boundary, including a tampered-log case).
- **Cold-start backfill.** `_since=0` MUST cover **ALL** pre-existing canonical rows, served as a verifiable snapshot built by rebuilding the §8.2 aggregate from the **RAW normalized tables** in the HAARRRvest export — never the lossy `location_master` materialized view. Round-trip parity test asserts snapshot aggregate ≡ live `/export` aggregate.
- **Vocabulary crosswalk (v3.1).** Before HSDS-FX extraction, crosswalk the envelope's `actor`/`attributedTo`/`origin` to Open Referral's in-flight BODS-inspired **publisher / steward / source** role model (spec issues #558 / #553 / #508) and carry **`org-id.guide`** identifiers alongside `did:web` (§7 / §8.5). The §8.5 engagement wedge (contribute to #558; propose the extend-`last_modified` and tombstone PRs upstream) may begin during P1.
- **Pin to the 3.2 line.** `@context`, Profile, and fixtures pin the **HSDS 3.2 line** (vendored baseline v3.2.3).

## File-map

- `app/federation/log.py` — append helper (+ safe-high-water + retention/archive + export/state/history queries); takes a plain DB session so dedup scripts can call it.
- `app/database/models.py` — `+ FederationLog` (columns per §6.2: `sequence`, `id`/`leaf_hash`, `type`, `federation_id`, `object_canonical`, `published_at`, `origin_did`; index on `sequence`).
- A DB migration for `federation_log`.
- `app/reconciler/job_processor.py` — call the log helper at the matched-Location and new-Location commit sites (after Task 0 decomposition).
- `scripts/dedupe_near_duplicate_locations.py` + `scripts/dedupe_same_org_locations.py` — **the real soft-delete site**: append `Delete` + `redirectTo` at the `is_canonical=FALSE` UPDATE + `dedup_run_audit` insert; reuse Beacon `_resolve_terminal` survivor chain.
- `app/reconciler/submarine_location_handler.py` — enrichment → append `Update`.
- `app/api/v1/federation/{__init__,router}.py` — `export` / `state.txt` / `checkpoint` / `history`; included in `app/api/v1/router.py`.
- `fixtures/federation/` — canonical activity examples + JSON Schema + JCS canonicalization vectors + a worked proof + the RFC-3339 `Date` fixture (pinned byte-exactly).
- `infra/stacks/federation_stack.py` + `infra/stacks/monitoring_stack.py` + `infra/tests/` — the retention-prune/archive EventBridge Lambda + its alarm.
- HSDS-FX spec repo/artifact + hosted `@context` / Profile / `/schema` + Readiness Checker + static-feed generator (DRY with `fixtures/`).
- In-repo reference second node (for the golden journey test).

## Tasks (each → red-first failing test + impl + commit when expanded)

- [ ] **Task 0 — Principle-IX decomposition gate (BINARY, do FIRST).** The `Update` hooks land in `job_processor.py` (**1892 lines**, >600). Either (a) extract the matched/new-Location commit branch into a focused sub-module under 600 lines with tests green, **OR** (b) author `docs/superpowers/specs/federation-principle-ix-exception.md` with the written justification + simpler-alternatives-considered (Governance clause) and link it in the PR. Also fix the stale constitution §IX table entry (1568 → 1892). **Recommended: (a).** This is a binary gate — no hooks land until it is resolved.
- [ ] **Task 1 — `FederationLog` model + migration.** Columns per §6.2; index on `sequence`. Test: insert + query by `_since`.
- [ ] **Task 2 — Append helper.** Lock scoped to **ONLY** sequence allocation + INSERT (short critical section), NOT the reconciler resource commit. Safe-high-water = top of the gap-free committed prefix. Tests: (i) out-of-order commit → consumer at `_since=N` never skips the late row (the M5 hazard); (ii) the per-resource reconciler commit is NOT globally serialized (no whole-commit lock held). If load testing shows contention → escalate to the §6.2f single-writer relay / CDC fallback.
- [ ] **Task 3 — Location aggregate serializer (§8.2).** Location + embedded schedules/phones/addresses/languages/accessibility/services-at-location, reusing Beacon/PTF shaping. Test: aggregate matches HSDS Pydantic models; `federation_id`/`attributedTo` live in the **envelope**, NOT the object (m1).
- [ ] **Task 4 — Hook matched/new-Location commit sites.** Append an `Update` at both branches in `job_processor.py`; **publish-side echo suppression** — a commit driven solely by `federated_node` appends nothing (m7). Test: PPR-origin commit appends; pure-federated commit does not.
- [ ] **Task 5 — Delete derivation (corrected — real site).** Hook the soft-delete in the **offline dedup backfill scripts** at the `is_canonical=FALSE` UPDATE + `dedup_run_audit` insert, appending a `federation_log` `Delete` with `redirectTo` = survivor `federation_id`. The reconciler's inline Tier-3 path is prevent-on-ingest (no soft-delete) — do **NOT** hook it. The append runs in script context (no reconciler worker), so `log.py`'s helper takes a plain DB session **and the signing key must be available in script context**. Test: a script soft-delete emits a `Delete` whose `redirectTo` resolves through the `dedup_run_audit` survivor chain (Beacon `_resolve_terminal`).
- [ ] **Task 6 — Hook submarine enrichment.** `submarine_location_handler.update_location` appends an `Update`. Test: submarine enrichment emits a `federation_log` row.
- [ ] **Task 7 — `/api/v1/federation/export` + `state.txt` + `checkpoint` + `history`.** Keyset pagination; `X-Federation-Next-Cursor`; `X-Federation-Sequence` = signed-checkpoint tree_size (safe-high-water); `_since < live-window floor` → redirect to verifiable snapshot/archive (or `410` + archive pointer). Rows carry inclusion proofs. Reuse Beacon `is_canonical` + confidence serve gate. Tests: delta pull by sequence; archive/410 boundary; checkpoint consistency detects a rewritten log.
- [ ] **Task 8 — Cold-start `_since=0` (M8).** Served from the HAARRRvest S3/SQLite snapshot. **Rebuild the §8.2 aggregate from the RAW normalized tables** (location + schedule + phone + address + language + accessibility + service_at_location + service) — NOT the lossy `location_master` view (it collapses schedules via `DISTINCT ON` and string-aggregates phones/languages). Must cover ALL pre-existing canonical rows. Test: cold-start aggregate byte-equals the live `/export` aggregate for the same `federation_id` (round-trip parity — a flattened-view shortcut fails CI).
- [ ] **Task 9 — Archive tiering, NOT prune (dual-env, Principle XV; §6.2g).** Live Postgres window bounded by SLA; older objects + tile hashes archived to S3 (still origin-verifiable); tree state retained so checkpoints + consistency proofs stay valid forever; `state.txt` advertises live-window floor + archive location. AWS: an **EventBridge-scheduled Lambda** (HAARRRvest-publisher cadence); Docker: a **bouy-invoked worker/loop**. Test: archive + redirect/410 boundary in both realizations; consistency proof still verifies across the archive boundary.
- [ ] **Task 10 — Observability for P1 AWS constructs (Principle XIV).** Add the archive/prune Lambda's Error alarm + a dashboard widget routed to `pantry-pirate-radio-alerts-{env}` on `PantryPirateRadio-{env}`, with an `infra/tests/` assertion. (The pull-consumer Lambda + ingest SQS alarms are P2's.)
- [ ] **Task 11 — Normative wire spec + JSON Schema + `fixtures/` (§8).** Envelope key `type`; `id` + `proof` REQUIRED on every published envelope; `@context` set-membership match against advertised versions (major-mismatch → `422`); the `Date`/`published` field is RFC-3339 per §8.3, pinned byte-exactly in a fixture; include JCS canonicalization vectors + a worked proof. Tests validate fixtures against the schema. **HSDS-FX extraction** + governance section + Readiness Checker + static-feed generator (DRY with `fixtures/`); vocabulary crosswalk to publisher/steward/source (#558/#553/#508) + `org-id.guide`; pin to the 3.2 line.
- [ ] **Task 12 — Docs.** CLAUDE.md export/checkpoint contract + the `federation_*` structlog grep targets; `./bouy test`.

## Acceptance

**Golden P1 journey test:** concurrent-append → pull `/export?_since=<cursor>` → proof-verify (object signature + inclusion + checkpoint consistency) → cold-start parity → archive boundary, **including a tampered-log case** that breaks the consistency proof and is detected. Kill-switch byte-identical-reconciler test passes (flag off → zero appends, byte-identical reconciler path). Checkpoint consistency detects a rewritten history.

**P1 acceptance block (plan):**

- [ ] A second process pulls `/export?_since=<cursor>` and receives exactly the activities committed since, in order, with **no skips under concurrent reconciler writes**.
- [ ] A dedup-script soft-delete surfaces as a `Delete` + `redirectTo` (resolved through the survivor chain).
- [ ] A Submarine enrichment surfaces as an `Update`.
- [ ] Cold-start parity holds (`_since=0` aggregate ≡ live `/export` aggregate; covers ALL pre-existing canonical rows).
- [ ] Fixtures validate against the normative JSON Schema; JCS vectors + worked proof pin byte-exactly.
- [ ] The retention/archive Lambda carries its Principle XIV alarm + `infra/tests/` assertion.
- [ ] The in-repo reference second node completes the golden journey against this node.

## Constitution touchpoints

- **IX (file-size)** — resolved by **Task 0** (decompose `job_processor.py` 1892 → focused sub-module), not gestured; stale §IX table entry fixed in the same PR; new `app/federation/` modules stay ≤600 / cyclomatic ≤15 by construction.
- **III (TDD)** — every task is red-first failing test → impl → commit.
- **XII (structured logging)** — `federation_*` structlog taxonomy; documented grep targets (Task 12).
- **XIV (AWS observability)** — **Task 10** archive Lambda Error alarm + dashboard widget + `infra/tests/` assertion.
- **XV (dual-env)** — `/export` on both Uvicorn + Lambda; cold-start via S3; dual-env archive tiering (EventBridge Lambda on AWS, bouy worker/loop in Docker).

## Dependencies / blocked by

- **Blocked-hard-gate:** P1 may not start until **P0 is complete** AND **the P0.5 go/no-go memo is accepted by the owner** (green sequencer). If the P0.5 spike shows append-lock contention, escalate to the §6.2f single-writer-relay / CDC fallback **before** P1 begins.
- Parent: [EPIC] HSDS Federation in PPR Core.
- External dependency: **none** (the FA feed is a P2 concern; P1's reference second node is in-repo).

## Out of scope

- Pull ingest / consumer / corroboration of peers (P2).
- Inbound push / `/inbox` / outbound signed sender (P3).
- Witness cosigning *mesh* and outbound `Announce` emission (P6) — the checkpoint **format** is witness-compatible from day one, but the mesh is not built here.
- VC trust / `verified_by='network'` (P5); `Flag`/PII/Lighthouse-claim trust UX (P4).

## Decomposition

Per the living-plan contract, P1 is a roadmap-level phase: it is **expanded into a bite-sized sibling plan at session start** (red-first failing test → impl → commit per task), and the v3 DELTA + roadmap row are authoritative over any older task text. The Task 0–12 checklist above is the provisional sub-task list carried from the plan and the binding v3 DELTA; expand each into concrete steps when the implementation session opens. Task 0 (Principle-IX decomposition) is a binary gate executed FIRST.

## Open decision (design §21 — settle at P1 expansion)

- [ ] **Archive live-window length** — how much log stays in live Postgres before tiering to S3 (§6.2g) — and the **S3 archive layout** (tlog-tiles / Tessera tile-prefix scheme). Recorded open in design §21; resolve when P1 is expanded into its bite-sized sibling plan.
````

### `P2` — P2 — Pull ingest

**kind:** `phase` · **parent:** `epic` · **milestone:** `P2` · **labels:** `federation`, `phase:P2`, `blocked:hard-gate`, `constitution`

````markdown
## Summary

Ingest a peer — a PPR/compatible node **or** a plain-HSDS upstream — into the reconciler as `source_type='federated_node'`, correctly and safely. This closes the two-node federation loop **with a real node #2**: the concrete acceptance is that PPR ingests and corroborates **the live Feeding America HSDS 3.0 feed** end-to-end (the adoption spearhead, no recruitment required). P2 lands the §12.3 reconciler corrections plus the §12.1 origin-dedup citogenesis fix, the §11.6a equity caveat, the §12.1 CvRDT order-shuffle property test, and §11.11 field-change anomaly detection.

**Design of record:** `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`
**Living plan:** `docs/superpowers/plans/2026-06-03-hsds-federation-core.md` → `## P2 — Pull ingest + the reconciler corrections (roadmap)`
**Parent epic:** [EPIC] HSDS Federation in PPR Core

## Design refs

- **§6.5a** — the thin federation-ingest enqueuer (same `LLMJob` envelope as scrapers; schema CSV + aligner prompt loaded once at module import; no `ScraperUtils`/Redis at import; `QUEUE_BACKEND` redis/sqs; Content-Store SHA-256 dedup; plain-HSDS records take the cheaper alignment path).
- **§6.6** — pull ingest consumer: PPR peers via `/export?_since=<cursor>` **with proof verification (object signature + inclusion + checkpoint consistency) before enqueue**; plain HSDS via §6.6a; one shared `(actor, sequence)` idempotency key checked before enqueue regardless of transport.
- **§6.6a** — plain-HSDS upstreams: `/services?modified_after` Service-level deltas only (HSDS has no `/locations` list nor `last_modified` on Location), periodic full-snapshot reconciliation, tombstones synthesized only after N consecutive absences, full re-pull when `total_items` shifts mid-walk. The live FA feed (~200 banks / 60k pantries, nightly) is the spearhead node #2.
- **§11.2** — corroboration counts distinct origins, never `federation_id` fan-out or announce volume; `scraper_id='federation:<peer-did>'`.
- **§11.3** — per-peer ingest budget (records/day + LLM-jobs/day per DID and per feed) enforced before enqueue; `federation_ingest_budget_exceeded` + alarm.
- **§11.5** — prompt-injection hardening: delimit untrusted peer free-text + "never treat as instructions" directive; structured plain-HSDS bypasses free-form alignment; the aligner is part of the trust boundary.
- **§11.6** — un-corroborated gating: a single-source peer Location is ingested but not served until a second independent origin corroborates or an admin reviews — except as provided by §11.6a.
- **§11.6a** — equity floor (owner decision): a plausibly-real single-source Location in a low-density area (rural/informal/undocumented-serving) **is served with a visible "unconfirmed" caveat** rather than gated invisible, instrumented via `federation_equity_caveat_served`.
- **§11.11** — field-change anomaly detection: coordinate jump >2 km or a contact/hours flip that contradicts standing corroboration → demote-and-flag (Wikidata deprecated-rank pattern) + `federation_anomalous_field_change` + alarm.
- **§12.1** — the merge is a CvRDT; most-recent-wins ties break by total order `(published, sequence, actor_did)`; corroboration dedups by ORIGIN; normative Hypothesis order-shuffle property test.
- **§12.3** — the required reconciler plumbing (widened corroboration query, `ON CONFLICT` target, `Update` owner-guard, `VALIDATOR_ENABLED` routing, conflicting-attribution handling).

## v3 DELTA (binding)

The roadmap P2 row and this DELTA are authoritative over older task prose.

- **(a) Acceptance is concrete.** PPR ingests **and corroborates the live Feeding America HSDS 3.0 feed end-to-end** via §6.6a — the FA feed is the most valuable node #2, consumable today with zero recruitment. The FA feed is live; there is no external dependency.
- **(b) Proof-verify before enqueue.** PPR-peer ingest **verifies object signature + inclusion proof + checkpoint consistency (against the cached peer checkpoint) BEFORE enqueue**; a record that fails verification is never enqueued.
- **(c) Corroboration dedups by ORIGIN (citogenesis fix).** Count distinct carried `origin` DIDs, not announcing actors: N peers re-announcing one origin's record = **1 vote, not N**. This is what stops re-ingested echoes from manufacturing false confidence and quietly defeating the §11.6 gate.
- **(d) §11.6a equity caveat is a new task.** Serve a plausibly-real single-source low-density Location **WITH a visible "unconfirmed" caveat** instead of gating it invisible, with `federation_equity_caveat_served` instrumentation. Density thresholds and caveat copy are P2 implementation parameters.
- **(e) §12.1 CvRDT order-shuffle Hypothesis property test is a new task.** Shuffling the arrival order of a fixed activity set across N simulated peers MUST produce a byte-identical canonical Location.
- **(f) §11.11 field-change anomaly detection lands here** with its alarm: coord jump >2 km / contact-hours flip against standing corroboration → demote-and-flag + `federation_anomalous_field_change`.

## File-map

- `app/federation/enqueue.py` — thin `LLMJob` enqueuer; no `ScraperUtils`; Content-Store dedup; `QUEUE_BACKEND` redis/sqs.
- `app/federation/ingest.py` — pull consumer (PPR `/export` keyset + plain-HSDS snapshot-diff §6.6a); shared inbox activity router.
- `app/reconciler/merge_strategy.py` — corroboration widened to count distinct `federated_node` peer **origins** (§12.1 origin-dedup / §12.3 plumbing / §11.2 anti-gaming). **>600 lines — Task 0 gate.**
- `app/reconciler/location_creator.py` — new partial unique index + `ON CONFLICT` target for `federated_node`; exact-`federation_id` lookup before coordinate tiers (m9). **>600 lines — Task 0 gate.**
- `app/reconciler/job_processor.py` — federated `Update` cannot overwrite `verified_by ∈ {admin,source,claimed}` (M3).
- `app/llm/...` — delimit untrusted peer free-text (§11.5).
- `app/database/models.py` — `federation_peer`, `federation_peer_cursor` (peer + cursor via `CursorStore` protocol).
- `infra/stacks/federation_stack.py` + `infra/stacks/monitoring_stack.py` + `infra/tests/` — pull-consumer Lambda + ingest SQS + DLQ alarms.

Each task is red-first: failing test → implementation → commit.

## Task checklist

- [ ] **Task 0 — Principle-IX gate (binary, do FIRST).** P2 edits `merge_strategy.py` (888 lines) and `location_creator.py` (968 lines), both >600. For each file being edited: either (a) extract the touched responsibility under 600 lines (tests green), OR (b) author/extend `federation-principle-ix-exception.md` with the specific justification per Governance. Make the choice binding **before** adding the §12 corrections below.
- [ ] **Task 1** — `federation_peer` + `federation_peer_cursor` models + migration. One shared inbound idempotency key `(actor, sequence)` (used by both pull and the P3 inbox), per-peer budget counters, per-peer pull/push cursors. (NOTE: `ptf_broker_sync_state` is keyed `PRIMARY KEY(location_id)` — a *pattern* reference only, not the shape.)
- [ ] **Task 2** — Thin, CONSUMABLE enqueuer. Produce the same `LLMJob` envelope scrapers produce (valid `format` + `prompt`) by loading the schema CSV + aligner prompt **once at module import** (static files; no `ScraperUtils`, no Redis at import). Already-structured plain-HSDS peer records take the cheaper alignment path (§6.6a/§11.5); state which records take which path. Tests: (i) slim-import — `import app.federation.enqueue` pulls in no Redis/`ScraperUtils` (Principle XV); (ii) consumable — an enqueued federation job carries non-empty `format`+`prompt` an aligner worker accepts (envelope ref `app/llm/queue/job.py` `LLMJob`; worker read `app/llm/queue/processor.py`). Content-Store SHA-256 dedup applied here (Principle VIII).
- [ ] **Task 3** — `VALIDATOR_ENABLED` routing (M4). Federated ingest routes through `should_use_validator()` exactly like scraped data; with `VALIDATOR_ENABLED` off, a `federated_node` record still gets confidence scoring + `VALIDATION_REJECTION_THRESHOLD` enforcement (NOT bypassed) — Principle VI. Test: a federated job with the validator off lands at the reconciler with a scored confidence and is subject to the rejection threshold (`should_use_validator` defaults False via `getattr` even though config defaults True — lock this in).
- [ ] **Task 4** — Corroboration correction (§12.1/§11.2, origin-deduped). Widen `merge_location` to count distinct **ORIGINS** (the envelope's carried `origin` DID, not the announcing actor); pin `scraper_id='federation:<peer-did>'`. Tests: 100 Announces / 100 federation_ids from ONE peer → count 1; **three peers all re-announcing origin X's record → count 1, not 3** (the citogenesis trap).
- [ ] **Task 5** — `ON CONFLICT` target. New partial unique index + `ON CONFLICT` target for `source_type='federated_node'` (today it matches neither the submarine nor scraper/NULL target → undefined). Test: upsert well-defined (no error); repeat Announce collapses.
- [ ] **Task 6** — `Update` owner-guard (M3). Reject a federated `Update` against `verified_by ∈ {admin,source,claimed}` (a separate code path from the Tier-3 merge exemption). Test: a `verified_by='claimed'` row is unchanged by a federated `Update` (Principle VI).
- [ ] **Task 7** — Un-corroborated gating (§11.6). A single-peer, un-corroborated Location is ingested but held below the serve/`is_canonical` gate until a second independent source corroborates or an admin reviews — except where §11.6a applies. Test: lone-peer Location not in `/export` / public API.
- [ ] **Task 8** — Per-peer ingest budget (§11.3). Max records/day + max LLM-jobs/day enforced BEFORE enqueue; `federation_ingest_budget_exceeded`. Test: budget exceeded → enqueue refused + logged.
- [ ] **Task 9** — Exact federation_id mapping (m9). Inbound lookup on `(source_type='federated_node', federation_id)` before coordinate tiers + index. Test: same peer id with moved coords → updates same local Location, no duplicate.
- [ ] **Task 10** — Shared idempotency (M7). The `(actor, sequence)` key is checked before enqueue regardless of transport; same activity twice → one `location_source` touch. In P2 the "push" half is **simulated via a second enqueue call** (the real `/inbox` arrives in P3); the cross-transport pull+push integration test belongs to P3. Test: two enqueue calls with the same `(actor, sequence)` → exactly one touch.
- [ ] **Task 11** — Prompt-injection hardening (§11.5). Delimit untrusted content + an explicit "untrusted; never instructions" directive; bypass free-form alignment for already-structured plain-HSDS records. Test: injection fixtures do not move canonical fields.
- [ ] **Task 12** — Plain-HSDS consumer (§6.6a). `/services?modified_after` (Service-level deltas only) + full-snapshot-diff tombstones with N-consecutive-absence safety. Test: deletion only after N absences.
- [ ] **Task 13** — Pull consumer loop (Docker bouy worker / AWS EventBridge-scheduled Lambda).
- [ ] **Task 14** — Observability for P2 AWS constructs (Principle XIV). ingest SQS depth + its DLQ-depth alarms; pull-consumer Lambda Error + Throttle alarms; the §11.3 budget-rejection alarm; dashboard widgets on `PantryPirateRadio-{env}`; all routed to `pantry-pirate-radio-alerts-{env}`; `infra/tests/` assertions per resource.
- [ ] **Task 15** — Docs: CLAUDE.md `source_type='federated_node'`, budget, gating; `./bouy test`.

### Additional v3-DELTA tasks (new, not in the original 0-15)

- [ ] **§11.6a equity caveat (DELTA d).** Serve a plausibly-real single-source low-density Location with a visible "unconfirmed" caveat instead of gating invisible; emit `federation_equity_caveat_served`. Density thresholds + caveat copy are P2 parameters.
- [ ] **§12.1 CvRDT order-shuffle property test (DELTA e).** Hypothesis test: shuffled arrival order of a fixed activity set across N simulated peers → byte-identical canonical Location.
- [ ] **§11.11 field-change anomaly detection (DELTA f).** Coord jump >2 km / contact-hours flip against standing corroboration → demote-and-flag + `federation_anomalous_field_change` + alarm.

## Acceptance criteria

- [ ] **Concrete acceptance:** PPR ingests **and corroborates the live Feeding America HSDS feed end-to-end** via the §6.6a plain-HSDS path against existing scraper sources.
- [ ] **Golden P2 journey** passes against the reference node: publish → `federated_node` → origin-dedup (100 announces → 1; **3 relays of one origin → 1**) → lone-peer gated → **equity caveat served where §11.6a applies**.
- [ ] PPR-peer ingest verifies **object signature + inclusion + checkpoint consistency BEFORE enqueue**; a record failing any check is never enqueued.
- [ ] The §12.1 CvRDT order-shuffle Hypothesis property test passes (byte-identical canonical Location under shuffled arrival).
- [ ] The enqueued federation job is **consumable by the aligner** (non-empty `format`+`prompt` an aligner worker accepts); `import app.federation.enqueue` pulls in no Redis/`ScraperUtils` at import (Principle XV).
- [ ] `VALIDATOR_ENABLED`-off federated record still scored + subject to the rejection threshold (not bypassed).
- [ ] Per-peer budget, prompt-injection, shared idempotency, owner-guard, and anomaly-demote tests pass.
- [ ] `federated_node` `ON CONFLICT` target defined; repeat Announce collapses; exact `federation_id` lookup maps coord-drifting records to the same local Location.
- [ ] The pull-consumer Lambda + ingest SQS carry their Principle-XIV alarms (SQS depth, DLQ depth, Lambda Error/Throttle, budget-rejection) with `infra/tests/` assertions per resource.
- [ ] `./bouy test` green; CLAUDE.md updated (`source_type='federated_node'`, budget, gating).

## Constitution touchpoints

- **VI — Data Quality (NON-NEGOTIABLE):** un-corroborated gating (Task 7), `Update` owner-guard (Task 6), per-peer budget (Task 8), mandatory `VALIDATOR_ENABLED` scoring for `federated_node` (Task 3); the §11.6a equity caveat is itself a Principle-VI under-serve mitigation; §11.11 anomaly demote-and-flag.
- **VIII — Content Deduplication:** Content-Store SHA-256 dedup applied in the enqueuer (Task 2); the §11.3 budget also bounds LLM-cost amplification (Principle VIII).
- **III — TDD (NON-NEGOTIABLE):** every task is red-first (failing test → impl → commit); the §12.1 order-shuffle Hypothesis property test is normative.
- **IX — File Size & Complexity:** Task 0 is the binary 600-line gate for `merge_strategy.py` (888) and `location_creator.py` (968) — extract-or-memo before any §12 corrections.
- **XI — Pipeline Resilience:** poison-record handling — drop + structlog + metric, **bounded retries so one poison record can't wedge the cursor**.
- **XIV — AWS Observability:** Task 14 — ingest SQS + DLQ + pull-consumer Lambda + budget-rejection alarms, dashboard widgets, `infra/tests/` per resource.
- **XV — Dual-Environment (NON-NEGOTIABLE):** slim-import enqueuer (no Redis/`ScraperUtils` at import); dual-env pull consumer (Docker bouy worker / AWS EventBridge Lambda); Postgres-local / DynamoDB-AWS cursor behind the `CursorStore` protocol.

## Dependencies / blocked by

- **Blocked by P0.5 hard gate** — the go/no-go memo must be accepted before any P1-P7 phase work begins (`blocked:hard-gate`).
- **Blocked by P1 complete** — P2's pull consumer pulls the **P1 `/export` + proofs** (signed content-addressed objects, Merkle log, signed checkpoints, inclusion/consistency proofs); proof-verify-before-enqueue depends on the P1 substrate and the in-repo reference second node.
- **No external dependency** — the Feeding America feed is live; the §6.6a path needs no partner recruitment.

## Decomposition

Per the living-plan contract, this phase is **not yet decomposed into executable tasks at the line level**. At session start, P2 is expanded into a bite-sized sibling plan (red-first failing test → minimal impl → commit per task), with the roadmap P2 row and the **v3 DELTA (binding)** above authoritative over older task prose. The Task checklist above (Tasks 0-15 plus the three new DELTA tasks) is the **provisional** sub-task list and will be refined into the sibling plan before execution. **Task 0 (the Principle-IX gate) is executed FIRST and its choice is binding before the §12 reconciler corrections land.**

## Notes

- Examples in this issue and the sibling plan use fictional data only (`555-` phone prefixes, `example.com` / `h.example` hosts) per Principle VII.
- `record_version` continues to log each job's raw submission; for multi-source federated Locations this diverges from the merged canonical row (audit-of-submission vs merged-state), consistent with the existing matched-location merge limitation.
- Coordinate selection is most-recent-wins with ties broken by `(published, sequence, actor_did)` per §12.1; per-source geocoder quality weighting is reserved for §12.2 (later phase).
- Freshness decay and per-peer trust tiers (§12.2) are interfaces reserved now, built later; v1 ships origin-dedup (§12.1) + anomaly detection (§11.11) as the good-faith-degradation answers available today.
````

### `P3` — P3 — Push

**kind:** `phase` · **parent:** `epic` · **milestone:** `P3` · **labels:** `federation`, `phase:P3`, `blocked:hard-gate`, `constitution`

````markdown
## Summary

P3 adds **real-time, RFC-9421-signed-body webhooks** to the federation network so a publisher can push a Location change to peers the moment it is reconciled, instead of waiting for the next pull. It ships the **inbound `/federation/inbox` verify/guard chain** (transport signature → object signature → allow-list → attribution → replay/sequence → checkpoint consistency → budget → enqueue, all with zero attacker-directed network I/O), the **outbound signed sender** (with retry/backoff + DLQ + per-DID rate limit), and the **peer-remove recovery** path that drops a rogue/compromised peer's corroboration votes and reverts the canonical fields it last wrote. Push shares the same `(actor, sequence)` idempotency key as the P2 pull path, so a record delivered by both transports is processed exactly once. This phase also carries the **full Principle-XIV observability enumeration** for every new AWS resource it introduces.

## Design refs

- Design of record: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`
  - **§6.5** — inbound push verification *order* (RFC 9421 transport sig against the **pinned** `federation_peer` key → object signature → `actor ∈` allow-list → `actor == attributedTo` for `Update`/`Delete` → `(actor, sequence)` strictly-increasing dedup → checkpoint consistency → per-peer budget → thin enqueuer → `202`; per-DID rate-limited)
  - **§6.5a** — the thin `app/federation/enqueue.py` both inbox and pull funnel through (same `LLMJob` envelope, SHA-256 content-store dedup); inbox is its **own non-slim Lambda → ingest SQS** on AWS
  - **§11.1** — SSRF / pinned-key, **the inbox NEVER fetches**; `keyId` host MUST equal the actor DID host
  - **§11.4** — rogue/compromised peer recovery on `peer-remove` (recompute confidence dropping its votes + flag/auto-revert canonical fields it last wrote; model on `scripts/undo_dedup_run.py`)
  - **§11.6** — un-corroborated gating context (anomaly detector is a guardrail); **§11.11** — field-change anomaly detection (coordinate jump >2 km or contact/hours flip contradicting standing corroboration → demote-and-flag, `federation_anomalous_field_change`)
  - **§11.10** — replay (RFC 9421 `created`/`expires` ±300 s; per-actor strictly-increasing sequence)
  - **§13** — dual-env table (inbox = own non-slim Lambda → ingest SQS; outbound sender = EventBridge Lambda + DLQ; `federation_peer_cursor` = DynamoDB via the `CursorStore` protocol)
  - **§14** — observability enumeration (this phase first creates the inbox + outbound Lambdas + DLQs + DynamoDB cursor + anomaly alarms, so XIV is non-deferrable here)
- Living plan: `docs/superpowers/plans/2026-06-03-hsds-federation-core.md` → **## P3 — Push** and the **Roadmap P3 row**

## File-map

- `app/federation/outbound.py` — read new `federation_log`, build signed activities, deliver to peers' inboxes, per-peer push high-water mark, retry/backoff, DLQ
- `app/federation/ingest.py` — inbox router: verify against the **pinned** `federation_peer.public_key` (zero network I/O) → allow-list → `actor == attributedTo` → `(actor, sequence)` dedup + strictly-increasing → checkpoint consistency → budget → rate-limit → thin enqueuer
- `infra/stacks/federation_stack.py` — inbox Lambda (**own non-slim image**, mirrors `ppr-write-api`); outbound sender Lambda + DLQ; ingest SQS + DLQ; DynamoDB cursor (`CursorStore`)
- `infra/stacks/monitoring_stack.py` + `infra/tests/` — alarms + dashboard widgets + one assertion per resource class (Principle XIV)
- Tests (single-file via `./bouy exec app pytest`; full gate via `./bouy test`): inbox guard-chain rejection-reason tests, outbound sender + DLQ tests, peer-remove recovery test, anomaly-detector test, the **golden P3 journey** integration test, `infra/tests/` alarm-existence assertions

## Task checklist

- [ ] **Inbox verify/guard chain** (`app/federation/ingest.py`) implemented in the §6.5 order, with **one rejection-reason test each**, emitting the matching reject reason:
  - [ ] RFC 9421 transport signature against the **pinned** key (no network I/O; `keyId` host == actor DID host) → `federation_inbox_rejected_signature`
  - [ ] object signature (origin authenticity, independent of the delivering hop)
  - [ ] `actor ∈` allow-list → `federation_inbox_rejected_allowlist`
  - [ ] `actor == attributedTo` for `Update`/`Delete` → `federation_inbox_rejected_attribution`
  - [ ] `(actor, sequence)` strictly-increasing dedup (±300 s `created`/`expires`) → `federation_inbox_rejected_replay`
  - [ ] checkpoint consistency (stale/forked advertised checkpoint → reject + `federation_consistency_failed` alarm) → `federation_inbox_rejected_version`
  - [ ] per-peer budget (§11.3) → thin enqueuer → `202`
- [ ] **Outbound signed sender + DLQ** (`app/federation/outbound.py`): read `federation_log`, build RFC-9421-signed-body activities, deliver to peers' inboxes, per-peer push high-water mark, retry/backoff, failures to DLQ
- [ ] **Per-DID rate-limit** on both inbound and outbound paths
- [ ] **Peer-remove recovery (§11.4)**: on `peer-remove`, recompute confidence for every Location the removed DID corroborated (drop its votes) **and** flag/auto-revert canonical fields last written by that DID — modeled on `scripts/undo_dedup_run.py` (reversible, audited; honor the human-verified owner exemption so `verified_by ∈ {admin,source,claimed}` is never reverted)
- [ ] **Mass-anomaly alarms (§11.6/§11.11)**: per-peer mass `Delete`/`Update` anomaly detection → alarm; field-change anomaly (coordinate jump >2 km, contact/hours flip contradicting standing corroboration) → demote-and-flag + `federation_anomalous_field_change`
- [ ] **Full Principle-XIV enumeration, item-by-item** (copy design §14 verbatim into infra + `infra/tests/`, all routed to `pantry-pirate-radio-alerts-{env}`):
  - [ ] inbox Lambda → Errors + Throttles alarms
  - [ ] outbound sender Lambda → Errors + Throttles alarms
  - [ ] ingest SQS → DLQ-depth + queue-depth alarms
  - [ ] outbound DLQ → DLQ-depth alarm
  - [ ] DynamoDB cursor → throttle + system-error alarms
  - [ ] dashboard widgets for the above (`PantryPirateRadio/Federation/*`: inbox accept/reject by reason, push latency/failures, anomaly count)
  - [ ] **one `infra/tests/` assertion per resource class** (Lambda alarms, SQS DLQ-depth, DynamoDB throttle/system-error)
- [ ] **Docs**: update CLAUDE.md with the P3 structlog grep targets (`federation_inbox_rejected_*`, `federation_consistency_failed`, `federation_anomalous_field_change`) per Principle XIII
- [ ] **`./bouy test`** green (black + ruff + mypy + bandit + pytest)

## Acceptance criteria

The **golden P3 journey** integration test (one black-box `@pytest.mark.integration`, driven against the in-repo reference second node) is the literal phase gate:

- [ ] A signed push is **verified with NO outbound fetch** (pinned-key only; §11.1)
- [ ] The pushed record **dedups idempotently with the pull path** — a record delivered by both push and concurrent pull is processed exactly once (shared `(actor, sequence)` idempotency key)
- [ ] The inbox **rejects** bad signature, bad attribution, replay/out-of-order sequence, and a stale/forked (consistency) checkpoint — each with the matching `federation_inbox_rejected_*` reason
- [ ] **Peer-remove demonstrably reverts a poisoned field**: a field last-written by the removed DID is reverted and its corroboration votes dropped (confidence recomputed)
- [ ] **Alarms exist in `infra/tests/`** for every new Lambda/SQS/DynamoDB resource class, routed to `pantry-pirate-radio-alerts-{env}`
- [ ] `./bouy test` passes end-to-end

## Constitution touchpoints

- **Principle XIV — AWS observability (NON-NEGOTIABLE):** P3 is the phase that *first* introduces the inbox + outbound Lambdas, their DLQs, the ingest SQS, and the DynamoDB cursor — so their alarms + widgets + `infra/tests/` assertions ship **in this same phase**, not deferred (§14). This is the constitution-heavy core of the phase.
- **Principle XV — dual-env (NON-NEGOTIABLE):** the inbox is its **own non-slim Lambda → ingest SQS** (mirrors `ppr-write-api`); the slim read Lambda gains no Redis/LLM imports. Locally the inbox is an app-container route via the §6.5a enqueuer. Both-env behavior is tested; `FEDERATION_ENABLED` kill switch honored.
- **Principle XI — pipeline resilience / no silent loss:** outbound failures land in a DLQ with retry/backoff; inbox rejections are explicit and logged with reason; peer-remove recovery is reversible and audited (modeled on `scripts/undo_dedup_run.py`).
- (Also: Principle III red-first per task; Principle VI confidence recompute on revert; Principle XII structlog reasons.)

## Dependencies / blocked by

- **Hard-gate:** this phase is gated on the **P0.5 go/no-go memo** (see `blocked:hard-gate`). No P3 code ships before the gate clears.
- **P2 complete:** P3 reuses the **shared `(actor, sequence)` idempotency** key in the single `federation_peer_cursor` row and the **reconciler corrections** (§12.3 — `federated_node` origin-dedup, `ON CONFLICT` target, owner-guard, validator routing) landed in P2. Push without P2's idempotency + corrections would double-count.
- **External:** a partner accepting webhooks. This dependency is satisfied internally for the gate — **PPR-to-PPR push works via the in-repo reference node** (a minimal fixture peer serving `/export` + `state.txt` + signed `/inbox`), so the golden journey is self-contained.

## Out of scope

- `Announce` relay / outbound `Announce` emission, witness cosigning, and provenance-weighted/freshness-decayed corroboration → **P6**.
- The operator CLI (`./bouy federation peer-add/remove/list/status`), the PII heuristic + takedown path, the minimal `Flag`/dispute verb, the Lighthouse claim/verify corroboration tier, and the prioritized review queue → **P4** (P3 wires the recovery *mechanism* that `peer-remove` triggers; P4 ships the operator-facing command).
- VC trust, Regions/relay actors, version negotiation, GDPR redaction → P5–P7.

## Decomposition

Per the living-plan contract, this roadmap phase is **expanded into a bite-sized sibling plan at session start** (`./bouy` + subagent-driven or inline execution, red-first per task) before any code ships. The task checklist above is the **provisional** decomposition taken from the plan's P3 Tasks list and roadmap P3 row; the roadmap row + this issue are authoritative over older task text. No code ships ahead of its phase, and no P3 code ships before the P0.5 hard gate clears.

## Notes

- All examples use fictional data only (555- phone prefixes, `example.com` / `h.example` hosts) per Principle VII.
- Parent epic: **[EPIC] HSDS Federation in PPR Core**.
- Federation is core (`app/federation/`), on-by-default, with the `FEDERATION_ENABLED` kill switch.
- Docs live on branch `docs/hsds-federation-core-design` (PR #518, DRAFT); implementation begins on `feat/federation-p0-foundations` off `main`, with each phase branched in turn.

## Open decision (design §21 — settle in this phase)

- [ ] Decide whether the optional **`/federation/stream`** no-proofs JSON delta lane (Jetstream pattern; design §2 *Reserved* + §21 *Remaining open*) ships in P3 or is deferred until a consumer demands it. **Default per §2: reserved/named, not built — ship only on demand.**
````

### `P4` — P4 — Trust UX & PII

**kind:** `phase` · **parent:** `epic` · **milestone:** `P4` · **labels:** `federation`, `phase:P4`, `blocked:hard-gate`

````markdown
## Summary

P4 ships the **operator surface, PII minimums, and review-at-scale** for HSDS federation. It gives operators a documented `./bouy federation` flow to onboard/remove/list/inspect peers, adds an ingest-side PII heuristic that flags-not-suppresses (equity-aware), and stands up a takedown path that purges/redacts exports and emits a redaction `Delete` downstream. Per the v3 DELTA, P4 also pulls forward a minimal `Flag`/dispute verb so a refutation can un-serve a bad record at least as fast as corroboration serves one, wires the **existing Lighthouse claim/verify flow in as a corroboration tier** (consume it, do not build a parallel queue), and adds a **prioritized review queue** ranked by served-population-impact × uncertainty × staleness with auto-expiry.

Why it matters: federation is on-by-default in core. Without a human-grade operator surface and a refutation path at least as fast as the publish path, a single rogue or stale peer record harms vulnerable users every hour it is served. P4 is the trust-and-safety seam that makes federation safe to leave on.

## Design refs

- §6.7 — Trust / allow-list & onboarding (`federation_peer`, `./bouy federation peer-add/remove/list/status`, the review bar: both fingerprints + retention/archive policy + sample records).
- §6.1a — Recovery-key hierarchy: `peer-add` displays and pins **both** the day-to-day signing-key fingerprint **and** the offline recovery-key fingerprint, so a did:web domain takeover is detectable, not silent.
- §11.4 — Rogue/compromised peer recovery: `peer-remove` recomputes confidence dropping the removed DID's votes and reverts canonical fields last written by that DID (model: `scripts/undo_dedup_run.py`). Delivered in P3; P4 wires `peer-remove` to trigger it.
- §11.6 / §11.6a — Un-corroborated gating + equity floor: the Lighthouse claim/verify corroboration tier satisfies the §11.6 gate immediately; the PII heuristic flags-not-suppresses informal pantries (equity).
- §11.8 — PII amplification (Principle VII): personal-email-domain / non-business-phone heuristic flags rather than auto-publishes; takedown = peer-remove + purge/redact exported records + emit a redaction `Delete`; re-export makes PPR a processor of peers' PII (the peer-add review acknowledges this).
- §11.12 — Review at scale + fast refutation: prioritized (non-FIFO) queue reusing `pick_next_scraper_task.py`'s population weighting, with auto-expiry; Lighthouse claim/verify as a corroboration tier; minimal `Flag`/dispute verb pulled forward from P6 with mesh-wide retraction propagation and a published, instrumented **time-to-correct SLA**.
- Metrics namespace `PantryPirateRadio/Federation/*` (§ design §14): time-to-correct (§11.12 SLA), equity-caveat count, anomaly count.

## v3 DELTA (binding)

The roadmap P4 row + this DELTA are authoritative over any older task text. P4 additionally ships:

- **Minimal `Flag`/dispute verb** (pulled forward from P6): a refutation can un-serve a bad record **at least as fast as corroboration serves one**, with **mesh-wide retraction propagation** (downstream `Delete`/redirect) and a **published, instrumented time-to-correct SLA**. A wrong record harms every hour it is served; the network must retract at least as fast as it publishes.
- **Lighthouse claim/verify flow wired in as a corroboration tier**: an owner-claim or source-confirm **immediately satisfies the §11.6 serve gate**. **Consume the existing flow — do not invent a parallel queue.**
- **Prioritized review queue**: ranked by **served-population-impact × uncertainty × staleness**, reusing `pick_next_scraper_task.py`'s population weighting; **auto-expiry** so nothing silently sticks. Never FIFO.
- **Peer-add shows BOTH key fingerprints**: the day-to-day signing key fingerprint AND the offline recovery-key fingerprint (§6.1a).

## File-map

- `bouy` — add the `federation` command group (peer-add/remove/list/status), routed to the CLI module.
- `app/federation/cli.py` (create) — `./bouy federation` implementation: peer-add fetches discovery via the hardened egress helper (`app/federation/fetch.py`, §11.1), displays both fingerprints + retention/archive policy + a sample of recent records, approves to an allow-list row; peer-remove triggers the §11.4 recovery path.
- `app/federation/pii.py` (create) — ingest-side PII heuristic (personal-email-domain / non-business-phone) → flag-not-suppress.
- Flag/dispute verb, prioritized review queue, Lighthouse corroboration-tier wiring, and takedown path land alongside the above (exact module boundaries fixed at decomposition; the `Flag` verb extends `app/federation/activities.py`'s verb models, the queue reuses `pick_next_scraper_task.py`'s weighting, and the takedown path composes `peer-remove` + export purge/redact + redaction `Delete` emission).
- Tests: red-first per task (Principle III); both-env coverage and the slim-import test (Principle XV); `infra/tests/` assertions for any new AWS resources / alarms (Principle XIV, including the time-to-correct SLA metric).

## Task checklist

- [ ] `./bouy federation peer-add <did>` — hardened discovery fetch via the §11.1 egress helper; display **signing AND recovery key fingerprints** (§6.1a) + retention/archive policy + **a sample of recent records** (the §11.7 review bar); approve → allow-list row.
- [ ] `./bouy federation peer-remove <did>` — triggers the P3 §11.4 recovery (recompute confidence dropping removed DID's votes + revert fields last-written by that DID).
- [ ] `./bouy federation peer-list` — list configured peers.
- [ ] `./bouy federation status` — peer/cursor/checkpoint status.
- [ ] **PII ingest heuristic** (`app/federation/pii.py`): personal-email-domain / non-business-phone → **flag, not auto-publish**; for informal pantries **flag rather than auto-suppress** (§11.6a equity).
- [ ] **Takedown path**: `peer-remove` + **purge/redact exported records** + **emit a redaction `Delete`** downstream.
- [ ] **Minimal `Flag`/dispute verb**: un-serve a bad record at least as fast as corroboration serves one; **mesh-wide retraction propagation**; **published, instrumented time-to-correct SLA** metric.
- [ ] **Lighthouse claim/verify as a corroboration tier**: owner-claim / source-confirm immediately satisfies the §11.6 gate; consume the existing flow (no parallel queue).
- [ ] **Prioritized review queue**: served-population-impact × uncertainty × staleness (reuse `pick_next_scraper_task.py` weighting); **auto-expiry**.
- [ ] Docs (CLAUDE.md + the federation operator runbook updated alongside the code, Principle XIII).
- [ ] `./bouy test` (black + ruff + mypy + bandit + pytest all green, Principle X).

## Acceptance criteria

From the plan's **P4 acceptance** block:

- [ ] Peer onboarding is a **documented `bouy` flow**.
- [ ] A **PII-flagged record is held, not published**.
- [ ] A **takedown emits a redaction and purges exports**.

## Constitution touchpoints

- **VII (Privacy and Security)** — the PII heuristic and takedown/redaction path are the core privacy seam; re-export makes PPR a processor of peers' PII (§11.8). The peer-add review bar acknowledges this. bandit must pass.
- **VI (Data Quality for Vulnerable Populations, NON-NEGOTIABLE)** — equity-aware flagging (flag-not-suppress for informal pantries, §11.6a); the prioritized review queue weights by served-population-impact so the hardest-to-reach communities are not buried; the `Flag` verb + time-to-correct SLA bound the harm window of a wrong served record.
- **I (Docker-First, NON-NEGOTIABLE)** — the entire operator surface is `./bouy federation …`; all dev/test via bouy, no local Python/poetry/docker-compose.
- (Also: III TDD red-first per task; X consistent quality gates; XIII docs updated with code.)

## Dependencies / blocked by

- **Hard gate**: blocked on the P0.5 go/no-go memo (all P1–P7 phases are gated on it). Label `blocked:hard-gate`.
- **P3 (Push)** — supplies the §11.4 `peer-remove` recovery path that `./bouy federation peer-remove` triggers.
- **P2 (Pull ingest)** — supplies the §11.6 corroboration/serve gate that the Lighthouse claim/verify corroboration tier and the `Flag` verb act on.

## Out of scope

- The full recovery-key ceremony (P7) — P4 only surfaces/pins the recovery-key fingerprint per §6.1a.
- VC trust / `verified_by='network'` and replacing `fano_allowlist.tsv` (P5).
- Witness-cosigning mesh, Region/Group actors, `Announce` relay, and provenance-weighted/freshness-decayed corroboration (P6).
- Full GDPR per-field redaction (P7) — P4 ships the §11.8 v1 PII minimums + takedown/redaction-`Delete`, not full per-field GDPR.

## Decomposition

This phase is **not yet decomposed into executable tasks**. Per the living-plan contract, P4 is expanded into a bite-sized sibling plan **at session start**, before any code is written, with red-first tests per task. The task checklist above is the **provisional** sub-task list drawn from the roadmap P4 row + the v3 DELTA block (which are authoritative over older task text). Reproduce the §11.12 review-at-scale model, the §6.1a both-fingerprints rule, and the §11.8 flag-not-suppress + takedown semantics verbatim into the decomposed plan.

## Links

- Design of record: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md` (§6.1a, §6.7, §11.4, §11.6/§11.6a, §11.8, §11.12).
- Implementation plan: `docs/superpowers/plans/2026-06-03-hsds-federation-core.md` (## P4 — Trust UX & PII; Roadmap P4 row).
- Constitution: `constitution.md` (Principles I, VI, VII).
- Parent epic: [EPIC] HSDS Federation in PPR Core (ref `epic`).
````

### `P5` — P5 — VC trust

**kind:** `phase` · **parent:** `epic` · **milestone:** `P5` · **labels:** `federation`, `phase:P5`, `blocked:hard-gate`

````markdown
## Summary

P5 turns network membership into a *verifiable* trust signal: a new `Verify` verb plus Verifiable-Credential (VC) verification at the PTF FANO gate lets a location be promoted to `verified_by='network'` when its origin presents a valid Feeding America FANO credential. This **replaces the curated `app/api/v1/partners/ptf/fano_allowlist.tsv`** scraper allowlist with cryptographic proof of affiliation, so FANO enrichment stops depending on a hand-maintained list of trusted scraper names. This phase matters because it closes the gap between "we believe this source is a FA affiliate" (allowlist) and "this source proved it" (VC), making the FANO surface tamper-evident and self-service for credentialed issuers.

> **DEFERRED — needs an external issuer (Feeding America).** This phase cannot be executed until an issuer (FA) is actually issuing FANO VCs. It is on the roadmap as designed-now interface, deferred at build time. See design §3 (v1 defers: `Verify`+VCs, §17 P5) and §17 P5.

## Design refs

- Design of record: [docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md](docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md)
  - §17 P5 (Rollout roadmap — "P5 VC trust *(deferred)*: `Verify`, VC verification, `verified_by='network'`; replaces `fano_allowlist.tsv`. External dep: an issuer (FA)")
  - §3 (v1 defers `Verify`+VCs with a designed-now interface)
  - §6 / line 133 (`verified_by='network'` reserved at P5; `caller_context.source_type` += `federated_*`)
  - §19 Glossary, §20 interop tiers, §21 decisions (substrate + corroboration context)
- Living plan: [docs/superpowers/plans/2026-06-03-hsds-federation-core.md](docs/superpowers/plans/2026-06-03-hsds-federation-core.md) → "## P5–P7 (roadmap only — see design §17)"
- Parent epic: [EPIC] HSDS Federation in PPR Core (`ref: epic`)

Authoritative-text note: the §17 roadmap row and the plan's P5 line are authoritative over any older task text. Roadmap row + plan: *FA issues a FANO VC → `Verify` → `verified_by='network'`, replacing `fano_allowlist.tsv`.*

## Scope / deliverables

- [ ] **`Verify` verb** — define and implement the federation `Verify` activity (verb) that carries/references a Verifiable Credential asserting FA / FANO affiliation for an origin or location.
- [ ] **VC verification at the PTF FANO gate** — verify a presented Feeding America FANO Verifiable Credential at the existing PTF FANO enrichment gate (the gate that today emits the `feeding_america_food_bank` block + `affiliations: ["FANO"]`).
- [ ] **`verified_by='network'`** — on successful VC verification, promote the matched location to `verified_by='network'` (the reserved value from design line 133). Wire `verified_by='network'` into scoring/serving so it behaves as a network-trust tier.
- [ ] **Retire `fano_allowlist.tsv`** — replace the curated scraper allowlist at `app/api/v1/partners/ptf/fano_allowlist.tsv` with VC-driven gating; remove the allowlist as the source of truth for FANO add-on data once VC verification covers the same surface.

## Files

- `app/federation/vc.py` (create) — VC verification logic and the `Verify` verb handling.
- `app/api/v1/partners/ptf/` (modify) — replace the `fano_allowlist.tsv` gate with VC-driven FANO gating; this is the PTF endpoint package that currently houses `fano_allowlist.tsv`, `fano_*` query CTE, and the transformer that emits the FANO block.
- Tests (create) — `tests/test_federation/test_vc.py` (or sibling): a valid FA VC promotes a location to `verified_by='network'`; an absent/invalid VC does not.

*(Exact create/modify/test paths are finalized in the bite-sized P5 sibling plan at session start — see Decomposition.)*

## Acceptance criteria

- [ ] A **valid Feeding America FANO Verifiable Credential** presented for a location causes that location to be promoted to `verified_by='network'`.
- [ ] FANO enrichment (the `feeding_america_food_bank` block / `affiliations: ["FANO"]`) is driven by VC verification rather than by membership in `fano_allowlist.tsv`.
- [ ] An invalid, expired, or absent VC does **not** promote a location to `verified_by='network'` (no silent trust escalation).
- [ ] `app/api/v1/partners/ptf/fano_allowlist.tsv` is retired as the FANO gate's source of truth.

## Constitution touchpoints

- **II HSDS (NON-NEGOTIABLE)** — `verified_by='network'` and the FANO enrichment surface stay HSDS-conformant; no new free-form fields outside the Pydantic models.
- **III TDD (NON-NEGOTIABLE)** — red-first tests for VC verify and the promotion path before implementation.
- **VI Data-quality (NON-NEGOTIABLE)** — VC verification is a *trust escalation*; only cryptographically valid credentials may bump confidence/`verified_by`. Invalid VCs must never promote, and `verified_by='network'` must not bypass existing quality gates.
- **VII Privacy** — VC payloads carry affiliation, not PII; no PII introduced into the FANO surface.
- **XV Dual-env** — VC verification must behave consistently across local Docker and AWS, with the local path degrading cleanly when no issuer is configured.
- **X Gates** — black + ruff + mypy + bandit + pytest must pass.

*(`constitution` label not applied: this phase is trust-tier work, not a NON-NEGOTIABLE-heavy buildout like P0/P1/P2 — the binding gates are still enumerated above and re-checked in the P5 sibling plan.)*

## Dependencies / blocked by

- **Blocked (hard gate):** gated on the P0.5 de-risking spike go/no-go memo (the verifiable substrate must be proven before any phase past P0 builds on it) — see `phase:P0.5`. This is the `blocked:hard-gate` dependency shared by all P1–P7 phases.
- **External issuer required (DEFERRED):** an issuer — Feeding America — must actually **issue a FANO Verifiable Credential** before this phase can be executed. Roadmap external dep: *an issuer (FA)*.
- **P2 corroboration in place:** P5 builds on the `verified_by` / corroboration trust model established by P2 pull-ingest (the §12 corrections + origin-deduped corroboration). VC-driven `verified_by='network'` slots in as a trust tier above corroboration; it must compose with, not bypass, the P2 corroboration logic.
- Builds on the federation identity/signing substrate from P0 (DID + RFC 9421) and the FANO gate that exists today in `app/api/v1/partners/ptf/`.

## Out of scope

- Issuing VCs (PPR is a verifier, not the FA issuer).
- Witness mesh, Region/Group actors, and `Announce` relay (P6).
- `Move`, recovery-key ceremony, RBSR anti-entropy, public-log anchoring, full GDPR redaction (P7).
- Any non-FANO credential type (P5 targets the FA FANO gate specifically).

## Decomposition

P5 is **roadmap-only** in the living plan ("## P5–P7 (roadmap only — see design §17)"). Per the living-plan contract, this phase is expanded into a bite-sized sibling plan at session start before execution begins; the Scope checklist above is the **provisional** sub-task list derived from the §17 P5 roadmap row and the plan's P5 line, and the §17 roadmap row + plan text are authoritative over any older task text. Because this phase is **DEFERRED pending an external FA issuer**, decomposition and execution do not begin until that dependency is satisfied (and the P0.5 hard gate has cleared).

## Notes

- The reserved value `verified_by='network'` is already documented as reserved-at-P5 in the design (line 133); P5 is where it goes live.
- The FANO gate today (per CLAUDE.md) gates on `fano_allowlist.tsv` of curated scrapers and emits `feeding_america_food_bank` + `affiliations: ["FANO"]` when a location's ZIP matches `feeding_america_zip_coverage`. P5 swaps the *trust* source from allowlist membership to a verified credential; the ZIP-coverage / enrichment shape is unchanged.
- Any example credentials/issuers in tests or docs must use fictional hosts (e.g. `issuer.example`/`h.example`) and `555-` phone prefixes per Principle VII.

````

### `P6` — P6 — Witness mesh + Regions/relay

**kind:** `phase` · **parent:** `epic` · **milestone:** `P6` · **labels:** `federation`, `phase:P6`, `blocked:hard-gate`

````markdown
## Summary

P6 turns the verifiable substrate from a set of bilaterally-trusted publish/pull links into a **witness mesh**: allow-listed peers (plus HAARRRvest, recast from privileged relay to the network's first, lowest-trust witness) cosign each other's signed checkpoints, so a node showing different histories to different consumers (split-view / equivocation) is detectable **mesh-wide**, not just bilaterally. It also adds FEP-1b12 Region/Group actors and an `Announce` relay (object signatures already carry origin natively across hops), and promotes the §12.2 provenance-weighted, freshness-decayed corroboration to a first-class served field — the "independently confirmed by N orgs in the last M days" trust signal surfaced on Beacon/PTF. The checkpoint format is witness-compatible from day one (P1), so this is an extension, not a flag-day rewrite.

**Status: COMMITTED (format fixed in v1) — needs 2+ peers.** The witness format was fixed in the v1 substrate (design §6.2c); execution requires 2+ live peers to act as mutual witnesses.

## Design refs

- [Design of record](../docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md) §6.2c (witness cosigning — committed later phase, format fixed now), §12.2 (provenance-weighted, freshness-decayed corroboration + the surfaced confirmation signal), §17 P6 (roadmap row).
- [Implementation plan](../docs/superpowers/plans/2026-06-03-hsds-federation-core.md) "P5–P7" P6 portion + roadmap §17 P6 row.
- Parent epic: [EPIC] HSDS Federation in PPR Core (ref `epic`).

## Scope / deliverables

- [ ] **Witness cosigning** (C2SP tlog-witness / tlog-cosignature): each allow-listed peer cosigns the largest **consistent** checkpoint it has observed for a peer.
  - [ ] Allow-list peers act as **mutual witnesses**.
  - [ ] **HAARRRvest recast** from privileged relay to the network's **first, lowest-trust witness** (no special status — just the first cosigner).
  - [ ] Split-view / equivocation (different histories to different consumers) becomes detectable **mesh-wide**, not only bilaterally.
- [ ] **FEP-1b12 Region/Group actors**: a peer can `Follow` a region/group actor.
- [ ] **`Announce` relay**: object signatures make origin survive hops natively (a relayed object's `proof` still attributes origin A regardless of who announced it).
- [ ] **Outbound `Announce` emission**.
- [ ] **§12.2 provenance-weighted, freshness-decayed corroboration**: freshness multiplier (full weight ≤30 d, decaying to a floor by ~180 d) + per-peer trust tier on `federation_peer` (own-scrapers / human-verification 1.0; pure aggregators 0.5), applied before the corroboration ladder.
- [ ] **Served confirmation signal**: promote "independently confirmed by N orgs in the last M days" to a first-class served field on the Location aggregate and surface it on **Beacon/PTF** (optional Profile properties).

## Files

- `app/federation/witness.py` (new) — witness cosigning / checkpoint cosignature verification.
- `app/federation/regions.py` (new) — FEP-1b12 Region/Group actors, `Announce` relay + outbound emission.
- HAARRRvest — recast as the first, lowest-trust witness participant.
- (Provenance/freshness weighting touches the §12.3 reconciler corroboration path and the Beacon/PTF served surfaces; exact module list is set when the phase is expanded — see Decomposition.)

## Acceptance criteria

- [ ] Split-view / equivocation is **detected mesh-wide** (a node showing divergent histories is caught by the witness cosignatures, not just by a single bilateral consistency check).
- [ ] A peer **`Follow`s a region** (Region/Group actor) and receives its relayed activities.
- [ ] The **confirmation signal is served** — "independently confirmed by N orgs in the last M days" appears as a first-class field on the aggregate and on the Beacon/PTF surfaces.

## Constitution touchpoints

- **II HSDS (NON-NEGOTIABLE):** the served confirmation signal rides as optional Profile properties on the HSDS-typed aggregate; relayed/announced objects remain HSDS-typed.
- **III TDD (NON-NEGOTIABLE):** red-first per the living-plan contract; expansion tasks open with a concrete failing test (`run; expect fail`) before implementation.
- **VI Data quality (NON-NEGOTIABLE):** provenance-weighted, freshness-decayed corroboration is the good-faith-staleness answer (§11.11); origin-dedup (§12.1) and confidence scoring continue to apply to relayed/announced records.
- **XII/XIV Observability:** witness consistency failures alarm as possible equivocation (`federation_consistency_failed`, design §14); the phase adds its structlog grep targets to CLAUDE.md (Principle XIII) and any new Lambda/SQS/DynamoDB ships its alarms + dashboard widgets + `infra/tests/` assertions in-phase (XIV — not deferrable past introduction).
- **XV Dual-env (NON-NEGOTIABLE):** witness participation and the served signal work in both Docker (`./bouy up`) and AWS Lambda paths.

## Dependencies / blocked by

- **Hard gate:** blocked on the **P0.5 go/no-go memo** (the de-risking spike gates everything downstream of P0). `blocked:hard-gate`.
- **2+ live peers** required (this is the gating external dependency for the witness mesh — peers must exist to act as mutual witnesses).
- **P3 Push** (signed inbox + consistency verify + peer-remove recovery) — relay/announce builds on the push substrate.
- **P2 corroboration** (origin-dedup + the §12.3 reconciler corrections + CvRDT property test) — the provenance/freshness weighting evolves the §12.1 origin-deduped corroboration.

## Open decision

- [ ] **Witness-set composition + minimum cosigner count** — decide **here** (deferred from design §21 "Remaining open" → "decide at the phase that needs them"). Determines which allow-listed peers participate as witnesses and how many cosignatures constitute mesh-wide equivocation detection.

## Decomposition

Per the living-plan contract (plan §"How this living plan is structured"), P6 is roadmapped at task granularity only. It is **expanded into its own bite-sized sibling plan at the start of its session** (e.g. `2026-..-hsds-federation-p6-witness-mesh.md`); writing exact code now would be stale false-precision against session-N signatures. The design doc + roadmap row carry the binding decisions; bite-sized code is written just-in-time against live signatures. **Red-first is inherited verbatim on expansion** — every implementation task opens with a concrete failing test + a `run; expect fail` step in P0's format. The roadmap row + the v3 DELTA / committed-status note are authoritative over any older task text.

Provisional sub-task checklist (from the §17 P6 roadmap row, to be refined on expansion):
- [ ] Witness cosigning (C2SP tlog-witness; allow-list peers as mutual witnesses; HAARRRvest as first/lowest-trust witness).
- [ ] FEP-1b12 Region/Group actors.
- [ ] `Announce` relay (object signatures make origin survive hops natively).
- [ ] Outbound `Announce` emission.
- [ ] §12.2 provenance/freshness weighting + the surfaced confirmation signal.

## Out of scope

- RBSR anti-entropy (Negentropy) for divergence repair, optional public-log anchoring (Sigsum/Rekor), full version negotiation, `Move`, the recovery-key ceremony, full GDPR per-field redaction, and a non-PPR reference implementation — all **P7 (hardening, partner-driven)**.
- `Verify` / Verifiable Credentials and `verified_by='network'` (replacing `fano_allowlist.tsv`) — **P5 (deferred, needs an issuer)**.

## Notes

- HAARRRvest's recast (privileged relay → first, lowest-trust witness) is the conceptual through-line: the network is being built for the 3+-mutually-distrusting-nodes world, so no single participant — including the project's own publisher — retains privileged trust.
- Fictional data only in any fixtures/examples (555- phone prefixes, `example.com` / `h.example` hosts) per Principle VII.
````

### `P7` — P7 — Hardening

**kind:** `phase` · **parent:** `epic` · **milestone:** `P7` · **labels:** `federation`, `phase:P7`, `blocked:hard-gate`

````markdown
## Summary

**DEFERRED — partner-driven.** P7 is the final hardening phase: it closes the remaining robustness and true-implementation-independence gaps that v1 deliberately deferred (each behind a designed-now interface). Its headline deliverable is the one that actually proves the bet — a **non-PPR reference implementation** that interoperates over HSDS-FX, demonstrating the wire spec is independent of `app/`. The rest is divergence-repair, integrity anchoring, full version negotiation, the `Move` verb, the complete recovery-key ceremony, and full GDPR per-field redaction. These have no fixed schedule; they unlock as real partners and mixed-version peers create the need.

This is a roadmap phase, not yet decomposed — see the **Decomposition** note below.

## Design refs

- Roadmap: design [§17 P7 row](docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md) — *"RBSR anti-entropy (Negentropy) for divergence repair; optional public-log anchoring (Sigsum/Rekor); full version negotiation; `Move`; recovery-key ceremony; full GDPR redaction; a non-PPR reference implementation validating HSDS-FX. — partner-driven"*
- §2 Non-goals — the explicit **"v1 defers"** list that P7 finally addresses: witness mesh (→ P6), RBSR anti-entropy (§17 P7), public-log anchoring (§17 P7), full HSDS version negotiation (**§8.4 inoculates now**), full GDPR per-field redaction (the §11.8 v1 PII minimums already ship earlier).
- §8.4 Version handling (fracture inoculation) — P0/P1 only *inoculate* via two binding rules (set-membership `@context` match against the advertised supported-versions list; ignore-unknown-fields / `ext` namespace; the only hard failure is a major-version mismatch → `422` + `federation_inbox_rejected_version`). **Full content negotiation is explicitly deferred to P7.**
- §6.1a Recovery-key hierarchy — the schema + verify-side priority check ship in v1 (P0); the **full recovery ceremony** is the later-phase work landed here.
- §8.5 / §7 Spec extraction & stewardship — HSDS-FX is extracted at P1 and the in-repo reference second node "doubles as the P7 clone-able example" (design §10); P7's non-PPR node is the real interop proof of that extraction.
- Plan: [`## P5–P7` (roadmap only)](docs/superpowers/plans/2026-06-03-hsds-federation-core.md) — *"P7 hardening (partner-driven): RBSR anti-entropy (Negentropy), optional public-log anchoring (Sigsum/Rekor), full version negotiation, `Move`, the recovery-key ceremony, full GDPR redaction, and a non-PPR reference implementation validating HSDS-FX."*

Source docs:
- Design of record: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`
- Living implementation plan: `docs/superpowers/plans/2026-06-03-hsds-federation-core.md`
- Parent epic: [EPIC] HSDS Federation in PPR Core (ref `epic`)

## Scope / deliverables

The roadmap-level deliverables for this phase (provisional sub-task checklist — see Decomposition):

- [ ] **RBSR anti-entropy (Negentropy) for divergence repair** — efficient range-based set reconciliation so two peers whose logs have diverged can identify and repair the missing/conflicting objects without re-shipping the whole log.
- [ ] **Optional public-log anchoring (Sigsum / Rekor)** — anchor signed checkpoints into an external transparency log so checkpoint history gains a third-party tamper-evidence backstop beyond the witness-cosigning mesh (P6). Optional, per-node opt-in.
- [ ] **Full HSDS version negotiation** — the complete content-negotiation layer on top of the §8.4 inoculation (set-membership `@context`, ignore-unknown-fields, `ext` namespace, major-version-only hard failure) that P0/P1 ship. P7 turns inoculation into active negotiation so a mixed-version mesh can downgrade/upgrade payloads rather than only refusing the major-mismatch case.
- [ ] **`Move` verb** — the activity verb for an org relocating its canonical identity/endpoint (the deferred ActivityStreams `Move`), so a node migration is a propagated, verifiable event rather than a silent re-discovery.
- [ ] **Full recovery-key ceremony (§6.1a)** — the complete offline recovery / key-rotation / repudiation ceremony built on the v1 schema + verify-side priority check, including the bounded-window repudiation flow and checkpoint-sequence-tied compromise revocation.
- [ ] **Full GDPR per-field redaction** — per-field redaction beyond the §11.8 v1 PII minimums (which ship earlier), so a takedown can scrub specific fields across the verifiable log while preserving log integrity/proofs.
- [ ] **NON-PPR reference implementation validating HSDS-FX (the real interop proof)** — a clone-able node built without reference to `app/`, ideally in a non-Python stack (e.g. TS / Cloudflare Worker), that publishes `/export` + `state.txt` + a signed `/inbox` and ingests a PPR peer, proving HSDS-FX is genuinely implementation-independent. Builds on the in-repo reference second node (P1) per design §10/§8.5.

## Acceptance criteria

- [ ] **Mixed-version peers interoperate** — a v1 node and a higher-version node successfully exchange and ingest activities via full version negotiation (not merely the §8.4 major-mismatch refusal); unknown fields are tolerated and round-tripped.
- [ ] **A TS/Worker (non-Python, non-PPR) node proves implementation-independence** — the non-PPR reference node interoperates with a PPR node over HSDS-FX end-to-end (publish → fetch → proof-verify → ingest), validating the spec carries no hidden `app/` dependency.
- [ ] Divergence between two peers is detected and repaired via RBSR anti-entropy without full-log re-transfer.
- [ ] (Optional, per-node) Signed checkpoints are anchored into an external transparency log and the anchor is independently verifiable.
- [ ] A `Move` is published, propagated, and verified end-to-end; peers re-point to the moved identity.
- [ ] The full recovery-key ceremony rotates/repudiates a compromised signing key per the §6.1a priority + bounded-window rules, with compromise-revocation tied to the checkpoint sequence.
- [ ] Per-field GDPR redaction scrubs targeted fields across the log while leaving inclusion/consistency proofs verifiable.

## Constitution touchpoints

- **II HSDS (NON-NEGOTIABLE)** — HSDS-FX objects continue to validate against unmodified HSDS Pydantic models; the non-PPR node must conform to the same schema; version negotiation pins the 3.2 line per the Profile.
- **III TDD (NON-NEGOTIABLE)** — red-first inherited verbatim on expansion (see Decomposition); every implementation task opens with a concrete failing test.
- **VII Privacy (NON-NEGOTIABLE)** — full GDPR per-field redaction extends the §11.8 v1 PII minimums; fictional data only in fixtures/examples (555- prefixes, example.com / h.example hosts).
- **X Quality gates (NON-NEGOTIABLE)** — single-file iteration via `./bouy exec app pytest …`; mandatory pre-PR `./bouy test` (black + ruff + mypy + bandit + pytest) satisfies III/X.
- **IX File-size/complexity** — new `app/federation/` modules stay ≤600 lines / cyclomatic ≤15 by construction.
- **XIV AWS observability** — anchoring, anti-entropy, and recovery-ceremony paths emit structured events / metrics consistent with the federation enumeration established in earlier phases.
- **XV Dual-env** — any new behavior must hold in both local Docker and AWS (or degrade cleanly per the dual-env exemption clause).

## Dependencies / blocked by

- **Hard gate:** blocked on the **P0.5 go/no-go memo** (the de-risking spike must clear before any P1–P7 work begins). This issue carries `blocked:hard-gate`.
- **P6 (Witness mesh + Regions/relay)** — the witness-cosigning mesh is the prerequisite integrity layer; public-log anchoring and mesh-wide divergence repair build on it.
- **Partner-driven** — there is no fixed schedule. P7 deliverables unlock as real partners, mixed-version peers, and migration/recovery events create the need. The non-PPR reference node depends on the HSDS-FX spec extraction + fixtures/conformance suite delivered at P1.

## Out of scope

- The §8.4 version *inoculation* rules (set-membership `@context`, ignore-unknown-fields, major-mismatch-only hard failure) — those ship at P0/P1, not here; P7 only adds full negotiation on top.
- The witness-cosigning mesh, Region/Group actors, `Announce` relay, and provenance-weighted corroboration — those are P6.
- The v1 PII minimums (§11.8) and the `Flag`/takedown UX — delivered at P4; P7 only adds full per-field GDPR redaction.
- CRDT/vector-clock machinery beyond §12.1's CvRDT formalization; JSON-LD context expansion; client-to-server protocol; transactional offer lifecycle (all permanent non-goals, §2).

## Decomposition

Per the living-plan contract, P7 is roadmapped at task granularity only and is **expanded into its own bite-sized sibling plan at the start of its session** (e.g. `2026-..-hsds-federation-p7-hardening.md`) against live signatures — writing exact code for partner-driven, far-future work now would produce stale false-precision. The design doc + the §17 roadmap row carry the binding decisions; bite-sized code is written just-in-time.

**Red-first is inherited verbatim on expansion:** when this section is expanded into bite-sized tasks, every implementation task MUST open with a concrete failing test + a `run; expect fail` step in P0's format (Principle III/X).

The **Scope / deliverables** checklist above is the provisional sub-task list, taken directly from the §17 P7 roadmap row and the plan's `## P5–P7` P7 entry. The roadmap row is authoritative over any older task text.

## Notes

- The non-PPR reference implementation is the *real* interop proof of the whole federation bet — HSDS-FX (§8.5) is extracted impl-first at P1, with the in-repo reference second node explicitly designed to double as the P7 clone-able example. P7 is where "the spec is implementation-independent" stops being an assertion and becomes a passing cross-stack test.
- `Move`, RBSR anti-entropy, and public-log anchoring are all named in §2 as deferred with a designed-now interface — P7 builds the implementations against those reserved seams, not net-new design.
````

### `P0.1` — P0.1 — Federation config + package skeleton

**kind:** `task` · **parent:** `P0` · **milestone:** `P0` · **labels:** `federation`, `phase:P0`, `ready`

````markdown
## Summary
Add the `app/federation/` package skeleton and the federation `Settings` field block (including the on-by-default `FEDERATION_ENABLED` kill switch) so every later P0 task has a config surface and an import root. This is the first executable task of P0 Foundations and has zero external dependencies.

## Design refs
- §6 (component module layout under `app/federation/`)
- §6.2d / §17 (the `FEDERATION_ENABLED` kill switch — on by default, driver 3)
- §8.3 (`FEDERATION_DATE_SKEW_SECONDS` = ±300 s replay window)
- §11.3 (`FEDERATION_INGEST_MAX_RECORDS_PER_PEER_PER_DAY` per-peer budget)

## Files
- Create: `app/federation/__init__.py`
- Modify: `app/core/config.py` (add a new `Settings` field block **before** the `build_database_url_from_components` model_validator, ~line 250 — NOTE: the Validator block does not end at ~line 137; Validation-Rules + Enrichment settings follow it, so insert just before the model_validator)
- Test: `tests/test_federation/test_config.py`

## TDD steps
- [ ] **Step 1 — Write the failing test** at `tests/test_federation/test_config.py`:

```python
# tests/test_federation/test_config.py
from app.core.config import Settings


def test_federation_settings_have_safe_defaults():
    s = Settings()
    assert s.FEDERATION_ENABLED is True            # on by default (driver 3)
    assert s.FEDERATION_DATE_SKEW_SECONDS == 300   # §8.3 replay window
    assert s.FEDERATION_RETENTION_DAYS == 365       # OPR SLA
    assert s.FEDERATION_INGEST_MAX_RECORDS_PER_PEER_PER_DAY > 0  # §11.3 budget
    assert s.FEDERATION_DID is None or s.FEDERATION_DID.startswith(("did:web:", "https://"))
```

- [ ] **Step 2 — Run it; expect fail.** `./bouy exec app pytest tests/test_federation/test_config.py -v` → FAIL (`AttributeError: 'Settings' object has no attribute 'FEDERATION_ENABLED'`).
- [ ] **Step 3 — Implement minimal config.** Add this field block inside `class Settings` (before the `build_database_url` model_validator):

```python
# app/core/config.py — new field block inside class Settings
    # Federation Settings (HSDS federation core)
    FEDERATION_ENABLED: bool = True
    FEDERATION_DID: str | None = None            # did:web:<domain> for this node; None disables publish identity
    FEDERATION_SIGNING_KEY: str | None = None    # Ed25519 private key (PEM/base64); secret — never committed
    FEDERATION_RETENTION_DAYS: int = Field(default=365, ge=1)
    FEDERATION_DATE_SKEW_SECONDS: int = Field(default=300, ge=1)
    FEDERATION_INGEST_MAX_RECORDS_PER_PEER_PER_DAY: int = Field(default=50_000, ge=1)
    FEDERATION_INGEST_MAX_LLM_JOBS_PER_PEER_PER_DAY: int = Field(default=50_000, ge=1)
    FEDERATION_EXPORT_PAGE_SIZE: int = Field(default=1000, ge=1, le=10_000)
```

```python
# app/federation/__init__.py
"""HSDS federation core. See docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md."""
```

- [ ] **Step 4 — Run; expect pass.** `./bouy exec app pytest tests/test_federation/test_config.py -v` → PASS.
- [ ] **Step 5 — Commit:**

```bash
git add app/federation/__init__.py app/core/config.py tests/test_federation/
git commit -m "feat(federation): add federation config settings and package skeleton"
```

## Acceptance
- [ ] `tests/test_federation/test_config.py::test_federation_settings_have_safe_defaults` passes.
- [ ] `Settings()` exposes all eight federation fields with the documented defaults (`FEDERATION_ENABLED` True, skew 300, retention 365, per-peer budgets > 0, export page size bounded 1–10_000).
- [ ] `app/federation/__init__.py` is importable as a package root.
- [ ] Secrets (`FEDERATION_SIGNING_KEY`) remain env/Secrets-Manager only — never committed (Principle VII).

## Constitution touchpoints
- III (TDD red-first — test before config field).
- VII (secret signing key never committed; fictional test data only).
- IX (all new code under `app/federation/`, files ≤600 lines).

## Dependencies / blocked by
- Parent epic: [EPIC] HSDS Federation in PPR Core.
- Parent phase: P0 — Foundations.
- No upstream task dependency (first P0 task; zero external deps).

## Notes
- Branch: implementation starts on `feat/federation-p0-foundations` off `main` (the design + plan live on `docs/hsds-federation-core-design`, PR #518 DRAFT).
- Source of truth: design [`docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`](docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md); plan [`docs/superpowers/plans/2026-06-03-hsds-federation-core.md`](docs/superpowers/plans/2026-06-03-hsds-federation-core.md) Task 0.1.
- Per-task run uses `./bouy exec app pytest <path> -v` (single-file selection; `./bouy test --pytest` does not select files well — owner practice). Pre-PR full gate `./bouy test` runs at Task 0.9.

## Out of scope
- Wiring the kill switch at hook sites (no-op behavior lands in P1).
- Any consumer of these settings (signing, discovery, fetch) — separate P0 tasks.
````

### `P0.2` — P0.2 — SSRF-hardened egress helper (§11.1)

**kind:** `task` · **parent:** `P0` · **milestone:** `P0` · **labels:** `federation`, `phase:P0`, `ready`

````markdown
## Summary
Provide the single hardened egress helper through which ALL federation outbound HTTP must flow, blocking internal/IMDS/CGNAT IPs and non-HTTPS URLs before any peer fetch happens. This is an §11.1 blocker: every later discovery fetch, pull, and onboarding call routes through it. IP-range validation is the tested core in P0; the DNS-rebind connect-pin and the streaming hard byte-cap are deferred together to P2/P3 (each with its own test).

## Design refs
- §11.1 (hardened egress helper — pinned key, no attacker-directed I/O, the single outbound HTTP chokepoint)
- §6.1 (all discovery fetches use the §11.1 hardened helper)

## Files
- Create: `app/federation/fetch.py`
- Test: `tests/test_federation/test_fetch.py`

## TDD steps
- [ ] **Step 1 — Write the failing test** at `tests/test_federation/test_fetch.py`:

```python
# tests/test_federation/test_fetch.py
import pytest
from app.federation.fetch import is_blocked_ip, FederationFetchError


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254",  # IMDS
    "100.64.0.1",        # CGNAT
    "::1", "fc00::1", "fe80::1",
])
def test_internal_ips_are_blocked(ip):
    assert is_blocked_ip(ip) is True


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "2606:4700::1111"])
def test_public_ips_are_allowed(ip):
    assert is_blocked_ip(ip) is False


async def test_fetch_rejects_non_https():  # asyncio auto-mode; no explicit marker (ruff PT)
    with pytest.raises(FederationFetchError):
        from app.federation.fetch import hardened_get
        await hardened_get("http://example.com/x")  # http -> reject
```

- [ ] **Step 2 — Run; expect fail.** `./bouy exec app pytest tests/test_federation/test_fetch.py -v` → FAIL (module missing).
- [ ] **Step 3 — Implement** `app/federation/fetch.py`:

```python
# app/federation/fetch.py
"""Single hardened egress helper for ALL federation outbound HTTP (SSRF guard, §11.1)."""
import ipaddress
import socket

import httpx

_MAX_BYTES = 5 * 1024 * 1024
_MAX_REDIRECTS = 3
_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


class FederationFetchError(Exception):
    """Raised when a federation fetch is rejected or fails safety checks."""


def is_blocked_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        return True
    if addr.is_multicast or addr.is_unspecified:
        return True
    # CGNAT 100.64.0.0/10 (not flagged is_private)
    if addr.version == 4 and addr in ipaddress.ip_network("100.64.0.0/10"):
        return True
    return False


def _resolve_and_validate(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FederationFetchError(f"DNS resolution failed for {host}") from exc
    for info in infos:
        ip = info[4][0]
        if is_blocked_ip(ip):
            raise FederationFetchError(f"blocked internal IP {ip} for host {host}")


async def hardened_get(url: str) -> httpx.Response:
    """HTTPS-only GET with internal-IP blocking, redirect cap + per-hop revalidation, size cap."""
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        parsed = httpx.URL(current)
        if parsed.scheme != "https":
            raise FederationFetchError(f"non-https URL rejected: {current}")
        if parsed.host is None or _is_ip_literal(parsed.host):
            raise FederationFetchError("IP-literal or hostless URL rejected")
        _resolve_and_validate(parsed.host)
        async with httpx.AsyncClient(follow_redirects=False, timeout=_TIMEOUT) as client:
            resp = await client.get(current)
        if resp.is_redirect and resp.has_redirect_location:
            current = str(resp.next_request.url)  # revalidate next hop on loop
            continue
        if int(resp.headers.get("content-length", 0)) > _MAX_BYTES:
            raise FederationFetchError("response exceeds size cap")
        return resp
    raise FederationFetchError("too many redirects")


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False
```

- [ ] **Step 4 — Run; expect pass.** `./bouy exec app pytest tests/test_federation/test_fetch.py -v` → PASS.
- [ ] **Step 5 — Commit:** `git commit -am "feat(federation): SSRF-hardened egress helper (§11.1)"`

## Acceptance
- [ ] `is_blocked_ip` returns True for loopback, RFC-1918 private, link-local (incl. `169.254.169.254` IMDS), CGNAT `100.64.0.0/10`, and IPv6 `::1`/`fc00::1`/`fe80::1`; False for public `8.8.8.8`/`1.1.1.1`/`2606:4700::1111`.
- [ ] `hardened_get` raises `FederationFetchError` on non-HTTPS, IP-literal/hostless URLs, blocked resolved IPs, and >`_MAX_REDIRECTS` redirects (revalidating each hop).
- [ ] All `tests/test_federation/test_fetch.py` tests pass.

## Constitution touchpoints
- VII / Privacy & Security (SSRF guard — read-only public-facing surface must not be coerced into internal requests).
- III (TDD red-first).
- IX (single-purpose module under 600 lines).

## Dependencies / blocked by
- Parent phase: P0 — Foundations. Parent epic: [EPIC] HSDS Federation in PPR Core.
- No upstream task dependency.

## Notes
- **Deferred together to P2/P3 (neither forgotten):** (1) the DNS-rebinding pin — connect to the *validated* IP while preserving SNI/Host, via an httpx transport that connects to the resolved IP; (2) the streaming hard size-cap — the P0 `content-length` check is header-only/post-buffer (the body is already buffered and `content-length` is optional), so replace it with `client.stream()` + an incremental byte counter that aborts past `_MAX_BYTES`. Add both (each with a test) when wiring real peer fetches in P2/P3. The IP-range validation is the tested core in P0.
- Source of truth: plan Task 0.2; design §11.1. Plan [`docs/superpowers/plans/2026-06-03-hsds-federation-core.md`](docs/superpowers/plans/2026-06-03-hsds-federation-core.md).

## Out of scope
- The connect-pin transport and streaming byte-counter (deferred to P2/P3 per the plan note above).
````

### `P0.3` — P0.3 — JCS canonicalization + RFC 9421 signing

**kind:** `task` · **parent:** `P0` · **milestone:** `P0` · **labels:** `federation`, `phase:P0`, `ready`

````markdown
## Summary
Implement JCS (RFC 8785) canonicalization — the normative byte form for everything that is hashed or signed — and RFC 9421 HTTP Message Signatures over Ed25519 with an RFC 9530 `Content-Digest`. Canonicalization ambiguity is the fediverse's signature-interop graveyard, so we pin it on day one with fixture vectors. This is the resolved-v3 signing decision (RFC 9421; the expired Cavage-12 profile is dropped).

## Design refs
- §8.3 (RESOLVED v3: RFC 9421 transport sigs + RFC 9530 `Content-Digest` + Ed25519; covered components `@method @target-uri content-digest created`; ±300 s replay window; JCS/RFC 8785 normative for every signed/hashed byte; `keyId`/`verificationMethod` host MUST equal the `actor` DID host)
- §6.2a (the envelope **object** signature — `proof` over JCS bytes — will reuse `canonical.py` + the same key in P1)
- §21 (decision 2: signing = RFC 9421 + RFC 9530 + JCS)

## Files
- Create: `app/federation/canonical.py`, `app/federation/signing.py`
- Test: `tests/test_federation/test_canonical.py`, `tests/test_federation/test_signing.py`

## TDD steps
- [ ] **Step 1 — Write the failing tests** (canonicalization first — every byte that is hashed or signed flows through it):

```python
# tests/test_federation/test_canonical.py
from app.federation.canonical import jcs_bytes


def test_jcs_orders_keys_and_strips_whitespace():
    # RFC 8785: lexicographic key order, no insignificant whitespace, UTF-8
    assert jcs_bytes({"b": 1, "a": "ü"}) == '{"a":"ü","b":1}'.encode()


def test_jcs_is_stable_across_dict_insertion_order():
    assert jcs_bytes({"x": [2, 1], "a": True}) == jcs_bytes(dict([("a", True), ("x", [2, 1])]))
```

```python
# tests/test_federation/test_signing.py
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app.federation.signing import build_signature_base, sign_request, verify_request, SignatureError
import pytest


def _keys():
    priv = Ed25519PrivateKey.generate()
    return priv, priv.public_key()


def test_signature_base_is_rfc9421_shaped():
    base = build_signature_base(
        method="POST", target_uri="https://h.example/federation/inbox",
        content_digest="sha-256=:abc=:", created=1780600000,
        keyid="did:web:h.example#main-key",
    )
    assert '"@method": POST' in base
    assert '"@target-uri": https://h.example/federation/inbox' in base
    assert base.rstrip().endswith(
        '"@signature-params": ("@method" "@target-uri" "content-digest")'
        ';created=1780600000;keyid="did:web:h.example#main-key";alg="ed25519"'
    )


def test_sign_then_verify_roundtrips_and_rejects_tamper():
    priv, pub = _keys()
    headers = sign_request(priv, "did:web:h.example#main-key", "POST",
                           "https://h.example/federation/inbox", body=b'{"x":1}', created=1780600000)
    assert {"Content-Digest", "Signature-Input", "Signature"} <= set(headers)
    verify_request(pub, "POST", "https://h.example/federation/inbox", headers,
                   body=b'{"x":1}', max_skew_seconds=300, now=1780600060)
    with pytest.raises(SignatureError):
        verify_request(pub, "POST", "https://h.example/federation/inbox", headers,
                       body=b'{"x":2}', max_skew_seconds=300, now=1780600060)
```

- [ ] **Step 2 — Run; expect fail.** `./bouy exec app pytest tests/test_federation/test_canonical.py tests/test_federation/test_signing.py -v` → FAIL.
- [ ] **Step 3 — Implement.**
  - `canonical.py`: `jcs_bytes()` via the `rfc8785` PyPI library **if it passes the Principle-VII supply-chain vet** (bandit/safety/pip-audit), else a minimal RFC 8785 serializer (sorted keys, JSON number normalization, UTF-8, no whitespace).
  - `signing.py`: `build_signature_base` per RFC 9421 §2.5 over covered components `("@method" "@target-uri" "content-digest")` with `created`/`keyid`/`alg` params; `sign_request` computes the **RFC 9530 `Content-Digest`** (`sha-256=:base64(sha256(body)):` structured-field byte-sequence), builds the base, Ed25519-signs, returns `Content-Digest`/`Signature-Input`/`Signature` headers; `verify_request` recomputes the digest (reject mismatch), checks `created` within `±max_skew_seconds` of `now`, rebuilds the base, verifies (`InvalidSignature`→`SignatureError`). Consider the `http-message-signatures` PyPI package — vet it; else implement the minimal Ed25519 profile only.
- [ ] **Step 4 — Run; expect pass.** `./bouy exec app pytest tests/test_federation/test_canonical.py tests/test_federation/test_signing.py -v` → PASS.
- [ ] **Step 5 — Commit:** `git commit -am "feat(federation): JCS canonicalization + RFC 9421 Ed25519 HTTP Message Signatures (§8.3)"`

## Acceptance
- [ ] `jcs_bytes` produces lexicographic key order, no insignificant whitespace, UTF-8 output, and is byte-stable across dict insertion order (the two `test_canonical.py` assertions pass).
- [ ] `build_signature_base` emits the exact RFC 9421 shape asserted (`@method`, `@target-uri`, and the `@signature-params` line ending with `;created=…;keyid=…;alg="ed25519"`).
- [ ] `sign_request` returns `Content-Digest` (RFC 9530), `Signature-Input`, and `Signature` headers; `verify_request` round-trips a valid signature and raises `SignatureError` on a tampered body.
- [ ] `created` outside `±max_skew_seconds` of `now` is rejected (replay window, §8.3).
- [ ] Any vendored crypto/canonicalization dependency passes bandit/safety/pip-audit.

## Constitution touchpoints
- VII (supply-chain vet of any signing/canonicalization dependency; fictional `h.example`/`example.com` hosts in fixtures).
- III (TDD red-first; canonicalization tested before signing).
- IX (two focused modules, each <600 lines).
- X (bandit must pass on the new crypto code).

## Dependencies / blocked by
- Parent phase: P0 — Foundations. Parent epic: [EPIC] HSDS Federation in PPR Core.
- No upstream task dependency (independent of 0.1/0.2; commonly sequenced after 0.1 for the package root).

## Notes
- **Object-signature reuse:** the envelope object signature (`proof`, design §6.2a) reuses `canonical.py` + the same Ed25519 key in P1 — design both modules with that P1 consumer in mind (clean `jcs_bytes(...)` boundary; a sign-over-bytes primitive usable for both transport and object proofs).
- `keyId`/`verificationMethod` host MUST equal the `actor` DID host; the inbox verifies against the pinned key (no hot-path fetch) — enforced at the inbox in P3, but the host-equality contract is fixed here.
- All fixtures use fictional hosts (`h.example`, `example.com`) per Principle VII.
- Source of truth: plan Task 0.3; design §8.3 / §6.2a / §21.

## Out of scope
- The envelope `proof` object signature itself (P1).
- Inbox-side pinned-key verification and the allow-list/attribution/consistency chain (P3, design §6.5).
````

### `P0.4` — P0.4 — Identity: did.json, actor doc, Ed25519 key loading (recovery-key schema §6.1a)

**kind:** `task` · **parent:** `P0` · **milestone:** `P0` · **labels:** `federation`, `phase:P0`, `ready`

````markdown
## Summary
Build the node identity primitives: a `did:web` DID document, the federation actor document, and Ed25519 signing-key loading. The `did.json` `verificationMethod` is an **ordered list with an explicit `priority` attribute** supporting N≥2 keys (the online signing key plus ≥1 higher-priority offline recovery key) — the did:plc-inspired recovery-key hierarchy of §6.1a. The schema is forward-compatible now; the verify-side priority rule ships in P3.

## Design refs
- §6.1 (identity & discovery — `did:web:<domain>` → `/.well-known/did.json`; raw `https://…` org-URL accepted as one identity)
- §6.1a (recovery-key hierarchy: `verificationMethod` ordered list with explicit priority; online signing key + ≥1 higher-priority offline recovery key; schema + verify-side priority check ship in v1 forward-compatible, full ceremony later-phase)
- §8.3 (`keyId`/`verificationMethod` host equals actor DID host)

## Files
- Create: `app/federation/identity.py`
- Test: `tests/test_federation/test_identity.py`

## TDD steps
- [ ] **Step 1 — Write the failing test** at `tests/test_federation/test_identity.py`. Assert:
  - `build_did_document(did="did:web:h.example", public_key_multibase=...)` returns a dict with `id == "did:web:h.example"`, a `verificationMethod` entry whose `id` is `did:web:h.example#main-key` and `type` `Ed25519VerificationKey2020`, and `alsoKnownAs` containing the actor URL.
  - `verificationMethod` is an **ordered list** that also contains a higher-priority **recovery-key** entry (include a recovery-key entry in the test fixture; assert its `priority` outranks the signing key).
  - `load_signing_key(None)` returns `None`; `load_signing_key(<pem>)` returns an `Ed25519PrivateKey`.
  - `build_actor(did, domain)` returns `{id, type: "Service", inbox, outbox, publicKey}`.
- [ ] **Step 2 — Run; expect fail.** `./bouy exec app pytest tests/test_federation/test_identity.py -v` → FAIL (module missing).
- [ ] **Step 3 — Implement** `build_did_document`, `build_actor`, `load_signing_key`, and a `public_key_multibase` helper in `app/federation/identity.py`. `verificationMethod` is an **ORDERED list with an explicit `priority` attribute** supporting N≥2 keys: the online signing key plus ≥1 higher-priority offline recovery key (§6.1a). All fixture hosts are fictional (`h.example`).
- [ ] **Step 4 — Run; expect pass.** `./bouy exec app pytest tests/test_federation/test_identity.py -v` → PASS.
- [ ] **Step 5 — Commit:** `git commit -am "feat(federation): did:web document, actor, Ed25519 key loading"`

## Acceptance
- [ ] `build_did_document` returns `id` = the DID, a `verificationMethod` ordered list whose signing entry is `<did>#main-key` / `Ed25519VerificationKey2020`, plus a higher-`priority` recovery-key entry, and `alsoKnownAs` containing the actor URL.
- [ ] `load_signing_key(None)` → `None`; `load_signing_key(<pem>)` → an `Ed25519PrivateKey`.
- [ ] `build_actor` returns `{id, type:"Service", inbox, outbox, publicKey}`.
- [ ] All `tests/test_federation/test_identity.py` assertions pass.

## Constitution touchpoints
- VII (recovery key held offline; signing key never committed; fictional `h.example` fixtures).
- III (TDD red-first).
- IX (single module <600 lines).

## Dependencies / blocked by
- Parent phase: P0 — Foundations. Parent epic: [EPIC] HSDS Federation in PPR Core.
- Soft dependency on P0.3 for `Ed25519PrivateKey` key handling conventions (key loading mirrors the signing module); no hard ordering required.

## Notes
- **Recovery-key schema is forward-compatible in P0:** the ordered `verificationMethod` list with explicit `priority` ships now; the **verify-side priority rule** (a key-change honored only if signed by a key of ≥ priority of the key being replaced; recovery key can repudiate a lower-priority key within a bounded window) ships in **P3** (§6.1a). Include the recovery-key entry in the test fixture so the schema is exercised today.
- `peer-add` will display and pin the recovery-key fingerprint (P4); the schema authored here is what that flow reads.
- WebFinger (`build_webfinger`) is a separate sibling task (0.6) that extends `identity.py`/`test_identity.py` — not in scope here.
- Source of truth: plan Task 0.4; design §6.1 / §6.1a.

## Out of scope
- The verify-side recovery-key priority check and full recovery ceremony (P3 / later-phase).
- Serving these docs over HTTP routes (Task 0.7).

## Design ↔ plan divergence (flagged for owner)

Design §6.1a says the verify-side recovery-key **priority CHECK ships in v1** (forward-compatible ordered schema). The implementation plan (P0.4) sequences the verify-side priority **RULE to P3**; only the ordered schema + a recovery-key fixture land in P0. **This issue follows the plan (enforcement in P3); the P0 deliverable is the forward-compatible ordered schema only.** If the owner intends design-faithful v1 enforcement, pull the priority check into a P0/P1 task. (Decision recorded for the owner — see the epic's *Open decisions* section.)
````

### `P0.5-task` — P0.5 — Discovery document (.well-known/hsds-federation)

**kind:** `task` · **parent:** `P0` · **milestone:** `P0` · **labels:** `federation`, `phase:P0`, `ready`

````markdown
## Summary
Build the `build_discovery_doc(settings)` document advertising this node's DID, key location, supported HSDS version**s** (a list, per §8.4 set-membership — NOT a hardcoded string), Profile URI, absolute endpoint URLs, allow-list policy, and retention/contact. This task also includes a baseline-verification step: the vendored spec submodule is HSDS **v3.2.3** while `router.py:362` advertises **3.1.1** — verify what the code actually implements and set the advertised version(s) accordingly (v3.1 baseline note, design §7).

## Design refs
- §6.1 (`/.well-known/hsds-federation` advertises DID, key material, supported HSDS version(s), Profile URI, endpoint URLs, allow-list policy, retention/archive policy, checkpoint location, contact)
- §8.4 (version handling — `hsds_versions` is set-membership, a LIST, not exact-string equality)
- §7 (v3.1 baseline note: vendored spec is HSDS v3.2.3; router advertises 3.1.1; P0 verifies what the code implements and sets the advertised version accordingly; Profile/fixtures/@context pin the 3.2 line)
- §endpoint-convention (endpoint URLs are absolute, OPR-advertised, derived from the node domain)

## Files
- Create: `app/federation/discovery.py`
- Test: `tests/test_federation/test_discovery.py`

## TDD steps
- [ ] **Step 1 — Write the failing test** at `tests/test_federation/test_discovery.py`. Assert `build_discovery_doc(settings)` returns a dict with keys:
  - `did`
  - `jwks_or_key_location`
  - `hsds_versions` — a **LIST** (per §8.4 set-membership), asserted against a `FEDERATION_HSDS_VERSIONS` setting (NOT a hardcoded string)
  - `profile_uri`
  - `endpoints.export`, `endpoints.inbox`, `endpoints.history`
  - `allow_list_policy in {"open", "mutual", "private"}`
  - `retention_days == settings.FEDERATION_RETENTION_DAYS`
  - `contact`
- [ ] **Step 2 — Run; expect fail.** `./bouy exec app pytest tests/test_federation/test_discovery.py -v` → FAIL (module missing).
- [ ] **Step 3 — Implement** `build_discovery_doc` in `app/federation/discovery.py`; endpoint URLs are absolute, derived from the node domain (OPR-advertised, §endpoint-convention). As part of implementation, **verify the HSDS version the code actually implements** (vendored submodule v3.2.3 vs the `router.py:362` 3.1.1 advert) and set `hsds_versions` / the `FEDERATION_HSDS_VERSIONS` setting accordingly (3.2 line per §7).
- [ ] **Step 4 — Run; expect pass.** `./bouy exec app pytest tests/test_federation/test_discovery.py -v` → PASS.
- [ ] **Step 5 — Commit:** `git commit -am "feat(federation): .well-known/hsds-federation discovery document"`

## Acceptance
- [ ] `build_discovery_doc(settings)` returns all documented keys; `hsds_versions` is a list driven by a `FEDERATION_HSDS_VERSIONS` setting (no hardcoded version string).
- [ ] `allow_list_policy` ∈ {`open`, `mutual`, `private`}; `retention_days` equals `settings.FEDERATION_RETENTION_DAYS`.
- [ ] `endpoints.export`/`inbox`/`history` are absolute URLs derived from the node domain.
- [ ] The advertised HSDS version(s) reflect what the code actually implements (3.2 baseline verification recorded), not the stale 3.1.1.
- [ ] All `tests/test_federation/test_discovery.py` assertions pass.

## Constitution touchpoints
- II / HSDS compliance (advertised HSDS version must match what the code implements; Profile/@context pin the 3.2 line).
- VIII baseline-verification step ensures the advertised version is grounded in the vendored submodule, not assumed.
- III (TDD red-first).
- IX (single module <600 lines).

## Dependencies / blocked by
- Parent phase: P0 — Foundations. Parent epic: [EPIC] HSDS Federation in PPR Core.
- Depends on P0.1 (`FEDERATION_RETENTION_DAYS` + the new `FEDERATION_HSDS_VERSIONS` setting the test asserts against). The Profile URI it advertises is finalized in Task 0.8 (router profile URI replacement) — coordinate the URI value.

## Notes
- **HSDS version list (§8.4):** `hsds_versions` MUST be a list (set-membership matching), driven by a `FEDERATION_HSDS_VERSIONS` setting, never a hardcoded string. This is the version-fracture inoculation: a v1 node and a v5 node still talk by advertising and matching against a list.
- **3.2.3 baseline verification (§7, v3.1):** the vendored spec submodule is HSDS v3.2.3 while `app/api/v1/router.py:362` advertises 3.1.1. This task verifies what the code actually implements and sets the advertised version(s) accordingly; the Profile, fixtures, and `@context` pin the 3.2 line (also the source of the `GET /` `publisher`/`data_guide` block and the `modified_after`/`format=ndjson` read primitives reused by later catch-up paths).
- Endpoint URLs are advertised (OPR-style), not fixed by convention, so partners never hard-code the `/api/v1/federation/*` prefix.
- Source of truth: plan Task 0.5; design §6.1 / §8.4 / §7.

## Out of scope
- Serving the doc over the `/.well-known/hsds-federation` route in both apps (Task 0.7).
- The Profile merge-patch files and router profile-URI replacement (Task 0.8).
````

### `P0.6` — P0.6 — WebFinger JRD responder

**kind:** `task` · **parent:** `P0` · **milestone:** `P0` · **labels:** `federation`, `phase:P0`, `ready`

````markdown
## Summary

Add a `build_webfinger(resource, actor_url)` helper to the federation identity module that returns a WebFinger JRD pointing `acct:` handles at the node's ActivityStreams actor document. WebFinger is part of the discovery surface that makes a PPR node addressable by handle (`acct:<org>@<domain>`), complementing `did:web` (design §6.1). This is a small, pure helper extending Task 0.4's `identity.py`.

## Files

- **Modify (Create addition):** `app/federation/identity.py` — add `build_webfinger(resource, actor_url)`
- **Test (extends):** `tests/test_federation/test_identity.py`

## TDD steps

- [ ] **Step 1: Failing test** — extend `tests/test_federation/test_identity.py`: assert `build_webfinger("acct:north-jersey-fb@h.example", "https://h.example/federation/actor")` returns a JRD with a `subject` field and a `links` entry equal to:

```python
{"rel": "self", "type": "application/activity+json", "href": "https://h.example/federation/actor"}
```

- [ ] **Step 2: Run; fail.** `./bouy exec app pytest tests/test_federation/test_identity.py -v`
- [ ] **Step 3: Implement** `build_webfinger(resource, actor_url)` in `app/federation/identity.py`, returning a JRD whose `subject` echoes the requested `resource` and whose `links` contains the `rel:"self"` / `type:"application/activity+json"` / `href:<actor_url>` entry.
- [ ] **Step 4: Run; pass.** `./bouy exec app pytest tests/test_federation/test_identity.py -v`
- [ ] **Step 5: Commit.** `git commit -am "feat(federation): WebFinger JRD responder"`

## Acceptance

- [ ] `build_webfinger(...)` returns a JRD with `subject` and a `links[]` entry `{rel:"self", type:"application/activity+json", href:<actor_url>}`.
- [ ] Test added in `tests/test_federation/test_identity.py` is green; uses fictional hosts only (`h.example`) per Principle VII.

## Design refs

- §6.1 Identity & discovery — "WebFinger resolves `acct:` handles."
- Plan task 0.6 (`docs/superpowers/plans/2026-06-03-hsds-federation-core.md`).

## Constitution touchpoints

- III (TDD red-first). VII (fictional data only — `h.example`, no real handles). IX (small pure helper, stays well under 600 lines).

## Dependencies / blocked by

- Builds on Task 0.4 (`identity.py` with `build_actor`). The actor URL passed in is the doc produced there.
- The route that exposes `/.well-known/webfinger` is wired in Task 0.7.

## Notes

- Pure function only — no route registration here (that is Task 0.7). Parent epic: see `[EPIC] HSDS Federation in PPR Core`. Design of record: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`. Plan: `docs/superpowers/plans/2026-06-03-hsds-federation-core.md`.
````

### `P0.7` — P0.7 — Wire root-level public routes into both apps

**kind:** `task` · **parent:** `P0` · **milestone:** `P0` · **labels:** `federation`, `phase:P0`, `ready`, `constitution`

````markdown
## Summary

Expose the federation discovery surface — `/.well-known/hsds-federation`, `/.well-known/did.json`, `/.well-known/webfinger`, and the actor doc — as root-level GET routes registered identically in both runtime entry points: the Uvicorn app (`app/main.py`) and the slim API Lambda (`app/api/lambda_app.py`). `did:web` and WebFinger require these paths at the domain root, so they cannot live under the `/api/v1` router. The shared `register_federation_public_routes(app)` helper must import only `app.federation.{identity,discovery}` so the slim Lambda image stays slim (no Redis/LLM deps) — a Principle XV dual-environment requirement.

## Files

- **Create:** `app/federation/routes_public.py` (exports `register_federation_public_routes(app)`)
- **Modify:** `app/main.py` (after line 78), `app/api/lambda_app.py` (after line 66)
- **Test:** `tests/test_federation/test_public_routes.py`

## TDD steps

- [ ] **Step 1: Failing test** — create `tests/test_federation/test_public_routes.py`:

```python
# tests/test_federation/test_public_routes.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.federation.routes_public import register_federation_public_routes


def _client():
    app = FastAPI()
    register_federation_public_routes(app)
    return TestClient(app)


def test_well_known_discovery_served():
    r = _client().get("/.well-known/hsds-federation")
    assert r.status_code == 200
    assert isinstance(r.json()["hsds_versions"], list)  # §8.4 set-membership; pinned to the 3.2 line (see Task 0.5)


def test_did_json_served():
    r = _client().get("/.well-known/did.json")
    assert r.status_code in (200, 404)  # 404 only if FEDERATION_DID unset; 200 when configured


def test_webfinger_requires_resource():
    assert _client().get("/.well-known/webfinger").status_code == 422
```

- [ ] **Step 2: Run; fail.** `./bouy exec app pytest tests/test_federation/test_public_routes.py -v`
- [ ] **Step 3: Implement** `register_federation_public_routes(app)` in `app/federation/routes_public.py`, registering root GETs for:
  - [ ] `/.well-known/hsds-federation` (the discovery doc from Task 0.5; `hsds_versions` is a **list**, §8.4 set-membership).
  - [ ] `/.well-known/did.json` — returns the did document when `FEDERATION_DID` is configured; **404 when `FEDERATION_DID` is unset**.
  - [ ] `/.well-known/webfinger` — `resource` query parameter is **required → 422 if absent**; returns the WebFinger JRD (Task 0.6) when present.
  - [ ] the actor doc.
  - [ ] Call `register_federation_public_routes(app)` from `app/main.py` (after line 78) **and** `app/api/lambda_app.py` (after line 66).
  - [ ] Confirm `routes_public.py` imports **only** `app.federation.{identity,discovery}` (no Redis/LLM) so the slim Lambda stays slim (Principle XV).
- [ ] **Step 4: Run; pass.** `./bouy exec app pytest tests/test_federation/test_public_routes.py -v` — then run the whole package green: `./bouy exec app pytest tests/test_federation/ -v`
- [ ] **Step 5: Commit.** `git commit -am "feat(federation): serve .well-known discovery/did/webfinger/actor in both apps"`

## Acceptance

- [ ] `GET /.well-known/hsds-federation` → 200 with `hsds_versions` as a JSON **list** (pinned to the 3.2 line per Task 0.5).
- [ ] `GET /.well-known/did.json` → 200 when `FEDERATION_DID` configured, 404 when unset.
- [ ] `GET /.well-known/webfinger` without `resource` → 422; with `resource` → JRD.
- [ ] Routes registered in **both** `app/main.py` and `app/api/lambda_app.py`.
- [ ] `routes_public.py` import graph contains no Redis/LLM modules — slim-Lambda import purity verified.
- [ ] Whole `tests/test_federation/` package green.

## Design refs

- §6.1 / §6.1a (discovery surface, did.json), §8.4 (version set-membership → `hsds_versions` is a list), §13 dual-environment table row: "Read endpoints + `.well-known/*` → Uvicorn routes (`app/main.py`) | slim Lambda (`lambda_app.py`) + new root-level routes."
- Endpoint path convention (plan §"Endpoint path convention"): discovery docs are root-level; only the data endpoints live under `/api/v1/federation/*` (created in P1).
- Plan task 0.7.

## Constitution touchpoints

- **XV (NON-NEGOTIABLE):** wired into both Uvicorn and the slim Lambda; the slim-import-purity check (only `identity`+`discovery`) is the load-bearing dual-env requirement.
- III (red-first). VII (fictional `h.example`/`example.com` only). IX (helper stays ≤600 lines).

## Dependencies / blocked by

- Depends on Task 0.4 (identity: did.json/actor), Task 0.5 (discovery doc with `hsds_versions` list), Task 0.6 (WebFinger JRD).

## Out of scope

- The `/api/v1/federation/export|state.txt|history` router package — created in **P1**, not here (per the roadmap P0 row).

## Notes

- Parent epic: `[EPIC] HSDS Federation in PPR Core`. Design of record: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`. Plan: `docs/superpowers/plans/2026-06-03-hsds-federation-core.md`.
````

### `P0.8` — P0.8 — HSDS Profile files + replace router profile URI

**kind:** `task` · **parent:** `P0` · **milestone:** `P0` · **labels:** `federation`, `phase:P0`, `ready`, `constitution`

````markdown
## Summary

Publish the PPR HSDS Profile as multi-file RFC-7386 merge patches and stop advertising the generic upstream profile URI. The Profile adds only the optional PPR fields (`confidence_score`, `verified_by`, `sources`) on top of unmodified HSDS core, plus an OpenAPI patch for the `/api/v1/federation/*` paths, and resolves `app/api/v1/router.py:362` to the canonical PPR profile URI on the same host as `@context`. Patches are authored against the **HSDS 3.2 line** (the vendored submodule is v3.2.3 — design §7 baseline note). This satisfies Principle II by keeping the HSDS core schema intact and declaring PPR's extension as a profile rather than a schema fork.

## Files

- **Create:**
  - `profiles/hsds-ppr/location.json` (RFC-7386 merge patch — adds optional `confidence_score`, `verified_by`, `sources`)
  - `profiles/hsds-ppr/service.json` (RFC-7386 merge patch — same optional props)
  - `profiles/hsds-ppr/openapi.json` (patch adding `/api/v1/federation/*` paths)
  - `profiles/hsds-ppr/README.md`
- **Modify:** `app/api/v1/router.py:362` (replace the generic profile URI)
- **Test:** `tests/test_federation/test_profile.py`

## TDD steps

- [ ] **Step 1: Failing test** — create `tests/test_federation/test_profile.py`:
  - [ ] Assert the API root (`GET /api/v1/`) `profile` field is **no longer** the generic `docs.openhumanservices.org/hsds/` and points at the PPR profile.
  - [ ] Assert each profile patch file is valid JSON.
  - [ ] Assert `location.json` adds **only optional properties** (none of the added keys appear in HSDS core `required`).
- [ ] **Step 2: Run; fail.** `./bouy exec app pytest tests/test_federation/test_profile.py -v`
- [ ] **Step 3: Implement** the merge-patch files. Permitted modifications per `docs/HSDS/docs/hsds/profiles.md` are **new optional props only** — author them against the **HSDS 3.2 line** (vendored submodule v3.2.3, design §7 baseline note). Then set `app/api/v1/router.py:362`'s profile to the canonical PPR profile URI (same host as `@context`).
- [ ] **Step 4: Run; pass.** `./bouy exec app pytest tests/test_federation/test_profile.py -v`
- [ ] **Step 5: Commit.** `git commit -am "feat(federation): publish multi-file HSDS Profile; resolve profile URI (§7,M12)"`

## Acceptance

- [ ] `GET /api/v1/` `profile` field resolves to the canonical PPR profile URI (same host as `@context`), not the generic upstream URI.
- [ ] `location.json`, `service.json`, `openapi.json` are each valid JSON; `location.json` adds only optional properties (no HSDS-core-`required` keys touched).
- [ ] `openapi.json` patch adds the `/api/v1/federation/*` paths.
- [ ] Patches authored against the HSDS 3.2 line (v3.2.3 baseline).

## Design refs

- §7 Data model → **HSDS Profile**: multi-file per `docs/HSDS/docs/hsds/profiles.md`; per-schema RFC-7386 merge patches (`location.json`, `service.json` for `confidence_score`/`verified_by`/`sources[]`), an `openapi.json` patch adding `/federation/*`, one canonical host for `@context` + Profile; "P0 replaces the router's generic profile URI."
- §7 / §8.1 baseline note (v3.1): vendored spec is HSDS v3.2.3; the router currently advertises 3.1.1; Profile/fixtures/`@context` pin the 3.2 line.
- Plan task 0.8 (M12 / Principle II).

## Constitution touchpoints

- **II (HSDS Compliance, NON-NEGOTIABLE):** PPR fields declared as an additive optional profile over unmodified HSDS core — the test enforces "optional props only."
- III (red-first). IX (profile JSON files; no oversized code module).

## Dependencies / blocked by

- Coordinates with Task 0.5 (advertised version) — both verify the 3.2.3 baseline and set the advertised HSDS version(s) to match what the code implements.

## Out of scope

- The actual `/api/v1/federation/*` route implementations (the OpenAPI patch documents them, but the router package is created in **P1**).

## Notes

- Parent epic: `[EPIC] HSDS Federation in PPR Core`. Design of record: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`. Plan: `docs/superpowers/plans/2026-06-03-hsds-federation-core.md`.
````

### `P0.9` — P0.9 — Docs + full gate (phase-closing; open the P0 PR)

**kind:** `task` · **parent:** `P0` · **milestone:** `P0` · **labels:** `federation`, `phase:P0`, `ready`, `constitution`

````markdown
## Summary

The phase-closing task for P0: document the new federation surface in `CLAUDE.md` (Principle XIII), run the full `./bouy test` quality gate (Principle X), and open the P0 pull request. This is the gate where all P0 work (identity, discovery, JCS canonicalization + RFC 9421 signing, SSRF-hardened fetch, public routes in both envs, HSDS Profile) is verified green and surfaced for review. The `gh pr create` command is the deliverable — but per the planning-artifact rules it is **noted, not executed** by this issue.

## Files

- **Modify:** `CLAUDE.md` (add a "Federation (core)" subsection)

## TDD steps

- [ ] **Step 1:** Update `CLAUDE.md` — add a **"Federation (core)"** subsection documenting:
  - [ ] the `.well-known` discovery surface (`/.well-known/hsds-federation`, `/.well-known/did.json`, `/.well-known/webfinger`, actor doc).
  - [ ] the (forthcoming) `./bouy federation` command family.
  - [ ] `source_type='federated_node'`.
  - [ ] a **placeholder** for the `federation_*` structlog grep targets (filled in from P1 onward — e.g. `federation_checkpoint_published`, `federation_proof_failed`, `federation_consistency_failed`).
- [ ] **Step 2:** Run the full gate: `./bouy test` (black, ruff, mypy, bandit, pytest, coverage ratchet). Fix any failures.
- [ ] **Step 3: Commit + open PR.** Commit:

```bash
git add -A && git commit -m "docs(federation): document P0 federation surface in CLAUDE.md"
```

  Then open the P0 PR with this command (**deliverable — do NOT run as part of drafting; this is the operator's action**):

```bash
gh pr create --base main --title "feat(federation): P0 foundations — identity, discovery, signing, SSRF guard, HSDS Profile" --body "Implements P0 of docs/superpowers/plans/2026-06-03-hsds-federation-core.md"
```

## Acceptance (P0 phase gate)

- [ ] `CLAUDE.md` carries a "Federation (core)" subsection (discovery surface, `./bouy federation` placeholder, `source_type='federated_node'`, `federation_*` grep-target placeholder).
- [ ] `./bouy test` is green (black + ruff + mypy + bandit + pytest + coverage ratchet — no regression).
- [ ] discovery/did.json/webfinger/actor resolve in **both** Uvicorn and the slim Lambda (did.json carries the ordered recovery-key schema from Task 0.4).
- [ ] JCS vectors pass; RFC 9421 signing round-trips and rejects tampering (Task 0.3).
- [ ] the fetch helper blocks internal IPs and non-HTTPS (Task 0.2).
- [ ] the PPR HSDS Profile URI resolves (Task 0.8).
- [ ] P0 PR opened against `main` from `feat/federation-p0-foundations` with the title/body above.

## Design refs

- §17 P0 row; §14 (the `federation_*` structlog taxonomy whose grep targets are stubbed here, filled in P1+).
- Plan task 0.9 and the **P0 acceptance** block.

## Constitution touchpoints

- **XIII (Documentation Maintenance):** CLAUDE.md updated in the same PR as the code.
- **X (Consistent Quality Gates, NON-NEGOTIABLE):** the full `./bouy test` gate must pass before the PR.
- I (all commands via `./bouy`).

## Dependencies / blocked by

- Blocked by Tasks 0.1–0.8 (this is the phase-closing task; the PR encompasses all of P0).

## Out of scope

- Filling in the real `federation_*` grep targets and the `/api/v1/federation/*` export contract — that is P1's CLAUDE.md update (plan P1 task 12).

## Notes

- **Do NOT run `gh pr create`** as part of any planning/drafting work — it is recorded here only as the operator's deliverable command. Parent epic: `[EPIC] HSDS Federation in PPR Core`. Design of record: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`. Plan: `docs/superpowers/plans/2026-06-03-hsds-federation-core.md`.
````

### `STD-1` — STD: crosswalk envelope vocabulary to Open Referral provenance model (#558/#553/#508)

**kind:** `standards` · **parent:** `epic` · **milestone:** `Ecosystem & Standards` · **labels:** `federation`, `type:standards`

````markdown
## Summary

Donate HSDS Federation's per-aggregate attribution + identity model to Open Referral's in-flight provenance work, aligned to *their* vocabulary, so the eventual HSDS-FX spec speaks the community's field names from day one. This is the **wedge** move (now, pre-P1): show up where the community is already working (the source-of-records / publisher-steward-source discussion) and contribute, rather than arriving later with a parallel vocabulary. Aligning the envelope to BODS-inspired publisher/steward/source roles before extraction de-risks the entire stewardship play and signals first-mover alignment (confirmed by live scan, 2026-06-04).

## Design refs

- §8.5 "Spec extraction & stewardship" → engagement sub-plan, *Wedge (now, pre-P1)*.
- §7 "Data model" → *Vocabulary crosswalk*: the envelope's `actor`/`attributedTo`/`origin` crosswalked to Open Referral's BODS-inspired **publisher / steward / source** role model (#558/#553/#508); `org-id.guide` identifiers carried alongside `did:web`.
- §1.1 incentive ledger (complementary positioning; this is the standards-track corollary).

Design of record: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`
Living plan: `docs/superpowers/plans/2026-06-03-hsds-federation-core.md`
Parent epic: see ref `epic`.

## Scope / actions

- [ ] Contribute to spec issue **#558** (source-of-records; maintainer **mrshll1001**, who is reaching for OpenLineage) — bring HSDS-FX's per-aggregate attribution model into the discussion.
- [ ] Contribute to spec issues **#553 / #508** (publisher / steward / source metadata).
- [ ] Produce a written crosswalk mapping the envelope's `actor` / `attributedTo` / `origin` onto the BODS-inspired **publisher / steward / source** role model.
- [ ] Confirm the model carries **`org-id.guide` identifiers alongside `did:web`** so federated entities have a community-recognized org id in addition to the DID.
- [ ] Align HSDS-FX's identity model to the community vocabulary *before* the P1 HSDS-FX extraction task locks the field names (the extraction task — P1 — consumes this crosswalk).

## Timing

**Wedge — now / pre-P1.** This is permissionless and additive: contributing to open spec issues needs no committee buy-in and front-loads the vocabulary alignment that the P1 extraction depends on.

## Dependencies

- No hard blockers; permissionless and runs in parallel with P0.
- **Feeds** the P1 HSDS-FX spec extraction (P1 Task 11 builds fixtures/schema; STD-3 governs the artifact). The crosswalk output must land before the envelope vocabulary is frozen in HSDS-FX.
- Pairs with **STD-2** (the upstream PRs) as the two-part "wedge" — same window, same community surface.

## Notes

- The roadmap row + the §8.5 / §7 v3.1 DELTA text are authoritative over any older task phrasing.
- Pin alignment to the **3.2 line** (vendored baseline v3.2.3) per §7, consistent with how HSDS-FX `@context` / Profile / fixtures will pin.
- This issue is the *vocabulary/donation* track only; the actual fixture + schema build is P1 Task 11, and the standalone governed artifact is **STD-3**.
````

### `STD-2` — STD: propose upstream HSDS PRs — extend last_modified + tombstone/Delete semantics

**kind:** `standards` · **parent:** `epic` · **milestone:** `Ecosystem & Standards` · **labels:** `federation`, `type:standards`

````markdown
## Summary

Propose the two low-controversy upstream HSDS PRs the community demonstrably needs and that PPR's federation work proves out: (1) **extend `last_modified` beyond `service`** — it exists nowhere else in HSDS today (PR #375's orphan) and incremental federation sync needs per-aggregate modification timestamps; (2) **tombstone / Delete deletion-propagation semantics** — HSDS has no deletion-propagation mechanism at all, yet federation requires it (a peer must be able to learn a record was removed and re-point to a survivor). Landing these upstream makes PPR's federation shape align with vanilla HSDS rather than diverge from it.

## Design refs

- §8.5 engagement sub-plan, *Wedge (now, pre-P1)*: "propose the two low-controversy PRs the community demonstrably needs: **extend `last_modified` beyond `service`** (it exists nowhere else — PR #375's orphan) and **tombstone/Delete semantics** (no deletion-propagation exists in HSDS at all)."
- §9 Activity semantics — `Delete` → Tombstone (`is_canonical=FALSE` semantics) + `redirectTo` survivor; receiver re-points. This is the concrete behavior the upstream tombstone semantics would standardize.
- §6.2 / §8.4 — version handling and the verifiable-log basis for per-aggregate freshness.

Design of record: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`
Living plan: `docs/superpowers/plans/2026-06-03-hsds-federation-core.md`
Parent epic: see ref `epic`.

## Scope / actions

- [ ] Draft and open an upstream HSDS PR to **extend `last_modified` beyond `service`** (the field exists only on `service` today; PR #375 is the dormant precedent / orphan to revive or reference).
- [ ] Draft and open an upstream HSDS PR (or proposal) for **tombstone / `Delete` deletion-propagation semantics** — currently absent from HSDS entirely.
- [ ] Frame both as low-controversy, community-needed additions (not federation-specific bolt-ons) so they can land in pure-HSDS independently of HSDS-FX.
- [ ] Reference PPR's running federation behavior (§9 `Delete`+`redirectTo`; the dedup-script soft-delete site) as the proof-of-need.
- [ ] Coordinate timing with the TC's rough-consensus + 2-week-RFC process (Open Data Services as Technical Steward).

## Timing

**Wedge — pre-P1 / during P1.** The §8.5 engagement wedge "can start during P1." These are permissionless upstream contributions and do not depend on the hard gate; they should be opened in the same window as STD-1.

## Dependencies

- No hard blockers; runs in parallel with P0/P1.
- Tombstone-semantics PR is informed by the §9 `Delete`+`redirectTo` behavior, which P1 actually implements at the dedup-script soft-delete site — but the *proposal* need not wait for P1 to land.
- Pairs with **STD-1** (vocabulary crosswalk) as the joint wedge; both surface in the Open Referral spec repo.

## Notes

- Everything inside pure-HSDS here is "provenance/deletion discussion PPR is ahead of and aligned with" — first-mover status confirmed by live scan (2026-06-04, §21).
- Keep these PRs *additive* and not crypto-coupled: per §8.5, lead with what the TC already accepts (provenance/freshness), present verifiability separately.
````

### `STD-3` — STD: extract & govern HSDS-FX spec artifact + conformance suite

**kind:** `standards` · **parent:** `epic` · **milestone:** `Ecosystem & Standards` · **labels:** `federation`, `type:standards`

````markdown
## Summary

Extract §8 of the design — envelope, Location aggregate, RFC-9421 signing profile, `federation_id` grammar, endpoints, C2SP checkpoint format, JSON Schema, and fixtures — into a **separately-versioned, neutrally-named spec artifact (working name "HSDS-FX", HSDS Federation Exchange)** that is implementable with **zero reference to `app/`**. This issue owns the *artifact, its governance annex, and its hosting* — the standalone candidate community standard, distinct from the in-repo build of fixtures/conformance (which is P1 Task 11). HSDS-FX is what makes federation an open standard a non-PPR partner can implement against, rather than a plugin-private contract (§4).

## Design refs

- §8.5 "Spec extraction & stewardship (RESOLVED v3: impl-first, donate in parallel)": its own SemVer; a public issue tracker; HSDS-style backwards-compat rule; **no normative change without a fixture + conformance test**; hosted on **one neutral, non-PPR-branded domain** also serving `@context` + Profile + `/schema`; stated intent to donate stewardship to Open Referral.
- §8.5: fixtures double as (a) PPR's CI conformance gate, (b) a hosted **"Federation Readiness Checker"** (paste your `/export` URL → tier report), and (c) a **copy-paste static-feed generator** (Tier 1 = an afternoon).
- §8.1–§8.4 (envelope; Location aggregate; RFC-9421 signing; version handling / fracture inoculation), §6.2 checkpoint format (C2SP signed-note), §7 `federation_id` grammar, §20 interop tiers.
- §21 resolved decision 7: neutral naming (spec artifact "HSDS-FX").

Design of record: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`
Living plan: `docs/superpowers/plans/2026-06-03-hsds-federation-core.md`
Parent epic: see ref `epic`.

## Scope / actions

- [ ] Stand up a **neutrally-named, separately-versioned HSDS-FX artifact** (repo/tracker) implementable with zero reference to `app/`.
- [ ] Extract §8 content: envelope, Location aggregate, **RFC-9421 signing profile**, `federation_id` grammar, endpoints, **C2SP checkpoint format**, JSON Schema, fixtures.
- [ ] Establish governance: **own SemVer**; public issue tracker; HSDS-style backwards-compat rule; **"no normative change without a fixture + conformance test"** enforced as a contribution rule.
- [ ] Host **one neutral, non-PPR-branded domain** serving the spec + `@context` + HSDS Profile + `/schema`.
- [ ] Wire the fixtures so they serve triple duty: PPR CI conformance gate (DRY with `fixtures/federation/`), hosted **Federation Readiness Checker**, and **copy-paste static-feed generator**.
- [ ] Write the **governance annex** covering: network membership; **key / recovery-key management (§6.1a)**; **deletion authority (§9 `Delete`)**; **dispute / refutation (§11.12)**; **rogue-peer recovery (§11.4)** — "who controls a federated entity?" is the real battleground per §8.5.
- [ ] State the intent to donate stewardship to Open Referral (impl-first, donate in parallel).

## Timing

**Wedge → reveal bridge.** Extraction is sequenced *impl-first* (§8.5): the running reference is built first (the fixtures/conformance build is **P1 Task 11**), then the artifact is governed and hosted here and brought to the TC at reveal (STD-4, P2).

## Dependencies

- **Depends on the §8.5 governance annex** content: membership, key/recovery-key mgmt (§6.1a), deletion authority (§9), dispute/refutation (§11.12), rogue-peer recovery (§11.4) — several of which are designed-now-but-shipped-later (recovery-key schema lands P0.4; `Flag`/dispute lands P4; witness/rogue-peer recovery matures P6). The annex documents the designed model; it does not block on those phases shipping.
- **DRY with P1 Task 11** (the in-repo fixtures + JSON Schema + conformance suite build, plan §P1). THIS issue is the standalone artifact + governance + hosting; Task 11 is the build. They must not diverge.
- **Consumes STD-1's vocabulary crosswalk** — the envelope field names (publisher/steward/source; `org-id.guide` alongside `did:web`) must be aligned before the artifact freezes them.
- Soft-gated on P1 producing a running reference worth governing (impl-first sequencing).

## Out of scope

- The actual *building* of fixtures / JSON Schema / conformance tests in-repo — that is **P1 Task 11**.
- The TC presentation / Open Referral engagement choreography — that is **STD-4**.

## Notes

- Pin `@context` / Profile / fixtures to the **3.2 line** (vendored baseline v3.2.3) per §7.
- The neutral name and host are deliberate (§21 decision 7): incumbent-adoption neutrality beats the lighthouse metaphor.
- Per §8.5, present signed checkpoints / proofs as the **optional verifiability tier**, not a prerequisite — Tier 0/1 (plain NDJSON `/export` + `state.txt`) must remain implementable with no crypto (§20).
````

### `STD-4` — STD: Open Referral TC engagement — reveal at P2 with the running reference

**kind:** `standards` · **parent:** `epic` · **milestone:** `Ecosystem & Standards` · **labels:** `federation`, `type:standards`

````markdown
## Summary

Reveal HSDS-FX to the Open Referral Technical Committee at **P2**, leading with the **running reference implementation** and the **live-Feeding-America-feed corroboration test** as fait-accompli proof. Revive Greg Bloom's dormant federation thread (forum 601, dormant since 2025-05; Bloom is now at **Inform USA / AIRS** — the 211-institutional tie), and pitch HSDS-FX as **complementary** to the United Way National Data Platform (NDP) hub and to the Resource Record-Matcher coalition, never a bypass. This is the **reveal** half of the impl-first/donate-in-parallel strategy: a running, adopted reference precedes committee stewardship — the cautionary tale is Service Net, dead of dormancy Dec 2022 despite sound tech.

## Design refs

- §8.5 engagement sub-plan, *Reveal (at P2)*: revive Bloom's federation thread (forum 601) with the running reference + the live-FA-feed corroboration test as proof; complementary to the **United Way NDP hub** and the **Resource Record-Matcher** (Connect211 / ServiceNet / Do Good Data); TC runs rough-consensus + 2-week RFC with **Open Data Services** as Technical Steward; engage **Mike Thacker** (ORUK steward, #485, the one person who has said "federated sources" in the repo); **lead with Tier 0/1** (no-crypto on-ramp), present checkpoints/proofs as the optional verifiability tier; **cite Service Net** (dead Dec 2022) as why a running adopted reference precedes committee stewardship.
- §1.1 incentive ledger — complementary positioning: "feeding and reading the National 211 Data Platform hub, never bypassing it"; Record-Matcher as the offline-dedup consumer of clean attributed aggregates.
- §20 interop tiers (Tier 0/1 = plain NDJSON `/export` + `state.txt`, no crypto required).
- Plan §P2 DELTA: acceptance is concrete — PPR ingests + corroborates the **live FA HSDS 3.0 feed** end-to-end (the proof artifact this reveal leads with).

Design of record: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`
Living plan: `docs/superpowers/plans/2026-06-03-hsds-federation-core.md`
Parent epic: see ref `epic`.

## Scope / actions

- [ ] Revive **Greg Bloom's federation thread (forum 601)**, dormant since 2025-05; frame around Bloom's current **Inform USA / AIRS** role (the 211-institutional tie).
- [ ] Lead the pitch with the **running reference** + the **live-FA-feed corroboration test** as proof (the P2 acceptance artifact).
- [ ] Position HSDS-FX as **complementary to the United Way NDP hub** — a verifiable feed into and between hubs and independents, never a bypass.
- [ ] Position HSDS-FX as **complementary to the Resource Record-Matcher** — the live attributed exchange layer feeding clean aggregates into their offline dedup; consider **co-presenting with the Record-Matcher coalition (Connect211 / ServiceNet / Do Good Data)**.
- [ ] Engage **Mike Thacker** (ORUK steward, #485).
- [ ] **Lead with Tier 0/1** (plain NDJSON `/export` + `state.txt`, no crypto to participate); present signed checkpoints / proofs as the **optional verifiability tier** tied to provenance work the TC already accepts.
- [ ] Run the engagement through the TC's **rough-consensus + 2-week RFC** process with **Open Data Services** as Technical Steward.
- [ ] Bring the **governance annex** (from STD-3), not just the wire spec.
- [ ] **Cite Service Net** (the only prior multi-party sync attempt; dead of dormancy Dec 2022 despite sound tech) as the argument for running-adopted-reference-before-committee-stewardship.

## Timing

**Reveal — at P2.** Consume-first is permissionless; the *telling* is timed to when the live-FA-feed corroboration is demonstrable end-to-end (P2 acceptance). FA outreach timing relative to P2 is an explicitly-remaining-open question (§21) to settle at this point.

## Dependencies

- **Soft-gated on P2** producing the live-FA-feed corroboration proof (plan §P2 acceptance) — that is the lead artifact.
- **Depends on STD-3** for the governed, hosted HSDS-FX artifact + governance annex to present.
- Builds on **STD-1 / STD-2** having already established alignment with the community's provenance vocabulary and upstream PRs (the wedge that makes the reveal land as additive, not competing).

## Notes

- The reveal is deliberately *after* a running, adopted reference exists — the Service Net failure mode is the explicit justification (§8.5).
- Keep verifiability framed as additive integrity, not a prerequisite — the community has zero crypto precedent (§8.5).
````

### `WATCH-1` — WATCH: FHIR Connectathon 2026-07-14..16 + FHIR HSD IG federation scope

**kind:** `watch` · **parent:** `epic` · **milestone:** `Ecosystem & Standards` · **labels:** `federation`, `type:watch`

````markdown
## Summary

Monitor the **CMS/HL7 FHIR Connectathon (2026-07-14..16)** and any move by the **FHIR Human-Services-Directory (HSD) Implementation Guide** to lift its explicit *federation out-of-scope* stance and adopt **NDH v2's `$export` + Subscriptions** directory-exchange patterns. This is the **only credible path to a competing standard** for directory-to-directory exchange in the adjacent world. Notably, NDH chose **Subscriptions over signed feeds** — which both **de-risks our bulk-NDJSON `/export` shape** and **leaves cryptographic verifiability as PPR's clear differentiation**. Everything inside pure-HSDS is provenance-field discussion PPR is already ahead of and aligned with (first-mover status confirmed by live scan, 2026-06-04).

## Design refs

- §21 "Standing watch items (v3.1 — the only credible paths to a competing standard)": the FHIR Connectathon (2026-07-14..16) and any FHIR HSD IG move to lift federation out-of-scope and adopt NDH v2's `$export`+Subscriptions; NDH is the one real directory-to-directory protocol in the adjacent world, and "it chose Subscriptions over signed feeds, which both de-risks our bulk-NDJSON shape and leaves verifiability as our differentiation."
- §3 core insight: PPR is reference-data exchange (FHIR Bulk + VhDir lineage) — the FHIR family is the nearest neighbor, not a rival in shape.
- §22 / §21 first-mover status (live scan, 2026-06-04).

Design of record: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`
Living plan: `docs/superpowers/plans/2026-06-03-hsds-federation-core.md`
Parent epic: see ref `epic`.

## Scope / actions

- [ ] Watch the **CMS/HL7 FHIR Connectathon (2026-07-14..16)** for any Human-Services-Directory federation tracks or outcomes.
- [ ] Watch whether the **FHIR HSD IG lifts its explicit federation out-of-scope** stance.
- [ ] Watch whether the HSD IG **adopts NDH v2's `$export` + Subscriptions** directory-exchange patterns.
- [ ] Confirm the NDH Subscriptions-over-signed-feeds choice still holds (it de-risks our bulk-NDJSON `/export` shape and leaves verifiability as our differentiation).
- [ ] **Report back after the Connectathon** with a short read on whether anything changes PPR's competitive posture or any binding decision.

## Timing

**Watch — monitor; report back after the Connectathon (2026-07-14..16).** No build action. This is a standing watch item, not a deliverable.

## Dependencies

- None. This is observation-only; it neither blocks nor is blocked by any phase.
- A material finding (e.g., HSD IG adopting signed feeds, contradicting the differentiation thesis) would feed back into the §21 "remaining open" decisions and the STD-4 TC-reveal framing — escalate to the owner if so.

## Notes

- This is not a competing-standard alarm by default: pure-HSDS provenance work is alignment, not competition (§21). The watch is specifically for the FHIR-side scope change.
- Keep findings light-touch — a paragraph back to the epic after 2026-07-16 is the expected output.
````

