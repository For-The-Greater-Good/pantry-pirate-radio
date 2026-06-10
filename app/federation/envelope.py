"""HSDS Federation activity envelope: content-address ``id`` + W3C DI ``proof``.

Design §6.2a / §8.1, rewritten for Slice W onto the standard W3C Data Integrity
``eddsa-jcs-2022`` cryptosuite (``app/federation/di_proof.py``). The bespoke
``proof.type = "ed25519-jcs-2026"`` (a base64 Ed25519 signature over the pre-image
bytes) is replaced by the off-the-shelf ``DataIntegrityProof`` so any conforming
eddsa-jcs-2022 verifier — not just PPR's — can verify our envelopes.

Two canonicalizations now sit side by side (they do not share a buffer anymore):

  1. **Content address** — over the envelope WITHOUT ``id`` and ``proof``::

         pre-image = jcs_bytes({envelope minus {id, proof}})
         id        = "sha256:" + hex(sha256(pre-image))

     This is BYTE-IDENTICAL to P1 — the content address is proof-format-INDEPENDENT,
     and the Merkle log / inclusion+consistency proofs / archive all depend on it
     staying stable (the Slice W "proof-independence" invariant, pinned by
     ``test_vector_invariance.py`` and ``test_content_address_pinned_unchanged_by_proof_rewrite``).

  2. **DI proof** — the eddsa-jcs-2022 suite over the DI *document*, which is the
     envelope minus {proof} (``id`` INCLUDED). Standard DI document scope: an
     off-the-shelf verifier strips only ``proof`` and hashes the rest. ``di_proof``
     copies the document's ``@context`` (a scalar string for our envelopes) into the
     proof, hashes ``SHA256(JCS(proofConfig)) || SHA256(JCS(document))`` (config
     FIRST), and emits a multibase-base58btc ``proofValue``.

``verificationMethod`` binds to the origin: ``actor + "#main-key"``. ``created``
defaults to the envelope's ``published`` so re-signing the same logical envelope is
byte-deterministic (RFC 8032 Ed25519 is deterministic); an explicit ``created``
overrides.

**I-JSON integer bound (RFC 7493 §2.2):** any integer ANYWHERE in the envelope with
``abs(v) > 2^53 - 1`` is rejected at THIS boundary — ``finalize``/``build`` raise
``ValueError``, ``verify_envelope`` returns ``False``. Our JCS serializer renders
ints exactly via ``str(int)``, but a strict double-based JCS peer (ECMAScript
``Number``) diverges above 2^53; enforcing the interoperable integer range here
keeps ``canonical.py`` a general RFC-8785 serializer while guaranteeing a foreign
double-based reader cannot be handed an envelope whose canonical bytes it would
disagree with. Bools are NOT ints for this purpose (excluded); floats are untouched.

Envelope-only identity fields (``federation_id`` / ``attributedTo`` / ``origin``)
live at the top level, NEVER inside ``object`` (Principle II — the object validates
against the unmodified HSDS models).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.federation import di_proof
from app.federation.canonical import jcs_bytes

#: ``proof.type`` / ``cryptosuite`` for the W3C Data Integrity eddsa-jcs-2022 proof.
PROOF_TYPE = di_proof.PROOF_TYPE  # "DataIntegrityProof"
CRYPTOSUITE = di_proof.CRYPTOSUITE  # "eddsa-jcs-2022"

_ID_PREFIX = "sha256:"
_EXCLUDED_FROM_PREIMAGE = ("id", "proof")
#: The proof's bound purpose — a non-assertion purpose is rejected.
_PROOF_PURPOSE = "assertionMethod"
#: Largest interoperable integer (RFC 7493 §2.2): a double can represent it exactly.
_I_JSON_MAX_INT = 2**53 - 1


def published_now() -> str:
    """An RFC-3339 UTC timestamp at second precision (``...Z``).

    Second precision (no microseconds) keeps ``published`` byte-stable across
    nodes that re-emit the same logical activity.
    """
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _i_json_ok(obj: Any) -> bool:
    """True iff no integer anywhere in ``obj`` violates the RFC 7493 §2.2
    interoperable integer range (``abs > 2^53 - 1``). Recurses dicts/lists; bools
    are excluded (a JSON boolean is not an integer for this rule); floats untouched.
    """
    if isinstance(obj, bool):
        return True
    if isinstance(obj, int):
        return abs(obj) <= _I_JSON_MAX_INT
    if isinstance(obj, dict):
        return all(_i_json_ok(v) for v in obj.values())
    if isinstance(obj, list | tuple):
        return all(_i_json_ok(v) for v in obj)
    return True


def build_preimage(
    *,
    context: str,
    activity_type: str,
    actor: str,
    attributed_to: str,
    origin: str,
    federation_id: str,
    obj: dict[str, Any],
    sequence: int,
    published: str,
    license: str,
) -> dict[str, Any]:
    """The envelope WITHOUT ``id``/``proof`` — the exact dict whose JCS bytes are the
    content-address pre-image AND (with ``id`` added) the DI proof document.

    (``context`` should be ``settings.FEDERATION_PROFILE_URI``; do not hardcode a
    version — Task -1 pinned 3.1.1. ``license`` should be ``settings.FEDERATION_LICENSE``:
    license-in-band rides in the SIGNED document so a relayed/archived object keeps a
    signed, DID-attributed license paper trail even detached from its feed —
    mesh-resilience decision, 2026-06-06.)
    """
    return {
        "@context": context,
        "type": activity_type,
        "actor": actor,
        "attributedTo": attributed_to,
        "origin": origin,
        "federation_id": federation_id,
        "object": obj,
        "published": published,
        "sequence": sequence,
        "license": license,
    }


def content_address(preimage: dict[str, Any]) -> str:
    """``"sha256:" + hex(sha256(jcs_bytes(preimage)))`` — the envelope ``id``."""
    return _ID_PREFIX + hashlib.sha256(jcs_bytes(preimage)).hexdigest()


def finalize_with_bytes(
    preimage: dict[str, Any],
    signing_key: Ed25519PrivateKey,
    *,
    created: str | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Like :func:`finalize`, but also return the canonical pre-image bytes.

    The returned ``bytes`` are the EXACT content-address pre-image buffer
    (``jcs_bytes(preimage)``). The log persists them verbatim so a leaf can be
    re-derived byte-for-byte without depending on any storage layer's number
    normalization (JSONB normalizes extreme-magnitude floats differently than this
    JCS form) — the substrate's "store what you signed" invariant. The content
    address is proof-format-independent, so these bytes are byte-identical to P1.

    The DI proof is computed over the DI *document* = ``{**preimage, "id": env_id}``
    (envelope minus {proof}); ``verificationMethod = preimage["actor"] + "#main-key"``;
    ``created`` defaults to ``preimage["published"]`` for byte-deterministic re-signing.

    Raises ``ValueError`` if any integer in the envelope violates the I-JSON
    interoperable range (RFC 7493 §2.2) — never emit a divergent envelope.
    """
    if not _i_json_ok(preimage):
        raise ValueError(
            "envelope integer exceeds the I-JSON interoperable range (RFC 7493 §2.2,"
            " |v| <= 2^53-1)"
        )
    pb = jcs_bytes(preimage)
    env_id = _ID_PREFIX + hashlib.sha256(pb).hexdigest()
    di_document = {**preimage, "id": env_id}
    proof = di_proof.create_proof(
        di_document,
        signing_key=signing_key,
        verification_method=f"{preimage['actor']}#main-key",
        proof_purpose=_PROOF_PURPOSE,
        created=created if created is not None else preimage["published"],
    )
    return {**di_document, "proof": proof}, pb


