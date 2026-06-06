# base58btc encode vectors (vendored)

Pins `app/federation/identity.py::_b58encode` — the base58btc encoder used by
`public_key_multibase` (the `did:key` / `publicKeyMultibase` encoding). The
hand-rolled encoder is the production path when the optional `base58` PyPI
package is not installed, so it must be anchored to external truth (constitution
v1.7.0; registry: [`../REGISTRY.md`](../REGISTRY.md), row `base58btc`).

- **Source**: `keis/base58` test suite — https://github.com/keis/base58/blob/master/test_base58.py
- **Retrieved**: 2026-06-06
- **Why authoritative**: `keis/base58` uses the Bitcoin base58 alphabet and its
  vectors reproduce the Bitcoin Core base58 reference. `b"hello world" ->
  "StV1DL6CwTryKyV"` is the canonical base58 (Bitcoin) result reproduced across
  implementations.
- **License**: MIT (keis/base58).

The `000068656c6c6f…` vector (`b"\x00\x00hello world"`) is the **leading-zero**
case: each leading `0x00` byte must encode to a leading `'1'` — the exact branch
a pad/leading-zero refactor could silently break.
