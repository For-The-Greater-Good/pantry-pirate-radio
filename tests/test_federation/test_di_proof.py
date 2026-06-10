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