def finalize(
    preimage: dict[str, Any],
    signing_key: Ed25519PrivateKey,
    *,
    created: str | None = None,
) -> dict[str, Any]:
    """Attach the content address ``id`` and the W3C DI ``proof`` to a pre-image."""
    return finalize_with_bytes(preimage, signing_key, created=created)[0]


def _vm_binds_actor(verification_method: Any, actor: Any) -> bool:
    """True iff ``verificationMethod`` is ``"<DID>#<fragment>"`` with the DID part
    EXACTLY equal to a NON-EMPTY ``actor`` and a non-empty fragment (review R9).
    Splits on the LAST ``#`` so a DID containing no fragment is rejected and a
    fragment-only or empty-fragment string fails. The non-empty ``actor`` guard
    rejects the degenerate ``vm="#main-key"`` paired with ``actor=""`` (empty
    did_part == empty actor) — a real envelope actor is always a non-empty DID."""
    if not isinstance(verification_method, str) or not isinstance(actor, str):
        return False
    if not actor:
        return False
    did_part, sep, fragment = verification_method.rpartition("#")
    return bool(sep) and did_part == actor and bool(fragment)


def _content_address_matches(envelope: dict[str, Any], claimed_id: str) -> bool:
    """True iff ``"sha256:"+hex(sha256(jcs_bytes(envelope minus {id,proof})))`` equals
    ``claimed_id``. Guarded: a non-JSON value (``jcs_bytes`` ValueError) or a
    pathologically deep envelope (``RecursionError``) yields ``False``, never a raise
    — keeping :func:`verify_envelope` total."""
    preimage = {k: v for k, v in envelope.items() if k not in _EXCLUDED_FROM_PREIMAGE}
    try:
        pb = jcs_bytes(preimage)
    except (ValueError, RecursionError):
        return False
    return _ID_PREFIX + hashlib.sha256(pb).hexdigest() == claimed_id


