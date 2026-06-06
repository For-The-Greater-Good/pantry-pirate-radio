# Adversarial Design & Planning

A portable process for **designing** a hard system before you build it — the
companion to [Machine-Reviewed RED-Tier Development](./machine-reviewed-red-tier-development.md)
(which governs the build). Distilled from designing a federation/crypto epic, but
the method is domain-agnostic.

The premise: **spend heavily on design and review now to save far more effort —
and avoid production failures — later.** A few days of adversarial design review
and a throwaway spike are cheap next to shipping the wrong architecture, or a
correct-looking one that fails the first time it meets reality. Reviews run
*constantly*, not once at the end.

The other premise, equally load-bearing: **the human is in the loop throughout, but
is never asked to understand the implementation.** They own judgment — scope, risk
appetite, product behavior, go/no-go — and the machine owns mechanism. So every
question put to them is framed in approachable, outcome-level terms (§4).

---

## 1. Artifacts

Keep design state in a small, stable set of documents:

- **Design-of-record** — the normative spec: the wire formats, the data model, the
  trust/threat model, the activity semantics. The single source of truth a
  partner could implement against. Carries a **versioned amendment log** at the top
  so the design's *history and rationale* are legible (why v3 chose X over Y).
- **Living plan** — the phased task breakdown that turns the design into PRs. Tasks
  are sized to one Gauntlet-able PR each, ordered by dependency, with risk tier
  tagged.
- **Epic / tracker** — the issue that links them and tracks phase status.
- **Spec-cache / fixtures** — pinned byte-format vectors and worked examples (see
  §5), so the design is *executable*, not just prose.

Versioning the design (v1 → v2 → v3 …) with an amendment log is what lets review be
continuous: each pass produces a new version with its corrections folded in and
attributed.

---

## 2. The design Gauntlet — review the DESIGN, not just the code

Before a line is built, the design itself goes through the same adversarial,
multi-perspective treatment the code will (the build Gauntlet). Run **panels of
independent lenses** over the design and fold the blockers back in, iterating to a
new version. The lenses that paid off here:

- **Constitution / first-principles** — does it violate a standing project
  invariant? (Caught: "no new logic needed" was false — there *was* an integration
  contract that had to be specified.)
- **Completeness** — what's unspecified, hand-waved, or "just works"? (Caught: a
  "plain ingestion just works" claim that did not.)
- **Partner / implementability** — could an outsider build against this from the
  spec alone? Forces the wire format to be normative.
- **Threat model / security** — enumerate the attacks; each becomes a v1 requirement
  (SSRF, cost-amplification, injection, equivocation, rogue-peer recovery).
- **Ecosystem / standards research** — *don't design in a vacuum.* A live scan of
  the surrounding ecosystem ("is anyone already doing this? what vocabulary do they
  use?") prevents duplicating a standard or freezing field names you'll have to
  rename. Align, don't reinvent.

Then a distinct pass that is **steelman, not bug-hunt**: a panel that tries to make
the design *stronger and more ambitious in the one way that compounds* (here:
verifiability), rather than only finding flaws. Bug-hunting hardens; steelmanning
raises the ceiling. Do both, in that order.

Every pass ends at an **owner decision point** (§4), not an agent fait accompli.

---

## 3. De-risk the riskiest assumption first (a throwaway spike)

Identify the single assumption that, if wrong, breaks the whole plan — and prove it
*before* committing the design. Build a **throwaway spike** that exercises exactly
that risk against reality (real DB, real concurrency, real volume), get a clear
**GO / NO-GO**, and write the result into the plan. Then throw the spike away and
build it properly with tests.

> Worked example: the riskiest assumption was that a dense, gapless sequence could
> be assigned under a short advisory lock without serializing the main write path.
> A spike proved the exact lock shape **GO** under real concurrency before the plan
> depended on it. (It also surfaced the caveats — re-confirm throughput at real
> volume — which became tracked plan items.)

A spike is cheap insurance on the most expensive possible mistake.

---

## 4. Owner decision points — judgment to the human, mechanism to the machine

This is the heart of keeping a non-implementer human meaningfully in control.

**Bring to the human** (they own these):
- scope and phasing ("ship A now, defer B?"), go/no-go, priorities
- risk appetite and irreversible/expensive trade-offs (cost, blast radius, security posture)
- product behavior and policy ("serve low-confidence data with a caveat, or hide it?")
- naming, positioning, external/partner-facing choices
- anything genuinely ambiguous in their request

**Decide yourself** (mechanism — do *not* make them adjudicate):
- algorithms, data structures, lock shapes, byte formats, library choices
- whether the crypto/concurrency is *correct* (that's the Gauntlet's job, not theirs)
- test design, refactors, conventional defaults

**How to ask — approachably (non-negotiable):**
- Frame the question in **outcomes and trade-offs**, never implementation. "Do we
  optimize for the cheapest path or the most-thorough audit?" not "should we use a
  CvRDT origin-dedup?"
- Offer **2–4 concrete options**, each with a plain-language description of what it
  means and its consequence; **lead with a recommendation** and say why.
- Make **"defer to your default" easy** — if they don't have an opinion, your
  recommended option proceeds.
- Reserve questions for where the answer **changes what you do**. Don't ask to
  offload work or to seem diligent; don't ask them to grade a proof.
- When you made a reversible mechanism choice on your own, **state it in one line**
  and move on — visibility without a quiz.
- After a hard call, record it (with the rationale) in the amendment log / decision
  record so it isn't re-litigated and survives the context window.

The test: a smart non-engineer should be able to answer every question you ask them
without opening the code.

---

## 5. Conformance-first / pin the bytes before you build

If the system implements a standard or a wire format, **pin the exact bytes with
vendored official vectors during design**, not after. Canonicalization ambiguity is
the classic interop graveyard; pinning a worked example + the standard's own
conformance vectors in the spec-cache turns "we think this is right" into "any
conformant peer reproduces this byte-for-byte." This is the design-time half of the
build process's "machinery, not memory" (conformance vectors over self-derived
oracles).

