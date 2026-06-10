"""Slice W "proof-independence" invariant: the proof-INDEPENDENT conformance
vectors MUST NOT change when the envelope proof format is replaced.

Replacing the bespoke ``ed25519-jcs-2026`` proof with W3C ``eddsa-jcs-2022`` is a
proof-only change. The leaf bytes (JCS), the content address, the Merkle
checkpoint/inclusion/consistency proofs, the export wire shape, the federation_id
grammar, and the raw JCS vectors are all defined OVER THE PREIMAGE (envelope ∖
{id,proof}) or are entirely proof-agnostic — so their bytes are frozen across this
slice (the D1 wire-freeze "leaf/content-address/checkpoint bytes don't move").

This test PASSES now and guards the green phase: if a regeneration during Slice W
drifts any of these vectors, CI fails here. ``envelope_proof.json`` and
``envelope_assembly.json`` are deliberately EXCLUDED (they re-bake this slice's
proof and must change); ``activity_verbs.json`` is excluded (it may gain vectors).

Any FUTURE legitimate change to one of these pinned vectors must update its hash
here in an explicitly-reviewed diff — never silently.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

_VECTORS = Path(__file__).resolve().parents[2] / "conformance" / "hsdsfx" / "vectors"

# sha256 hex of each proof-independent vector, verified 2026-06-10 (pre-change).
_PINNED = {
    "checkpoint.json": "307fc413bdd2ae449162a656707352bc59cdca5d20afb5697dfb0b471728b5ee",
    "consistency_proof.json": "967617e63c77fd45ec74afcc9f694a85ad6e2a2a1623a632aefea2048f639ea7",
    "envelope_content_address.json": "40f84d472c1d955436de3d2f0d23c5fd8e094ef0dee1ba6c88e08bf92d50425f",
    "export_wire.json": "d4d9e7bed57b0f47258c28b364329aeba606bb318de607ce5bd630944c00d17c",
    "federation_id.json": "929297d74ea4d9e0d3f9101fec2f5f25652ec1be00f75c3d7f5432e8e157d266",
    "jcs.json": "bc3bff60a81ab9df014961e80471e366ee00df7e48b78c283a4ec3f69d3efd23",
    "merkle_inclusion.json": "51739472f14c1643f4f7498e0f5ea1d470224ef41c6b9ab13fc7686c1c61746a",
}


@pytest.mark.parametrize("name", sorted(_PINNED))
def test_proof_independent_vector_unchanged(name: str) -> None:
    digest = hashlib.sha256((_VECTORS / name).read_bytes()).hexdigest()
    assert digest == _PINNED[name], (
        f"{name} drifted: {digest} != pinned {_PINNED[name]}. The proof rewrite "
        f"must NOT change proof-independent vectors (Slice W wire-freeze). If this "
        f"change is intentional, update the pin in an explicitly-reviewed diff."
    )
