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

DB-backed; all data fictional. These tests SERIALIZE on the single ``federation_log``
table — each TRUNCATEs, seeds, and TRUNCATEs again — so they must not be reordered
to interleave or run in parallel (e.g. pytest-xdist / pytest-randomly) while sharing
one DB; the seed→snapshot→truncate sequencing is what gives two identities one table.
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
    (the checkpoint origin == the node DID). Fails CLOSED: raises if the doc is
    unavailable, if there is not EXACTLY one ``#main-key`` (no entry, or a duplicate
    an attacker could prepend to win a first-match), or if the advertised key is
    undecodable — a peer refuses an ambiguous or unparseable trust anchor rather
    than proceeding with a bogus key."""
    r = get("/.well-known/did.json")
    if r.status_code != 200 or r.json_body is None:
        raise ValueError(f"did.json unavailable: {r.status_code}")
    doc = r.json_body
    did = doc["id"]
    mains = [m for m in doc["verificationMethod"] if m["id"] == f"{did}#main-key"]
    if len(mains) != 1:
        raise ValueError(f"expected exactly one #main-key, found {len(mains)}")
    pub = identity.public_key_from_multibase(mains[0]["publicKeyMultibase"])
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


def _pin_note_anchored(get, adapter, pubkey_hex, key_name) -> tuple[int, str]:
    """Pin the node's current checkpoint the way a peer must: verify the SIGNED
    note, derive (tree_size, root) FROM the note, and require the unsigned JSON to
    agree (§6.3). Returns (tree_size, root_hex) anchored to the signed bytes."""
    cp = get("/api/v1/federation/checkpoint").json_body
    assert adapter.verify_note(cp["note"], pubkey_hex, key_name)
    parsed = adapter.parse_checkpoint(cp["note"])
    assert cp["tree_size"] == parsed["tree_size"]
    assert cp["root_hash"] == parsed["root_hex"]
    return parsed["tree_size"], parsed["root_hex"]


@pytest.mark.integration
def test_two_node_consistency_proof_across_growth(node_a):
    """B pins A at size K (anchored to A's SIGNED note), A publishes more (the log
    GROWS to N), and B verifies the RFC-6962 CONSISTENCY proof K→N via the
    note-anchored consumer ``verify_consistency_to_head`` — the append-only
    guarantee a peer relies on to trust an incremental pull. Roots come from the
    signed note, never the unsigned JSON convenience field."""
    client, session = node_a
    get = _get_fn(client)
    pubkey_hex, key_name = _discover_trust_anchor(get)
    adapter = RefAdapter()

    k, root_k = _pin_note_anchored(get, adapter, pubkey_hex, key_name)
    assert k == 3

    # A publishes two more activities -> head grows to N=5.
    _append(session, _DID_A, _key(_SEED_A), count=2, start=3)

    report = runner.verify_consistency_to_head(
        get, adapter, pubkey_hex, key_name, held_size=k, held_root_hex=root_k
    )
    assert report.current_verified, report.detail
    assert report.proof_present, report.detail
    assert report.consistent, report.detail
    assert report.tree_size == 5
    assert report.ok


@pytest.mark.integration
def test_two_node_consistency_rejects_a_forked_history(node_a):
    """The append-only guarantee at the primitive level: a forged/rewritten second
    root cannot satisfy the consistency proof. Roots are NOTE-anchored; feeding
    ``verify_consistency`` a forged second root MUST be rejected, while the genuine
    note-anchored root verifies (so the proof itself is sound, not vacuous)."""
    client, session = node_a
    get = _get_fn(client)
    pubkey_hex, key_name = _discover_trust_anchor(get)
    adapter = RefAdapter()

    k, root_k = _pin_note_anchored(get, adapter, pubkey_hex, key_name)
    _append(session, _DID_A, _key(_SEED_A), count=2, start=3)
    n, root_n = _pin_note_anchored(get, adapter, pubkey_hex, key_name)
    proof = get(f"/api/v1/federation/checkpoint?from_tree_size={k}").json_body[
        "consistency_proof"
    ]

    forged_root_n = "00" * 32
    assert not adapter.verify_consistency(k, n, proof, root_k, forged_root_n)
    # And the genuine note-anchored root still verifies (the proof is sound).
    assert adapter.verify_consistency(k, n, proof, root_k, root_n)


@pytest.mark.integration
def test_two_node_consistency_rejects_equivocating_json_root(node_a):
    """The equivocation teeth (the defect a JSON-anchored pattern would have): a
    node serving an HONEST signed note but a LYING unsigned JSON ``root_hash`` is
    REJECTED by the note-anchored consumer, which pins the root from the note and
    cross-checks the JSON. Trusting the unsigned field instead would let an
    equivocating node pass off a forked history as an append-only extension."""
    client, session = node_a
    get = _get_fn(client)
    pubkey_hex, key_name = _discover_trust_anchor(get)
    adapter = RefAdapter()

    k, root_k = _pin_note_anchored(get, adapter, pubkey_hex, key_name)
    _append(session, _DID_A, _key(_SEED_A), count=2, start=3)

    base = _get_fn(client)

    def lying_json_get(path: str) -> runner.Resp:
        r = base(path)
        if path.startswith("/api/v1/federation/checkpoint") and r.json_body is not None:
            body = dict(r.json_body)
            body["root_hash"] = "11" * 32  # forge the unsigned field, keep the note
            r = runner.Resp(r.status_code, r.text, r.headers, body)
        return r

    report = runner.verify_consistency_to_head(
        lying_json_get, adapter, pubkey_hex, key_name, held_size=k, held_root_hex=root_k
    )
    assert not report.current_verified
    assert not report.ok
    assert "disagree" in report.detail


@pytest.mark.integration
def test_two_node_consistency_rejects_a_malformed_proof(node_a):
    """A node serving a MALFORMED (non-hex) consistency_proof element is a failed
    node, not a crash: the note-anchored consumer catches the decode error and
    returns consistent=False, honoring its 'hostile/garbage must not crash' contract
    (the note + JSON here are honest, so only the proof is bad)."""
    client, session = node_a
    get = _get_fn(client)
    pubkey_hex, key_name = _discover_trust_anchor(get)
    adapter = RefAdapter()

    k, root_k = _pin_note_anchored(get, adapter, pubkey_hex, key_name)
    _append(session, _DID_A, _key(_SEED_A), count=2, start=3)

    base = _get_fn(client)

    def mangled_proof_get(path: str) -> runner.Resp:
        r = base(path)
        if "from_tree_size" in path and r.json_body is not None:
            body = dict(r.json_body)
            proof = list(body.get("consistency_proof") or [])
            body["consistency_proof"] = ["zz"] + proof[1:] if proof else ["zz"]
            r = runner.Resp(r.status_code, r.text, r.headers, body)
        return r

    report = runner.verify_consistency_to_head(
        mangled_proof_get,
        adapter,
        pubkey_hex,
        key_name,
        held_size=k,
        held_root_hex=root_k,
    )
    assert report.current_verified  # note + JSON are honest; only the proof is bad
    assert report.proof_present
    assert not report.consistent
    assert not report.ok
    assert "malformed" in report.detail


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
def test_two_node_discovery_rejects_missing_main_key(node_a):
    """A did.json with no ``#main-key`` verificationMethod is rejected at discover —
    a peer fails closed rather than indexing into an empty selection."""
    client, _ = node_a
    base = _get_fn(client)

    def stripped_get(path: str) -> runner.Resp:
        r = base(path)
        if path == "/.well-known/did.json" and r.json_body is not None:
            doc = json.loads(json.dumps(r.json_body))
            doc["verificationMethod"] = [
                m
                for m in doc["verificationMethod"]
                if not m["id"].endswith("#main-key")
            ]
            r = runner.Resp(r.status_code, r.text, r.headers, doc)
        return r

    with pytest.raises(ValueError):
        _discover_trust_anchor(stripped_get)


@pytest.mark.integration
def test_two_node_discovery_rejects_duplicate_main_key(node_a):
    """A did.json advertising TWO ``#main-key`` entries is ambiguous — reject rather
    than first-wins, which an attacker could exploit by PREPENDING a forged key to
    win the match. Fails closed at discover."""
    client, _ = node_a
    base = _get_fn(client)
    foreign_mb = public_key_multibase(_key(bytes([5]) + bytes(31)).public_key())

    def dup_get(path: str) -> runner.Resp:
        r = base(path)
        if path == "/.well-known/did.json" and r.json_body is not None:
            doc = json.loads(json.dumps(r.json_body))
            did = doc["id"]
            forged = {
                "id": f"{did}#main-key",
                "type": "Ed25519VerificationKey2020",
                "controller": did,
                "publicKeyMultibase": foreign_mb,
                "priority": 1,
            }
            doc["verificationMethod"] = [forged] + doc["verificationMethod"]
            r = runner.Resp(r.status_code, r.text, r.headers, doc)
        return r

    with pytest.raises(ValueError):
        _discover_trust_anchor(dup_get)


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
