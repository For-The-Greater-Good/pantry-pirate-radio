"""Hypothesis property tests for the pure federation crypto substrate (PR-B).

These cover the three pure (no DB / no I/O) substrate modules with randomized
adversaries, complementing the bounded exhaustive self-oracle round-trips and the
external KAT vectors already in the suite:

  - ``merkle``: a MerkleFrontier root equals an INDEPENDENT recursive RFC-6962
    MTH oracle re-derived inside this file (the oracle never imports merkle
    internals); inclusion + consistency proofs round-trip for random sizes; a
    flipped proof byte, a wrong index, or a wrong size is rejected.
  - ``envelope``: ``finalize`` / ``verify_envelope`` round-trips over random
    JSON-safe objects, and mutating ANY single top-level envelope field after
    signing breaks verification.
  - ``checkpoint``: ``build_checkpoint`` / ``verify_note`` round-trips over random
    origins, sizes, 32-byte roots and timestamps; ``parse_checkpoint`` recovers
    exactly the inputs; and a flipped root byte fails verification.

Determinism: every Ed25519 key is derived from a fixed/derived 32-byte seed (no
``Date.now``-style nondeterminism), and all data is fictional. Example counts are
kept moderate so the whole file stays well under 30s.
"""

import base64
import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.federation import checkpoint, envelope, merkle
from app.federation.canonical import jcs_bytes

# --- Independent RFC-6962 oracle (recomputed here, NOT imported from merkle) ---


def _h(x: bytes) -> bytes:
    return hashlib.sha256(x).digest()


def _oracle_leaf(d: bytes) -> bytes:
    return _h(b"\x00" + d)


def _oracle_node(left: bytes, right: bytes) -> bytes:
    return _h(b"\x01" + left + right)


def _oracle_mth(leaves: list[bytes]) -> bytes:
    """Canonical recursive RFC-6962 Merkle Tree Hash — the independent oracle."""
    n = len(leaves)
    if n == 0:
        return _h(b"")
    if n == 1:
        return _oracle_leaf(leaves[0])
    k = 1
    while k * 2 < n:
        k *= 2
    return _oracle_node(_oracle_mth(leaves[:k]), _oracle_mth(leaves[k:]))


# Leaf payloads: arbitrary byte strings, including empty, up to a small bound.
_leaf_bytes = st.binary(min_size=0, max_size=40)
_leaf_lists = st.lists(_leaf_bytes, min_size=0, max_size=60)
_nonempty_leaf_lists = st.lists(_leaf_bytes, min_size=1, max_size=60)


# --- merkle: frontier root == independent RFC-6962 oracle ---------------------


@settings(max_examples=200)
@given(leaves=_leaf_lists)
def test_frontier_root_equals_independent_oracle(leaves):
    """The O(log n) frontier root byte-matches the recursive MTH at every prefix."""
    frontier = merkle.MerkleFrontier()
    assert frontier.root() == _oracle_mth([])  # empty tree
    for i, leaf in enumerate(leaves, start=1):
        frontier.append(leaf)
        assert frontier.size == i
        assert frontier.root() == _oracle_mth(leaves[:i])


@settings(max_examples=200)
@given(data=st.data(), leaves=_nonempty_leaf_lists)
def test_inclusion_proof_round_trips_for_random_index(data, leaves):
    """A proof built for a random leaf index verifies against the oracle root."""
    n = len(leaves)
    m = data.draw(st.integers(min_value=0, max_value=n - 1))
    root = _oracle_mth(leaves)
    proof = merkle.inclusion_proof(leaves, m)
    assert merkle.verify_inclusion(leaves[m], m, n, proof, root) is True


