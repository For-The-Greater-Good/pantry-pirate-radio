"""External-KAT anchor for the W3C eddsa-jcs-2022 cryptosuite (Slice W).

Drives ``app.federation.di_proof`` over the freshly vendored, cryptographically
verified official W3C "Data Integrity EdDSA Cryptosuites v1.0" (vc-di-eddsa,
REC 2025-05-15) eddsa-jcs-2022 test vectors
(``tests/test_federation/vendor/w3c_eddsa_jcs_2022/``). These bytes come from the
W3C spec itself (its §B.3 worked example is generated from these files), NOT from
a value re-derived alongside our implementation — per constitution Principle III
this is the external conformance anchor the implementation MUST be tied to. So
nothing here is ``interop_pending``: it is externally anchored.

The vectors settle the load-bearing facts (see vendor/README.md):
  * ``hashData = SHA256(canonicalProofConfig) || SHA256(canonicalDocument)`` — the
    proof-config hash comes FIRST (spec §3.3.4 step 3).
  * The proof-config canonicalization is over the proof object WITHOUT
    ``proofValue`` but WITH the ``@context`` copied from the document (§3.3.1 step 2).
  * ``proofValue`` is multibase base58btc ("z") over the 64-byte Ed25519 signature.

``di_proof`` does not exist yet — importing it IS the RED failure for this file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.federation import di_proof  # RED: module does not exist yet (Slice W).
from app.federation.canonical import jcs_bytes
from app.federation.identity import _b58decode

_VENDOR = Path(__file__).resolve().parent / "vendor" / "w3c_eddsa_jcs_2022"

# multicodec varint prefixes (vendor/README §"Multikey prefixes").
_ED25519_PUB_PREFIX = b"\xed\x01"
_ED25519_PRIV_PREFIX = b"\x80\x26"


def _load_json(name: str) -> dict:
    return json.loads((_VENDOR / name).read_text(encoding="utf-8"))


def _load_bytes(name: str) -> bytes:
    # The .txt artifacts have NO trailing newline in the source (preserved).
    return (_VENDOR / name).read_bytes()


def _decode_multibase_key(multibase: str, prefix: bytes) -> bytes:
    """Strip the 'z' multibase prefix, base58btc-decode, require the multicodec
    ``prefix``, and return the trailing 32 raw key bytes."""
    assert multibase.startswith("z"), multibase
    payload = _b58decode(multibase[1:])
    assert payload[: len(prefix)] == prefix, payload[:2].hex()
    raw = payload[len(prefix) :]
    assert len(raw) == 32, len(raw)
    return raw


def _vendored_private_key() -> Ed25519PrivateKey:
    seed = _decode_multibase_key(
        _load_json("keys.json")["privateKeyMultibase"], _ED25519_PRIV_PREFIX
    )
    return Ed25519PrivateKey.from_private_bytes(seed)


def _vendored_public_key() -> Ed25519PublicKey:
    raw = _decode_multibase_key(
        _load_json("keys.json")["publicKeyMultibase"], _ED25519_PUB_PREFIX
    )
    return Ed25519PublicKey.from_public_bytes(raw)


# --- (1) JCS of the unsecured credential == canonical-document.jcs.txt ----------
def test_jcs_of_unsecured_document_matches_vendored_canonical_bytes() -> None:
    doc = _load_json("unsecured-credential.json")
    assert jcs_bytes(doc) == _load_bytes("canonical-document.jcs.txt")


# --- (2) JCS of the proof config (minus proofValue) == canonical-proof-config ---
def test_jcs_of_proof_config_matches_vendored_canonical_bytes() -> None:
    proof_options = _load_json("proof-options.json")
    # The vendored proof-options.json is already the proof object WITHOUT
    # proofValue; strip it defensively in case a refresh adds it.
    proof_config = {k: v for k, v in proof_options.items() if k != "proofValue"}
    assert jcs_bytes(proof_config) == _load_bytes("canonical-proof-config.jcs.txt")


# --- (3) SHA-256 of each canonical form matches hashes.json ---------------------
def test_sha256_of_canonical_forms_match_vendored_hashes() -> None:
    hashes = _load_json("hashes.json")
    doc_hash = hashlib.sha256(_load_bytes("canonical-document.jcs.txt")).hexdigest()
    pc_hash = hashlib.sha256(_load_bytes("canonical-proof-config.jcs.txt")).hexdigest()
    assert doc_hash == hashes["document_hash_sha256_hex"]
    assert pc_hash == hashes["proof_config_hash_sha256_hex"]
    # Combined hashData has the proof-config hash FIRST (spec §3.3.4 step 3).
    assert pc_hash + doc_hash == hashes["combined_hash_data_hex"]


# --- (4) create_proof reproduces the EXACT published proofValue -----------------
def test_create_proof_reproduces_published_proof_value() -> None:
    """The headline KAT: signing the vendored unsecured credential with the
    vendored secret key, the vector's created/verificationMethod/proofPurpose,
    must reproduce the published ``proofValue`` byte-for-byte (Ed25519 is
    deterministic per RFC 8032)."""
    unsecured = _load_json("unsecured-credential.json")
    proof_options = _load_json("proof-options.json")
    signed = _load_json("signed-credential.json")
    expected_pv = signed["proof"]["proofValue"]

    proof = di_proof.create_proof(
        unsecured,
        signing_key=_vendored_private_key(),
        verification_method=proof_options["verificationMethod"],
        proof_purpose=proof_options["proofPurpose"],
        created=proof_options["created"],
    )
    assert proof["type"] == "DataIntegrityProof"
    assert proof["cryptosuite"] == "eddsa-jcs-2022"
    assert proof["proofValue"] == expected_pv
    # The proof copies the document's @context (spec §3.3.1 step 2): this doc has
    # a list @context, so the proof carries that same list.
    assert proof["@context"] == unsecured["@context"]


# --- (5) verify_proof accepts the published signed credential -------------------
def test_verify_proof_accepts_vendored_signed_credential() -> None:
    signed = _load_json("signed-credential.json")
    assert di_proof.verify_proof(signed, _vendored_public_key()) is True


# --- (6) negatives ---------------------------------------------------------------
def test_verify_rejects_flipped_hash_order() -> None:
    """Constructing the signature over docHash || configHash (the WRONG order)
    must NOT verify under verify_proof — pins that the suite hashes proof-config
    FIRST (§3.3.4 step 3), not the document."""
    unsecured = _load_json("unsecured-credential.json")
    proof_options = _load_json("proof-options.json")
    signed = _load_json("signed-credential.json")

    # Rebuild the proof config exactly as create_proof would (copy @context).
    proof_config = {
        "@context": unsecured["@context"],
        "type": "DataIntegrityProof",
        "cryptosuite": "eddsa-jcs-2022",
        "created": proof_options["created"],
        "verificationMethod": proof_options["verificationMethod"],
        "proofPurpose": proof_options["proofPurpose"],
    }
    doc_hash = hashlib.sha256(jcs_bytes(unsecured)).digest()
    cfg_hash = hashlib.sha256(jcs_bytes(proof_config)).digest()
    # WRONG order: document hash first.
    flipped_hash_data = doc_hash + cfg_hash
    sk = _vendored_private_key()
    from app.federation.identity import _b58encode

    bad_proof_value = "z" + _b58encode(sk.sign(flipped_hash_data))

    forged = dict(signed)
    forged_proof = dict(signed["proof"])
    forged_proof["proofValue"] = bad_proof_value
    forged["proof"] = forged_proof
    assert di_proof.verify_proof(forged, _vendored_public_key()) is False


def test_verify_rejects_tampered_credential_field() -> None:
    signed = _load_json("signed-credential.json")
    tampered = dict(signed)
    tampered["name"] = "Tampered Credential"  # mutate a signed field
    assert di_proof.verify_proof(tampered, _vendored_public_key()) is False


def test_verify_rejects_proof_value_without_multibase_prefix() -> None:
    """A proofValue with the 'z' base58btc multibase prefix stripped is not a valid
    multibase string and must NOT verify."""
    signed = _load_json("signed-credential.json")
    bad = dict(signed)
    bad_proof = dict(signed["proof"])
    pv = bad_proof["proofValue"]
    assert pv.startswith("z")
    bad_proof["proofValue"] = pv[1:]  # strip the 'z'
    bad["proof"] = bad_proof
    assert di_proof.verify_proof(bad, _vendored_public_key()) is False
