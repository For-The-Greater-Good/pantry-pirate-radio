# Vendored RFC 8785 (JCS) conformance vectors

These `input/*.json` and `output/*.json` files are the official JSON
Canonicalization Scheme (RFC 8785) test vectors published by the spec's author,
**Anders Rundgren**, and are used by `tests/test_federation/test_canonical_official_vectors.py`
as an **external** conformance anchor for `app/federation/canonical.py::jcs_bytes`.

- **Source:** https://github.com/cyberphone/json-canonicalization (`testdata/`)
- **Pinned commit:** `19d51d7fe467d4706a3ff08adf8a748f29fc21e0`
- **License:** Apache License 2.0 — Copyright 2018 Anders Rundgren
  (https://www.apache.org/licenses/LICENSE-2.0). Vendored verbatim, solely as
  test fixtures, with attribution per the license.

Each `output/<name>.json` is the byte-exact canonical form of `input/<name>.json`.
`weird.json` is the load-bearing case: it has a non-BMP object key (😂 U+1F602)
that must sort by **UTF-16 code units** (§3.2.3), not Unicode code point.

To refresh (rarely needed — RFC 8785 is stable): re-fetch the six input/output
pairs from the path above at a newer commit and update the pinned SHA here.
