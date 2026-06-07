# HSDS-FX canonical conformance suite

The vectors that turn HSDS-FX from "PPR's implementation" into "a standard anyone
can implement against." Design refs: `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md`
§8.5a (the suite) + §8.6 (packaging). Tracking: #540 (extraction/governance),
#565 (published packages), #558 (two-node interop), #522 (P1).

## Layout

- `vectors/<area>.json` — the language-agnostic source of truth: one manifest per
  normative wire element (§8/§7/§6.2-6.3/§9). **Pure JSON, no code** — a foreign
  implementation in any language runs these through the adapter contract with zero
  dependency on PPR. Expected values are byte-as-hex / canonical-base64 / JSON
  shapes; crypto seeds/keys are hex.
- `manifest.schema.json` — the JSON Schema each manifest satisfies (accept vectors
  carry `expected`; `must_reject` vectors do not).
- `VERSION` — the corpus SemVer, independent of the PPR app version.
- `generate.py` — **repo-local** regeneration tool: recomputes the corpus from the
  reference implementation (`app/federation/`) so it can never silently drift from
  what the node actually signs. `--check` fails CI on drift. This is the one file
  here that couples to `app/`; it does **not** ship in the published vectors
  package.

The pytest harness (the runner + the reference adapter) lives at
`tests/test_federation/conformance/` because it is pytest-bound today; the runner
imports only the adapter Protocol (portability-gated), and `RefAdapter` is the only
sanctioned `app.federation` coupling. On extraction (#540), `vectors/` ships
verbatim as the published vectors package and the runner becomes the SDK's
`hsdsfx verify`.

## Anchoring policy (anti-self-grading — constitution v1.7.x)

Each manifest declares `interop_status`:

- **`anchored`** — the expected bytes derive from a vendored upstream conformance
  suite (`tests/test_federation/vendor/`: JCS RFC-8785, RFC-6962 transparency-dev,
  C2SP Go `sumdb/note`, RFC-9421). The corpus references those, it does not
  re-author them. Genuinely externally validated.
- **`interop_pending`** — a PPR-native canonical reading: the **new** HSDS-FX
  composition (envelope assembly + content-address + proof, `federation_id`
  grammar, the `/export` row shape, the Tombstone shape). These are pinned **by
  fiat** and CANNOT be self-validated — only a second independent implementation
  (#558 two-node loop, #565 non-PPR SDK, the live partner) finally settles them.
  Each carries `interop_pending: true` + an `interop_row` pointer into
  `tests/test_federation/vendor/INTEROP_PENDING.md`.

The runner's report **separates** anchored from interop-pending passes. **Do not
present this suite to the Open Referral TC as "conformance-proven" until ≥1
non-PPR adapter passes the interop-pending areas** — until then it is "PPR's CI
gate + a candidate spec," exactly the §8.5a impl-first sequencing.

The `anchored` label is **machine-enforced**, not honor-system: a test asserts
every `anchored` area names a real `vendor/<suite>/` in `derives_from` AND that at
least one of its byte values appears verbatim in that vendored suite
(`test_anchored_areas_actually_trace_to_a_vendored_suite`). The corpus is also
**closed-world** — `generate.py --check` and a pytest gate both fail on any
`vectors/*.json` the generator does not produce, so a hand-authored manifest
cannot be smuggled in (the runner globs every `*.json`).

## Status

Areas present (6):

| Area | `interop_status` | Anchor |
|---|---|---|
| `envelope_content_address` | `interop_pending` | INTEROP_PENDING.md (envelope wire shape) |
| `envelope_proof` | `interop_pending` | INTEROP_PENDING.md (proof.type + verificationMethod + sig) |
| `envelope_assembly` | `interop_pending` | INTEROP_PENDING.md (10-key field set; license-in-band) |
| `checkpoint` | `interop_pending` (per-vector mixed) | Go `sumdb/note` KAT anchored (`cp-note-go-kat-001`); body PPR-native |
| `export_wire` | `interop_pending` | INTEROP_PENDING.md (the `/export` row shape + leaf definition) |
| `merkle_inclusion` | **`anchored`** | `vendor/rfc6962_transparency_dev` (inclusion proofs, verbatim) + root-equality teeth |

Forthcoming: `federation_id` grammar (interop-pending; needs a reference
normalizer — owner decision A), activity/Tombstone (interop-pending), a direct
`canonicalize` (JCS) area anchored to `vendor/jcs_rfc8785`.
