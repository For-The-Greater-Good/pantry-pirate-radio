"""RFC 6962 conformance against the AUTHORITATIVE transparency-dev/merkle suite.

These vectors are the Merkle-tree reference test data published by
transparency-dev/merkle (the maintained successor to
google/certificate-transparency-go), vendored under
``vendor/rfc6962_transparency_dev/`` (see that dir's README for the pinned
commit and license). They are an EXTERNAL anchor for ``app/federation/merkle.py``
— a third party that independently implements RFC 6962 — and so cannot share the
blind spots of our own derived ``test_log_merkle.py`` corpus.

The conformance LOCK here is byte-level: every tree root, leaf-hash, inclusion
proof, and consistency proof we compute must equal the PUBLISHED bytes, not a
value we re-derived. The leaf inputs, root hashes (sizes 0..8), per-leaf node
hashes, and proof vectors all come from the upstream ``constants.go`` and
``testdata/*/happy-path.json`` files.
"""

import json
from pathlib import Path

import pytest

from app.federation import merkle

_VECTORS = (
    Path(__file__).resolve().parent
    / "vendor"
    / "rfc6962_transparency_dev"
    / "vectors.json"
)
_DATA = json.loads(_VECTORS.read_text(encoding="utf-8"))

_LEAVES = [bytes.fromhex(h) for h in _DATA["leaf_inputs_hex"]]
_ROOTS = [bytes.fromhex(h) for h in _DATA["root_hashes_hex"]]
_LEAF_NODE_HASHES = [bytes.fromhex(h) for h in _DATA["leaf_node_hashes_hex"]]
_EMPTY_ROOT = bytes.fromhex(_DATA["empty_root_hex"])


def test_vendored_vectors_self_consistent() -> None:
    """Transcription guard: 8 leaf inputs, 9 root hashes (sizes 0..8), 8 leaf
    node hashes; the size-0 root is the empty root. Catches any copy error in
    the vendored JSON before it can mask a real assertion below."""
    assert len(_LEAVES) == 8
    assert len(_ROOTS) == 9
    assert len(_LEAF_NODE_HASHES) == 8
    assert _ROOTS[0] == _EMPTY_ROOT


def test_empty_root_matches_published() -> None:
    """merkle.EMPTY_ROOT == published EmptyRootHash() == SHA-256("")."""
    assert merkle.EMPTY_ROOT == _EMPTY_ROOT
    assert merkle.merkle_root([]) == _EMPTY_ROOT


@pytest.mark.parametrize("idx", range(8))
def test_leaf_hash_matches_published_node_hash(idx: int) -> None:
    """RFC-6962 leaf hash SHA-256(0x00 || data) for each vendored leaf input must
    equal the published level-0 NodeHashes() entry."""
    assert merkle.leaf_hash(_LEAVES[idx]) == _LEAF_NODE_HASHES[idx]


@pytest.mark.parametrize("n", range(9))
def test_merkle_root_matches_published_root(n: int) -> None:
    """merkle_root over the first n vendored leaves == published RootHashes()[n]."""
    assert merkle.merkle_root(_LEAVES[:n]) == _ROOTS[n]


@pytest.mark.parametrize("n", range(9))
def test_frontier_root_matches_published_root(n: int) -> None:
    """A MerkleFrontier built by appending the first n leaves must reach the same
    published root — the incremental O(log n) path and the recursive path agree
    with the external oracle at every size 0..8."""
    frontier = merkle.MerkleFrontier()
    for leaf in _LEAVES[:n]:
        frontier.append(leaf)
    assert frontier.size == n
    assert frontier.root() == _ROOTS[n]


@pytest.mark.parametrize("vec", _DATA["inclusion_proofs"], ids=lambda v: v["source"])
def test_published_inclusion_proof_verifies(vec: dict) -> None:
    """verify_inclusion must ACCEPT the published proof bytes against the
    published root (not a proof we generated)."""
    leaf_data = bytes.fromhex(vec["leaf_input_hex"])
    proof = [bytes.fromhex(h) for h in vec["proof_hex"]]
    root = bytes.fromhex(vec["root_hex"])
    assert merkle.verify_inclusion(
        leaf_data, vec["leaf_index"], vec["tree_size"], proof, root
    ), f"published inclusion proof rejected: {vec['source']}"


@pytest.mark.parametrize("vec", _DATA["inclusion_proofs"], ids=lambda v: v["source"])
def test_our_inclusion_proof_reproduces_published_bytes(vec: dict) -> None:
    """We must also REGENERATE the published proof byte-for-byte: build the proof
    over the same LeafInputs prefix and compare to the vendored hashes."""
    leaves = _LEAVES[: vec["tree_size"]]
    expected = [bytes.fromhex(h) for h in vec["proof_hex"]]
    assert merkle.inclusion_proof(leaves, vec["leaf_index"]) == expected


@pytest.mark.parametrize("vec", _DATA["inclusion_proofs"], ids=lambda v: v["source"])
def test_published_inclusion_proof_tamper_rejected(vec: dict) -> None:
    """A one-byte flip in the published proof (or a wrong leaf) must be rejected
    — confirms the assertion above is not a tautology that accepts anything."""
    leaf_data = bytes.fromhex(vec["leaf_input_hex"])
    proof = [bytes.fromhex(h) for h in vec["proof_hex"]]
    root = bytes.fromhex(vec["root_hex"])
    if proof:
        tampered = list(proof)
        tampered[0] = bytes([tampered[0][0] ^ 0x01]) + tampered[0][1:]
        assert not merkle.verify_inclusion(
            leaf_data, vec["leaf_index"], vec["tree_size"], tampered, root
        )
    # A wrong leaf under the same (correct) proof must also fail.
    assert not merkle.verify_inclusion(
        leaf_data + b"\xff", vec["leaf_index"], vec["tree_size"], proof, root
    )


@pytest.mark.parametrize("vec", _DATA["consistency_proofs"], ids=lambda v: v["source"])
def test_published_consistency_proof_verifies(vec: dict) -> None:
    """verify_consistency must ACCEPT the published proof between the published
    first/second roots."""
    proof = [bytes.fromhex(h) for h in vec["proof_hex"]]
    first_root = bytes.fromhex(vec["first_root_hex"])
    second_root = bytes.fromhex(vec["second_root_hex"])
    assert merkle.verify_consistency(
        vec["first_size"], vec["second_size"], proof, first_root, second_root
    ), f"published consistency proof rejected: {vec['source']}"


@pytest.mark.parametrize("vec", _DATA["consistency_proofs"], ids=lambda v: v["source"])
def test_our_consistency_proof_reproduces_published_bytes(vec: dict) -> None:
    """We must REGENERATE the published consistency proof byte-for-byte over the
    same LeafInputs tree."""
    leaves = _LEAVES[: vec["second_size"]]
    expected = [bytes.fromhex(h) for h in vec["proof_hex"]]
    assert merkle.consistency_proof(leaves, vec["first_size"]) == expected


@pytest.mark.parametrize("vec", _DATA["consistency_proofs"], ids=lambda v: v["source"])
def test_published_consistency_proof_tamper_rejected(vec: dict) -> None:
    """A one-byte flip in the published consistency proof must be rejected."""
    proof = [bytes.fromhex(h) for h in vec["proof_hex"]]
    first_root = bytes.fromhex(vec["first_root_hex"])
    second_root = bytes.fromhex(vec["second_root_hex"])
    tampered = list(proof)
    tampered[0] = bytes([tampered[0][0] ^ 0x01]) + tampered[0][1:]
    assert not merkle.verify_consistency(
        vec["first_size"], vec["second_size"], tampered, first_root, second_root
    )
