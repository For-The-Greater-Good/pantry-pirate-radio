"""HSDS-FX two-node interop — the §15 P1 golden journey (#558, the "raw sync").

The single-node Level-2 loop (``test_hsdsfx_level2.py``) hands the verifier the
publisher's public key. THIS test closes the loop a *real* federating peer runs:
**Node B DISCOVERS Node A's trust anchor from A's published
``/.well-known/did.json``** (decoding the ``#main-key`` ``publicKeyMultibase`` via
``identity.public_key_from_multibase`` — the one genuinely-new primitive) and only
then pulls + cross-verifies A's signed checkpoint, every envelope signature, the
RFC-6962 inclusion proofs, and the consistency proof across growth. Nothing is
handed in: the key flows from the served document, so a swapped/forged discovery
doc is caught.

Honest framing: A and B here are two *instances of the same code*, sequenced over
one ``federation_log`` table (seed → snapshot → truncate). That is genuine
cross-node discovery + cryptographic-verification integration evidence and the
partner-reuse seed (a partner check-in tool that REUSES this app federates exactly
this way) — it is **NOT** a foreign-implementation interop confirmation (that needs
a non-PPR node, §180 / P7) and promotes no ``interop_pending`` corpus row. The
behavioral P2 effects (pull INGEST, corroboration, authority, tombstone-redirect)
are deliberately out of scope: this loop is verify-only.

DB-backed; all data fictional.
"""

from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.federation.router import router as federation_router
from app.federation import identity, log
from app.federation.identity import public_key_multibase
from app.federation.routes_public import register_federation_public_routes
from tests.test_federation.conformance import runner
from tests.test_federation.conformance.adapter import RefAdapter

# Two DISTINCT node identities — distinct DIDs AND distinct signing keys.
_SEED_A = bytes(range(32))
_SEED_B = bytes(range(32, 64))
_DID_A = "did:web:node-a.example"
_DID_B = "did:web:node-b.example"
_CONTEXT = "https://hsds-federation.pantrypirateradio.org/profile"
_LICENSE = "sandia-ftgg-nc-os-1.0"


def _key(seed: bytes) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(seed)


def _sync_session():
    from app.core.config import settings

    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    return sessionmaker(bind=create_engine(url))()


def _truncate(session) -> None:
    session.execute(text("TRUNCATE federation_log"))
    session.commit()


def _configure(monkeypatch, did: str, seed: bytes) -> None:
    """Point the module-level settings singleton at one node's identity."""
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_ENABLED", True)
    monkeypatch.setattr(live, "FEDERATION_DID", did)
    monkeypatch.setattr(
        live, "FEDERATION_SIGNING_KEY", base64.b64encode(seed).decode("ascii")
    )
    # A node's checkpoint origin/domain derives from its DID; keep it unset so the
    # discovery doc + checkpoint both fall back to the DID host (no override drift).
    monkeypatch.setattr(live, "FEDERATION_DOMAIN", None, raising=False)


def _append(
    session, did: str, key: Ed25519PrivateKey, count: int, start: int = 0
) -> None:
    """Publish ``count`` Update activities for the node identified by ``did``."""
    for i in range(start, start + count):
        log.append(
            session,
            activity_type="Update",
            federation_id=f"{did.split(':')[-1]}:loc-{i}",
            obj={"id": f"loc-{i}", "name": f"Pantry {i}"},
            origin_did=did,
            signing_key=key,
            context=_CONTEXT,
            license=_LICENSE,
            published="2026-06-06T00:00:00Z",
        )


def _bring_up_node(monkeypatch, did: str, seed: bytes, count: int):
    """A live node: configured identity, ``count`` published activities, an app
    serving BOTH the data router (/export, /checkpoint, ...) and the public
    discovery routes (/.well-known/did.json) so a peer can resolve its key."""
    _configure(monkeypatch, did, seed)
    session = _sync_session()
    _truncate(session)
    _append(session, did, _key(seed), count)
    app = FastAPI()
    app.include_router(federation_router, prefix="/api/v1")
    register_federation_public_routes(app)
    return TestClient(app), session