@settings(max_examples=200)
@given(data=st.data(), leaves=_nonempty_leaf_lists)
def test_inclusion_proof_rejects_flipped_byte_and_wrong_root(data, leaves):
    """A flipped proof byte or a wrong root is rejected.

    Leaf payloads here may collide (e.g. two empty leaves), so the wrong-INDEX
    rejection is asserted separately with index-tagged distinct leaves: with
    duplicate leaves a symmetric tree can legitimately verify the same leaf hash
    at a mirror index — correct RFC-6962 behaviour, not a bug.
    """
    n = len(leaves)
    m = data.draw(st.integers(min_value=0, max_value=n - 1))
    root = _oracle_mth(leaves)
    proof = merkle.inclusion_proof(leaves, m)

    # A wrong root never verifies (covers n == 1 where the proof is empty).
    assert merkle.verify_inclusion(leaves[m], m, n, proof, _h(b"wrong-root")) is False

    if proof:
        # Flip one byte of one (randomly chosen) proof element.
        elem_idx = data.draw(st.integers(min_value=0, max_value=len(proof) - 1))
        byte_idx = data.draw(st.integers(min_value=0, max_value=31))
        flip = data.draw(st.integers(min_value=1, max_value=255))
        bad = list(proof)
        mutated = bytearray(bad[elem_idx])
        mutated[byte_idx] ^= flip
        bad[elem_idx] = bytes(mutated)
        assert merkle.verify_inclusion(leaves[m], m, n, bad, root) is False


@settings(max_examples=200)
@given(data=st.data(), n=st.integers(min_value=2, max_value=60))
def test_inclusion_proof_rejects_wrong_index(data, n):
    """With DISTINCT leaves, verifying a leaf at any other index is rejected.

    Index-tagged leaves guarantee no two leaf hashes collide, so a proof verifies
    only at the true index — a different in-range index must fail.
    """
    leaves = [b"leaf-%d" % i for i in range(n)]  # all distinct
    root = _oracle_mth(leaves)
    m = data.draw(st.integers(min_value=0, max_value=n - 1))
    wrong_m = data.draw(
        st.integers(min_value=0, max_value=n - 1).filter(lambda x: x != m)
    )
    proof = merkle.inclusion_proof(leaves, m)
    assert merkle.verify_inclusion(leaves[m], m, n, proof, root) is True
    assert merkle.verify_inclusion(leaves[m], wrong_m, n, proof, root) is False


@settings(max_examples=200)
@given(data=st.data(), leaves=_nonempty_leaf_lists)
def test_consistency_proof_round_trips_for_random_prefix(data, leaves):
    """A consistency proof between a random prefix and the full tree verifies."""
    n = len(leaves)
    first = data.draw(st.integers(min_value=1, max_value=n))
    old_root = _oracle_mth(leaves[:first])
    new_root = _oracle_mth(leaves)
    proof = merkle.consistency_proof(leaves, first)
    assert merkle.verify_consistency(first, n, proof, old_root, new_root) is True


@settings(max_examples=200)
@given(data=st.data(), leaves=st.lists(_leaf_bytes, min_size=2, max_size=60))
def test_consistency_proof_rejects_wrong_size_and_flipped_byte(data, leaves):
    """A wrong first_size, a forked new root, or a flipped proof byte is rejected."""
    n = len(leaves)
    first = data.draw(st.integers(min_value=1, max_value=n - 1))  # strict prefix
    old_root = _oracle_mth(leaves[:first])
    new_root = _oracle_mth(leaves)
    proof = merkle.consistency_proof(leaves, first)
    assert merkle.verify_consistency(first, n, proof, old_root, new_root) is True

    # A forked history (rewrite a leaf inside the old prefix) breaks the proof.
    forked = list(leaves)
    forked[0] = forked[0] + b"-forked"
    forked_new_root = _oracle_mth(forked)
    assume(forked_new_root != new_root)
    assert (
        merkle.verify_consistency(first, n, proof, old_root, forked_new_root) is False
    )

    # A wrong (smaller) first_size with the same proof is rejected.
    if first > 1:
        smaller_old = _oracle_mth(leaves[: first - 1])
        assert (
            merkle.verify_consistency(first - 1, n, proof, smaller_old, new_root)
            is False
        )

    # Flip one byte of one proof element.
    if proof:
        elem_idx = data.draw(st.integers(min_value=0, max_value=len(proof) - 1))
        byte_idx = data.draw(st.integers(min_value=0, max_value=31))
        flip = data.draw(st.integers(min_value=1, max_value=255))
        bad = list(proof)
        mutated = bytearray(bad[elem_idx])
        mutated[byte_idx] ^= flip
        bad[elem_idx] = bytes(mutated)
        assert merkle.verify_consistency(first, n, bad, old_root, new_root) is False


