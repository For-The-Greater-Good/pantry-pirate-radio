"""HSDS-FX Level-2 conformance — the live-node publish→pull→verify loop (Slice 3).

Drives a LIVE federation node over its §6.3 HTTP endpoints (the minimal
federation-router app, the in-repo reference node / #558 node-2) and runs the
conformance runner's ``verify_level2``: pin the signed ``/checkpoint``, pull
``/export`` at that tree_size, and verify every row's envelope signature AND its
RFC-6962 inclusion proof against the checkpoint root — exactly what a peer (or the
hosted Readiness Checker, #565) does. DB-backed; all data fictional.

The runner is transport-agnostic — here it is wired to a FastAPI ``TestClient``
(real ASGI HTTP); a deployed external check points the same runner at a URL.
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
from app.federation import log
from tests.test_federation.conformance import runner
from tests.test_federation.conformance.adapter import RefAdapter

_SEED = bytes(range(32))
_CONTEXT = "https://hsds-federation.pantrypirateradio.org/profile"
_LICENSE = "sandia-ftgg-nc-os-1.0"
_NODE_DID = "did:web:node.example"


def _key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_SEED)


def _pubkey_hex() -> str:
    pub = _key().public_key()
    return pub.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def _sync_session():
    from app.core.config import settings

    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    return sessionmaker(bind=create_engine(url))()


@pytest.fixture()
def configured(monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_ENABLED", True)
    monkeypatch.setattr(live, "FEDERATION_DID", _NODE_DID)
    monkeypatch.setattr(
        live, "FEDERATION_SIGNING_KEY", base64.b64encode(_SEED).decode("ascii")
    )
    return live


@pytest.fixture()
def node(configured):
    """A live HSDS-FX node: the federation router seeded with 3 activities."""
    session = _sync_session()
    session.execute(text("TRUNCATE federation_log"))
    session.commit()
    for i in range(3):
        log.append(
            session,
            activity_type="Update",
            federation_id=f"node.example:loc-{i}",
            obj={"id": f"loc-{i}", "name": f"Pantry {i}"},
            origin_did=_NODE_DID,
            signing_key=_key(),
            context=_CONTEXT,
            license=_LICENSE,
            published="2026-06-06T00:00:00Z",
        )
    app = FastAPI()
    app.include_router(federation_router, prefix="/api/v1")
    yield TestClient(app)
    session.execute(text("TRUNCATE federation_log"))
    session.commit()
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


def test_level2_live_node_publish_pull_verify_loop(node):
    """The full §6.6 loop: pin /checkpoint, pull /export@N, every row's envelope +
    inclusion proof verifies against the held root. This is the conformance a peer
    or the hosted Readiness Checker runs against a live node."""
    report = runner.verify_level2(_get_fn(node), RefAdapter(), _pubkey_hex(), _NODE_DID)
    assert report.checkpoint_verified, report.detail
    assert report.rows_total == 3, report.detail
    assert report.rows_verified == 3, report.detail
    assert report.ok


def test_level2_detects_a_tampered_row(node):
    """A consumer-side guard: if a served row's object is tampered (without the
    private key), its envelope signature fails and it is NOT counted verified —
    the live loop surfaces tampering, it doesn't rubber-stamp."""
    # Sanity: clean loop verifies all rows.
    clean = runner.verify_level2(_get_fn(node), RefAdapter(), _pubkey_hex(), _NODE_DID)
    assert clean.ok

    # Wrap get so /export rows are tampered in flight (simulating a hostile relay).
    base = _get_fn(node)

    def tampering_get(path: str) -> runner.Resp:
        r = base(path)
        if path.startswith("/api/v1/federation/export"):
            lines = []
            for line in r.text.splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                row["object"]["name"] = "EVIL"  # mutate, keep stale id+proof
                lines.append(json.dumps(row))
            r = runner.Resp(r.status_code, "\n".join(lines) + "\n", r.headers, None)
        return r

    report = runner.verify_level2(tampering_get, RefAdapter(), _pubkey_hex(), _NODE_DID)
    assert report.checkpoint_verified
    assert report.rows_total == 3
    assert report.rows_verified == 0  # every tampered row fails envelope verify
    assert not report.ok


def test_level2_detects_a_truncated_export(node):
    """A row-WITHHOLDING node — checkpoint commits to tree_size N but /export serves
    a valid subset — MUST fail: the served subset verifies individually, so only the
    tree_size/completeness checks expose the equivocation a Merkle log makes
    detectable."""
    base = _get_fn(node)

    def truncating_get(path: str) -> runner.Resp:
        r = base(path)
        if path.startswith("/api/v1/federation/export"):
            kept = [ln for ln in r.text.splitlines() if ln.strip()][:1]
            r = runner.Resp(r.status_code, "\n".join(kept) + "\n", r.headers, None)
        return r

    report = runner.verify_level2(
        truncating_get, RefAdapter(), _pubkey_hex(), _NODE_DID
    )
    assert report.checkpoint_verified
    assert report.tree_size == 3
    assert report.rows_total == 1
    assert report.rows_verified == 1  # the one served row is itself genuine
    assert not report.rows_complete
    assert not report.ok  # ...but the node withheld 2 of the 3 committed rows


def test_level2_rejects_a_checkpoint_that_does_not_verify(node):
    """If the served checkpoint note does not verify under the pubkey the consumer
    holds (a wrong-key / forged checkpoint), the loop bails before pulling rows."""
    wrong_seed = bytes([7]) + bytes(31)
    wrong_pub = (
        Ed25519PrivateKey.from_private_bytes(wrong_seed)
        .public_key()
        .public_bytes(Encoding.Raw, PublicFormat.Raw)
        .hex()
    )
    report = runner.verify_level2(_get_fn(node), RefAdapter(), wrong_pub, _NODE_DID)
    assert not report.checkpoint_verified
    assert report.rows_total == 0
    assert not report.ok


def test_level2_rejects_checkpoint_json_disagreeing_with_signed_note(node):
    """The signed note is the trust anchor: a /checkpoint whose unsigned JSON
    root_hash contradicts the signed note MUST be rejected (internal-consistency
    check), even though the note signature itself is valid."""
    base = _get_fn(node)

    def lying_json_get(path: str) -> runner.Resp:
        r = base(path)
        if path.startswith("/api/v1/federation/checkpoint") and r.json_body is not None:
            body = dict(r.json_body)
            body["root_hash"] = "00" * 32  # forge the convenience field, keep the note
            r = runner.Resp(r.status_code, r.text, r.headers, body)
        return r

    report = runner.verify_level2(
        lying_json_get, RefAdapter(), _pubkey_hex(), _NODE_DID
    )
    assert not report.checkpoint_verified
    assert not report.ok
    assert "disagree" in report.detail


def test_level2_follows_export_pagination(node, monkeypatch):
    """An HONEST node larger than one /export page MUST still pass — verify_level2
    follows Federation-Next-Cursor across pages and asserts completeness only over
    the assembled prefix. Regression guard: the completeness fix pulled a single page,
    which would wrongly FAIL every real node bigger than FEDERATION_EXPORT_PAGE_SIZE
    (a worse failure mode than the truncation hole it closed). Shrinking the page size
    to 1 makes the 3-row node paginate across 3 pages."""
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_EXPORT_PAGE_SIZE", 1)
    report = runner.verify_level2(_get_fn(node), RefAdapter(), _pubkey_hex(), _NODE_DID)
    assert report.tree_size == 3
    assert report.rows_total == 3, report.detail  # assembled across 3 pages
    assert report.rows_verified == 3, report.detail
    assert report.rows_complete
    assert report.ok
