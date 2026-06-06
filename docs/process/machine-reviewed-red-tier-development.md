# Machine-Reviewed RED-Tier Development

A portable process for building high-assurance code with one human and a fleet of
AI agents. Distilled from a federation/crypto build, but the method is
stack-agnostic — swap the examples for your domain. Companion:
[Adversarial Design & Planning](./adversarial-design-and-planning.md) governs the
design phase that precedes this build phase.

The premise: **a solo builder cannot deep-review crypto, concurrency, or
data-integrity code alone, so the machine becomes the reviewer.** The human owns
product judgment, go/no-go, and merges; the agents own the exhaustive adversarial
review the human can't personally perform. Everything below exists to make that
trade safe.

---

## 0. The mandate (non-negotiable)

When this process is invoked, two rules are not optional:

1. **The Gauntlet runs at least once per PR, before merge.** Once per PR is the
   *floor*, not the target — re-run it after any critical or structural
   remediation (§4.6). **No PR merges without a clean (or fully-triaged-and-
   deferred) Gauntlet pass on its final state.** A green test suite and green CI
   are necessary but **not sufficient**: the Gauntlet is a required, independent
   merge gate that sits alongside CI, never in place of it. If the code changed
   after the last Gauntlet, the Gauntlet is stale — run it again on what will
   actually merge.

2. **Multi-agent orchestration is authorized by default and preferred.** Running
   the review (and much of the build) as parallel agent workflows — "ultracode" in
   this project's tooling — is the standing default for substantive work under this
   process, not a special-case escalation. Optimize for the most exhaustive,
   correct result; thoroughness and independent adversarial verification outweigh
   speed and token cost. Reserve solo, single-context work for trivial or purely
   mechanical changes.

These two rules are what make "the machine is the reviewer" real rather than
aspirational. Write them into your project's governing doc so they bind future
contributors (human and agent), not just the person who set the process up.

---

## 1. Roles

- **Operator (human):** product sign-off, scope/go-no-go decisions, and the final
  merge. Does *not* line-by-line review RED-tier internals — that's the machine's job.
- **Builder (main agent):** decomposes work, writes code TDD-first, orchestrates
  the review workflows, triages findings, remediates.
- **Reviewers (sub-agents in workflows):** independent adversarial perspectives —
  review lenses, red-team attackers, completeness critics. Their findings are
  *acted on*, not just filed.

The rule that makes it honest: **the machine review is a merge gate, not a
formality.** A confirmed breach or unremediated high-severity finding blocks the
merge exactly like a failing test.

---

## 2. RED-tier classification

Not all code earns the full treatment — that would be wasteful. Tag modules
**RED-tier** when a defect is (a) hard for a human to catch by reading and (b)
high-blast-radius:

- cryptography / signing / hashing / canonicalization
- concurrency / locking / ordering / idempotency
- data integrity / migrations / canonical-write paths
- money or cost amplification (anything that can run up a bill)
- security boundaries / untrusted-input parsers / auth

Everything else is ordinary-tier: normal TDD + the standard gates. RED-tier adds
the Gauntlet, the conformance machinery, and the per-file floors below.

Write the RED-tier list into your project's governing doc (constitution / CONTRIBUTING)
so it's binding, not folklore.

---

## 3. The core loop: TDD, red-first, reviewed between units

1. **RED** — write the test that encodes the desired behavior; **run it and watch
   it fail.** A test you never saw fail proves nothing.
2. **GREEN** — minimum code to pass.
3. **REFACTOR** — clean up with tests green.
4. **Review between units** — don't batch ten changes then review once. Each
   cohesive unit (a PR-sized task) gets its own review pass.

Prefer a **fresh agent/context per task** (subagent-driven development). A new
context doesn't inherit the builder's blind spots; one-context-iterated work
accumulates them.

---

## 4. The Gauntlet

The centerpiece: a **multi-agent adversarial review** run as a deterministic
workflow against a finished, green PR. **Mandatory at least once per PR before
merge (§0).** Three phases.

### 4.1 Phase 1 — Review lenses (parallel)

N independent agents, each owning **one correctness dimension** of the change
(e.g. "crypto correctness", "concurrency/append", "schema/storage byte-identity",
"API/endpoint", "kill-switch + wiring + isolation", "integration round-trip").
Each lens *adversarially re-reads* its dimension and emits structured findings.
Diversity is the point — a single reviewer (human or agent) shares one set of
assumptions; six lenses with disjoint mandates do not.

### 4.2 Phase 2 — Red-team attackers (parallel)

