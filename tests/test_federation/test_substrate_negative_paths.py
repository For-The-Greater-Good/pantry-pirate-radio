"""Negative / guard-path coverage for the federation verifiable substrate (PR-B).

Every test here drives a *reachable-from-hostile-or-buggy-input* guard branch
that the existing happy-path + KAT suites do not exercise — the error short
circuits a malformed peer activity, a truncated proof, an out-of-range index, an
invalid key, or a malformed signed note hits. Coverage targets named by the
audit lenses (module: line):

  - canonical.py    49 (unsupported type), 60 (non-str key), 88 (NaN/Inf)
  - identity.py     90-91/93 (PEM load errors), 100 (bad base64 seed),
                    111-113 (_host_from_did branches), 51-56 (_b58encode pad)
  - discovery.py    31-33 (_host_from_did https / bare branches)
  - merkle.py       117 (inclusion_proof range), 142/145 (verify_inclusion
                    range + wrong proof length), 216/220/226-227
                    (verify_consistency guards), 79 (_largest_power split)
  - envelope.py     114 (proof not dict / id not str), 121 (signature not str),
                    125-126 (jcs ValueError path), 49 (published_now),
                    88 (content_address)
  - checkpoint.py   66 (sign_note newline guard), 93 (no sig lines), 133/137/
                    145-146 (parse_checkpoint malformed bodies), key-hash
                    mismatch with a DIFFERENT valid key
  - signing.py      111/118/121 (missing headers), 127 (created not int)
  - log.py          151 (leaf_data tree_size exceeds committed prefix) — DB

Defensive-unreachable (NOT chased here): canonical._shortest_digits_and_point
lines 143/148 (empty digit strings a finite nonzero positive float cannot
produce) and identity._b58encode's ImportError fallback at line 71 (only runs
when the base58 hard dependency is absent). The _b58encode leading-zero padding
(51-56) IS pinned below via a direct unit call rather than uninstalling base58.

Pure tests first; the single DB-backed test (log.leaf_data) is last and reuses
the TRUNCATE-isolated session fixture from test_log_append.py.
"""

import base64
import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.federation import (
    canonical,
    checkpoint,
    discovery,
    envelope,
    identity,
    log,
    merkle,
    signing,
)

_SEED = bytes(range(32))


def _key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_SEED)


# --- canonical.py: serialization rejection paths ----------------------------


def test_canonical_rejects_unsupported_type() -> None:
    """_serialize line 49: a set is not a JSON type -> ValueError."""
    with pytest.raises(ValueError, match="unsupported type for JCS"):
        canonical.jcs_bytes({1, 2, 3})


def test_canonical_rejects_non_string_object_key() -> None:
    """_serialize_object line 60: an int-keyed dict is not canonicalizable."""
    with pytest.raises(ValueError, match="object keys must be strings"):
        canonical.jcs_bytes({1: "x"})


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_canonical_rejects_nan_and_infinity(bad: float) -> None:
    """_format_float line 88: NaN / +-Inf are not valid JCS numbers."""
    with pytest.raises(ValueError, match="not valid JCS numbers"):
        canonical.jcs_bytes(bad)


def test_canonical_rejects_nested_unsupported_type() -> None:
    """The reject path is reachable through a nested object value, not just the
    top level — an envelope.object could smuggle a bytes value."""
    with pytest.raises(ValueError, match="unsupported type for JCS"):
        canonical.jcs_bytes({"object": {"blob": b"\x00\x01"}})


# --- identity.py: key loading + DID host parsing ----------------------------


def test_load_signing_key_none_yields_none() -> None:
    assert identity.load_signing_key(None) is None


def test_load_signing_key_rejects_invalid_pem() -> None:
    """identity lines 90-91: malformed PEM -> ValueError (never silent None)."""
    bad_pem = "-----BEGIN PRIVATE KEY-----\nnotpem\n-----END PRIVATE KEY-----"
    with pytest.raises(ValueError, match="invalid PEM Ed25519 private key"):
        identity.load_signing_key(bad_pem)