# --- envelope: finalize/verify round-trip + single-field tamper ---------------

# JSON-safe values for an envelope ``object`` (HSDS payload stand-in): no NaN/inf,
# no surrogates, str keys only — the exact domain JCS is defined over.
_json_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    max_size=16,
)
_json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**9), max_value=10**9),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e9, max_value=1e9),
    _json_text,
)
_json_values = st.recursive(
    _json_scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=3),
        st.dictionaries(_json_text, children, max_size=3),
    ),
    max_leaves=8,
)
_json_objects = st.dictionaries(_json_text, _json_values, max_size=5)


def _key(seed: bytes = bytes(range(32))) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(seed)


def _make_preimage(obj, sequence):
    return envelope.build_preimage(
        context="https://hsds-federation.pantrypirateradio.org/profile",
        activity_type="Update",
        actor="did:web:example.org",
        attributed_to="did:web:example.org",
        origin="did:web:example.org",
        federation_id="example.org:fed-1",
        obj=obj,
        sequence=sequence,
        published="2026-06-05T00:00:00Z",
        license="sandia-ftgg-nc-os-1.0",
    )


@settings(max_examples=150)
@given(obj=_json_objects, sequence=st.integers(min_value=0, max_value=10**9))
def test_envelope_finalize_verify_round_trips(obj, sequence):
    """A finalized envelope verifies, and its id is sha256 of the JCS pre-image."""
    key = _key()
    pre = _make_preimage(obj, sequence)
    env = envelope.finalize(pre, key)
    assert envelope.verify_envelope(env, key.public_key()) is True
    assert env["id"] == "sha256:" + hashlib.sha256(jcs_bytes(pre)).hexdigest()


@settings(max_examples=200)
@given(
    obj=_json_objects,
    sequence=st.integers(min_value=0, max_value=10**9),
    field=st.sampled_from(
        [
            "@context",
            "type",
            "actor",
            "attributedTo",
            "origin",
            "federation_id",
            "object",
            "published",
            "sequence",
            "license",
        ]
    ),
)
def test_mutating_any_top_level_field_breaks_verify(obj, sequence, field):
    """Changing ANY single signed top-level field (keeping id+proof) fails verify.

    This exercises every field uniformly rather than the two hand-picked fields
    of the worked-vector test, proving the whole pre-image is bound by the proof.
    """
    key = _key()
    env = envelope.finalize(_make_preimage(obj, sequence), key)

    original = env[field]
    if field == "sequence":
        mutated = original + 1
    elif field == "object":
        mutated = {**original, "__tamper__": "x"} if original != {} else {"x": 1}
    else:  # all the string fields
        mutated = str(original) + "-tampered"
    assume(mutated != original)

    tampered = {**env, field: mutated}
    assert envelope.verify_envelope(tampered, key.public_key()) is False


@settings(max_examples=120)
@given(obj=_json_objects, sequence=st.integers(min_value=0, max_value=10**9))
def test_envelope_rejects_wrong_key(obj, sequence):
    """An envelope signed by one key does not verify under an unrelated key."""
    env = envelope.finalize(_make_preimage(obj, sequence), _key())
    stranger = _key(bytes([7]) * 32)
    assert envelope.verify_envelope(env, stranger.public_key()) is False