@pytest.fixture()
def node_a(monkeypatch):
    """Node A (DID_A/key_A): a live HSDS-FX node with 3 published activities."""
    client, session = _bring_up_node(monkeypatch, _DID_A, _SEED_A, count=3)
    try:
        yield client, session
    finally:
        _truncate(session)
        session.close()


def _get_fn(client: TestClient):
    def get(path: str) -> runner.Resp:
        r = client.get(path)
        body = None
        if r.headers.get("content-type", "").startswith("application/json"):
            body = r.json()
        return runner.Resp(
            status_code=r.status_code,
            text=r.text,
            headers=dict(r.headers),
            json_body=body,
        )

    return get


def _discover_trust_anchor(get) -> tuple[str, str]:
    """Node B's DISCOVER step: resolve a peer's (pubkey_hex, checkpoint key_name)
    purely from its published ``/.well-known/did.json`` — nothing handed in.

    Picks the ``#main-key`` verificationMethod, decodes its ``publicKeyMultibase``
    to raw Ed25519 bytes, and takes the document ``id`` as the checkpoint key name
    (the checkpoint origin == the node DID). Raises if the doc is unavailable or
    the advertised key is undecodable — a peer refuses a trust anchor it can't
    parse rather than proceeding with a bogus key."""
    r = get("/.well-known/did.json")
    if r.status_code != 200 or r.json_body is None:
        raise ValueError(f"did.json unavailable: {r.status_code}")
    doc = r.json_body
    did = doc["id"]
    main = next(m for m in doc["verificationMethod"] if m["id"] == f"{did}#main-key")
    pub = identity.public_key_from_multibase(main["publicKeyMultibase"])
    pubkey_hex = pub.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return pubkey_hex, did


@pytest.mark.integration
@pytest.mark.parametrize("did, seed", [(_DID_A, _SEED_A), (_DID_B, _SEED_B)])
def test_two_node_publish_discover_pull_crossverify(monkeypatch, did, seed):
    """The full §15 golden journey, for EITHER node identity (A, then its mirror
    B): publish → B discovers the key from did.json → pull /export@N → verify the
    signed checkpoint + every envelope signature + every inclusion proof. Running
    it for both DIDs proves the verify key is RESOLVED from each node's own
    published document, never hardcoded."""
    client, session = _bring_up_node(monkeypatch, did, seed, count=3)
    try:
        get = _get_fn(client)
        pubkey_hex, key_name = _discover_trust_anchor(get)
        # The anchor genuinely came from the served did.json, and matches the
        # node's signing key (so it will verify the checkpoint the node signs).
        assert key_name == did
        expected_hex = (
            _key(seed).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        )
        assert pubkey_hex == expected_hex

        report = runner.verify_level2(get, RefAdapter(), pubkey_hex, key_name)
        assert report.checkpoint_verified, report.detail
        assert report.tree_size == 3
        assert report.rows_total == 3
        assert report.rows_verified == 3, report.detail
        assert report.rows_complete
        assert report.ok
    finally:
        _truncate(session)
        session.close()


@pytest.mark.integration
def test_two_node_consistency_proof_across_growth(node_a):
    """B pins A at size K, A publishes more (the log GROWS to N), and B verifies the
    RFC-6962 CONSISTENCY proof K→N served by ``/checkpoint?from_tree_size=K`` — the
    append-only guarantee a peer relies on to trust an incremental pull."""
    client, session = node_a
    get = _get_fn(client)
    pubkey_hex, key_name = _discover_trust_anchor(get)
    adapter = RefAdapter()

    # Pin A at its current head K (=3); the SIGNED note is the trust anchor.
    cp_k = get("/api/v1/federation/checkpoint").json_body
    assert adapter.verify_note(cp_k["note"], pubkey_hex, key_name)
    k = cp_k["tree_size"]
    root_k = cp_k["root_hash"]
    assert k == 3

    # A publishes two more activities -> head grows to N.
    _append(session, _DID_A, _key(_SEED_A), count=2, start=3)
    cp_n = get("/api/v1/federation/checkpoint").json_body
    assert adapter.verify_note(cp_n["note"], pubkey_hex, key_name)
    n = cp_n["tree_size"]
    root_n = cp_n["root_hash"]
    assert n == 5

    proof_body = get(f"/api/v1/federation/checkpoint?from_tree_size={k}").json_body
    assert proof_body["consistency_from"] == k
    proof = proof_body["consistency_proof"]
    assert adapter.verify_consistency(k, n, proof, root_k, root_n)


