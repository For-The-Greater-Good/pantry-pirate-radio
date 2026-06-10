# Federation standards-conformance registry

Constitution v1.7.0 (Principle III) requires: **every external standard the
federation code implements MUST appear here** with its official-vector status.
If a standard publishes official test vectors / a reference implementation / a
conformance suite, using them is MANDATORY (vendored under
`tests/test_federation/vendor/<suite>/` with a README pinning source URL + commit
SHA + license). A self-derived oracle is NOT conformance evidence.

**Status legend**
- `vendored:<dir>` — official vectors vendored here and asserted in tests.
- `covered-transitive` — no separate suite needed; the behavior is pinned
  byte-for-byte by another vendored vector that exercises this code path.
- `shape-only` — we implement a small, well-defined slice (a document shape /
  header), no official vector suite applies; pinned by example tests.
- `MISSING:<id>` — official vectors exist and are NOT yet vendored; tracked.
- `cross-ref` — named in comments but not implemented in `app/federation/`.

| Standard | Implemented in | Official vectors? | Status |
|---|---|---|---|
| RFC 8785 (JCS) | `canonical.py:jcs_bytes` | yes (cyberphone suite) | `vendored:jcs_rfc8785/` |
| RFC 6962 (Merkle) | `merkle.py` | yes (transparency-dev) | `vendored:rfc6962_transparency_dev/` |
| RFC 9421 (HTTP Message Signatures) | `signing.py` | yes (Appendix B.2.6) | `vendored:rfc9421_appendix_b/` |
| C2SP signed-note (checkpoint) | `checkpoint.py` | yes (Go `sumdb/note` PeterNeumann) | `vendored:c2sp_sumdb_note/` — reproduced byte-for-byte in `test_checkpoint.py` and anchored as the HSDS-FX `cp-note-go-kat-001` conformance vector |
| W3C Data Integrity `eddsa-jcs-2022` (vc-di-eddsa REC 2025-05-15) | `di_proof.py` (+ `envelope.py` `finalize_with_bytes`/`verify_envelope`) | yes (spec §B.3 vectors; `w3c/vc-di-eddsa@45d646b`) | `vendored:w3c_eddsa_jcs_2022/` — anchored by `test_eddsa_jcs_2022_kat.py`, incl. exact `proofValue` reproduction (`create_proof` regenerates the published proof byte-for-byte; `verify_proof` accepts the signed credential) |
| RFC 8032 (Ed25519) | `signing.py`, `envelope.py`, `checkpoint.py`, `identity.py:load_signing_key` | yes (RFC 8032 §7.1 KAT) | `covered-transitive` via the Go-note + RFC 9421 seed→pubkey→signature KATs — **but** the `load_signing_key` base64-seed branch is not yet pinned to an external seed (tracked: CONF-1) |
| base58btc / multibase / multicodec (`did:key`) | `identity.py:public_key_multibase` (`_b58encode`/`b58btc_encode`/`b58btc_decode`) | yes (W3C did:key `z6Mk…` vectors) | `MISSING:CONF-2` (partially anchored) — the vendored W3C eddsa-jcs-2022 suite now externally exercises the base58btc codec on the load-bearing paths: the `z6Mk…` public-key decode + `z3u2…` secret-key decode (key resolution) and the `proofValue` base58btc encode of a 64-byte signature, all reproduced byte-for-byte by `test_eddsa_jcs_2022_kat.py`. The remaining gap that keeps this row MISSING: the leading-zero-byte edge case (`'1'`-padding round-trip) and the `did:key`-specific multicodec vectors are still pinned only by the self-derived decoder (`test_identity.py`) |
| RFC 7386 (JSON Merge Patch) | `profiles/hsds-ppr/*` (HSDS Profile patches) | yes (RFC 7386 Appendix A) | `MISSING:CONF-4` — patches tested in isolation only; no patch-over-base merge test |
| RFC 3986 (URI generic syntax: `unreserved` set §2.3, percent/case normalization §6.2.2) | `grammar.py:normalize_uri_component` (the §6.2.2 primitive); composed by `grammar.py:normalize_federation_id` | yes (the §6.2.2.1 `%3a`/`%3A` worked example; §6.2.2.2 is rule-only) | `vendored:rfc3986_normalization/` — the §6.2.2 decode-unreserved + uppercase-hex mechanic is anchored to the RFC's one verbatim worked example (+ rule-applications over the §2.3 set) by the dedicated test `test_grammar.py:test_normalize_uri_component_matches_vendored_rfc3986_examples`. (NOT a portable conformance area: tracing a tiny normalized-string output through the generic anchored-honesty check would have re-weakened it, so foreign impls hit the same mechanic via the `federation_id` area's `%2D`/`%3a`/`%41` vectors instead.) WHATWG urltestdata was rejected (its percent-encode sets diverge from RFC 3986 — would false-fail). The `federation_id` *composition* (host:internal-id, reject-raw-reserved) stays PPR-native (interop_pending, row 7) |
| RFC 4343 (DNS case-insensitivity clarification) | `grammar.py:normalize_federation_id` (host ASCII-lowercasing) | no formal vector suite (a clarification RFC) | `shape-only` — host `str.lower()` (NOT casefold) pinned by `test_grammar.py` (incl. the ß→ss must-NOT-collide proof) |
| did:web / did-core | `identity.py` (DID document) | partial / informal | `shape-only` (document-shape example tests) |
| RFC 7033 (WebFinger) | `identity.py` / `routes_public.py` (JRD) | no formal vector suite | `shape-only` |
| ActivityStreams 2.0 / ActivityPub | `identity.py` (actor), `envelope.py` | no machine-checkable conformance suite for our slice | `shape-only` |
| RFC 9530 (Content-Digest) | `signing.py` | no published KAT for the SHA-256 member | `shape-only` |
| RFC 3339 (timestamps) | `envelope.py:published_now` | n/a (format) | `shape-only` |
| HSDS 3.1.1 (data shape) | `aggregate.py` → `LocationResponse` | no strict JSON-Schema conformance suite (the vendored descriptor is a Frictionless tabular descriptor with `additionalProperties` unset — verified to lack discriminating power; CONF-3 rejected) | `covered` via `extra="forbid"` model round-trip |
| RFC 5545 (iCal byday/bymonthday) | `app/utils/ical.py` (not `app/federation/`) | — | `cross-ref` |

> Update this table in the same PR that adds/changes a standard implementation.
> A future CI grep gate (REG-1) can enforce that every standard token in
> `app/federation/*.py` appears in a row above.
