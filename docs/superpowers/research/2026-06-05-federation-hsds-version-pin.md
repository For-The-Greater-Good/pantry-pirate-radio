# HSDS Federation P1 — HSDS Version-Pin Decision Memo

**Date:** 2026-06-05
**Phase issue:** #522 (P1 — Verifiable publish)
**Task:** P1 Task -1 (decision gate, first in PR-A #549)
**Decision required:** which HSDS version do the federation `@context` / Profile / `fixtures/` pin to?
**Decision:** **Option (b) — pin 3.1.1 honestly for P1.** (Owner-confirmed on #522; recorded here.)

## The conflict

The design of record (`specs/2026-06-03-hsds-federation-core-design.md` §7, §8.5; living-plan v3.1 DELTA;
epic #522) reads as pinning the published `@context` / Profile / conformance fixtures to the **HSDS 3.2
line** (the vendored submodule baseline is v3.2.3).

But the live code — verified on this branch — exposes a deliberately **flattened, curated subset** of the
HSDS Location shape, advertised honestly as **3.1.1**:

- `app/models/hsds/response.py::LocationResponse` (and the schedule/service models) omit a number of HSDS
  fields — e.g. the core HSDS `attributes` extensibility block (present on `docs/HSDS/schema/location.json`),
  plus org/service fields like `additional_websites` (HSDS `organization`, added v3.1) and `additional_urls`
  (HSDS `service`, added v3.1). (NB: these are *not* "3.2 Location additions" — v3.2 added no new Location
  schema fields; they're simply HSDS fields PPR's curated model does not expose. The point is that the model
  is a subset, not which release each omitted field traces to.)
- `app/core/config.py` advertises `FEDERATION_HSDS_VERSIONS = ["3.1.1"]` (line 263).

These conflict. Principle II (HSDS Specification Compliance — **NON-NEGOTIABLE**) requires that federated
`object`s validate against the *unmodified* HSDS Pydantic models. Advertising `@context: …/3.2` over this
curated-subset object is therefore not allowed — a conformance fixture (Task 11) would have to either ignore
the mismatch (defeating its purpose) or fail on it.

## Options

**(a) Expand the models to fuller HSDS coverage first, then advertise 3.2.**
Add the omitted HSDS fields (the `attributes` block; org/service fields like `additional_websites` /
`additional_urls` on their proper entities) to the Pydantic models so the published objects genuinely cover
the 3.2.x line, then advertise 3.2 everywhere. This is the design's literal intent.
*Cost:* it expands P1 and folds a non-trivial HSDS-modeling change into a phase whose risk profile is
crypto + concurrency (the verifiable substrate). It mixes two unrelated review surfaces and delays the
substrate. Those fields would also need real producers (scrapers/validator) to be more than empty columns,
which is out of P1 scope.

**(b) Pin `@context` / Profile / `fixtures/` to 3.1.1 for P1. — CHOSEN**
Advertise what the models actually emit. Smaller, truthful, and unblocks the substrate now. Expanding the
models to fuller HSDS coverage becomes a clean, separate follow-up (and aligns with STD-2's upstream
`last_modified`/tombstone work). The P1 wire spec, JSON Schema, and `fixtures/federation/` all freeze
against 3.1.1; a later 3.2 bump is an additive, independently reviewable change.

## Decision and rationale

**Pin 3.1.1 (option b).** Truth over aspiration: federation's whole value proposition is *verifiable*
publish — advertising a version the bytes don't satisfy would undermine that on day one, and would violate
Principle II. P1 ships the verifiable substrate against honest 3.1.1 fixtures; the 3.2 model implementation
is filed as a separate follow-up to be done before (or alongside) any future 3.2 `@context` bump.

## Consumed by

- **Task 3 / Task 7 / Task 11** read the pinned value: `@context` host + version, Profile URI, and the
  `fixtures/federation/` vectors all freeze to 3.1.1. Nothing in P1 freezes the `@context`/Profile/fixtures
  until this memo's decision is in force — it now is.
- `FEDERATION_HSDS_VERSIONS` stays `["3.1.1"]` in `app/core/config.py`; `FEDERATION_PROFILE_URI` stays as-is.

## Regression lock

`tests/test_federation/test_hsds_version_pin.py::test_advertised_hsds_version_matches_model_shape` is the
durable guard. It passes today (both the models and the advertised version say 3.1.1) and **fails the
moment** someone bumps `FEDERATION_HSDS_VERSIONS` to 3.2 while `LocationResponse` is still the curated
subset (or expands the model toward fuller HSDS coverage without revisiting the advertised version). The
decision is therefore enforced by CI, not just documented here.

## Follow-up (separate from P1)

Expand the Pydantic models to fuller HSDS coverage (the `attributes` block; org/service fields like
`additional_websites` / `additional_urls` on their proper entities; the metadata block) with real
producers, then flip `FEDERATION_HSDS_VERSIONS` to include 3.2 and re-freeze the fixtures. The guard test
will go green on the new branch only once both sides agree.

A pre-existing inaccuracy worth folding into that follow-up: `app/core/config.py` (the
`FEDERATION_HSDS_VERSIONS` comment, ~L261-262) calls these the "decisive 3.2 fields," carrying the same
mislabel corrected above; tidy it when the models are expanded.
