# Federation wire-format readings pinned BY FIAT (interop-pending)

The vendored KATs (`jcs_rfc8785/`, `rfc6962_transparency_dev/`,
`rfc9421_appendix_b/`, the Go `sumdb/note` checkpoint) anchor JCS, the Merkle
tree, the HTTP-signature, and the checkpoint *format*. But several **envelope
wire-shape** decisions are settled only by our own reading of the spec — there is
no cross-implementation anchor yet. Two valid readings would both pass our suite;
only interop with a second implementation (the PR-D reference node / the live
Feeding America feed at P2) can settle them.

Each row is tagged `@pytest.mark.interop_pending` in the suite, so
`pytest -m interop_pending --co -q` is the **P2 re-validation checklist**.

| # | Pinned reading | Where | Spec basis | Confirmed by |
|---|---|---|---|---|
| 1 | Integers serialized via `str(int)` (diverges from a double-based JCS peer above 2^53) | `envelope.py:build_preimage`; `canonical.py` | RFC 8785 number domain | P2 ingest of a foreign object carrying a large integer |
| 2 | `license` rides INSIDE the signed pre-image (in-band) | `envelope.py:build_preimage` | design m1 / mesh-resilience 2026-06-06 | a peer verifying our relayed object's license binding |
| 3 | Envelope top-level field set + key names (`@context,type,actor,attributedTo,origin,federation_id,object,published,sequence,license`) | `envelope.py:build_preimage` | design §8.1 | a peer parsing our `/export` envelopes |
| 4 | `proof.type = "ed25519-jcs-2026"` | `envelope.py:PROOF_TYPE` | design §8.1 | a peer's signature-suite dispatch |
| 5 | The object is the HSDS **3.1.1-curated** field set (no top-level phones/addresses) | `aggregate.py` | Task -1 3.1.1 pin vs design §8.2 (3.2) | a peer validating our object against its HSDS model |
| 6 | `published` at second precision (`...Z`, no microseconds) | `envelope.py:published_now` | RFC 3339 | byte-stable re-emission across nodes |

When P2 lands the two-node loop / FA-feed ingest, walk this list: each reading
either gets a cross-impl KAT (promote to `vendor/<suite>/`) or a documented
divergence + fix. Do not delete a row until it is interop-confirmed.
