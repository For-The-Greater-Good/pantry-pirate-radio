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
        """Produce the W3C Data Integrity ``proof`` object (``eddsa-jcs-2022``
        cryptosuite) for ``preimage`` signed by the Ed25519 key derived from the
        32-byte ``seed_hex``. The proof carries ``{@context (copied from the
        document), type="DataIntegrityProof", cryptosuite="eddsa-jcs-2022", created,
        verificationMethod, proofPurpose="assertionMethod", proofValue}`` where
        ``proofValue`` is multibase base58btc (``"z"``-prefixed) over the 64-byte
        Ed25519 signature on ``SHA256(JCS(proofConfig)) || SHA256(JCS(document))``
        (proof config FIRST), the DI *document* being the envelope minus ``proof``
        (``id`` included). ``created`` defaults to the preimage's ``published`` so the
        op is deterministic (§6.2a/§8.1, vc-di-eddsa §3.3)."""
        ...

    def verify_envelope(self, envelope: dict[str, Any], pubkey_hex: str) -> bool:
        """True iff the envelope's content address matches AND the W3C Data Integrity
        ``eddsa-jcs-2022`` proof verifies. ``pubkey_hex`` is the 32-byte raw Ed25519
        public key as hex. Verification recomputes ``SHA256(JCS(proofConfig)) ||
        SHA256(JCS(document))`` (proof config first; document = envelope minus
        ``proof``) and Ed25519-verifies the base58btc ``proofValue`` against it,
        with strict multibase decoding (§8.1, vc-di-eddsa §3.3)."""
        ...

    # --- checkpoint (C2SP signed note; §6.2b) ---------------------------------

    def encode_note(self, seed_hex: str, text: str, key_name: str) -> str:
        """A C2SP signed note over ``text`` (which ends in a newline) signed by the
        Ed25519 key from ``seed_hex``, under ``key_name`` — the note format anchored
        to the Go ``sumdb/note`` KAT."""
        ...

    def checkpoint_body(
        self, origin: str, tree_size: int, root_hex: str, timestamp: str
    ) -> str:
        """The HSDS-FX checkpoint body text (the C2SP tlog-checkpoint shape):
        ``origin\\n<tree_size>\\n<base64-std(root)>\\nTimestamp: <ts>\\n`` — the root
        is canonical base64-std (with padding), matching the signature encoding."""
        ...

    def encode_checkpoint(
        self, seed_hex: str, origin: str, tree_size: int, root_hex: str, timestamp: str
    ) -> str:
        """A full signed checkpoint note = ``encode_note(checkpoint_body(...))`` with
        ``key_name = origin``."""
        ...

    def verify_note(self, note: str, pubkey_hex: str, key_name: str) -> bool:
        """True iff ``note`` carries a valid signature for ``key_name`` under the
        raw Ed25519 public key ``pubkey_hex``."""
        ...

    def parse_checkpoint(self, note: str) -> dict[str, Any]:
        """Extract ``{origin, tree_size, root_hex, timestamp}`` from a checkpoint
        note (parse only — caller verifies separately)."""
        ...

    # --- merkle inclusion (RFC-6962; §6.3 export rows) -------------------------

    def verify_inclusion(
        self, leaf_data_hex: str, m: int, n: int, proof_hex: list[str], root_hex: str
    ) -> bool:
        """True iff ``proof_hex`` proves the leaf whose DATA is ``leaf_data_hex``
        (the JCS pre-image bytes, NOT the content-address) at index ``m`` in the
        size-``n`` tree with ``root_hex``. The leaf-vs-content-address distinction
        is load-bearing — RFC-6962 leaf = sha256(0x00 ‖ data)."""
        ...

    def verify_consistency(
        self,
        first_size: int,
        second_size: int,
        proof_hex: list[str],
        first_root_hex: str,
        second_root_hex: str,
    ) -> bool:
        """True iff ``proof_hex`` shows the size-``second_size`` tree is an
        APPEND-ONLY extension of the size-``first_size`` tree (RFC-6962 §2.1.2): a
        rewritten / forked / truncated history cannot satisfy it. Roots/proof are
        hex of the 32-byte node hashes."""
        ...

    # --- federation_id grammar (§8.x / design §135) ---------------------------

    def normalize_federation_id(self, value: str) -> str:
        """Canonicalize ``federation_id = <host> ":" <internal-id>``: split on the
        FIRST colon; ASCII-lowercase the host + strip one trailing dot; RFC 3986
        §6.2.2-normalize the internal-id (decode %XX of unreserved octets, uppercase
        the hex of the rest). Deterministic, idempotent, collision-safe. RAISE on a
        malformed id (no colon, empty side, non-ASCII host, raw reserved char in the
        internal-id, malformed percent-escape)."""
        ...

    # --- activity verbs (§117/§160/§204-206) ----------------------------------

    def validate_activity(self, envelope: dict[str, Any]) -> bool:
        """True iff ``envelope`` satisfies the STATELESS verb wire rules: verb ∈
        {Update, Announce, Delete}; Update/Delete have actor==attributedTo==origin;
        Announce carries a distinct origin (origin!=actor) with attributedTo==origin;
        a Delete's object is a Tombstone {type:"Tombstone", federation_id, redirectTo
        (null|str)} (unknown keys ignored, §8.4). Stateless only — no allow-list /
        sequence / corroboration / merge, and NOT a re-check of id/proof or the full
        federation_id grammar."""
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

    def encode_note(self, seed_hex: str, text: str, key_name: str) -> str:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )

        from app.federation.checkpoint import sign_note

        key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
        return sign_note(text.encode("utf-8"), key_name, key)

    def checkpoint_body(
        self, origin: str, tree_size: int, root_hex: str, timestamp: str
    ) -> str:
        from app.federation.checkpoint import checkpoint_body

        return checkpoint_body(
            origin, tree_size, bytes.fromhex(root_hex), timestamp
        ).decode("utf-8")

    def encode_checkpoint(
        self, seed_hex: str, origin: str, tree_size: int, root_hex: str, timestamp: str
    ) -> str:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )

        from app.federation.checkpoint import build_checkpoint

        key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
        return build_checkpoint(
            origin=origin,
            tree_size=tree_size,
            root_hash=bytes.fromhex(root_hex),
            timestamp=timestamp,
            signing_key=key,
        )

    def verify_note(self, note: str, pubkey_hex: str, key_name: str) -> bool:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )

        from app.federation.checkpoint import verify_note

        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))
        return verify_note(note, pub, key_name)

    def parse_checkpoint(self, note: str) -> dict[str, Any]:
        from app.federation.checkpoint import parse_checkpoint

        parsed = parse_checkpoint(note)
        if parsed is None:
            raise ValueError("not a valid checkpoint note")
        return {
            "origin": parsed["origin"],
            "tree_size": parsed["tree_size"],
            "root_hex": parsed["root_hash"].hex(),
            "timestamp": parsed["timestamp"],
        }

    def verify_inclusion(
        self, leaf_data_hex: str, m: int, n: int, proof_hex: list[str], root_hex: str
    ) -> bool:
        from app.federation.merkle import verify_inclusion

        return verify_inclusion(
            bytes.fromhex(leaf_data_hex),
            m,
            n,
            [bytes.fromhex(h) for h in proof_hex],
            bytes.fromhex(root_hex),
        )

    def verify_consistency(
        self,
        first_size: int,
        second_size: int,
        proof_hex: list[str],
        first_root_hex: str,
        second_root_hex: str,
    ) -> bool:
        from app.federation.merkle import verify_consistency

        return verify_consistency(
            first_size,
            second_size,
            [bytes.fromhex(h) for h in proof_hex],
            bytes.fromhex(first_root_hex),
            bytes.fromhex(second_root_hex),
        )

    def normalize_federation_id(self, value: str) -> str:
        from app.federation.grammar import normalize_federation_id

        return normalize_federation_id(value)

    def validate_activity(self, envelope: dict[str, Any]) -> bool:
        from app.federation.activities import validate_activity

        return validate_activity(envelope)