Where two valid readings of a spec exist and the vectors don't settle it, **pin
your reading in a fixture and flag it as interop-pending** — only a second
implementation (or the real external feed) resolves it later; track it explicitly
so it isn't silently assumed.

---

## 6. Cost is a first-class design constraint

Design for the bill, not just for correctness. If the project can be killed by
cost (a runaway build, an unbounded scan, a per-request fan-out), that constraint
shapes the architecture as hard as any functional requirement — and it's an
explicit owner trade-off (§4), surfaced in plain terms ("this option adds ~$X per
run; the cheaper one is slower — which do you want?").

---

## 7. Phasing — each phase stands alone and is killable

Decompose the epic so that **every phase is independently shippable, independently
valuable, and reversible** — gated behind a kill switch / feature flag, with a clean
no-op when off. This lets you ship incrementally, get real feedback, and back out a
phase without unwinding the rest. The first phase that delivers a *real external
edge* (a live partner, a usable artifact) is worth pulling earlier than its
"logical" order — a running reference beats a finished spec.

---

## 8. Hand-off to the build

When a phase's design is settled and de-risked, it enters the build process: each
task is TDD red-first, each PR runs the **Gauntlet at least once before merge**, and
multi-agent orchestration is the default. Design review and build review are the
same discipline applied at two altitudes — **continuously, never once.** See the
companion doc.

---

## 9. Anti-patterns this prevents

- **Designing in a vacuum** — reinventing a standard, or freezing vocabulary you
  must later rename. → ecosystem-signals research (§2).
- **Committing the plan on an unproven assumption** — discovering the core mechanism
  doesn't work after building three phases on it. → de-risk spike (§3).
- **Asking the human to adjudicate mechanism** — "should the Merkle leaf be
  0x00-prefixed?" They can't, shouldn't, and will rubber-stamp. → §4 framing.
- **Silent designer decisions on product/policy** — quietly choosing user-facing
  behavior the operator owns. → bring it to them, approachably (§4).
- **Bug-hunt-only review** — a technically-correct design that's unambitious where
  ambition compounds. → the steelman pass (§2).
- **Prose-only rigor** — a great design rule that never becomes an executable gate.
  → pin bytes + fixtures at design time (§5), enforce them in the build.

---

## 10. Adapting to your domain

- Swap the **design lenses** for your risk dimensions (payments: settlement,
  idempotency, reconciliation, regulatory).
- Swap the **riskiest-assumption spike** for whatever would sink *your* plan.
- Keep the **shape**: versioned design-of-record → multi-lens adversarial passes +
  a steelman → de-risk spike → owner decision points (asked approachably) →
  conformance-pinned, cost-aware, phased plan → hand off to the per-PR Gauntlet.
- Keep the two non-negotiables: **review constantly** (design and build), and **the
  human is asked throughout but never asked to understand the implementation.**
