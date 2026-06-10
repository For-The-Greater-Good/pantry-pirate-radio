# Federation deep review — design + implementation + HSDS-FX spec RFC-readiness (2026-06-10)

Two adversarial review workflows (each = 5 expert lenses → adversarial verification → synthesis), run at the P1→P2 boundary. Raw outputs: design review `wi4ovzwf0`, spec review `wuto9jnuf`. This doc is the durable record; the actionable items are folded into the P2 plan + CLAUDE.md separately.

## A. Design + implementation review — verdict: **RIGHT, with corrections**

The substrate (JCS→Ed25519→RFC-6962→C2SP→proofs) is the right call and the shipped P0/P1 code is sound. **Keep:** the verifiable substrate (§21-1) re-justified vs the steelmanned plain-HTTPS alternative; the crypto composition core (full-preimage RFC-6962 leaves w/ 0x00/0x01 domain separation; sequence/origin/actor/published inside the signed bytes → no transplantation/replay; strict canonical-base64); the note-anchored consumer; external-KAT epistemics; the append hot-path (measured O(1) ~4 ms/append, flat across N — the write side scales fine); HUMAN_VERIFIED guard (intact at all 5 sites); the wire authority layer.

**But the P2 plan as written would fail the partner on integration day** — three failures invisible to current tests:

### Critical (block the partner demo)
1. **Slice 5 routes verified, by-construction-valid peer HSDS through the temp-0.7 LLM aligner** — severs the crypto chain at the canonical write (we'd store an LLM paraphrase of the partner's signed bytes) and falsifies the §12.1 CvRDT byte-identical property. **Fix:** invert Slice 5 — verified PPR-peer envelopes take a **deterministic no-LLM structured path** (validate against HSDS Pydantic → validator → reconciler; the `app/replay/replay.py:enqueue_to_validator` precedent proves the pipeline supports validator-stage entry); LLM reserved for genuinely free-form §6.6a sources. Slice 7b runs the property over the REAL ingest path.
2. **O(L·N) /export pages, O(N²) full pulls — #562 was absent from all 19 slices of the pre-REVISION-2 plan** (since fixed: Slice 5.5 added) though its own gate text says "blocking before P2 live pull." MEASURED (live, fit error <5%): checkpoint O(N) ~11.4µs/leaf; one inclusion proof ~1.76µs/leaf; /export page of 1000 ≈ 1.8ms×N (**9.0s at N=5k**); full pull ≈ 1.8e-6·N² s (**43s at N=5k**). AWS API-GW ~30s timeout kills /export at **N≈16k**; read Lambda OOMs (full-preimage materialization ~1.47KB×N) at **N≈250-500k**; prod has **87,683** canonical locations + ~4,665 record_version rows/day → 1.7M-30M log rows/year. **Fix:** NEW blocking scale slice before Slices 16/17 — Tier A (request-scoped subtree-root memoization + short-TTL checkpoint cache; bit-identical, KAT-gated; solid to ~100k) now; Tier B (persisted Merkle node table under the existing append lock; O(log N); RED-tier Gauntlet) as the hard gate on prod-publish enablement.
3. **First retention prune permanently bricks every proof-bearing endpoint** — reproduced (N=1200, 1100 pruned): one /checkpoint = 2×1100 sequential S3 round-trips; the prod read Lambda can't reach the archive at all → immediate permanent 410. **Fix:** archive-format fix (store full reconstructed envelope incl. id+proof, format-versioned — also closes the §6.2g "still origin-verifiable from the archive" gap, which today archives preimage only and destroys the proof); prune guard refusing to trim when the read path has no persisted-tree/archive-capable serving story; Tier B is the real fix.

