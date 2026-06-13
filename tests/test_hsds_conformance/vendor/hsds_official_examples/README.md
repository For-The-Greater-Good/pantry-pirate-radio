# Vendored HSDS official worked examples

These files are the **official worked examples** published by the Open
Referral project as part of the Human Services Data Specification (HSDS).
They are an **external** conformance anchor for PPR's HSDS response models
(`app/models/hsds/response.py`) — used by
`tests/test_hsds_conformance/test_tier_a_representation.py` (Tier A:
`model_validate` against the official example) and
`tests/test_hsds_conformance/test_tier_b_roundtrip.py` (Tier B: RFC 8785 JCS
round-trip byte-equality of `model_dump(mode="json", by_alias=True,
exclude_none=True)` vs the example, via `app/federation/canonical.py:jcs_bytes`).

Per constitution Principle III ("machinery, not memory"), a self-derived oracle
written alongside the implementation is NOT conformance evidence — these
examples come from the spec itself, independent of PPR's models.

## Source and provenance

- **Source repo:** https://github.com/openreferral/specification.git
- **Pinned commit:** `74fcf85b0534fd8c6e61eae13d246b4b375a4495` (tag **v3.2.3**)
- **Vendored from:** the `docs/HSDS` git submodule in this repository, checked
  out at the pinned commit above.
- **Retrieved:** 2026-06-13.
- **License:** Creative Commons Attribution-ShareAlike 4.0 International
  (CC BY-SA 4.0) — see `docs/HSDS/LICENSE` ("The Human Services Data
  Specification (HSDS) and associated documentation are licensed under the
  Creative Commons Attribution Share-Alike 4.0 license."). Vendored verbatim,
  solely as test fixtures, with attribution.

## Drift guard

`tests/test_hsds_conformance/test_submodule_pin_guard.py` reads the LIVE
`docs/HSDS` submodule HEAD (`git -C docs/HSDS rev-parse HEAD`) and asserts it
equals the pinned commit above. If the submodule is bumped, re-vendor these
files from the new commit (byte-exact `cp`, including re-resolving the
`examples/csv/datapackage.json` symlink — see below) and update the pin in
BOTH that test and this README. The test FAILS (does not skip) if the
submodule is missing or unreadable — drift must be loud.

## What's vendored

Verbatim, byte-exact copies (`cp -p`) of:

- `docs/HSDS/examples/*.json` (13 files): `base.json`, `location.json`,
  `organization_full.json`, `organization_list.json`, `service_full.json`,
  `service_list.json`, `service_at_location_full.json`,
  `service_at_location_list.json`, `taxonomy.json`, `taxonomy_list.json`,
  `taxonomy_term.json`, `taxonomy_term_list.json`, `tabular.json`.
- `docs/HSDS/examples/csv/*.csv` (24 files) → `csv/`.
- `docs/HSDS/examples/csv/datapackage.json` is a **symlink** to
  `../../datapackage.json` (the repo-root HSDS datapackage descriptor, ~134 KB).
  We vendor a **resolved, real copy** of that target file at `csv/datapackage.json`
  (NOT a dangling symlink — symlinks do not survive `cp` into a different tree
  reliably, and a dangling link would silently break any test that opens it).

`docs/HSDS/examples/make_datapackages.py` (a generator script, not a fixture)
is intentionally NOT vendored.

## What each tier asserts

- **Tier A (`test_tier_a_representation.py`)** — `model_validate(example)`
  succeeds against the mapped response model with `extra="forbid"` kept (the
  ratchet — `HSDSBaseModel.model_config["extra"] = "forbid"`, see
  `app/models/hsds/base.py`). A fixture passes Tier A only when our model
  accepts every field the official example carries and requires nothing it
  lacks.
- **Tier B (`test_tier_b_roundtrip.py`)** — having passed Tier A,
  `jcs_bytes(model.model_dump(mode="json", by_alias=True, exclude_none=True))
  == jcs_bytes(example)`. Byte-equality is computed AFTER RFC 8785
  canonicalization, so key ordering / number formatting differences alone are
  not failures — only genuine content differences (missing, extra, or
  differently-shaped fields/values) are.
- `base.json` and `tabular.json` are **corpus presence only** — no response
  model maps to either (`base.json` is the `@context`-style version/profile
  descriptor; `tabular.json` is a CSV-table dump), so neither is exercised by
  Tier A or Tier B. They remain vendored for future use (e.g. Z2's tabular
  gate).

## Current conformance state (G1 baseline)

As of this vendoring (G1, issue #593), **every** entity and list fixture in
`FIXTURE_MODEL_MAP` (`tests/test_hsds_conformance/_fixture_map.py`) FAILS both
tiers — PPR's response models are deliberately thin subsets of full HSDS, and
`TaxonomyResponse`/`TaxonomyTermResponse` do not exist yet. Each failing
`(fixture, tier)` pair is recorded as a `strict=True` xfail row in
`tests/test_hsds_conformance/xfail_manifest.json`. Each later phase of the
HSDS full-compliance epic flips specific rows by extending the models — see
`docs/superpowers/plans/2026-06-10-hsds-full-compliance.md` for the phase map
(G3, T1, L1-L7, S1-S5, O1-O4, A1, ...).

## Deferred-3.1 carve-out (owner decision D4)

Two fields appear in the `*_full.json` examples that are HSDS v3.1 additions
PPR has NOT yet decided to expose: `additional_websites`
(`organization_full.json`) and `additional_urls` (`service_full.json`). These
remain part of their fixtures' `xfail_manifest.json` rows EVEN AFTER the rest
of a fixture's gaps are otherwise closed by a later slice (O4 / S5), until
owner decision **D4** resolves whether/how to expose them. This is a narrow,
documented carve-out for these two specific fields — NOT a general
strip-list, and NOT a reason to relax `extra="forbid"`.