N agents whose job is to **break it for real, in a sandbox** — not to reason about
whether it's breakable, but to *construct the exploit and run it*: forge a
signature, race the lock to produce a gap, bypass the kill switch, get a parser to
accept a malformed input, make a hook abort its caller. Each reports
`succeeded: true|false` with the actual command output. **Any `succeeded: true` is
a blocking breach.**

"You MUST actually attempt the construction and report the real outcome; do not
merely reason" — put that in the attacker prompt. Reasoned-but-unrun attacks are
worthless.

### 4.3 Phase 3 — Completeness critic

One agent that assumes the lenses and attackers missed something: runs the
**executable truth** (full suite + the conformance vectors + the concurrency test;
report the count), then asks *what is not covered* — an untested guard branch, an
integration seam, an error path, a deferred item that must stay tracked. What it
finds becomes the next round of work.

### 4.4 Structured output

Force machine-parseable results so triage is mechanical, not prose-diving:

```jsonc
// finding (review lens + critic)
{ "severity": "critical|high|medium|low|info",
  "title": "...", "location": "file:line", "claim": "...",
  "evidence": "...", "exploitable": true|false, "recommended_action": "..." }

// attack (red-team)
{ "attack": "...", "attempted": "...", "succeeded": true|false,
  "severity": "...", "evidence": "<real command output>", "recommended_action": "..." }
```

### 4.5 Triage rules

- **`succeeded: true` breach** → blocking. Fix before merge.
- **critical / high** → blocking.
- **medium** → fix if cheap and in-scope; else defer *with a tracked issue*.
- **low / info** → fix-if-trivial or record as a decision (see §8: rejected-on-record).
- A finding tagged `regression: true` (introduced by your own remediation) is
  treated one tier hotter.

### 4.6 Remediate red-first → re-Gauntlet → converge

Fix each real finding **red-first** (write the failing test that reproduces the
defect, then fix). When a fix is structural or a critical, **re-run the Gauntlet**
to confirm it's closed *and that the fix introduced no new defect* — remediation is
where regressions are born. Iterate until the Gauntlet returns only documented
minor/deferred items.

> Real example: a Gauntlet caught a publish hook whose `commit()` ran inside a
> batch job's open savepoint — it would have aborted production runs after one
> iteration. The fix (collect-and-replay after the outer commit) was itself
> re-Gauntleted, which confirmed the savepoint now survives and no new path
> folded the transaction.

---

## 5. Machinery, not memory

The hardest-won principle: **a quality rule that lives only in prose gets skipped.
Encode it as an executable gate.** A doctrine an agent has to *remember* to follow
fails the first time an agent doesn't read that doc.

Concrete gates that transfer to any project:

- **Conformance vectors over self-derived oracles.** When you implement a published
  standard (RFC / W3C / spec), test against the *standard's own* vectors / reference
  / conformance suite — vendored into the repo with pinned source URL + commit +
  license. A test you wrote alongside the implementation shares the
  implementation's blind spot. (A real canonicalization bug shipped green against a
  self-derived "official-looking" test and was caught only by the spec author's
  actual suite.)
- **Byte-identity / round-trip invariants** at every serialization or storage
  boundary: assert `serialize(x) == stored_bytes == reserialize(read_back(x))`.
  This is the class of "ships green because nothing asserts the bytes are stable."
- **Per-file coverage floors in CI** for RED-tier modules — a global average hides
  one module decaying from 95% to 46%. Floor each RED-tier file; fail CI on a drop;
  add a no-vacuous-pass guard (a module silently dropping out of the report must
  fail, not pass).
- **Kill-switch / feature-flag no-op proofs:** if a flag is meant to make a
  subsystem inert, *prove it* — a test asserting zero side effects (no write, no
  network, no signature) when the flag is off, on *every* entry point (the leak is
  always the one entry point nobody added the guard to).
- **A conformance registry** (`tests/<area>/vendor/REGISTRY.md`): one row per
  implemented standard → has-official-vectors? → vendored-path-or-justified-absence,
  plus a CI grep gate that fails if code references a standard not in the registry.
  This makes "did you check for official vectors?" un-missable.
- **Make the doctrine binding:** write all of the above into the governing doc
  (constitution), with a version bump, so a future contributor (human or agent)
  who obeys "follow the constitution" actually inherits the obligation.

If a rule matters, it has a failing build behind it. If it only has a paragraph,
assume it will be violated.

---

## 6. The PR gate (end to end)

```
decompose → per task: [RED test → GREEN → refactor] → review between tasks
   → PR is green locally (full suite + all standard gates)
   → GAUNTLET (review lenses ‖ attackers ‖ critic)      [MANDATORY, ≥1× per PR — §0]
   → triage; remediate red-first; RE-GAUNTLET on critical/structural fixes
   → (Gauntlet clean or fully triaged on the FINAL state)
   → push; CI green (the authoritative gate — alongside, never instead of, the Gauntlet)
   → operator reviews + merges
```

