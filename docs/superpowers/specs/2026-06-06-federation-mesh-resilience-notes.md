# Federation Mesh — Resilience & Sync Model Notes

**Status:** Discussion / design companion (not a spec change). **Adopted with corrections 2026-06-06** after a 5-lens adversarial evaluation (pivot-or-affirmation, CRDT-claim-vs-real-code, distributed-systems soundness, in-flight-work impact, red-team). Verdict: **not a pivot — course-affirmation of #518** plus three additions (M-of-N governance, license-in-band, threat taxonomy). Corrections from that evaluation are folded in below and marked **[corrected]**.
**Companions:** `2026-06-03-hsds-federation-core-design.md` (design of record, PR #518), `2026-03-25-lighthouse-design.md` (Federation-Aware Design Notes)
**Purpose:** A decision-framing artifact for any agent or contributor working the federation mesh. It answers one question the core design implies but doesn't argue out loud: *how should a network of cross-organization PPR nodes stay "in sync" and survive takedowns?* Read this before reaching for quorum consensus or a blockchain.

**Decision already taken from this doc (2026-06-06):** license-in-band — a `license` field rides inside the **signed** envelope pre-image (landed in P1 PR-B `app/federation/envelope.py` + `FEDERATION_LICENSE` config, before the Task 11 fixture freeze). Everything else here is commentary, P2+ targets, or P4–P6 governance material; nothing resequences P1.

---

## How an agent should use this doc

- Treat the **AP-data / CP-governance split** (below) as the default architecture. If a task pushes toward global quorum/consensus on the *data* path, stop and flag it against the "Why not quorum" section.
- When evaluating a sync, replication, or "keep nodes consistent" task, classify it into one of the **three layers** first. The layer determines the correct consistency model.
- **[corrected] Implementation-status discipline:** statements below about convergence, witnesses, and cheap nodes are *targets with owners and phases*, not shipped properties. Where this doc and the design of record disagree, the design wins (cite §).
- This doc is opinionated on purpose. It is not neutral about blockchain — see TL;DR.

---

## TL;DR (the decision)

1. **The goal is takedown resilience, which means the data path must stay available under partition, not globally consistent.** A surviving node must keep serving *and writing* when peers go dark. **[corrected]** "AP" is shorthand here: each full node is an independent replica of the corpus with its own canonical view — there is no shared write register to be "C" about. The CAP frame is a guardrail against *introducing* one, not a literal description of the current system.
2. **Quorum consensus (Raft/Paxos/PBFT/any blockchain) is the wrong tool for the data path.** It buys global agreement at the cost of availability — partition the quorum and the minority side **stalls** (the majority side can proceed; the point stands that *somebody's* surviving nodes freeze) **[corrected]**. That manufactures a new, more fragile single point of failure: the quorum itself.
3. **The "distributed ledger / transparency" instinct is correct — and #518 already *specifies* the right half of it:** a Merkle-committed, content-addressed, append-only **transparency log** (P1, in flight) with witness cosigning (**format fixed now, witness mesh ships P6 — not yet implemented [corrected]**). That gives auditability and tamper-evidence *without* coupling write-availability to a quorum.
4. **Nodes "agree" by computing, not voting — as a normative P2 target, not a property the code has today [corrected].** The intended end-state: same signed input logs → same deterministic merge (confidence/corroboration, origin-deduplicated) → same canonical view. Today's pipeline does **not** deliver this: peer ingest routes through the **LLM aligner** (nondeterministic across nodes), coordinate merge keys on the **local ingest clock** (`updated_at = NOW()`), majority-vote ties resolve by **insertion order**, and nodes differ in scraper sets and code versions. **Merkle proofs verify log integrity, not merge-output equality** — "provable agreement" applies to *what was published*, not *what each node computed*. P2 must specify the deterministic merge over a fixed assertion-row set (envelope-clock ordering, total tie-breaks, alignment bypass for already-HSDS peer records) before this claim is true. Until then: convergence-*ish*, by design intent.
5. **Reserve real quorum for the trust root only** — membership (peer DID allow-list), key rotation, schema version. Tiny, rare, and *safe to freeze* during a partition (**but see the succession tension in Open Questions #1 [corrected]**).

---

## Takedown is five threats, not one

"Resilient to takedowns" conflates distinct failure modes. The mesh handles them unevenly, and naming them keeps design honest.

| # | Threat | Single-org multi-region HA | Cross-org mesh |
|---|---|---|---|
| 1 | **Infra failure** — cloud deplatforms you, DDoS, domain seizure | ✅ | ✅ |
| 2 | **Legal takedown** — DMCA / C&D / lawsuit against *the org* | ❌ one legal entity to sue | ✅ independent entities & jurisdictions |
| 3 | **Organizational death** — funding dies (already happened: HAARRRvest archived at ~$1,600/build) | ❌ | ✅ *iff* peers are full nodes, not consumers |
| 4 | **Hostile capture** — someone acquires/coerces the authoritative org | ❌ one keyset | ⚠️ **[corrected]** contained + attributable, not prevented: a captured org's keys still sign valid-looking `Update`s **within its own attributed authority** until peers de-list it. What no single party can do is rewrite *other* origins' contributions or the corroborated weighting. Actual mitigations: §9 merge authority (`Update` only by `attributedTo`, subordinate to local human curation / `HUMAN_VERIFIED_SOURCES`), corroboration weighting, peer-remove + §11.4 recovery. |
| 5 | **Poisoning** — don't delete, quietly degrade the data | ❌ | ⚠️ **[corrected]** the transparency log makes poisoning **attributable and auditable** (signed, sequenced, DID-bound), and corroboration dampens it — it does not *prevent* it. Detection still requires someone to look (monitors/witnesses, P6). |

**Load-bearing conclusion:** multi-AZ/multi-region replication only covers row 1. Rows 2–4 require *independent legal entities, independent funding, and independent key custody*. That is why "cross-organization" is the essential word — one org running ten regions is one subpoena (or one budget shortfall) away from gone.

---

## Why NOT quorum consensus / blockchain on the data path

- **Partitions are unavoidable in a WAN/cross-org mesh.** Consensus systems privilege agreement: a partitioned minority **stalls** for writes (the majority proceeds) **[corrected — stated precisely]**. For a takedown-resilience mission, *any* configuration where surviving honest nodes can be frozen by others' absence is the wrong trade.
- **Quorum liveness is a new takedown target.** "Absolute sync by quorum" means a quorum must be alive to make progress. Take down enough orgs and the *surviving* nodes can no longer write. You'd be engineering fragility while trying to engineer resilience.
- **Consensus doesn't solve data validity.** A chain still commits garbage if garbage is submitted. The hard problem here is *trustworthy merge of conflicting human-services data*, which the confidence/corroboration model addresses — consensus adds nothing to it.
- **Cost & throughput.** Public-chain consensus is expensive and slow; permissioned BFT (Tendermint/Hyperledger-style) is more apt but still couples write-liveness to quorum. Neither earns its complexity here.
- **[corrected] The one CP-ish ask worth naming rather than dismissing:** "authoritative single answer *right now*" (e.g., two nodes serving different addresses for the same pantry mid-partition). The mesh's honest answer is per-origin attribution + confidence, not a global lock; consumers see *whose* claim they're reading. If a future requirement genuinely demands one global answer, that is a product decision to revisit — not something to back into via infrastructure.

**Net:** a blockchain would *feel* like it adds resilience while quietly adding a quorum you can lose.

---

## What #518 already chose (and why it's right)

The design's "Merkle-committed append-only log + signed checkpoints + witness cosigning" **is** a distributed ledger — specifically a **transparency log**, the proven family behind:

- **Certificate Transparency** — tamper-evident append-only logs, audited by independent monitors; gossip detects split-view.
- **C2SP `tlog-witness` / Go checksum DB** — witnesses cosign tree heads so no node can present a forked history.
- **Sigstore Rekor / Trillian** — transparency log infrastructure.
- **did:plc** — auditable identity directory with recovery-key hierarchies (already cited by #518 for key recovery).

**[corrected] Status precision:** P1 (in flight) ships the log, checkpoints, and proofs. Witness cosigning is **specified now (checkpoint format is witness-compatible from day one) and implemented in P6**. Until P6, split-view detection is bilateral (consumer-side consistency proofs), not mesh-wide.

The witnesses are a distributed-trust quorum that cosigns **integrity** ("this log is append-only and we all see the same head") — they do **not** gate **writes**. Kill some witnesses and data keeps flowing; you temporarily get weaker/staler split-view detection, not a frozen network. That decoupling is the whole point.

---

## "Staying in sync" is three separate things

Don't lump them. Each has a different correct consistency model.

1. **Replication of bytes** — gossip / pull-ingest / push-inbox (all three exist in #518; pull/push land P2/P3). Eventually every node holds every peer's signed log.
2. **Agreement on "the truth"** — *computed, not voted* — **a P2 normative target [corrected]**. End-state: given the same set of signed input logs, every node runs the same deterministic merge (confidence/corroboration, origin-deduplicated to stop citogenesis) and derives the same canonical view, CRDT-style (commutative + idempotent contributions). **Today's gaps that P2 must close before this is claimable:** LLM-aligner nondeterminism on the ingest path (already-HSDS peer records need the deterministic cheap path, §6.6a/§11.5); "most-recent" coordinate merge keyed on local `updated_at` instead of the envelope clock; majority-vote tie-breaks that depend on row order; per-node scraper-set and code-version differences (a merge-ruleset version must be part of the contract). And precisely: **Merkle inclusion/consistency proofs verify the *logs*; they do not prove two nodes' *merged views* are equal.**
3. **Tamper-evidence** — transparency log (P1) + witness cosigning (P6) (availability-independent).

None of these requires quorum consensus on the data.

---

## The architecture: AP data, CP trust root

The clean split. Apply this table when classifying any sync/consistency task.

| Layer | Volume | Model | CAP choice | Freezes under partition? |
|---|---|---|---|---|
| **Data** (locations, schedules, corroboration) | High | Signed append-only logs + gossip + deterministic merge (P2 target) | **AP** | No — never stalls |
| **Trust root** (peer DID allow-list, key rotation, schema version) | Tiny, rare | M-of-N org threshold signatures / witnessed governance log (**proposed — NOT in #518, which has per-node unilateral allow-lists §6.7; this is new P4–P6 governance design [corrected]**) | **CP** | Yes — *and that's usually desirable (but see Open Q #1)* |
| **Integrity** (spans both) | — | Transparency log (P1) + witness cosigning (P6) | Availability-independent | No |

**Trust root is the one place real quorum belongs.** Membership and key changes are rare, high-stakes, and you *want* them to freeze during a partition — you do not want a captured node unilaterally adding peers. An M-of-N ("M of N orgs must cosign") threshold over a witnessed governance log fits exactly — **as a proposal to design in the §8.5 governance annex, not a settled component [corrected]**.

---

## Open questions / decisions for the team

These are the genuinely unsettled parts — good candidates for the federation agent to investigate or for design discussion.

1. **Succession & key recovery — and it conflicts with freeze-under-partition [corrected, the sharpest unresolved tension].** If PPR-the-org dies, how does a successor node get re-added to every peer's allow-list? `did:plc`-style recovery hierarchies must be first-class, with recovery keys *distributed across orgs* (the P0 `did.json` recovery-key schema defines the slots; cross-org custody of those keys is unbuilt). But note: org death and partitions co-occur — a CP trust root that freezes under partition can freeze *exactly when succession is needed*. The M-of-N threshold and the recovery flow must be designed together so recovery quorum ≠ liveness quorum. Unsolved; P4–P6.
2. **Every peer must stand alone.** Resilience holds only if peers are full nodes that can cold-start the canonical view from raw logs (the design's "cold-start rebuilds aggregates from raw tables" is exactly right). Watch for Feeding America-as-source quietly becoming a hub — if all data flows *from* one feed, that feed is the takedown target even with independent nodes.
3. **Minimum viable mesh is a number.** "Takedown resilient" is theater below roughly **≥3 independent orgs across ≥2 jurisdictions**, with **witnesses that are not data producers** (libraries, universities, archive.org-style, digital-rights orgs) so integrity-checking is independent of data production. Name candidate node operators now. **[corrected] Honest status: zero candidates are named today; until partners exist the resilience premise is aspirational, and P1–P3's contribution is making node #2 cheap to stand up — not resilience itself.**
4. **The real risk is economic, not legal.** The pipeline was already "taken down" by cost, not a lawsuit. Cheap-node properties (cold-start-from-raw, archive-not-prune, per-peer ingest budgets) *are* the mitigation. **[corrected] The "$20/mo volunteer full node" is an aspiration that the current stack (Postgres+PostGIS, Redis, LLM alignment, crawl4ai) does not support and no roadmap phase currently funds — treat it as a packaging/profile project to scope, not a property to cite.**
5. **Governance of the allow-list is unsolved socially.** "Explicit allow-list of peer DIDs" is described mechanically but not politically. Without a web-of-trust or a minimal multi-org steering process, one org becomes the de facto gatekeeper — a social single point of failure replacing the technical one.

---

## Enclosure / values note (openness vs. predatory reuse)

This project's mission is open, maximally accessible point-of-interest data for people seeking free/charitable food. A real tension follows and should be stated plainly:

> **You cannot have open data that defeats takedowns and also keep a hostile reader out.** The same openness that lets a friendly org rehost the data after a takedown lets a predatory aggregator (e.g., funneling vulnerable people to healthcare-billing pipelines) scrape it. Access control on the public layer would undermine the resilience goal.

So the levers are **not** technical gating of the open data. They are:

- **License in-band — ADOPTED (2026-06-06).** The license (`sandia-ftgg-nc-os-1.0`, non-commercial) rides inside the **signed pre-image** of every federation activity envelope (P1 PR-B), so a relayed/archived object carries a signed, DID-attributed license trail even detached from its feed. **[corrected] Honesty about its weight:** this is *attribution and deterrence*, not protection — a determined scraper ignores it, and its legal force is untested; do not lean on it as a security property. **[corrected] Known tension to resolve with the ecosystem:** a non-commercial license sits awkwardly with "open data" norms (Open Referral leans CC-BY/ODbL); expect this to come up in the §8.5 donation conversation.
- **Provenance as deterrent.** Signed, DID-attributed records make hostile ingestion *traceable and attributable* — enforceable and name-able, even if not preventable.
- **Two data classes, kept separate.** (a) Public charitable-food POI = the mission, *maximize* replication on the open mesh. (b) Restricted data some contributors will only share under terms = a **selective-disclosure / capability-scoped** lane (Verifiable Credentials, *deferred* in #518). If a private lane is what gets some orgs to participate at all, that deferral may be more adoption-critical than it looks. **Do not let class (b) bleed into the open mesh.**

The protocol can make enclosure **expensive, attributable, and legally actionable**. It cannot make it impossible without sacrificing the openness that is the whole point. For this mission, openness wins; predators are answered with license + provenance + governance, not gates.

---

## Glossary

- **AP / CP (CAP theorem):** under a network partition, a system can preserve **A**vailability or **C**onsistency, not both. AP keeps serving (possibly divergent then convergent); CP refuses to proceed until agreement is possible. Used here as a design guardrail, not a formal claim about the mesh (each node is an independent full replica).
- **Transparency log:** append-only, Merkle-committed log whose entries are content-addressed; tamper-evident because rewriting history breaks published checkpoints.
- **Witness cosigning:** independent parties sign the log's current head so no node can show different histories to different peers (split-view detection). *Specified in P1's checkpoint format; implemented P6.*
- **CRDT (Conflict-free Replicated Data Type):** data whose merge is commutative, associative, and idempotent, so replicas converge without coordination. *For this mesh: the P2 target property of the merge, not a current property.*
- **Citogenesis:** a re-ingested echo of one's own data being miscounted as independent corroboration; prevented by origin-deduplication.
- **DID:** Decentralized Identifier — a node/org's stable, self-owned cryptographic identity.
- **M-of-N threshold:** a change is valid only when M of N designated signers cosign it.

---

## One-line summary for the agent

> Data path = available-under-partition (signed append-only logs + gossip + a deterministic merge that P2 must make real + transparency log). Trust root = CP (M-of-N witnessed governance log — to be designed, P4–P6). Never put global quorum/consensus on the data path; reserve it for membership and keys only.
