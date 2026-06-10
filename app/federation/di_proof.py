"""W3C Data Integrity ``eddsa-jcs-2022`` cryptosuite (generic, document-agnostic).

Implements the **eddsa-jcs-2022** cryptosuite from the W3C "Data Integrity EdDSA
Cryptosuites v1.0" Recommendation (vc-di-eddsa, REC 2025-05-15, §3.3). This is the
standard, off-the-shelf Data Integrity proof — ``proof.type = "DataIntegrityProof"``,
``cryptosuite = "eddsa-jcs-2022"``, a multibase-base58btc ``proofValue`` — used to
sign the federation activity envelope (replacing the bespoke ``ed25519-jcs-2026``
proof). It is deliberately written against ANY unsecured JSON document, not just our
envelope, so:

  * the external W3C test vectors (the Alumni Credential, a JSON-LD doc with a LIST
    ``@context``) anchor it byte-for-byte (``tests/.../vendor/w3c_eddsa_jcs_2022/``),
    proving our proof-config canonicalization and hash order match the spec; and
  * the envelope (a scalar-string ``@context``) reuses the SAME code, so a third
    party can verify our envelopes with any conforming eddsa-jcs-2022 verifier.

Why these exact mechanics (the load-bearing facts the KAT settles):

  * **Hash order (§3.3.4 step 3):** ``hashData = SHA256(JCS(proofConfig)) ||
    SHA256(JCS(unsecuredDocument))`` — the proof-config hash comes FIRST. Flipping
    the order changes the signed bytes; ``verify_proof`` rejects a flipped-order
    signature even though it is a genuine Ed25519 signature.
  * **Proof config (§3.3.1 step 2 / §3.3.5):** the ``@context`` of the document is
    copied into the proof BEFORE canonicalizing the proof config (so a JSON-LD
    document and its proof share a context). ``proofConfig`` is the proof object
    WITHOUT ``proofValue``.
  * **proofValue (§3.3.6):** ``"z"`` (base58btc multibase prefix) followed by the
    base58btc encoding of the raw 64-byte Ed25519 signature over ``hashData``.

The key is ALWAYS caller-supplied — this module resolves no trust anchors; a
federating peer resolves the origin's key from its served ``did.json`` (see
``identity.public_key_from_multibase``) and hands the resolved key in.
"""

from __future__ import annotations

import hashlib
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.federation.canonical import jcs_bytes
from app.federation.identity import b58btc_decode, b58btc_encode

#: ``proof.type`` and ``cryptosuite`` are a CLOSED allowlist — only this exact pair
#: is the eddsa-jcs-2022 Data Integrity proof we accept.
PROOF_TYPE = "DataIntegrityProof"
CRYPTOSUITE = "eddsa-jcs-2022"

#: base58btc multibase prefix (the only multibase encoding this suite uses).
_MULTIBASE_PREFIX = "z"
#: An Ed25519 signature (RFC 8032) is always exactly 64 bytes.
_ED25519_SIGNATURE_LEN = 64


def _hash_data(proof_config: dict[str, Any], unsecured_doc: dict[str, Any]) -> bytes:
    """``SHA256(JCS(proofConfig)) || SHA256(JCS(document))`` — proof config FIRST
    (spec §3.3.4 step 3). The single buffer the Ed25519 signature commits to."""
    config_hash = hashlib.sha256(jcs_bytes(proof_config)).digest()
    document_hash = hashlib.sha256(jcs_bytes(unsecured_doc)).digest()
    return config_hash + document_hash