Keep each PR a single well-scoped unit. Resolve base-branch conflicts before the
final gate (a conflicted PR can't even produce a meaningful CI signal). Merge only
on green; if a branch-protection ruleset requires a review the author can't supply,
that's the operator's call — surface it, don't quietly force it.

---

## 7. Cost discipline

A workflow can spawn dozens of agents; that is real money. Under this process,
multi-agent orchestration is authorized-by-default (§0) — the opt-in gate is at the
level of *invoking the process at all*, not each individual workflow. Once you're
in, orchestrate freely; just spend deliberately:

- **Scale to risk.** "find any bugs" → a few lenses, single-vote verify.
  "thoroughly audit this RED-tier crypto" → a full lens panel + multi-vote
  adversarial attackers + a critic.
- **Reject ceremony, on the record.** A gate that adds CI minutes or flakiness for
  a defect class that *cannot occur here* is a net negative. When you decline a
  proposed gate, write down *why* (see §8) so it reads as a decision, not an
  oversight.

---

## 8. Decisions on the record

Every audit/Gauntlet produces a "considered and rejected" set — gates and tests
deliberately *not* added. **Record them with the reason.** A future reviewer
finding no schema-drift gate should see "rejected: the table is created by SQL only;
the ORM name never materializes; the defect class can't trigger" — not wonder if it
was forgotten. Rejections are first-class output.

Likewise, deferred work (P2/later-phase hardening, archive paths, follow-on
gates) gets a tracked issue immediately, quoted from the finding, so it survives
the context window.

---

## 9. Anti-patterns this prevents

- **Self-graded crypto.** An implementation + a same-author test pass each other
  while both misread the spec. → conformance vectors (§5).
- **Ships-green serialization bugs.** No test asserts the stored bytes equal the
  signed bytes; an extreme value diverges silently. → byte-identity invariants (§5).
- **The one unguarded entry point.** The kill switch covers `append` but not the
  *other* thing that signs. → no-op proofs on every entry (§5).
- **Remediation regressions.** A fix for finding A introduces finding B. →
  re-Gauntlet after structural/critical fixes (§4.6).
- **Doctrine drift.** A great quality rule lives in a doc nobody re-reads. → make
  it an executable gate (§5).
- **Coverage-average masking.** One file rots inside a healthy aggregate. →
  per-file floors (§5).
- **Transaction folding / fail-soft poisoning.** A "side" hook commits or aborts
  the caller's transaction. → run side effects after the resource commit; on
  failure, roll back so the caller's session survives; prove it with a test (§4.6).

---

## 10. Adapting to your stack

- Swap the **review lenses** for your risk dimensions (e.g. for a payments system:
  idempotency, money-rounding, reconciliation, webhook-replay, PII).
- Swap the **attackers** for your threat model (replay, double-spend, injection,
  privilege escalation).
- Swap the **conformance vectors** for whatever standards you implement (or, if
  none, drop that gate and say so on the record).
- Keep the **shape**: parallel lenses → real in-sandbox attackers → completeness
  critic → structured findings → red-first remediation → re-Gauntlet → green CI →
  human merge.
- Keep the **mandate (§0)**: the Gauntlet runs at least once per PR before merge,
  and multi-agent orchestration is the authorized default. Those two are what make
  the whole thing trustworthy when you carry it to a new repo.

---

## Appendix — Gauntlet workflow skeleton (pseudocode)

```js
// Phase 1: parallel review lenses, each adversarial on one dimension
const reviews = await parallel(LENSES.map(l => () =>
  agent(CTX + lensPrompt(l), { phase: 'Review', schema: FINDING_SCHEMA })))

// Phase 2: parallel attackers — MUST run the exploit in a sandbox
const attacks = await parallel(ATTACKS.map(a => () =>
  agent(CTX + attackPrompt(a) + ' Actually attempt it in-container; report the real outcome.',
        { phase: 'RedTeam', schema: ATTACK_SCHEMA })))
const breaches = attacks.filter(a => a.succeeded)   // any => blocking

// Phase 3: completeness critic — runs the executable truth, finds the gaps
const critic = await agent(CTX + criticPrompt, { phase: 'Critic', schema: FINDING_SCHEMA })

return { reviews, attacks, breaches, critic }
```

Findings flow back to the builder, who fixes red-first and re-runs until clean.
The human reads the synthesis, not the file dumps — and decides the merge.