### High
4. **Slice 8 (network tier) cannot be a mere owner-guard** — `merge_location`'s source query is `source_type='scraper' OR NULL` (excludes federated rows entirely), and the egalitarian merge (majority-name/longest-desc/most-recent-coord) would clobber the authoritative partner; recency keyed on local `updated_at` also breaks the §12.1 shuffle test. **Fix:** re-scope Slice 8 (8a/8b/8c) as a real merge-algorithm change with field-level tier precedence (`auto < network < human`); Slice 7b extends to mixed-tier shuffles.
5. **§11.6 un-corroborated serve gate hides the partner's ENTIRE complementary dataset** (complementary = lone-source by definition). **Fix:** tier-parameterize the gate — lone *network*-origin serves uncaveated (peer-add review = the standing admin review), lone *auto* low-density caveated, etc.
6. **The signed aggregate omits structured addresses, phones, services** — we'd immaculately protect cargo that can't tell a consumer where the pantry is or what to call. `aggregate.py` pins the wire object to the curated `LocationResponse` (no addresses/phones/languages/accessibility). **Fix:** NEW small slice hardening the wire shape BEFORE the demo + HSDS-FX extraction (additive within 3.1.1; cold-start parity guard re-run as its gate).
7. **Unbounded no-op republish** — every reconciler touch appends a full signed aggregate with zero change-detection (`publish.py:120-153`); the naive hash-compare fix is a near no-op because `sources[].last_updated` changes every commit. **Fix:** volatile-field-stripped change-detection projection + a heartbeat republish cadence (~30d).
8. **Announce corroboration is cryptographically unverifiable hearsay** — carried `origin` is an unsigned string; a rogue allow-listed peer mints N fabricated-origin votes to cross the §11.6 gate, or attributes data to a real origin. **Fix (wire, do before partner pins bytes):** Announce MUST carry the origin envelope's content-address `id` (min) or embed the origin's full signed envelope (ideal); Slice 7a counts a federated origin vote only when the origin DID is itself allow-listed; must_reject vector.
9. **proof.type / proof.verificationMethod unsigned + unchecked** (probe-confirmed: bogus suite + evil verificationMethod still verify; a third party re-signs A's preimage under its own key). The JWS `kid`/`alg` confusion trap for foreign implementers. **Fix (auto):** verify_envelope MUST resolve the key from signed `actor`/`origin` (never proof.verificationMethod), require proof.type ∈ supported suites, and bind verificationMethod DID == actor — + must_reject vectors.
10. **Split-view evidence discarded** — Slices 3/6 persist only (size, root), dropping the peer-SIGNED note bytes that make equivocation "provable, not alleged"; /checkpoint also signs a fresh O(N) note per anonymous GET (vs the design's coalesce/heartbeat). **Fix (auto):** persist the raw signed note in the cursor table; coalesce checkpoints (rides the scale slice).

### Medium/low
11. Trust/identity pins: scraper_id should be `federation:<ORIGIN-did>` (relayer in `delivered_by_did`); pull-side pinned-key enforcement; no peer-trust-import rule; `network` vs P5 VC reservation collision; >90 confidence silently clamped.
12. `inclusion_proof` injected at envelope top level — fail-closed but brittle (owner decision: nest it under a wrapper?).
13. Onboarding friction (no keygen/peer-add until P4); the P2 plan PR not yet merged; stale FA-feed/C2SP comments in docs.

## B. HSDS-FX spec RFC-readiness — verdict: **NOT submittable today; the gap is document-shaped, not protocol-shaped**

Strong foundation (shipped reference, externally-anchored KATs, the honesty ledger — a genuine differentiator, put it IN the spec, ~150-vector corpus). Missing: the document itself (#540 unstarted), and the design doc a reviewer reads today has load-bearing contradictions.

### Embarrassing (fix before ANYTHING goes external — repo is PUBLIC)
1. **Void FA-feed premise as live fact** across design §1.1/§6.6a/§17/§22, **public issue #541**, the epic doc, INTEROP_PENDING confirmers. Scrub all.
2. **No standalone spec doc**, and design §8.1's worked example produces **unverifiable bytes** (no `license` key, wrong @context, per-verb fields defined only "as in v2.1" — a superseded doc).
3. **§6.2a states the Merkle leaf WRONG** ("the object hash is the Merkle leaf") — shipped leaf is `leaf_data = JCS(envelope ∖ {id,proof})` under RFC-6962 0x00 prefix; a foreign impl reading the design builds a tree that fails every inclusion proof.
4. **`proof.type = "ed25519-jcs-2026"`** is an unregistered lookalike of W3C's real `eddsa-jcs-2022`, zero recorded rationale.
5. **Tier 0/1 "no crypto required" lead pitch is non-conformant** under the spec's own §8.1 ("id+proof REQUIRED on every envelope"); zero vectors/tooling for it.

### Major
6. The `sandia-ftgg-nc-os-1.0` license string baked into every SIGNED vector; `license` value space undefined; corpus itself unlicensed. 7. The §8.5-required publisher/steward/source (BODS) vocabulary crosswalk not done while AS names are pinned in circulating vectors. 8. No envelope/Tombstone/checkpoint JSON Schema (Open Referral's conformance model IS "validate against the Profile's JSON Schemas"). 9. HTTP binding exists only in router code. 10. Honesty machinery drifted (README says 6 areas, 10 ship; REGISTRY stale MISSING rows; §8.5a overclaims "every primitive anchored"). 11. Redaction-vs-append-only contradiction (§11.8 "purge exported" vs §6.2g "valid forever") unanswered. 12. Missing RFC table-stakes: governance annex, Privacy/Equity/Security Considerations as spec text, IANA/registry, version signaling.

### Required document outline (22 sections)
Abstract · Status · Intro · Conventions+Terminology (BCP 14) · Conformance classes (mapped from §20 tiers, Tier-0/1 no-crypto led) · Identifiers (did:web + federation_id ABNF) · Data Model (aggregate field set + envelope field table + verbs) · **Canonicalization & Octet-Level Definitions** (the leaf/id/proof bytes, normatively) · Verifiable Log (C2SP checkpoint profile) · HTTP Binding (discovery schema, /export pagination, status codes, headers) · Push (/inbox RFC 9421) · Versioning · Security Considerations · Privacy Considerations · Equity Considerations · IANA/Registry · References (normative/informative) · App A test vectors + honesty table · App B worked example · App C governance annex · App D crosswalk · App E impl status.

### Proposal sequencing
Stage 0 scrub+freeze (now) → Stage 1 enter as **contributors** (crosswalk comment on openreferral #558/#553 + the two low-controversy PRs they need: `last_modified` beyond service, tombstone/deletion semantics) → Stage 2 build the #540 packet → Stage 3 forum proposal as "candidate spec soliciting a second implementation."

## C. Protocol-freeze decisions needed BEFORE the spec is written / the partner pins the wire

These touch signed bytes or vector contents and become immutable once a P2 peer integrates — decide now while zero foreign impls exist. (Owner calls; see report for recommendations.)
1. **Cryptosuite:** adopt W3C `eddsa-jcs-2022` (DataIntegrityProof + Multikey + multibase proofValue) vs keep+document `ed25519-jcs-2026`. Migration is uniquely cheap now (leaves/checkpoints/content-addresses are all proof-independent).
2. **@context** value space + neutral profile-URI domain.
3. **Envelope vocabulary:** keep AS names on the wire + write the normative crosswalk (recommended).
4. **`license`:** define as SPDX id or absolute URI; regenerate vectors with a neutral example; license the corpus (CC0/CC-BY).
5. **Conformance classes:** split into HSDS-FX Core (proof OPTIONAL — the Tier-0/1 on-ramp) + a Verifiable tier.
6. **Announce shape:** embed origin's signed envelope or its content-address id (finding 8).
7. **PII redaction mechanism** vs append-only archive: leaf-payload redaction with leaf-hash retention (root + proofs stay valid).
8. Auto: verb registry; I-JSON integer domain (±2^53−1, cite RFC 7493); HTTP header rename (drop `X-` per RFC 6648); verify_note accept-set align to C2SP.

## What is NOT changing
The substrate decision; the crypto core; the note-anchored consumer; external-KAT epistemics; the append hot-path; archive-then-trim as a concept; the wire authority layer; HUMAN_VERIFIED guard; advertising HSDS 3.1.1; the validator-stage entry seams; P2 CI-only sequencing + bilateral-only equivocation posture for P2.
