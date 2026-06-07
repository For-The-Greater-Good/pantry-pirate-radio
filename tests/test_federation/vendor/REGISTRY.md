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
| RFC 8032 (Ed25519) | `signing.py`, `envelope.py`, `checkpoint.py`, `identity.py:load_signing_key` | yes (RFC 8032 §7.1 KAT) | `covered-transitive` via the Go-note + RFC 9421 seed→pubkey→signature KATs — **but** the `load_signing_key` base64-seed branch is not yet pinned to an external seed (tracked: CONF-1) |
| base58btc / multibase / multicodec (`did:key`) | `identity.py:public_key_multibase` (`_b58encode`) | yes (W3C did:key `z6Mk…` vectors) | `MISSING:CONF-2` — hand-rolled encoder currently pinned only by a self-derived decoder (`test_identity.py`); vendor W3C vectors incl. a leading-zero-byte case |
| RFC 7386 (JSON Merge Patch) | `profiles/hsds-ppr/*` (HSDS Profile patches) | yes (RFC 7386 Appendix A) | `MISSING:CONF-4` — patches tested in isolation only; no patch-over-base merge test |
| RFC 3986 (URI generic syntax: `unreserved` set §2.3, percent/case normalization §6.2.2) | `grammar.py:normalize_federation_id` | yes (WHATWG urltestdata.json / RFC §6.2.2 worked examples) | `MISSING:CONF-5` — the percent-decode-unreserved + uppercase-hex + host-lowercase mechanics are pinned by `test_grammar.py` example + Hypothesis property tests (incl. a per-256-octet decode check) today; vendor the WHATWG/RFC normalization corpus as `vendor/rfc3986_normalization/` and split an anchored sub-area (a natural sibling of the JCS anchor). The `federation_id` *composition* itself is PPR-native (interop_pending, row 7) |
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
