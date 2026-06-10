"""Guard-path unit tests for ``app.federation.di_proof`` (eddsa-jcs-2022).

The algorithm itself is externally anchored by the vendored W3C KAT
(``test_eddsa_jcs_2022_kat.py``); this module covers the defensive and optional
branches the KAT's happy path never reaches — the no-``@context`` /
no-``created`` create branches and the verifier's total-function guards — so the
new RED-tier module holds the 95% per-file federation coverage floor.
"""

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.federation import di_proof

_SEED = bytes(range(32))


@pytest.fixture
def signing_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_SEED)


def _public_key(key: Ed25519PrivateKey):
    return key.public_key()


def test_create_proof_without_context_omits_it_and_round_trips(signing_key) -> None:
    """A plain-JSON document (no ``@context``) gets a proof with NO ``@context``
    (spec §3.3.1 step 2 copies only when present), and the proof verifies — the
    no-constraint arm of the verifier's ``@context`` check."""
    doc = {"name": "Test Pantry", "latitude": 40.7128}
    proof = di_proof.create_proof(
        doc,
        signing_key=signing_key,
        verification_method="did:web:example.org#main-key",
        created="2026-06-05T00:00:00Z",
    )
    assert "@context" not in proof
    secured = {**doc, "proof": proof}
    assert di_proof.verify_proof(secured, _public_key(signing_key)) is True


def test_create_proof_without_created_omits_the_field(signing_key) -> None:
    """``created`` is optional in Data Integrity; omitted means absent from the
    signed proof config, not null — and the proof still verifies."""
    doc = {"@context": "https://example.org/profile", "name": "Test Pantry"}
    proof = di_proof.create_proof(
        doc,
        signing_key=signing_key,
        verification_method="did:web:example.org#main-key",
    )
    assert "created" not in proof
    secured = {**doc, "proof": proof}
    assert di_proof.verify_proof(secured, _public_key(signing_key)) is True


@pytest.mark.parametrize("junk", [None, "junk", 42, ["proof"], b"proof"])
def test_verify_rejects_non_dict_document(signing_key, junk) -> None:
    """verify_proof is total: a non-dict secured document is False, never a raise."""
    assert di_proof.verify_proof(junk, _public_key(signing_key)) is False


@pytest.mark.parametrize("junk_proof", [None, "sig", 42, ["DataIntegrityProof"]])
def test_verify_rejects_non_dict_proof(signing_key, junk_proof) -> None:
    """A document whose ``proof`` member is not a dict is False, never a raise."""
    doc = {"name": "Test Pantry", "proof": junk_proof}
    assert di_proof.verify_proof(doc, _public_key(signing_key)) is False


def test_verify_rejects_document_that_fails_jcs(signing_key) -> None:
    """A structurally-valid proof over a document containing a non-JSON value
    (JCS raises ValueError) is False — the canonicalization guard, not a crash."""
    doc = {"@context": "https://example.org/profile", "name": "Test Pantry"}
    proof = di_proof.create_proof(
        doc,
        signing_key=signing_key,
        verification_method="did:web:example.org#main-key",
        created="2026-06-05T00:00:00Z",
    )
    poisoned = {**doc, "junk": {"a", "b"}, "proof": proof}
    assert di_proof.verify_proof(poisoned, _public_key(signing_key)) is False


# --- F3: vc-di-eddsa §3.3.2 step 4.2 @context substitution ----------------------
def test_extended_context_document_verifies_via_context_substitution(
    signing_key,
) -> None:
    """vc-di-eddsa §3.3.2 step 4.2: if the proof has @context, after the prefix/
    equality check the verifier MUST set the DOCUMENT's @context equal to the proof's
    @context before hashing. A document signed with @context=['https://ctx/a'] then
    received with @context=['https://ctx/a','https://ctx/b'] (a legitimate
    superset-prefixed extension) MUST verify True — currently False because the
    document is hashed with its own (extended) @context."""
    signed_ctx = ["https://ctx/a"]
    doc_at_sign = {"@context": signed_ctx, "name": "Test Pantry"}
    proof = di_proof.create_proof(
        doc_at_sign,
        signing_key=signing_key,
        verification_method="did:web:example.org#main-key",
        created="2026-06-05T00:00:00Z",
    )
    assert proof["@context"] == signed_ctx
    # Received with an EXTENDED, prefix-preserving @context (the proof's is a prefix).
    received = {
        "@context": ["https://ctx/a", "https://ctx/b"],
        "name": "Test Pantry",
        "proof": proof,
    }
    assert di_proof.verify_proof(received, _public_key(signing_key)) is True