def create_proof(
    unsecured_doc: dict[str, Any],
    *,
    signing_key: Ed25519PrivateKey,
    verification_method: str,
    proof_purpose: str = "assertionMethod",
    created: str | None = None,
) -> dict[str, Any]:
    """Build an ``eddsa-jcs-2022`` Data Integrity proof over ``unsecured_doc``.

    The returned proof carries (in this field order, JCS makes order irrelevant to
    the bytes but the order documents the spec): an optional ``@context`` copied
    from the document (§3.3.1 step 2 — only when the document HAS one, so it works
    for the W3C vector's list AND our envelope's scalar string), ``type`` /
    ``cryptosuite`` (the closed allowlist), an optional ``created``,
    ``verificationMethod``, ``proofPurpose``, and finally ``proofValue``.

    ``proofValue`` is ``"z" + base58btc(Ed25519_sign(hashData))`` where ``hashData``
    is :func:`_hash_data` — the proof-config hash FIRST. Ed25519 is deterministic
    (RFC 8032), so re-signing the same logical document reproduces identical bytes.
    """
    proof: dict[str, Any] = {}
    # Copy the document @context into the proof BEFORE canonicalizing the config
    # (spec §3.3.1 step 2). Type-agnostic: list (W3C vector) or scalar (envelope).
    if "@context" in unsecured_doc:
        proof["@context"] = unsecured_doc["@context"]
    proof["type"] = PROOF_TYPE
    proof["cryptosuite"] = CRYPTOSUITE
    if created is not None:
        proof["created"] = created
    proof["verificationMethod"] = verification_method
    proof["proofPurpose"] = proof_purpose

    # proofConfig is the proof WITHOUT proofValue (which does not exist yet here).
    hash_data = _hash_data(proof, unsecured_doc)
    signature = signing_key.sign(hash_data)
    proof["proofValue"] = _MULTIBASE_PREFIX + b58btc_encode(signature)
    return proof


def _decode_proof_value(proof_value: Any) -> bytes | None:
    """Strict-decode a ``proofValue``: a ``str`` starting with the ``"z"`` base58btc
    multibase prefix, strict-base58btc-decoding to EXACTLY 64 bytes. Any deviation
    (non-str, wrong prefix, invalid base58 character, wrong length) returns ``None``
    so the verifier rejects rather than coerces."""
    if not isinstance(proof_value, str) or not proof_value.startswith(
        _MULTIBASE_PREFIX
    ):
        return None
    try:
        signature = b58btc_decode(proof_value[len(_MULTIBASE_PREFIX) :])
    except ValueError:
        return None
    if len(signature) != _ED25519_SIGNATURE_LEN:
        return None
    return signature


def _context_matches(proof: dict[str, Any], secured_doc: dict[str, Any]) -> bool:
    """If the proof carries an ``@context`` it must agree with the document's
    (spec §3.3.2): scalar==scalar equality; if both are lists, the document's
    ``@context`` must START WITH all of the proof's values in order. A proof with
    NO ``@context`` imposes no constraint."""
    if "@context" not in proof:
        return True
    proof_ctx = proof["@context"]
    doc_ctx = secured_doc.get("@context")
    if isinstance(proof_ctx, list) and isinstance(doc_ctx, list):
        return doc_ctx[: len(proof_ctx)] == proof_ctx
    return proof_ctx == doc_ctx


def verify_proof(secured_doc: dict[str, Any], public_key: Ed25519PublicKey) -> bool:
    """True iff ``secured_doc``'s ``eddsa-jcs-2022`` proof verifies under
    ``public_key``. TOTAL — returns ``False`` on any malformed input, never raises.

    Checks (all must hold): ``proof`` is a dict; ``type == "DataIntegrityProof"``;
    ``cryptosuite == "eddsa-jcs-2022"``; ``proofValue`` strict-decodes to a 64-byte
    Ed25519 signature; the proof ``@context`` (if any) matches the document's;
    ``hashData`` recomputed from (proof minus ``proofValue``, document minus
    ``proof``) Ed25519-verifies against the caller-supplied key."""
    if not isinstance(secured_doc, dict):
        return False
    proof = secured_doc.get("proof")
    if not isinstance(proof, dict):
        return False
    if proof.get("type") != PROOF_TYPE or proof.get("cryptosuite") != CRYPTOSUITE:
        return False
    signature = _decode_proof_value(proof.get("proofValue"))
    if signature is None:
        return False
    if not _context_matches(proof, secured_doc):
        return False

    proof_config = {k: v for k, v in proof.items() if k != "proofValue"}
    unsecured_doc = {k: v for k, v in secured_doc.items() if k != "proof"}
    try:
        hash_data = _hash_data(proof_config, unsecured_doc)
    except ValueError:
        return False
    try:
        public_key.verify(signature, hash_data)
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True
