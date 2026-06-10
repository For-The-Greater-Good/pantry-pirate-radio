# Vendored W3C eddsa-jcs-2022 cryptosuite test vectors

These files are the official **eddsa-jcs-2022** test vectors from the W3C
"Data Integrity EdDSA Cryptosuites v1.0" Recommendation (vc-di-eddsa). They are
an **external** conformance anchor for the planned `proof.type =
"DataIntegrityProof"` / `cryptosuite = "eddsa-jcs-2022"` implementation that
replaces the bespoke `ed25519-jcs-2026` proof. The bytes come from the W3C spec
itself (its §B.3 appendix examples are generated from these very files), not
from a value re-derived alongside our implementation — per constitution
Principle III, this is the kind of external test vector that conformance
evidence MUST be anchored to.

The repo's RFC 8785 JCS serializer (`app/federation/canonical.py::jcs_bytes`)
and base58btc decoder (`app/federation/identity.py::_b58decode`) already
reproduce these canonical forms and verify this signature end-to-end (see
"Verification" below).

## Source and provenance

- **Spec (normative, dated REC snapshot):**
  https://www.w3.org/TR/2025/REC-vc-di-eddsa-20250515/
  — W3C Recommendation, **15 May 2025**. The eddsa-jcs-2022 algorithms are
  §3.3 (3.3.1 Create Proof, 3.3.2 Verify Proof, 3.3.3 Transformation, 3.3.4
  Hashing, 3.3.5 Proof Configuration, 3.3.6 Proof Serialization, 3.3.7 Proof
  Verification). The worked example is **§B.3 "Representation: eddsa-jcs-2022"**
  (Examples 29–39).
- **Vector source files (what we vendored, byte-exact):**
  https://github.com/w3c/vc-di-eddsa — directory `TestVectors/`
  (`TestVectors/keyPair.json`, `TestVectors/unsigned.json`, and
  `TestVectors/eddsa-jcs-2022/*`).
  - **Pinned commit:** `45d646b1422bbbb227f29b8698757b8b78342305` (default branch `main`).
