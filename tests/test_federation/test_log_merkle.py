"""Task 2a (PR-B, RED): RFC-6962 Merkle tree — the verifiable substrate core.

Pinned formats (design §6.2b; spec-pinning workflow worked vectors):
  leaf node  = SHA-256(0x00 || leaf_data)
  interior   = SHA-256(0x01 || left || right)
  empty tree = SHA-256("")
The append-only O(log n) frontier root MUST byte-match the canonical RFC-6962
MTH at every size. Inclusion/consistency proofs are validated by full round-trip
against an INDEPENDENT recursive MTH oracle for every (m, n) in a dense range —
so a bug in construction OR verification is caught, not graded by itself.
"""

import hashlib

import pytest

from app.federation import merkle

# --- Independent RFC-6962 oracle (recomputed here, NOT imported from merkle) ---


def _h(x: bytes) -> bytes:
    return hashlib.sha256(x).digest()


def _oracle_leaf(d: bytes) -> bytes:
    return _h(b"\x00" + d)


def _oracle_node(left: bytes, right: bytes) -> bytes:
    return _h(b"\x01" + left + right)


def _oracle_mth(leaves: list[bytes]) -> bytes:
    n = len(leaves)
    if n == 0:
        return _h(b"")
    if n == 1:
        return _oracle_leaf(leaves[0])
    k = 1
    while k * 2 < n:
        k *= 2
    return _oracle_node(_oracle_mth(leaves[:k]), _oracle_mth(leaves[k:]))


def _leaves(n: int) -> list[bytes]:
    # distinct multi-byte leaves so leaf data is never ambiguous with a digest
    return [b"leaf-%d" % i for i in range(n)]


# --- leaf/node/empty hashing matches the pinned definitions -------------------


def test_leaf_node_empty_hashing() -> None:
    assert merkle.leaf_hash(b"x") == _h(b"\x00x")
    assert merkle.node_hash(b"l" * 32, b"r" * 32) == _h(b"\x01" + b"l" * 32 + b"r" * 32)
    assert merkle.EMPTY_ROOT == _h(b"")
    assert merkle.merkle_root([]) == _h(b"")


def test_known_vectors_from_spec() -> None:
    """Pinned worked vectors: leaves bytes([1..3]) (spec-pinning workflow)."""
    d = [bytes([1]), bytes([2]), bytes([3])]
    assert (
        merkle.leaf_hash(d[0]).hex()
        == "b413f47d13ee2fe6c845b2ee141af81de858df4ec549a58b7970bb96645bc8d2"
    )
    assert (
        merkle.merkle_root(d[:2]).hex()
        == "6bcf0e2e93e0a18e22789aee965e6553f4fbe93f0acfc4a705d691c8311c4965"
    )
    assert (
        merkle.merkle_root(d).hex()
        == "e2da0242936eb38ec996a543601b3a1da4226391ff92014ed1a7a248ace36347"
    )


def test_merkle_root_matches_oracle_dense() -> None:
    for n in range(1, 130):
        leaves = _leaves(n)
        assert merkle.merkle_root(leaves) == _oracle_mth(leaves), f"root mismatch n={n}"


# --- the O(log n) frontier root must equal the canonical MTH ------------------


def test_frontier_root_matches_rfc6962_mth() -> None:
    leaves = _leaves(2048)
    fr = merkle.MerkleFrontier()
    expected_sizes = {1, 2, 3, 100, 1024, 2048}
    for i, leaf in enumerate(leaves, start=1):
        fr.append(leaf)
        if i in expected_sizes:
            assert fr.root() == _oracle_mth(leaves[:i]), f"frontier!=mth n={i}"


def test_frontier_matches_oracle_every_size_to_300() -> None:
    leaves = _leaves(300)
    fr = merkle.MerkleFrontier()
    for i, leaf in enumerate(leaves, start=1):
        fr.append(leaf)
        assert fr.root() == _oracle_mth(leaves[:i]), f"frontier!=mth n={i}"


def test_empty_frontier_root() -> None:
    assert merkle.MerkleFrontier().root() == _h(b"")


# --- inclusion proofs: full round-trip for every (m, n), n<=64 ----------------


def test_inclusion_proof_roundtrip_exhaustive() -> None:
    for n in range(1, 65):
        leaves = _leaves(n)
        root = _oracle_mth(leaves)
        for m in range(n):
            proof = merkle.inclusion_proof(leaves, m)
            assert merkle.verify_inclusion(
                leaves[m], m, n, proof, root
            ), f"inclusion verify failed m={m} n={n}"


def test_inclusion_proof_rejects_tamper() -> None:
    leaves = _leaves(7)
    root = _oracle_mth(leaves)
    proof = merkle.inclusion_proof(leaves, 3)
    assert merkle.verify_inclusion(leaves[3], 3, 7, proof, root)
    # wrong leaf data
    assert not merkle.verify_inclusion(b"evil", 3, 7, proof, root)
    # wrong index
    assert not merkle.verify_inclusion(leaves[3], 4, 7, proof, root)
    # tampered sibling
    if proof:
        bad = list(proof)
        bad[0] = bytes(32)
        assert not merkle.verify_inclusion(leaves[3], 3, 7, bad, root)
    # wrong root
    assert not merkle.verify_inclusion(leaves[3], 3, 7, proof, bytes(32))


# --- consistency proofs: full round-trip for every (m, n), n<=48 --------------


def test_consistency_proof_roundtrip_exhaustive() -> None:
    for n in range(1, 49):
        leaves = _leaves(n)
        new_root = _oracle_mth(leaves)
        for m in range(1, n + 1):
            old_root = _oracle_mth(leaves[:m])
            proof = merkle.consistency_proof(leaves, m)
            assert merkle.verify_consistency(
                m, n, proof, old_root, new_root
            ), f"consistency verify failed m={m} n={n}"


def test_consistency_proof_rejects_forked_history() -> None:
    """A new tree that is NOT an append-only extension breaks the proof."""
    leaves = _leaves(8)
    old_root = _oracle_mth(leaves[:5])
    new_root = _oracle_mth(leaves)
    proof = merkle.consistency_proof(leaves, 5)
    assert merkle.verify_consistency(5, 8, proof, old_root, new_root)
    # a forked history: rewrite leaf 2 then extend -> old prefix no longer holds
    forked = list(leaves)
    forked[2] = b"rewritten"
    forked_new_root = _oracle_mth(forked)
    assert not merkle.verify_consistency(5, 8, proof, old_root, forked_new_root)
    # truncated/grown size mismatch
    assert not merkle.verify_consistency(5, 8, proof, bytes(32), new_root)


def test_consistency_equal_size_is_trivial() -> None:
    leaves = _leaves(4)
    root = _oracle_mth(leaves)
    assert merkle.verify_consistency(
        4, 4, merkle.consistency_proof(leaves, 4), root, root
    )


def test_consistency_rejects_bad_sizes() -> None:
    leaves = _leaves(4)
    with pytest.raises((ValueError, AssertionError)):
        merkle.consistency_proof(leaves, 0)
    with pytest.raises((ValueError, AssertionError)):
        merkle.consistency_proof(leaves, 5)
