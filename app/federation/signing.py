"""RFC 9421 HTTP Message Signatures — minimal Ed25519 profile.

Covered components are fixed at ``("@method" "@target-uri" "content-digest")``;
``created`` / ``keyid`` / ``alg="ed25519"`` are signature parameters. The
content-digest header follows RFC 9530 (``sha-256=:<b64>:``).

Design-forward: the P1 envelope ``proof`` (Ed25519 over ``jcs_bytes(envelope)``)
reuses the same key type. The raw ``private_key.sign(bytes)`` /
``public_key.verify(sig, bytes)`` primitives stay directly available here.
"""

import base64
import hashlib
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

_COVERED = '("@method" "@target-uri" "content-digest")'
_SIG_LABEL = "sig1"


class SignatureError(Exception):
    """Raised on any HTTP Message Signature construction or verification failure."""


def _signature_params(created: int, keyid: str) -> str:
    return f'{_COVERED};created={created};keyid="{keyid}";alg="ed25519"'


def build_signature_base(
    method: str,
    target_uri: str,
    content_digest: str,
    created: int,
    keyid: str,
) -> str:
    """Build the RFC 9421 signature base string (no trailing newline)."""
    return (
        f'"@method": {method}\n'
        f'"@target-uri": {target_uri}\n'
        f'"content-digest": {content_digest}\n'
        f'"@signature-params": {_signature_params(created, keyid)}'
    )


def _content_digest(body: bytes) -> str:
    """RFC 9530 Content-Digest for SHA-256."""
    digest = base64.b64encode(hashlib.sha256(body).digest()).decode("ascii")
    return f"sha-256=:{digest}:"


def sign_request(
    private_key: Ed25519PrivateKey,
    keyid: str,
    method: str,
    target_uri: str,
    body: bytes,
    created: int,
) -> dict[str, str]:
    """Sign a request; return the Content-Digest, Signature-Input, Signature headers."""
    content_digest = _content_digest(body)
    base = build_signature_base(method, target_uri, content_digest, created, keyid)
    signature = private_key.sign(base.encode("utf-8"))
    sig_b64 = base64.b64encode(signature).decode("ascii")
    return {
        "Content-Digest": content_digest,
        "Signature-Input": f"{_SIG_LABEL}={_signature_params(created, keyid)}",
        "Signature": f"{_SIG_LABEL}=:{sig_b64}:",
    }


def _parse_param(signature_input: str, name: str) -> str:
    """Extract a single parameter value from the Signature-Input header."""
    match = re.search(rf";{name}=\"?([^\";]+)\"?", signature_input)
    if match is None:
        raise SignatureError(f"missing {name} in Signature-Input")
    return match.group(1)


def _extract_signature(signature_header: str) -> bytes:
    """Strip the ``sig1=:<b64>:`` wrapper and decode the base64 signature."""
    match = re.search(r"=:(.+):\s*$", signature_header.strip())
    if match is None:
        raise SignatureError("malformed Signature header")
    try:
        return base64.b64decode(match.group(1), validate=True)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise SignatureError("invalid base64 in Signature header") from exc


def verify_request(
    public_key: Ed25519PublicKey,
    method: str,
    target_uri: str,
    headers: dict[str, str],
    body: bytes,
    max_skew_seconds: int,
    now: int,
) -> None:
    """Verify a signed request. Raise ``SignatureError`` on any failure."""
    received_digest = headers.get("Content-Digest")
    if received_digest is None:
        raise SignatureError("missing Content-Digest header")
    # 1. Body integrity: recomputed digest must match the header.
    if _content_digest(body) != received_digest:
        raise SignatureError("content-digest mismatch (body tampered)")

    signature_input = headers.get("Signature-Input")
    if signature_input is None:
        raise SignatureError("missing Signature-Input header")
    signature_header = headers.get("Signature")
    if signature_header is None:
        raise SignatureError("missing Signature header")

    # 2. Replay window.
    try:
        created = int(_parse_param(signature_input, "created"))
    except ValueError as exc:
        raise SignatureError("invalid created parameter") from exc
    if abs(now - created) > max_skew_seconds:
        raise SignatureError("created timestamp outside allowed skew")

    keyid = _parse_param(signature_input, "keyid")

    # 3. Rebuild the base from the verified digest + parsed params.
    base = build_signature_base(method, target_uri, received_digest, created, keyid)

    # 4. Verify the Ed25519 signature over the base.
    signature = _extract_signature(signature_header)
    try:
        public_key.verify(signature, base.encode("utf-8"))
    except InvalidSignature as exc:
        raise SignatureError("Ed25519 signature verification failed") from exc
