# Vendored RFC 9421 (HTTP Message Signatures) Ed25519 test vector

`vector.json` is the published Ed25519 test vector from **RFC 9421, "HTTP
Message Signatures"** (IETF, Feb 2024). It is used by
`tests/test_federation/test_signing_rfc9421_vectors.py` as an **external**
conformance anchor for `app/federation/signing.py` — the bytes come from the
standard's own appendix, not from a value we re-derived alongside the
implementation.

- **Source:** RFC 9421, https://www.rfc-editor.org/rfc/rfc9421.txt
  - **§B.1.4** "Example Ed25519 Test Key" (`test-key-ed25519`) — the PKCS#8 PEM
    public + private keys, copied verbatim.
  - **§B.2.6** "Signing a Request Using ed25519" — the documented signature base
    components and the `sig-b26` signature value.
- **License/provenance:** IETF RFC text. The vector is reproduced here solely as
  a test fixture, with the section citations recorded in `vector.json`.

## Transformations applied

The RFC text uses RFC 8792 `\` line-wrapping for display. Two fields were
**unfolded** (continuation lines joined, leading wrap-whitespace removed):

- `signature_base` — the §B.2.6 signature base, with `\n` between components and
  **no trailing newline** (RFC 9421 §2.5).
- `signature_b64` — the §B.2.6 `sig-b26` base64 signature, unwrapped.

`public_key_raw_hex` / `private_key_raw_hex` are the 32-byte raw Ed25519 keys
decoded from the §B.1.4 PEMs, included for a transcription cross-check (the test
asserts the PEM and the raw hex agree). No other transformation.

## Component-set note (important)

RFC 9421 §B.2.6 signs the covered-component set
`("date" "@method" "@path" "@authority" "content-type" "content-length")`.
`app/federation/signing.py` uses a **different, fixed** set —
`("@method" "@target-uri" "content-digest")` — appropriate to the federation
`/inbox` profile. The two are not byte-compatible, so the test does **not** drive
the vector through `sign_request`/`verify_request`'s header path (that would
require signing.py to support an arbitrary component set, which it deliberately
does not). Instead the test asserts at the level signing.py genuinely supports
and exposes as a primitive: the **raw Ed25519 sign/verify over the documented
signature base bytes** (signing.py's docstring documents that
`private_key.sign(bytes)` / `public_key.verify(sig, bytes)` stay directly
available, and `verify_request` calls exactly `public_key.verify(signature,
base.encode("utf-8"))` internally). This locks our Ed25519 + signature-base
handling to the RFC vector; the covered-component-set difference is documented
rather than papered over.
