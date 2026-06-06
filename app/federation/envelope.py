"""HSDS Federation activity envelope: content-address ``id`` + Ed25519 ``proof``.

Design §6.2a / §8.1. Pure (no DB/IO). Both the content address and the proof
signature are computed over a SINGLE canonical buffer — the JCS bytes of the
envelope with ``id`` and ``proof`` removed (you cannot hash/sign a field that
contains its own hash/signature):

    pre-image = jcs_bytes({envelope without "id" and "proof"})
    id        = "sha256:" + hex(sha256(pre-image))
    proof.sig = base64-std( Ed25519_sign(pre-image) )   # SAME bytes, not re-hashed

A verifier strips ``id``+``proof`` once, canonicalizes once, and reuses that one
buffer for both the ``sha256 == id`` content-address check and the Ed25519
signature check — so the two can never drift apart. The object-integrity proof
survives relays, mirrors, and S3 archives (a consumer verifies origin with zero
network trust). Envelope-only identity fields (``federation_id`` / ``attributedTo``
/ ``origin``) live at the top level, NEVER inside ``object`` (Principle II — the
object validates against the unmodified HSDS models).
"""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.federation.canonical import jcs_bytes

#: ``proof.type`` for the Ed25519-over-JCS object signature (design §8.1).
PROOF_TYPE = "ed25519-jcs-2026"

_ID_PREFIX = "sha256:"
_EXCLUDED_FROM_PREIMAGE = ("id", "proof")
#: An Ed25519 signature (RFC 8032) is always exactly 64 bytes.
_ED25519_SIGNATURE_LEN = 64


def published_now() -> str:
    """An RFC-3339 UTC timestamp at second precision (``...Z``).

    Second precision (no microseconds) keeps ``published`` byte-stable across
    nodes that re-emit the same logical activity.
    """
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    """The envelope WITHOUT ``id``/``proof`` — the exact dict that gets hashed and
    signed. (``context`` should be ``settings.FEDERATION_PROFILE_URI``; do not
    hardcode a version — Task -1 pinned 3.1.1. ``license`` should be
    ``settings.FEDERATION_LICENSE``: license-in-band rides in the SIGNED
    pre-image so a relayed/archived object keeps a signed, DID-attributed
    license paper trail even detached from its feed — mesh-resilience decision,
    2026-06-06.)

    Numeric-domain contract: integers are JCS-serialized via ``str(int)`` (exact),
    which a strict double-based JCS peer (ECMAScript ``Number``) diverges from
    above 2^53. Our own log re-derives leaves from the verbatim signed bytes
    (``log.leaf_data``), so this cannot break our proofs; it only matters for a
    foreign peer with a double-based JCS reader. HSDS objects carry no integer
    field that large today — revisit when P2 ingest accepts arbitrary foreign
    objects (fold in an explicit bound or a double pipeline then)."""
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
    preimage: dict[str, Any], signing_key: Ed25519PrivateKey
) -> tuple[dict[str, Any], bytes]:
    """Like :func:`finalize`, but also return the canonical pre-image bytes.

    The returned ``bytes`` are the EXACT buffer that was hashed and signed. The
    log persists them verbatim so a leaf can be re-derived byte-for-byte without
    depending on any storage layer's number normalization (JSONB normalizes
    extreme-magnitude floats differently than this JCS form) — the substrate's
    "store what you signed" invariant.
    """
    pb = jcs_bytes(preimage)
    env_id = _ID_PREFIX + hashlib.sha256(pb).hexdigest()
    signature = base64.b64encode(signing_key.sign(pb)).decode("ascii")
    proof = {
        "type": PROOF_TYPE,
        "verificationMethod": f"{preimage['actor']}#main-key",
        "signature": signature,
    }
    return {**preimage, "id": env_id, "proof": proof}, pb


def finalize(
    preimage: dict[str, Any], signing_key: Ed25519PrivateKey
) -> dict[str, Any]:
    """Attach the content address ``id`` and the Ed25519 ``proof`` to a pre-image."""
    return finalize_with_bytes(preimage, signing_key)[0]


def verify_envelope(envelope: dict[str, Any], public_key: Ed25519PublicKey) -> bool:
    """True iff the content address matches AND the Ed25519 proof verifies.

    This is the object-integrity check only (design §6.5 "object signature"
    step). Allow-list / actor-host policy is the caller's job (the inbox/pull
    consumer), not this function's.
    """
    if not isinstance(envelope, dict):
        return False
    proof = envelope.get("proof")
    claimed_id = envelope.get("id")
    if not isinstance(proof, dict) or not isinstance(claimed_id, str):
        return False
    signature_b64 = proof.get("signature")
    if not isinstance(signature_b64, str):
        return False
    preimage = {k: v for k, v in envelope.items() if k not in _EXCLUDED_FROM_PREIMAGE}
    try:
        pb = jcs_bytes(preimage)
    except ValueError:
        return False
    if _ID_PREFIX + hashlib.sha256(pb).hexdigest() != claimed_id:
        return False
    # Bind the signature to its EXACT bytes: strict base64 (no whitespace/garbage),
    # exactly 64 bytes (Ed25519), AND canonical encoding. Without the canonical
    # check the field is still malleable — base64's final-quantum padding bits are
    # ignored on decode, so ~16 distinct wire strings decode to one 64-byte
    # signature and would all verify True. ed25519-jcs-2026 is a PPR-native format
    # (no external oracle mandates leniency), so we require the one canonical form.
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except (ValueError, TypeError):
        return False
    if len(signature) != _ED25519_SIGNATURE_LEN:
        return False
    if base64.b64encode(signature).decode("ascii") != signature_b64:
        return False
    try:
        public_key.verify(signature, pb)
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True
