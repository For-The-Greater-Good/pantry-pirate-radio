# Vendored RFC 6962 (Merkle tree) conformance vectors

These vectors are the RFC 6962 Merkle-tree reference test data published by the
**transparency-dev/merkle** project (the maintained successor to
google/certificate-transparency-go's Merkle implementation). They are used by
`tests/test_federation/test_merkle_rfc6962_vectors.py` as an **external**
conformance anchor for `app/federation/merkle.py` — unlike the implementation's
own derived tests, these bytes come from a third party that independently
implements RFC 6962.

- **Source:** https://github.com/transparency-dev/merkle
- **Pinned commit:** `610b863f1496bc3f3546e56b35a542c5020309eb` (default branch `main`)
- **License:** Apache License 2.0 — Copyright Google LLC (see `NOTICE`).
  Vendored solely as test fixtures, with attribution per the license.

## What's in `vectors.json`

Extracted verbatim from the upstream repository:

- `leaf_inputs_hex` / `empty_root_hex` / `root_hashes_hex` / `leaf_node_hashes_hex`
  — from `testonly/constants.go`: `LeafInputs()` (8 leaves), `EmptyRootHash()`,
  `RootHashes()` (indexed by tree size 0..8), and the level-0 entries of
  `NodeHashes()` (the per-leaf RFC-6962 leaf-hashes). The Go file stores these as
  hex already; copied byte-for-byte.
- `inclusion_proofs` / `consistency_proofs` — the `happy-path.json` cases from
  `testdata/inclusion/{1,2,3,4}/` and `testdata/consistency/{1,2,3,4}/`. In the
  upstream files the roots and proof hashes are **base64**; here they are
  rendered as **hex** for direct comparison against our hex-native API, with the
  originating `source` path recorded on each entry. (The base64→hex conversion is
  the only transformation; the underlying 32-byte values are identical.) Every
  proof is taken over the same tree built from `LeafInputs()`, so the leaf inputs
  and roots cross-reference the `constants.go` extract above.

## To refresh (rarely needed — RFC 6962 is stable)

Re-fetch `testonly/constants.go` and the `testdata/{inclusion,consistency}/*/happy-path.json`
files at a newer commit and update the pinned SHA here:

```
gh api repos/transparency-dev/merkle/commits/main --jq .sha
gh api repos/transparency-dev/merkle/contents/testonly/constants.go --jq .content | base64 -d
```