def test_context_substitution_still_rejects_non_prefix_mismatch(signing_key) -> None:
    """The substitution applies ONLY after _context_matches passes: a document whose
    @context is NOT prefixed by the proof's is still rejected (the prefix check gates
    the substitution; it does not blanket-accept any context)."""
    proof = di_proof.create_proof(
        {"@context": ["https://ctx/a"], "name": "Test Pantry"},
        signing_key=signing_key,
        verification_method="did:web:example.org#main-key",
        created="2026-06-05T00:00:00Z",
    )
    received = {
        "@context": ["https://evil/z", "https://ctx/a"],  # NOT prefixed by proof ctx
        "name": "Test Pantry",
        "proof": proof,
    }
    assert di_proof.verify_proof(received, _public_key(signing_key)) is False


# --- F4: vc-di-eddsa §3.3.5 step 3 dateTimeStamp validation of proof.created -----
@pytest.mark.parametrize(
    "bad_created",
    [
        "not-a-date",
        "2026-06-05",  # date only, no time/offset
        "2026-06-05T00:00:00",  # no timezone offset (XSD dateTimeStamp requires one)
        "2026-06-05 00:00:00Z",  # space, not 'T'
        "2026-13-45T99:99:99Z",  # has 'T' but unparseable -> datetime.fromisoformat raises
        "06/05/2026",
        "",
    ],
)
def test_create_proof_raises_on_invalid_created(signing_key, bad_created) -> None:
    """§3.3.5 step 3: created must be a valid XSD dateTimeStamp (RFC 3339 with a
    mandatory timezone offset). create_proof must raise ValueError on garbage."""
    with pytest.raises(ValueError):
        di_proof.create_proof(
            {"@context": "https://example.org/profile", "name": "Test Pantry"},
            signing_key=signing_key,
            verification_method="did:web:example.org#main-key",
            created=bad_created,
        )


def test_verify_proof_rejects_invalid_created(signing_key) -> None:
    """A proof whose created is not a valid dateTimeStamp must NOT verify (build the
    proof over a valid created, then splice in garbage and re-sign so the signature
    is genuine — isolating the created check)."""
    doc = {"@context": "https://example.org/profile", "name": "Test Pantry"}
    valid = di_proof.create_proof(
        doc,
        signing_key=signing_key,
        verification_method="did:web:example.org#main-key",
        created="2026-06-05T00:00:00Z",
    )
    # Re-sign over a proofConfig carrying a garbage created, so the signature is valid
    # for that config and ONLY the created validation can reject.
    import hashlib

    from app.federation.canonical import jcs_bytes
    from app.federation.identity import b58btc_encode

    bad_config = {k: v for k, v in valid.items() if k != "proofValue"}
    bad_config["created"] = "not-a-date"
    config_hash = hashlib.sha256(jcs_bytes(bad_config)).digest()
    doc_hash = hashlib.sha256(jcs_bytes(doc)).digest()
    sig = signing_key.sign(config_hash + doc_hash)
    bad_proof = {**bad_config, "proofValue": "z" + b58btc_encode(sig)}
    assert (
        di_proof.verify_proof({**doc, "proof": bad_proof}, _public_key(signing_key))
        is False
    )


