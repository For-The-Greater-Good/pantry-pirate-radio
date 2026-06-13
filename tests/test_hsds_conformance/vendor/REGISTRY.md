# HSDS standards-conformance registry

Constitution v1.7.0 (Principle III) requires: **every external standard the
codebase implements MUST appear in a registry like this one** with its
official-vector status. If a standard publishes official test vectors / a
reference implementation / a conformance suite, using them is MANDATORY
(vendored under `tests/test_hsds_conformance/vendor/<suite>/` with a README
pinning source URL + commit SHA + license). A self-derived oracle is NOT
conformance evidence.

**Status legend**
- `vendored:<dir>` — official vectors vendored here and asserted in tests.
- `MISSING:<id>` — official vectors exist and are NOT yet vendored; tracked.

| Standard | Implemented in | Official vectors? | Status |
|---|---|---|---|
| HSDS 3.1.1/3.2.3 (Human Services Data Specification) official worked examples | `app/models/hsds/response.py` (`OrganizationResponse`, `ServiceResponse`, `LocationResponse`, `ServiceAtLocationResponse`, + future `TaxonomyResponse`/`TaxonomyTermResponse`) | yes (`docs/HSDS/examples/*.json` + `examples/csv/*.csv`, Open Referral `specification` repo) | `vendored:hsds_official_examples/` — Tier A (`model_validate` under `extra="forbid"`) + Tier B (RFC 8785 JCS round-trip byte-equality via `app/federation/canonical.py:jcs_bytes`) asserted by `test_tier_a_representation.py` / `test_tier_b_roundtrip.py`. Submodule-pin drift guard: `test_submodule_pin_guard.py`. Shrink-only xfail ratchet: `xfail_manifest.json` + `test_xfail_manifest_ratchet.py`. Today every fixture in `FIXTURE_MODEL_MAP` (`_fixture_map.py`) fails both tiers (G1 baseline, issue #593); later HSDS-completeness-epic slices (G3, T1, L1-L7, S1-S5, O1-O4, A1, ...) flip rows as the models grow. |

> Update this table in the same PR that adds/changes a vendored HSDS
> conformance suite under `tests/test_hsds_conformance/vendor/`.