def test_load_signing_key_rejects_non_ed25519_pem() -> None:
    """identity line 93: a valid PEM that is RSA/EC is not an Ed25519 key."""
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = rsa_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    with pytest.raises(ValueError, match="not an Ed25519 private key"):
        identity.load_signing_key(pem)


def test_load_signing_key_rejects_non_ed25519_ec_pem() -> None:
    """identity line 93 again, via an EC key, to pin the isinstance gate."""
    ec_key = ec.generate_private_key(ec.SECP256R1())
    pem = ec_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    with pytest.raises(ValueError, match="not an Ed25519 private key"):
        identity.load_signing_key(pem)


def test_load_signing_key_rejects_bad_base64_seed() -> None:
    """identity line 100: non-base64 seed material -> ValueError."""
    with pytest.raises(ValueError, match="invalid base64 Ed25519 seed"):
        identity.load_signing_key("not!base64!!")


def test_load_signing_key_rejects_wrong_length_seed() -> None:
    """A valid base64 string that does not decode to 32 bytes is rejected."""
    short = base64.b64encode(b"too short").decode("ascii")
    with pytest.raises(ValueError, match="invalid base64 Ed25519 seed"):
        identity.load_signing_key(short)


def test_load_signing_key_accepts_valid_base64_seed() -> None:
    """Positive control: a 32-byte base64 seed loads and round-trips."""
    seed_b64 = base64.b64encode(_SEED).decode("ascii")
    key = identity.load_signing_key(seed_b64)
    assert isinstance(key, Ed25519PrivateKey)


def test_identity_host_from_did_https() -> None:
    """identity lines 111-112: https:// DID strips scheme + path."""
    assert identity._host_from_did("https://node.example/path") == "node.example"


def test_identity_host_from_did_bare() -> None:
    """identity line 113: a bare string falls through unchanged."""
    assert identity._host_from_did("node.example") == "node.example"


def test_identity_host_from_did_web() -> None:
    """The did:web branch (line 110) for completeness."""
    assert identity._host_from_did("did:web:node.example") == "node.example"


def test_b58encode_leading_zero_padding() -> None:
    """identity lines 51-56: each leading 0x00 byte maps to a leading '1'.

    Pins the hand-rolled base58btc fallback directly (the base58 hard dep
    normally short-circuits this at line 69) so the standards-conformant
    encoding stays covered without uninstalling base58.
    """
    assert identity._b58encode(b"\x00\x00\x01") == "112"
    assert identity._b58encode(b"\x00") == "1"


# --- discovery.py: _host_from_did branches ----------------------------------


def test_discovery_host_from_did_none() -> None:
    assert discovery._host_from_did(None) is None


def test_discovery_host_from_did_https() -> None:
    """discovery lines 31-32: https:// form strips scheme + path."""
    assert discovery._host_from_did("https://node.example/path") == "node.example"


def test_discovery_host_from_did_bare() -> None:
    """discovery line 33: bare host fallthrough."""
    assert discovery._host_from_did("node.example") == "node.example"


def test_discovery_host_from_did_web() -> None:
    assert discovery._host_from_did("did:web:node.example") == "node.example"


# --- merkle.py: inclusion guards --------------------------------------------


def _leaves(n: int) -> list[bytes]:
    return [f"leaf-{i}".encode() for i in range(n)]


@pytest.mark.parametrize("bad_index", [4, -1])
def test_inclusion_proof_rejects_out_of_range_index(bad_index: int) -> None:
    """merkle line 117: index outside [0, n) -> ValueError."""
    with pytest.raises(ValueError, match="out of range"):
        merkle.inclusion_proof(_leaves(4), bad_index)


def test_verify_inclusion_rejects_out_of_range_index() -> None:
    """merkle line 142: m >= n is rejected without touching the proof."""
    leaves = _leaves(7)
    root = merkle.merkle_root(leaves)
    proof = merkle.inclusion_proof(leaves, 3)
    assert merkle.verify_inclusion(leaves[3], 9, 7, proof, root) is False
    assert merkle.verify_inclusion(leaves[3], -1, 7, proof, root) is False


