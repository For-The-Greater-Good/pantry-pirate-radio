# HSDS Federation — AI Build Playbook

> **READ THIS FIRST in any federation build session.** This is the operating model for turning the
> federation epic (#519) into merged, correct code with AI, across many sessions. It encodes decisions
> already made — do not relitigate them; execute them.

**Companion artifacts (read in this order at session start):**
1. [`../../constitution.md`](../../constitution.md) — the 15 principles (several NON-NEGOTIABLE). The gate everything passes through.
2. [`../../CLAUDE.md`](../../CLAUDE.md) — repo commands (all via `./bouy`), seams, federation subsection.
3. [`specs/2026-06-03-hsds-federation-core-design.md`](specs/2026-06-03-hsds-federation-core-design.md) — **design of record (v3.1).** §21 records the owner's binding decisions. This is authoritative over any code/plan text.
4. [`plans/2026-06-03-hsds-federation-core.md`](plans/2026-06-03-hsds-federation-core.md) — **living plan.** P0 fully task-decomposed; P0.5 spike; P1–P7 roadmap + binding "v3 DELTA" blocks.
5. [`federation-github-epic.md`](federation-github-epic.md) — the issue map (epic #519; P0 #520 + tasks #529–#537; P0.5 #521; P1–P7 #522–#528; STD/WATCH #538–#542).
6. **This playbook.**

---

## Why this shape (the binding constraint)

The owner is a **solo operator** who has stated plainly: *"I'm not capable of reviewing this level of work."*
For a security-critical append-only verifiable log with crypto and concurrency, that is the honest and
governing constraint. Therefore:

- **The machine is the deep reviewer, not the human.** Correctness assurance comes from an automated,
  multi-lens, adversarial, property-tested **PR Gauntlet** (below) that iterates until clean — not from
  the owner reading diffs.
- **The human's role is product/judgment, not line review.** The owner decides go/no-go gates, trust/equity
  questions, and "does this serve users right" — never "is this Merkle proof correct."
- **Shrink the trust surface so there is less for AI to get wrong.** Prefer vetted libraries over hand-rolled
  crypto; lean on executable truth (property tests, conformance fixtures, a second independent implementation)
  over opinion-based review.

### Locked decisions (2026-06-04)

| Decision | Choice | Consequence |
|---|---|---|
| Build engine | **Subagent-driven-development everywhere** | Fresh subagent per task; two-stage review between tasks; all phases (not just risky ones). |
| Review model | **Machine-led, iterate-until-clean per PR** | The owner cannot review deep correctness → the PR Gauntlet is the reviewer; owner does product sign-off only. |
| First move | **Kick off P0 (#520)**, starting at P0.1 (#529) | Low-risk, fully-specced — validates the AI loop; also the forced prerequisite for the P0.5 spike. |

---

## The build engine: `superpowers:subagent-driven-development`

Every phase is built by dispatching a **fresh subagent per task**, with a review gate between tasks.
Fresh context per task is the discipline that keeps an AI honest in a codebase with 600-line file limits
and a coverage ratchet.

**The per-task atom (TDD red-first — Principle III, NON-NEGOTIABLE):**
1. Write the **failing test first** (the test pins intent before any implementation exists).
2. Run it; **watch it fail** for the expected reason: `./bouy exec app pytest <file>::<test> -v`.
   *(Owner practice: `./bouy test --pytest` does not select single files well — use `./bouy exec app pytest` for iteration.)*
3. Write the **minimal** implementation to pass.
4. Run; **green**.
5. Refactor (keep green).
6. **Commit** (frequent, small commits).

Between tasks, subagent-DD runs its own two-stage review. This is the *intra-phase* quality layer.
The *pre-merge* quality layer is the PR Gauntlet.

---

## The PR Gauntlet (THE centerpiece — the machine review that replaces human review)

Run this on **every PR before merge.** It is a multi-phase process; phases 1–2 run on every PR, phases 3–4
run on yellow/red-tier PRs (see Risk Tiers). Express it as a `Workflow` so the lenses run in parallel and
synthesize. **Iterate the build→gauntlet loop until the verdict is clean — only then does it reach the owner.**

**Phase 1 — Static gates (hard pass/fail; no human, no judgment):**
- `./bouy test` — black + ruff + mypy + bandit + pytest + **coverage ratchet** (Principle X). Must be green.
- `./bouy test --xenon` (complexity ≤15) + file-size ≤600 lines (Principle IX).
- `./bouy test --vulture` (dead code), `--safety` / `--pip-audit` (dependency CVEs — matters for every new library).

**Phase 2 — Multi-lens review (parallel agents, every PR):**
- `pr-review-toolkit:code-reviewer` — project conventions, CLAUDE.md, constitution adherence.
- `pr-review-toolkit:silent-failure-hunter` — swallowed exceptions, inadequate fallbacks. **Critical:** Principle XI forbids silent data loss; the threat model (§11) demands every failure is logged + metered.
- `pr-review-toolkit:pr-test-analyzer` — is coverage *adequate* and are edge cases tested (not just line %).
- `pr-review-toolkit:type-design-analyzer` — invariants on new types (envelope, proof, checkpoint, cursor).
- `pr-review-toolkit:comment-analyzer` — doc/comment accuracy vs code.
- `senior-code-reviewer` — holistic security/perf/architecture.
- **HSDS-compliance lens** (Principle II) — federated objects validate against *unmodified* HSDS Pydantic models; envelope fields never leak into the `object`.
- **Constitution lens** — all 15 principles, with explicit attention to the NON-NEGOTIABLEs (I, II, III, VI, X).

**Phase 3 — Adversarial verification (yellow/red-tier; spawn N independent skeptics prompted to REFUTE):**
- Concurrency: *"Show me the interleaving of two reconciler commits that makes a consumer at `_since=N` skip a row."* Default to refuted if uncertain.
- Proofs: *"Show me the forged/rewritten log that still produces a valid inclusion or consistency proof."*
- Corroboration: *"Show me how N peers re-announcing one origin inflates the vote past 1"* (the citogenesis trap, §12.1).
- Owner-guard: *"Show me the federated `Update` that overwrites a `verified_by ∈ {admin,source,claimed}` row."*
- Majority-refute → **block and fix.** Use diverse framings, not N identical prompts.

**Phase 4 — Executable truth (yellow/red-tier; the real assurance):**
- **Hypothesis property tests:** order-shuffle convergence (§12.1 — shuffled arrival → byte-identical Location); proof-tampering must-fail; kill-switch byte-identical-reconciler; cold-start parity.
- **Conformance fixtures** (`fixtures/federation/`) validate; JCS vectors + worked proof pin byte-exactly.
- **In-repo reference second node** completes the phase's golden journey test.
- *(Future, P7 / ongoing:)* a **second independent implementation** (ideally non-Python) reading the same fixtures. Two implementations agreeing on fixtures is worth more than any amount of AI self-review.

**Phase 5 — Synthesis:** one agent collates all findings into a single severity-ranked punch-list + a
merge/no-merge verdict. A build subagent fixes the punch-list; re-run the Gauntlet; repeat until clean.

---

## "Verify the verifier" (the correlated-blindspot safeguard)

If AI both writes and reviews, blind spots can correlate. Mitigations, in priority order:
1. **Minimize hand-rolled crypto/security.** Use vetted libraries (`rfc8785`, `http-message-signatures`, a real Merkle/CT library) wherever they pass the supply-chain vet (`bandit`/`safety`/`pip-audit`). The smaller the hand-written trusted surface, the less AI must get right. Hand-roll *only* the minimal profile when no audited library fits, and pin it with fixtures.
2. **Executable truth over opinion.** Property tests and conformance fixtures catch what review misses; weight Phase 4 above Phases 2–3.
3. **Diversity in review.** Adversarial agents refute (don't confirm); lenses use different framings.
4. **Periodic human/external spot-audit.** For at least the **P1 verifiable-substrate PR**, strongly consider a one-off external security / distributed-systems review (even paid). It is the one place "AI reviewed itself" is genuinely insufficient. Alternatively, seed a known defect and confirm the Gauntlet catches it.

---

## Risk tiers (how much Gauntlet each issue gets)

- **GREEN — AI runs through the gates, Gauntlet phases 1–2, owner does product sign-off.**
  Config, routes, models/migrations, mechanical hooks, docs, dual-env CDK plumbing (has precedent), fixtures.
  Most of P0 (#529–#537), most docs/CLAUDE.md tasks, the CLI (P4 #525).
- **YELLOW — AI builds; Gauntlet phases 1–4; owner skims the synthesis verdict.**
  Reconciler plumbing (§12: corroboration/origin-dedup #523, ON CONFLICT, owner-guard), the enqueuer, ingest, the read endpoints.
- **RED — AI drafts; correctness is property-tested + adversarially verified + (P1) externally spot-audited; owner makes the judgment calls.**
  Dense-sequence concurrency (P0.5 #521 + P1 Task 2), Merkle log / inclusion-consistency proofs / signed checkpoints (P1 #522), CvRDT convergence (P2 #523), inbox verification chain (P3 #524), threat-model completeness (§11). **Never let AI grade its own crypto** — Phase 4 is mandatory here.

---

## The per-phase loop

For each phase issue (P0 is pre-decomposed; P1–P7 are roadmap-only by design):

1. **Expand** (P1–P7 only): turn the roadmap row + v3 DELTA into a bite-sized sibling plan via
   `superpowers:writing-plans` → `docs/superpowers/plans/2026-..-hsds-federation-<phase>.md`. Every task
   opens red-first. The design doc + roadmap + DELTA carry the binding decisions; the bite-sized code is
   written just-in-time against live signatures (avoids stale false-precision).
2. **Owner reviews the plan** (this is judgment-level, which the owner *can* do — "are we building the right thing").
3. **Build** via subagent-driven-development (fresh subagent per task, TDD red-first, two-stage review between tasks).
4. **PR Gauntlet** → iterate until clean.
5. **Owner product sign-off** (not line review) → merge.
6. **Same-PR docs** (Principle XIII): update `CLAUDE.md` (federation subsection + `federation_*` structlog grep targets) and any memory.
7. **Mark the phase issue closed**; its sub-issues should already be closed task-by-task.

**PR strategy:** P0 ships as one PR (plan Task 0.9 opens it). P1+ each ship as one PR per phase (split a large
phase into sub-PRs if it exceeds reviewable/Gauntlet-able size). The Gauntlet runs per PR.

---

## Cross-session machinery (this runs for months)

Durability is the constraint, not cleverness. A fresh session bootstraps from:
- **The issues are the work queue.** `gh issue list --label federation --state open`; pick the next issue
  whose dependencies are met and which is not `blocked:hard-gate` (or whose gate has cleared). Order:
  P0 → (P0.5 memo accepted) → P1 → P2 → P3 → P4; STD-1/STD-2 are permissionless and can run anytime.
- **The design doc + roadmap carry binding decisions** across context resets — cite §-numbers, don't re-derive.
- **CLAUDE.md + the memory files carry operational state.** Update them in the same PR as the code.
- **Each phase writes its own just-in-time plan**, so no session must hold the whole epic in context.

---

## Pending human decisions (the owner's, not AI's)

1. **P0.5 hard-gate go/no-go memo (#521).** After the spike, the owner accepts (or escalates to the §6.2f
   relay/CDC sequencer fallback). **P1–P7 stay `blocked:hard-gate` until this is accepted.**
2. **Recovery-key verify-side rule (#532 / P0.4).** Design §6.1a says the priority *check* ships in v1; the
   plan sequences enforcement to P3. The build follows the plan unless the owner says otherwise.
3. *(Recommended, not blocking)* An external security/distributed-systems spot-audit of the **P1**
   verifiable-substrate PR.

---

## START HERE in the next session

1. Read the six companion artifacts above (constitution → CLAUDE.md → design → plan → epic map → this playbook).
2. `gh issue view 520` (P0) and skim its 9 sub-issues (#529–#537). Confirm you're on the `For-The-Greater-Good`
   gh account for any write (`gh auth switch -u For-The-Greater-Good`; `gitgat` is pull-only).
3. Create the implementation branch off `main`: **`feat/federation-p0-foundations`**.
4. Invoke **`superpowers:subagent-driven-development`** on the plan's **P0 tasks**, beginning with
   **P0.1 (#529)** — config + package skeleton. One fresh subagent per task, TDD red-first.
5. Before opening the P0 PR (plan Task 0.9 / #537), run the **PR Gauntlet** (phases 1–2 suffice for P0's
   green-tier tasks; P0.3 signing #531 gets phase 4 property/vector tests).
6. Owner gives product sign-off → merge P0 → the P0.5 spike (#521) is unblocked next (it needs P0's
   JCS+Ed25519 to measure write-cost). The P0.5 memo is the first true human gate.

**Do not skip the gate that protects users:** TDD red-first + `./bouy test` green + the Gauntlet are how a
solo operator who cannot deep-review the code still ships correct, constitution-clean federation. That is the
whole point of this playbook.