def test_create_and_verify_accept_valid_z_suffixed_created(signing_key) -> None:
    """A valid ...Z (and +hh:mm offset) created is accepted on both create and verify."""
    doc = {"@context": "https://example.org/profile", "name": "Test Pantry"}
    for created in ("2026-06-05T00:00:00Z", "2026-06-05T00:00:00+02:00"):
        proof = di_proof.create_proof(
            doc,
            signing_key=signing_key,
            verification_method="did:web:example.org#main-key",
            created=created,
        )
        assert di_proof.verify_proof({**doc, "proof": proof}, _public_key(signing_key))


# --- F5: proofValue length cap before base58 decode (M5 DoS) --------------------
def test_decode_proof_value_short_circuits_on_oversize_proof_value(signing_key) -> None:
    """M5: _b58decode is O(n^2) bigint. A multi-megabyte proofValue must be rejected
    by a tight LENGTH cap BEFORE decoding (an Ed25519 base58btc proofValue is <=~89
    chars). This must return None/False FAST, not hang."""
    import time

    doc = {"@context": "https://example.org/profile", "name": "Test Pantry"}
    proof = di_proof.create_proof(
        doc,
        signing_key=signing_key,
        verification_method="did:web:example.org#main-key",
        created="2026-06-05T00:00:00Z",
    )
    # 200k non-'1' base58 chars: an UNBOUNDED _b58decode of this takes ~4s on this
    # box (the O(n^2) bigint path; '1's would be cheap leading-zeros). A length cap
    # short-circuits in microseconds.
    huge = "z" + "z" * 200_000
    assert di_proof._decode_proof_value(huge) is None
    bad = {**doc, "proof": {**proof, "proofValue": huge}}
    start = time.monotonic()
    assert di_proof.verify_proof(bad, _public_key(signing_key)) is False
    elapsed = time.monotonic() - start
    # A length short-circuit returns in microseconds; the unbounded decode of 200k
    # chars takes ~4s. The 0.5s bound proves we never entered the bigint decode.
    assert (
        elapsed < 0.5
    ), f"verify took {elapsed:.3f}s — did not short-circuit on length"


# --- F6: RecursionError totality (L2) -------------------------------------------
def test_verify_proof_is_total_on_pathologically_deep_nesting(signing_key) -> None:
    """verify_proof is documented TOTAL: a document nested past the recursion limit
    makes jcs_bytes (inside _hash_data) raise RecursionError; verify must return
    False, never propagate the raise."""
    import sys

    doc = {"@context": "https://example.org/profile", "name": "Test Pantry"}
    proof = di_proof.create_proof(
        doc,
        signing_key=signing_key,
        verification_method="did:web:example.org#main-key",
        created="2026-06-05T00:00:00Z",
    )
    deep: dict = {}
    cursor = deep
    for _ in range(sys.getrecursionlimit() + 100):
        nxt: dict = {}
        cursor["x"] = nxt
        cursor = nxt
    poisoned = {**doc, "deep": deep, "proof": proof}
    assert di_proof.verify_proof(poisoned, _public_key(signing_key)) is False


def test_verify_proof_is_total_on_pathologically_deep_context(signing_key) -> None:
    """The @context match (_context_matches) runs BEFORE the document hash, so a
    pathologically deep @context list raises RecursionError in the list-equality —
    verify must still return False, never propagate (the guard covers the match,
    not just the hash). Pins the residual totality gap."""
    import sys

    deep_list: list = []
    cursor = deep_list
    for _ in range(sys.getrecursionlimit() + 100):
        nxt: list = []
        cursor.append(nxt)
        cursor = nxt
    # A proof carrying a deep-list @context; the document's @context is a deep list
    # too, so _context_matches does a deep == comparison and recurses past the limit.
    proof = {
        "@context": deep_list,
        "type": di_proof.PROOF_TYPE,
        "cryptosuite": di_proof.CRYPTOSUITE,
        "verificationMethod": "did:web:example.org#main-key",
        "proofPurpose": "assertionMethod",
        "proofValue": "z" + "1" * 80,
    }
    secured = {"@context": deep_list, "name": "Test Pantry", "proof": proof}
    assert di_proof.verify_proof(secured, _public_key(signing_key)) is False