def test_verify_inclusion_rejects_wrong_proof_length() -> None:
    """merkle line 145: a proof of the wrong audit-path length is rejected."""
    leaves = _leaves(7)
    root = merkle.merkle_root(leaves)
    proof = merkle.inclusion_proof(leaves, 3)
    too_long = [*proof, bytes(32)]
    assert merkle.verify_inclusion(leaves[3], 3, 7, too_long, root) is False
    assert merkle.verify_inclusion(leaves[3], 3, 7, proof[:-1], root) is False


def test_largest_power_split_pins_four_leaf_root() -> None:
    """merkle line 79: n>=4 drives the k*=1 loop body. Pin the structural root.

    merkle_root([a,b,c,d]) = node(node(leaf a, leaf b), node(leaf c, leaf d)).
    """
    leaves = _leaves(4)
    expected = merkle.node_hash(
        merkle.node_hash(merkle.leaf_hash(leaves[0]), merkle.leaf_hash(leaves[1])),
        merkle.node_hash(merkle.leaf_hash(leaves[2]), merkle.leaf_hash(leaves[3])),
    )
    assert merkle.merkle_root(leaves) == expected


# --- merkle.py: consistency guards ------------------------------------------


def test_verify_consistency_rejects_bad_sizes() -> None:
    """merkle line 216: negative first_size, or second < first, -> False."""
    r = merkle.merkle_root(_leaves(5))
    assert merkle.verify_consistency(-1, 5, [], r, r) is False
    assert merkle.verify_consistency(5, 3, [], r, r) is False


def test_verify_consistency_first_size_zero() -> None:
    """merkle lines 219-220: from an empty first tree the proof must be empty."""
    new_root = merkle.merkle_root(_leaves(4))
    assert merkle.verify_consistency(0, 4, [], merkle.EMPTY_ROOT, new_root) is True
    # a non-empty proof for first_size==0 is rejected
    assert merkle.verify_consistency(0, 4, [b"x"], merkle.EMPTY_ROOT, new_root) is False


def test_verify_consistency_equal_sizes() -> None:
    """merkle line 218: first==second requires empty proof + equal roots."""
    r = merkle.merkle_root(_leaves(3))
    assert merkle.verify_consistency(3, 3, [], r, r) is True
    assert merkle.verify_consistency(3, 3, [], r, merkle.EMPTY_ROOT) is False
    assert merkle.verify_consistency(3, 3, [b"x"], r, r) is False


def test_verify_consistency_rejects_truncated_proof() -> None:
    """merkle lines 226-227: a too-short proof raises IndexError internally and
    verify_consistency catches it and returns False (not a crash)."""
    old_leaves = _leaves(5)
    new_leaves = _leaves(8)
    old_root = merkle.merkle_root(old_leaves)
    new_root = merkle.merkle_root(new_leaves)
    proof = merkle.consistency_proof(new_leaves, 5)
    assert merkle.verify_consistency(5, 8, proof, old_root, new_root) is True
    assert merkle.verify_consistency(5, 8, proof[:-1], old_root, new_root) is False


# --- envelope.py: verify short-circuits -------------------------------------

_ENV_ARGS = dict(
    context="https://hsds-federation.pantrypirateradio.org/profile",
    activity_type="Update",
    actor="did:web:example.org",
    attributed_to="did:web:example.org",
    origin="did:web:example.org",
    federation_id="example.org:abc-123",
    obj={"id": "loc-1", "name": "Test Pantry"},
    sequence=1,
    published="2026-06-05T00:00:00Z",
    license="sandia-ftgg-nc-os-1.0",
)


def test_verify_envelope_rejects_non_dict() -> None:
    """envelope line 113-114: a non-dict envelope is rejected outright."""
    assert envelope.verify_envelope("not a dict", _key().public_key()) is False  # type: ignore[arg-type]
    assert envelope.verify_envelope(None, _key().public_key()) is False  # type: ignore[arg-type]


def test_verify_envelope_rejects_proof_not_dict() -> None:
    """envelope line 114: proof present but not a dict -> False."""
    env = envelope.finalize(envelope.build_preimage(**_ENV_ARGS), _key())
    tampered = {**env, "proof": "notadict"}
    assert envelope.verify_envelope(tampered, _key().public_key()) is False


