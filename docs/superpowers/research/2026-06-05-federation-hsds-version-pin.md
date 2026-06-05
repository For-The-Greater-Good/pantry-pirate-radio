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

But the live code — verified on this branch — implements **3.1.1, not 3.2.3**:

- `app/models/hsds/response.py::LocationResponse` (and the schedule/service models) **lack** the 3.2
  additions `additional_websites`, `additional_urls`, and the Location-level `attributes` block.
- `app/core/config.py` advertises `FEDERATION_HSDS_VERSIONS = ["3.1.1"]` (line 263).

These conflict. Principle II (HSDS Specification Compliance — **NON-NEGOTIABLE**) requires that federated
`object`s validate against the *unmodified* HSDS Pydantic models. Emitting `@context: …/3.2` over a
3.1.1-shaped object is therefore not allowed — a conformance fixture (Task 11) would have to either ignore
the mismatch (defeating its purpose) or fail on it.

## Options

**(a) Implement the 3.2 model fields first, then pin 3.2.**
Add `additional_websites`, `additional_urls`, `attributes` (and the metadata block) to the HSDS Pydantic
models so they genuinely emit 3.2, then advertise 3.2 everywhere. This is the design's literal intent.
*Cost:* it expands P1 and folds a non-trivial HSDS-modeling change into a phase whose risk profile is
crypto + concurrency (the verifiable substrate). It mixes two unrelated review surfaces and delays the
substrate. The 3.2 fields would also need real producers (scrapers/validator) to be more than empty
columns, which is out of P1 scope.

**(b) Pin `@context` / Profile / `fixtures/` to 3.1.1 for P1. — CHOSEN**
Advertise what the models actually emit. Smaller, truthful, and unblocks the substrate now. Implementing
the 3.2 model fields becomes a clean, separate follow-up (and aligns with STD-2's upstream
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
moment** someone bumps `FEDERATION_HSDS_VERSIONS` to 3.2 without first implementing the 3.2 fields on the
models (or implements the fields without advertising them). The decision is therefore enforced by CI, not
just documented here.

## Follow-up (separate from P1)

Implement HSDS 3.2 on the Pydantic models (`additional_websites`, `additional_urls`, `attributes`, metadata
block) with real producers, then flip `FEDERATION_HSDS_VERSIONS` to include 3.2 and re-freeze the fixtures.
The guard test will go green on the new branch only once both sides agree.