- **Retrieved:** 2026-06-10.
- **License:** W3C Software and Document License
  (https://www.w3.org/Consortium/Legal/copyright-software), per the repo's
  `LICENSE.md`. The W3C document text itself is under the W3C Document License.
  Vendored verbatim, solely as test fixtures, with attribution.

This is the **eddsa-jcs-2022** vector set (JCS canonicalization). The
`eddsa-rdfc-2022` vectors (RDF Dataset Canonicalization, §B.2 / repo
`TestVectors/eddsa-rdfc-2022/`), `Ed25519Signature2020`, and `proof-set-chain`
vectors were **deliberately skipped** — they are a different cryptosuite /
legacy suite and are not what this implementation targets. The spec ships a
**single** eddsa-jcs-2022 example (the Alumni Credential, §B.3); there is no
separate enveloped/VC-2.0 eddsa-jcs-2022 variant.

## What's in each file

Each file below is a **byte-exact** copy of its upstream counterpart at the
pinned commit (file renames noted; no content edits). `.txt` artifacts have **no
trailing newline** in the source and are preserved that way.

| Vendored file | Upstream path | Spec example | Contents |
|---|---|---|---|
| `keys.json` | `TestVectors/keyPair.json` | §B.3 Ex. 29 | The Ed25519 key pair: `publicKeyMultibase` (`z6Mk…`) and `privateKeyMultibase` (`z3u2…`). |
| `unsecured-credential.json` | `TestVectors/unsigned.json` | §B.3 Ex. 30 (input) | The unsecured input credential (the Alumni Credential). |
| `proof-options.json` | `TestVectors/eddsa-jcs-2022/proofConfigJCS.json` | §B.3 Ex. 33 (input) | The proof options / proof configuration object (the proof object **without** `proofValue`, **with** the copied `@context`). |
| `canonical-proof-config.jcs.txt` | `TestVectors/eddsa-jcs-2022/proofCanonJCS.txt` | §B.3 Ex. 34 | RFC 8785 JCS of the proof configuration. |
| `canonical-document.jcs.txt` | `TestVectors/eddsa-jcs-2022/canonDocJCS.txt` | §B.3 Ex. 31 | RFC 8785 JCS of the unsecured credential. |
| `hashes.json` | `…/proofHashJCS.txt`, `…/docHashJCS.txt`, `…/combinedHashJCS.txt`, `…/sigHexJCS.txt` (+ base58 from `sigBTC58JCS.txt`) | §B.3 Ex. 32, 35, 36, 37 | The intermediate SHA-256 hex hashes (document, proof config, the concatenated `hashData`) and the raw signature hex. Transcribed verbatim into one JSON for convenience. |
| `signed-credential.json` | `TestVectors/eddsa-jcs-2022/signedJCS.json` | §B.3 Ex. 39 | The final signed verifiable credential with `proof.proofValue` (`z…`). |

The raw `combinedHashJCS.txt` / `sigHexJCS.txt` / `sigBTC58JCS.txt` `.txt` files
are not copied as standalone files; their values are recorded verbatim in
`hashes.json` (`combined_hash_data_hex`, `signature_ed25519_hex`,
`proof_value_multibase_base58btc`).

## Load-bearing facts these vectors settle

- **Hash order:** `hashData = SHA256(canonicalProofConfig) || SHA256(canonicalDocument)`
  — the proof config hash comes **FIRST** (spec §3.3.4 step 3;
  `combinedHashJCS.txt` = `proofHash` then `docHash`).
- **Proof config canonicalization** is over the proof object **without**
  `proofValue` but **with** `@context` (copied from the document — §3.3.1 step 2).
- **`@context` IS present in the final signed `proof` object** (Ex. 39 /
  `signed-credential.json`): for a JSON-LD document the proof carries a copy of
  the document's `@context`.
- **Multikey prefixes:** `publicKeyMultibase` payload begins `0xed 0x01`
  (ed25519-pub), `privateKeyMultibase` payload begins `0x80 0x26` (ed25519-priv);
  both base58btc-multibase (`z`), 32 raw key bytes each. (Verified by decode.)

## Verification

Transcription was verified end-to-end on 2026-06-10 with a script that reuses
this repo's own `jcs_bytes` and `_b58decode` plus `cryptography`'s Ed25519
(17/17 checks passed):

1. `jcs_bytes(unsecured-credential.json)` == `canonical-document.jcs.txt`.
2. `jcs_bytes(proof-options.json)` == `canonical-proof-config.jcs.txt`
   (and the same value when derived from `signed-credential.json`'s proof minus
   `proofValue`).
3. `SHA256` of each canonical form matches `hashes.json`
   (`document_hash_sha256_hex`, `proof_config_hash_sha256_hex`).
4. `proofConfigHash || documentHash` (proof config first) ==
   `combined_hash_data_hex`.
5. `keys.json` `publicKeyMultibase` decodes to a `0xed01`-prefixed 32-byte key;
   `privateKeyMultibase` decodes to a `0x8026`-prefixed 32-byte seed; the seed's
   derived public key equals the published public key.
6. `signed-credential.json` `proof.proofValue` (base58btc) decodes to the
   64-byte signature == `signature_ed25519_hex`.
7. **`Ed25519.verify(signature, hashData)` with the spec public key SUCCEEDS**,
   and deterministic re-signing of `hashData` with the spec private key
   reproduces the exact published signature byte-for-byte (RFC 8032).

## To refresh (rarely needed — this is a stable REC)

```
gh api repos/w3c/vc-di-eddsa/commits/main --jq .sha
gh api "repos/w3c/vc-di-eddsa/contents/TestVectors/eddsa-jcs-2022?ref=<sha>" --jq '.[].name'
# re-fetch each file via the contents API (.content is base64), then update the
# pinned SHA above and re-run the verification.
```
