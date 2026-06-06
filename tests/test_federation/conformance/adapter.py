"""The HSDS-FX conformance adapter contract — the spec's testable surface.

A conforming implementation provides exactly these operations; everything else in
the conformance suite is pure data (``conformance/hsdsfx/vectors/``). Boundary
types are language-neutral — JSON in; hex / canonical-base64 / strings out, never
crypto-library objects; 32-byte seeds/pubkeys are hex — so a Go/JS/Rust adapter
can implement the same contract. This Protocol IS the portability boundary: the
runner depends only on it, and ``RefAdapter`` is the ONLY sanctioned import of
``app.federation`` in the whole conformance harness (enforced by
``test_hsdsfx_portability.py``).

Slice 1 covers the envelope operations; later slices extend the Protocol
(checkpoint, merkle proofs, export rows, federation_id) without changing the data
format.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HsdsFxAdapter(Protocol):
    """Operations a conforming HSDS-FX implementation must expose to be tested.

    An adapter wraps one implementation. The conformance runner drives an adapter
    over the language-agnostic vector corpus; nothing else couples to the impl.
    """

    def canonicalize(self, obj: Any) -> bytes:
        """RFC 8785 JCS canonical bytes for a JSON value."""
        ...

    def content_address(self, preimage: dict[str, Any]) -> str:
        """The envelope content address: ``"sha256:" + hex(sha256(canonicalize(preimage)))``.
        ``preimage`` is the envelope WITHOUT ``id``/``proof`` (§8.1)."""
        ...

    def sign_envelope(self, seed_hex: str, preimage: dict[str, Any]) -> dict[str, Any]:
        """Produce the ``proof`` object for ``preimage`` signed by the Ed25519 key
        derived from the 32-byte ``seed_hex``: ``{type, verificationMethod,
        signature}`` where ``signature`` is canonical base64-std over the SAME JCS
        bytes the content address commits to (§6.2a/§8.1)."""
        ...

    def verify_envelope(self, envelope: dict[str, Any], pubkey_hex: str) -> bool:
        """True iff the envelope's content address matches AND the Ed25519 proof
        verifies, with canonical-base64 strictness (§8.1). ``pubkey_hex`` is the
        32-byte raw Ed25519 public key as hex."""
        ...


class RefAdapter:
    """PPR's reference adapter — wraps ``app.federation`` (the reference impl).

    This is the ONLY place the conformance harness may import ``app.*``; the
    portability lint asserts it. A foreign implementation supplies its own adapter
    satisfying :class:`HsdsFxAdapter` and runs the identical corpus.
    """

    def canonicalize(self, obj: Any) -> bytes:
        from app.federation.canonical import jcs_bytes

        return jcs_bytes(obj)

    def content_address(self, preimage: dict[str, Any]) -> str:
        from app.federation.envelope import content_address

        return content_address(preimage)

    def sign_envelope(self, seed_hex: str, preimage: dict[str, Any]) -> dict[str, Any]:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )

        from app.federation.envelope import finalize_with_bytes

        key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
        env, _ = finalize_with_bytes(dict(preimage), key)
        return env["proof"]

    def verify_envelope(self, envelope: dict[str, Any], pubkey_hex: str) -> bool:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )

        from app.federation.envelope import verify_envelope

        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))
        return verify_envelope(envelope, pub)