# --- checkpoint: build/verify round-trip + parse fidelity + flipped root ------

# Origin / timestamp text: DID-ish, control-char-free (C2SP §47-48 forbids any
# ASCII control char below U+0020, newline included — such a char makes the whole
# note malformed and is rejected by both build_checkpoint and verify_note), and
# surrogate-free so it survives the UTF-8 round-trip cleanly. ``Cc`` is the Unicode
# control category, which covers U+0000..U+001F (and U+007F, harmlessly excluded).
_note_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc")),
    min_size=1,
    max_size=40,
)
# The origin doubles as the C2SP signature key name, which must satisfy Go
# note.isValidName (non-empty, no Unicode whitespace, no '+') — real origins are
# DIDs. Filter to that valid set so build_checkpoint == verify_note round-trips.
_origin_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc")),
    min_size=1,
    max_size=40,
).filter(lambda s: "+" not in s and not any(c.isspace() for c in s))
_tree_sizes = st.integers(min_value=0, max_value=2**40)
_roots = st.binary(min_size=32, max_size=32)


@settings(max_examples=150)
@given(origin=_origin_text, tree_size=_tree_sizes, root=_roots, timestamp=_note_text)
def test_checkpoint_round_trips_and_parses_exactly(origin, tree_size, root, timestamp):
    """build_checkpoint -> verify_note True, and parse recovers exactly the inputs."""
    key = _key()
    note = checkpoint.build_checkpoint(
        origin=origin,
        tree_size=tree_size,
        root_hash=root,
        timestamp=timestamp,
        signing_key=key,
    )
    assert checkpoint.verify_note(note, key.public_key(), origin) is True
    parsed = checkpoint.parse_checkpoint(note)
    assert parsed == {
        "origin": origin,
        "tree_size": tree_size,
        "root_hash": root,
        "timestamp": timestamp,
    }


@settings(max_examples=150)
@given(
    data=st.data(),
    origin=_origin_text,
    tree_size=_tree_sizes,
    root=_roots,
    timestamp=_note_text,
)
def test_checkpoint_flipped_root_byte_fails_verify(
    data, origin, tree_size, root, timestamp
):
    """Flipping a byte of the (base64) root in the note text fails verify_note.

    The root rides inside the SIGNED body, so any mutation invalidates the
    Ed25519 signature over the checkpoint text.
    """
    key = _key()
    note = checkpoint.build_checkpoint(
        origin=origin,
        tree_size=tree_size,
        root_hash=root,
        timestamp=timestamp,
        signing_key=key,
    )
    byte_idx = data.draw(st.integers(min_value=0, max_value=31))
    flip = data.draw(st.integers(min_value=1, max_value=255))
    mutated_root = bytearray(root)
    mutated_root[byte_idx] ^= flip
    original_b64 = base64.b64encode(root).decode("ascii")
    tampered_b64 = base64.b64encode(bytes(mutated_root)).decode("ascii")
    assume(tampered_b64 != original_b64)
    # Replace the root line's base64 with the tampered one (only the root line).
    tampered_note = note.replace("\n" + original_b64 + "\n", "\n" + tampered_b64 + "\n")
    assume(tampered_note != note)
    assert checkpoint.verify_note(tampered_note, key.public_key(), origin) is False


@settings(max_examples=120)
@given(origin=_origin_text, tree_size=_tree_sizes, root=_roots, timestamp=_note_text)
def test_checkpoint_rejects_wrong_key(origin, tree_size, root, timestamp):
    """A checkpoint signed by one key does not verify under an unrelated key."""
    note = checkpoint.build_checkpoint(
        origin=origin,
        tree_size=tree_size,
        root_hash=root,
        timestamp=timestamp,
        signing_key=_key(),
    )
    stranger = _key(bytes([9]) * 32)
    assert checkpoint.verify_note(note, stranger.public_key(), origin) is False