def test_verify_envelope_rejects_id_not_str() -> None:
    """envelope line 114: id present but not a str -> False."""
    env = envelope.finalize(envelope.build_preimage(**_ENV_ARGS), _key())
    tampered = {**env, "id": 12345}
    assert envelope.verify_envelope(tampered, _key().public_key()) is False


def test_verify_envelope_rejects_signature_not_str() -> None:
    """envelope line 121: proof.signature missing / not a str -> False."""
    env = envelope.finalize(envelope.build_preimage(**_ENV_ARGS), _key())
    no_sig = {**env, "proof": {"type": envelope.PROOF_TYPE}}
    assert envelope.verify_envelope(no_sig, _key().public_key()) is False
    int_sig = {**env, "proof": {**env["proof"], "signature": 123}}
    assert envelope.verify_envelope(int_sig, _key().public_key()) is False


def test_verify_envelope_rejects_non_canonicalizable_object() -> None:
    """envelope lines 124-126: a preimage field jcs_bytes cannot serialize makes
    verify return False rather than raising (a hostile object carrying a set)."""
    env = envelope.finalize(envelope.build_preimage(**_ENV_ARGS), _key())
    # Splice in a non-JSON value while keeping id+proof shape valid-looking.
    poisoned = {**env, "object": {"weird": {1, 2, 3}}}
    assert envelope.verify_envelope(poisoned, _key().public_key()) is False


def test_content_address_matches_finalize_id() -> None:
    """envelope line 88: content_address pins the same id finalize attaches."""
    pre = envelope.build_preimage(**_ENV_ARGS)
    assert envelope.content_address(pre) == envelope.finalize(pre, _key())["id"]


def test_published_now_second_precision_z_suffix() -> None:
    """envelope line 49: RFC-3339 UTC, second precision, trailing Z, no micros."""
    import re

    stamp = envelope.published_now()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", stamp)


# --- checkpoint.py: malformed-note + sign guards ----------------------------


def test_sign_note_rejects_text_without_trailing_newline() -> None:
    """checkpoint line 66: the C2SP signed text must end in a newline."""
    with pytest.raises(ValueError, match="must end with a newline"):
        checkpoint.sign_note(b"no trailing newline", "name", _key())


def test_verify_note_rejects_blank_signature_part() -> None:
    """checkpoint line 93 (_split_note): a blank signature section -> None ->
    verify_note False. 'text\\n\\n\\n' splits to an all-empty sig part."""
    assert checkpoint.verify_note("text\n\n\n", _key().public_key(), "name") is False


def test_parse_checkpoint_rejects_no_blank_separator() -> None:
    """checkpoint lines 132-133: no blank-line separator -> _split_note None."""
    assert checkpoint.parse_checkpoint("garbage with no blank line\n") is None


def test_parse_checkpoint_rejects_blank_signature_part() -> None:
    """checkpoint line 133: _split_note returns None on an empty sig part."""
    assert checkpoint.parse_checkpoint("text\n\n\n") is None


def test_parse_checkpoint_rejects_short_body() -> None:
    """checkpoint line 137: a body with <4 lines (no Timestamp:) -> None."""
    note = "origin\nTimestamp: x\n\n— k sig\n"
    assert checkpoint.parse_checkpoint(note) is None


def test_parse_checkpoint_rejects_missing_timestamp_prefix() -> None:
    """checkpoint line 137: a 4-line body whose 4th line is not 'Timestamp: '."""
    note = "origin\n3\nAAAA\nNotTimestamp: t\n\n— k sig\n"
    assert checkpoint.parse_checkpoint(note) is None


def test_parse_checkpoint_rejects_non_integer_tree_size() -> None:
    """checkpoint lines 145-146: int() failure on the tree_size line -> None."""
    note = "origin\nNOTINT\nAAAA\nTimestamp: t\n\n— k sig\n"
    assert checkpoint.parse_checkpoint(note) is None


def test_parse_checkpoint_rejects_bad_base64_root() -> None:
    """checkpoint lines 145-146: b64decode failure on the root line -> None."""
    note = "origin\n3\nnotbase64!!\nTimestamp: t\n\n— k sig\n"
    assert checkpoint.parse_checkpoint(note) is None