@pytest.mark.integration
def test_two_node_consistency_rejects_a_forked_history(node_a):
    """A forked/rewritten peer (a different root at size N) cannot satisfy the
    consistency proof: feeding ``verify_consistency`` a forged second root MUST be
    rejected. The forked-peer negative for the two-node loop."""
    client, session = node_a
    get = _get_fn(client)
    pubkey_hex, key_name = _discover_trust_anchor(get)
    adapter = RefAdapter()

    cp_k = get("/api/v1/federation/checkpoint").json_body
    k = cp_k["tree_size"]
    root_k = cp_k["root_hash"]
    _append(session, _DID_A, _key(_SEED_A), count=2, start=3)
    cp_n = get("/api/v1/federation/checkpoint").json_body
    n = cp_n["tree_size"]
    proof = get(f"/api/v1/federation/checkpoint?from_tree_size={k}").json_body[
        "consistency_proof"
    ]

    forged_root_n = "00" * 32
    assert not adapter.verify_consistency(k, n, proof, root_k, forged_root_n)
    # And the genuine root still verifies (the proof itself is sound).
    assert adapter.verify_consistency(k, n, proof, root_k, cp_n["root_hash"])


@pytest.mark.integration
def test_two_node_rejects_when_did_json_key_is_swapped(node_a):
    """If A's published did.json advertises a DIFFERENT key than the one signing
    A's checkpoints (a forged / MITM'd discovery doc), B — which resolves the
    verify key FROM the did.json bytes — fails the checkpoint verify and pulls
    nothing. This is the teeth that the trust anchor flows from the served
    document, not a constant: swap the bytes, and the loop breaks."""
    client, _ = node_a
    base = _get_fn(client)
    foreign_mb = public_key_multibase(_key(bytes([9]) + bytes(31)).public_key())

    def swapped_get(path: str) -> runner.Resp:
        r = base(path)
        if path == "/.well-known/did.json" and r.json_body is not None:
            doc = json.loads(json.dumps(r.json_body))  # deep copy
            for m in doc["verificationMethod"]:
                if m["id"].endswith("#main-key"):
                    m["publicKeyMultibase"] = foreign_mb
            r = runner.Resp(r.status_code, r.text, r.headers, doc)
        return r

    pubkey_hex, key_name = _discover_trust_anchor(swapped_get)
    # The resolved (foreign) key is NOT the key A signs with.
    assert (
        pubkey_hex
        != _key(_SEED_A).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    )
    report = runner.verify_level2(swapped_get, RefAdapter(), pubkey_hex, key_name)
    assert not report.checkpoint_verified
    assert report.rows_total == 0
    assert not report.ok


@pytest.mark.integration
def test_two_node_discovery_rejects_malformed_multibase(node_a):
    """A did.json advertising a malformed ``publicKeyMultibase`` is rejected at the
    DISCOVER step — B refuses to derive a trust anchor it cannot decode rather than
    proceeding with a bogus key (the decoder's guard rail, exercised end-to-end)."""
    client, _ = node_a
    base = _get_fn(client)

    def garbage_get(path: str) -> runner.Resp:
        r = base(path)
        if path == "/.well-known/did.json" and r.json_body is not None:
            doc = json.loads(json.dumps(r.json_body))
            for m in doc["verificationMethod"]:
                if m["id"].endswith("#main-key"):
                    m["publicKeyMultibase"] = "z0OIl-not-base58"
            r = runner.Resp(r.status_code, r.text, r.headers, doc)
        return r

    with pytest.raises(ValueError):
        _discover_trust_anchor(garbage_get)


@pytest.mark.integration
def test_two_node_export_pin_beyond_head_is_a_clean_400(node_a):
    """Sibling guard exercised in the two-node path: a peer that pins a tree_size
    BEYOND A's head gets a clean 400 (tree_size_exceeds_head), never a 500. The
    genuine below-live-window 410 + cold-start archive surface is archival
    (Task 9), shipped in the archive-tiering increment — not faked here."""
    client, _ = node_a
    r = client.get("/api/v1/federation/export?_since=0&tree_size=999")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "tree_size_exceeds_head"
