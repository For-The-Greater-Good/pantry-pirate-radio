"""RFC-6962 Merkle tree for the HSDS Federation verifiable log (design §6.2b).

Pure crypto — no DB, no I/O. The append-only log's tree is built over the
JCS-canonical envelope **pre-image bytes** (the same bytes whose SHA-256 is the
content-address ``id``; the leaf is the object, but RFC-6962 leaf hashing with
the ``0x00`` prefix is applied inside the tree, so the leaf node hash and the
``id`` digest are deliberately distinct).

Hashing (RFC 6962 §2.1), domain-separated so leaf/interior nodes can never be
confused (second-preimage resistance):

    leaf node  = SHA-256(0x00 || leaf_data)
    interior   = SHA-256(0x01 || left || right)
    empty tree = SHA-256("")

``MerkleFrontier`` maintains the running root in O(log n) per append so a
checkpoint can be issued on every commit without re-reading the log; its root is
byte-identical to the canonical recursive MTH at every size (cross-checked
against an independent oracle in the tests for every n up to 300, plus the
2048-leaf gate from the spike).
"""

from __future__ import annotations

import hashlib

_LEAF_PREFIX = b"\x00"
_NODE_PREFIX = b"\x01"

#: Root of the empty tree, RFC 6962 §2.1: MTH({}) = SHA-256("").
EMPTY_ROOT = hashlib.sha256(b"").digest()