def test_verify_note_rejects_different_valid_key() -> None:
    """A note signed by one key must not verify under a DIFFERENT valid key with
    the SAME key name — the key-hash + signature both gate (defense in depth)."""
    root = merkle.merkle_root([b"leaf-0", b"leaf-1"])
    note = checkpoint.build_checkpoint(
        origin="did:web:example.org",
        tree_size=2,
        root_hash=root,
        timestamp="2026-06-06T00:00:00Z",
        signing_key=_key(),
    )
    other = Ed25519PrivateKey.from_private_bytes(bytes([9]) * 32)
    assert (
        checkpoint.verify_note(note, other.public_key(), "did:web:example.org") is False
    )


# --- signing.py: missing-header + bad-created guards ------------------------


def _signed_headers(body: bytes = b"{}", created: int = 1_700_000_000) -> dict:
    return signing.sign_request(
        _key(),
        keyid="did:web:example.org#main-key",
        method="POST",
        target_uri="https://node.example/api/v1/federation/inbox",
        body=body,
        created=created,
    )


def _verify(headers: dict, body: bytes = b"{}", now: int = 1_700_000_000) -> None:
    signing.verify_request(
        _key().public_key(),
        method="POST",
        target_uri="https://node.example/api/v1/federation/inbox",
        headers=headers,
        body=body,
        max_skew_seconds=300,
        now=now,
    )


def test_verify_request_round_trips() -> None:
    """Positive control: a freshly signed request verifies."""
    _verify(_signed_headers())  # no raise


def test_verify_request_rejects_missing_content_digest() -> None:
    """signing line 111."""
    with pytest.raises(signing.SignatureError, match="missing Content-Digest"):
        _verify({})


def test_verify_request_rejects_missing_signature_input() -> None:
    """signing line 118."""
    headers = _signed_headers()
    del headers["Signature-Input"]
    with pytest.raises(signing.SignatureError, match="missing Signature-Input"):
        _verify(headers)


def test_verify_request_rejects_missing_signature() -> None:
    """signing line 121."""
    headers = _signed_headers()
    del headers["Signature"]
    with pytest.raises(signing.SignatureError, match="missing Signature header"):
        _verify(headers)


def test_verify_request_rejects_non_integer_created() -> None:
    """signing lines 124-127: a non-integer created parameter -> SignatureError."""
    headers = _signed_headers()
    headers["Signature-Input"] = headers["Signature-Input"].replace(
        "created=1700000000", "created=abc"
    )
    with pytest.raises(signing.SignatureError, match="invalid created parameter"):
        _verify(headers)


# --- log.py: leaf_data prefix-density guard (DB-backed) ---------------------


@pytest.fixture()
def db_session():
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(url)
    maker = sessionmaker(bind=engine)
    session = maker()
    session.execute(text("TRUNCATE federation_log"))
    session.commit()
    yield session
    session.rollback()
    session.execute(text("TRUNCATE federation_log"))
    session.commit()
    session.close()
    engine.dispose()


def test_leaf_data_rejects_tree_size_beyond_committed_prefix(db_session) -> None:
    """log line 151: leaf_data is the integrity guard ensuring the committed
    prefix is dense. The build_* proof helpers short-circuit BEFORE calling
    leaf_data (their 1<=seq<=tree_size / 0<first<=second guards), so call
    leaf_data directly with a tree_size past MAX(sequence)."""
    for i in range(3):
        log.append(
            db_session,
            activity_type="Update",
            federation_id=f"example.org:loc-{i}",
            obj={"id": f"loc-{i}", "name": f"Pantry {i}"},
            origin_did="did:web:example.org",
            signing_key=_key(),
            context="https://hsds-federation.pantrypirateradio.org/profile",
            license="sandia-ftgg-nc-os-1.0",
            published="2026-06-06T00:00:00Z",
        )
    # Exactly the committed prefix is fine.
    assert len(log.leaf_data(db_session, 3)) == 3
    with pytest.raises(ValueError, match="exceeds committed prefix"):
        log.leaf_data(db_session, 5)