def _envelope_proof_bindings_ok(
    envelope: dict[str, Any], proof: dict[str, Any]
) -> bool:
    """The proof's envelope-level bindings: ``verificationMethod`` binds to ``actor``
    (R9) and ``proofPurpose == "assertionMethod"``."""
    if not _vm_binds_actor(proof.get("verificationMethod"), envelope.get("actor")):
        return False
    return proof.get("proofPurpose") == _PROOF_PURPOSE


def verify_envelope(envelope: dict[str, Any], public_key: Ed25519PublicKey) -> bool:
    """True iff the content address matches AND the W3C DI proof verifies.

    TOTAL (never raises, incl. ``RecursionError`` on a pathologically deep
    envelope). The object-integrity check only (design §6.5 "object signature"
    step); allow-list / actor-host policy is the caller's job (the inbox/pull
    consumer). Checks, in order:

      * structural — ``envelope`` a dict, ``proof`` a dict, ``id`` a str;
      * I-JSON integer bound (RFC 7493 §2.2) anywhere in the envelope (defense in
        depth: a peer cannot smuggle a ``> 2^53`` int past a double-based JCS reader);
      * content address over ``envelope minus {id, proof}`` equals the claimed ``id``;
      * ``verificationMethod`` binds to ``actor`` (``"<actor>#<fragment>"``, R9);
      * ``proofPurpose == "assertionMethod"``;
      * the eddsa-jcs-2022 proof verifies under the caller-supplied ``public_key``
        (``di_proof.verify_proof`` strips only ``proof`` and hashes the rest — so we
        pass the envelope WITH ``id``).

    The key is ALWAYS caller-supplied: the verifier never trusts a key derived from
    the envelope's own ``verificationMethod``.
    """
    if not isinstance(envelope, dict):
        return False
    proof = envelope.get("proof")
    claimed_id = envelope.get("id")
    if not isinstance(proof, dict) or not isinstance(claimed_id, str):
        return False
    try:
        if not _i_json_ok(envelope):
            return False
    except RecursionError:
        return False
    if not _content_address_matches(envelope, claimed_id):
        return False
    if not _envelope_proof_bindings_ok(envelope, proof):
        return False
    # di_proof.verify_proof strips only "proof" — pass the envelope WITH id so the
    # DI document scope (envelope minus {proof}) is exactly what was signed.
    return di_proof.verify_proof(envelope, public_key)