def leaf_hash(leaf_data: bytes) -> bytes:
    """RFC-6962 leaf hash: SHA-256(0x00 || leaf_data)."""
    return hashlib.sha256(_LEAF_PREFIX + leaf_data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    """RFC-6962 interior node hash: SHA-256(0x01 || left || right)."""
    return hashlib.sha256(_NODE_PREFIX + left + right).digest()


def _largest_power_of_two_below(n: int) -> int:
    """Largest power of two strictly less than n (n >= 2). RFC 6962 split point."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def merkle_root(leaves: list[bytes]) -> bytes:
    """Canonical recursive RFC-6962 Merkle Tree Hash over raw leaf-data bytes."""
    n = len(leaves)
    if n == 0:
        return EMPTY_ROOT
    if n == 1:
        return leaf_hash(leaves[0])
    k = _largest_power_of_two_below(n)
    return node_hash(merkle_root(leaves[:k]), merkle_root(leaves[k:]))


class MerkleFrontier:
    """O(log n) append-only Merkle frontier (RFC-6962 root over the prefix).

    ``_stack[i]``, when not None, is the root of a *perfect* subtree of exactly
    ``2**i`` leaves. ``append`` carries like binary addition; ``root`` folds the
    present perfect subtrees along RFC-6962's right spine (largest subtree
    leftmost). The root equals ``merkle_root(all appended leaf-data)`` at every
    size.
    """

    def __init__(self) -> None:
        self._stack: list[bytes | None] = []
        self._size = 0

    @property
    def size(self) -> int:
        return self._size

    def append(self, leaf_data: bytes) -> None:
        carry = leaf_hash(leaf_data)
        height = 0
        while height < len(self._stack) and self._stack[height] is not None:
            carry = node_hash(self._stack[height], carry)  # type: ignore[arg-type]
            self._stack[height] = None
            height += 1
        if height == len(self._stack):
            self._stack.append(carry)
        else:
            self._stack[height] = carry
        self._size += 1

    def root(self) -> bytes:
        present = [s for s in self._stack if s is not None]  # low -> high height
        if not present:
            return EMPTY_ROOT
        acc = present[0]
        for subtree in present[1:]:
            # higher (larger) subtree is the left child; accumulated lower part
            # hangs on the right — RFC-6962's right spine.
            acc = node_hash(subtree, acc)
        return acc


# --- Inclusion proofs (RFC 6962 §2.1.1) --------------------------------------


def inclusion_proof(leaves: list[bytes], m: int) -> list[bytes]:
    """Audit path proving leaf index ``m`` is in the tree of ``leaves``.

    Bottom-up: ``proof[0]`` is the deepest sibling. Mirrored exactly by
    :func:`verify_inclusion`.
    """
    n = len(leaves)
    if not 0 <= m < n:
        raise ValueError(f"leaf index {m} out of range for tree size {n}")
    if n == 1:
        return []
    k = _largest_power_of_two_below(n)
    if m < k:
        return [*inclusion_proof(leaves[:k], m), merkle_root(leaves[k:])]
    return [*inclusion_proof(leaves[k:], m - k), merkle_root(leaves[:k])]


def _root_from_inclusion(n: int, m: int, leaf: bytes, proof: list[bytes]) -> bytes:
    if n == 1:
        return leaf
    k = _largest_power_of_two_below(n)
    sibling = proof[-1]  # current-level sibling (appended last by inclusion_proof)
    rest = proof[:-1]
    if m < k:
        return node_hash(_root_from_inclusion(k, m, leaf, rest), sibling)
    return node_hash(sibling, _root_from_inclusion(n - k, m - k, leaf, rest))


def verify_inclusion(
    leaf_data: bytes, m: int, n: int, proof: list[bytes], root: bytes
) -> bool:
    """True iff ``proof`` proves ``leaf_data`` at index ``m`` in a size-``n`` tree with ``root``."""
    if not 0 <= m < n:
        return False
    expected_len = 0 if n == 1 else _audit_path_len(m, n)
    if len(proof) != expected_len:
        return False
    return _root_from_inclusion(n, m, leaf_hash(leaf_data), list(proof)) == root


def _audit_path_len(m: int, n: int) -> int:
    if n == 1:
        return 0
    k = _largest_power_of_two_below(n)
    if m < k:
        return _audit_path_len(m, k) + 1
    return _audit_path_len(m - k, n - k) + 1


# --- Consistency proofs (RFC 6962 §2.1.2) ------------------------------------


def consistency_proof(leaves: list[bytes], first_size: int) -> list[bytes]:
    """RFC-6962 consistency proof between the tree of the first ``first_size``
    leaves and the full tree of ``leaves``. Bottom-up order."""
    n = len(leaves)
    if not 0 < first_size <= n:
        raise ValueError(f"first_size {first_size} out of range (1..{n})")
    return _subproof(first_size, leaves, True)


def _subproof(m: int, leaves: list[bytes], b: bool) -> list[bytes]:
    n = len(leaves)
    if m == n:
        return [] if b else [merkle_root(leaves)]
    k = _largest_power_of_two_below(n)
    if m <= k:
        return [*_subproof(m, leaves[:k], b), merkle_root(leaves[k:])]
    return [*_subproof(m - k, leaves[k:], False), merkle_root(leaves[:k])]


def _reconstruct_consistency(
    m: int, n: int, stack: list[bytes], b: bool, first_root: bytes
) -> tuple[bytes, bytes]:
    """Reconstruct (old_root, new_root) for a size-``m`` prefix of a size-``n``
    subtree, mirroring :func:`_subproof` exactly and consuming ``stack`` from the
    end (where ``_subproof`` appended each level's sibling)."""
    if m == n:
        # An all-old subtree. On the leftmost (b=True) spine its root is the
        # known old root (first_root); otherwise _subproof emitted it as a node.
        if b:
            return first_root, first_root
        node = stack.pop()
        return node, node
    k = _largest_power_of_two_below(n)
    sibling = stack.pop()  # this level's sibling (appended last by _subproof)
    if m <= k:
        old_left, new_left = _reconstruct_consistency(m, k, stack, b, first_root)
        return old_left, node_hash(new_left, sibling)
    old_right, new_right = _reconstruct_consistency(
        m - k, n - k, stack, False, first_root
    )
    return node_hash(sibling, old_right), node_hash(sibling, new_right)


def verify_consistency(
    first_size: int,
    second_size: int,
    proof: list[bytes],
    first_root: bytes,
    second_root: bytes,
) -> bool:
    """True iff ``proof`` shows the size-``second_size`` tree is an append-only
    extension of the size-``first_size`` tree (RFC 6962 §2.1.2). A rewritten,
    forked, or truncated history cannot satisfy this — that is the property that
    makes tampering provable, not merely alleged (design §6.2b)."""
    if first_size < 0 or second_size < first_size:
        return False
    if first_size == second_size:
        return not proof and first_root == second_root
    if first_size == 0:
        return not proof
    stack = list(proof)  # popped from the end in top-down recursion order
    try:
        old_root, new_root = _reconstruct_consistency(
            first_size, second_size, stack, True, first_root
        )
    except IndexError:
        return False  # proof too short
    return not stack and old_root == first_root and new_root == second_root
