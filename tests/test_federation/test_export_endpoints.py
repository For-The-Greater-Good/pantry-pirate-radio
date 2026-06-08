"""Task 7 (PR-C): the federation publish-read endpoints (design §6.3).

DB-backed against the real ``federation_log`` table via a minimal FastAPI app that
mounts ONLY the federation data router (no full-app deps) — mirroring how the slim
Lambda mounts it. The log is seeded with ``log.append`` on a sync session.

Load-bearing properties:
  * ``/export`` rows are byte-faithful signed envelopes that verify under the
    publisher key, each carrying a valid RFC-6962 inclusion proof against the
    checkpoint tree (the §6.3 export-fidelity rule — served from preimage_canonical,
    not the JSONB);
  * delta pulls return only newer sequences; below-window → 410;
  * ``/checkpoint`` + ``/state.txt`` are Go-verifiable C2SP notes;
  * a consistency proof across pulls detects a rewritten log;
  * ``FEDERATION_ENABLED=False`` → every route 404s (publish kill switch).
"""

import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.federation.router import router as federation_router
from app.federation import checkpoint as checkpoint_mod
from app.federation import envelope as envelope_mod
from app.federation import log, merkle

_SEED = bytes(range(32))
_CONTEXT = "https://hsds-federation.pantrypirateradio.org/profile"
_LICENSE = "sandia-ftgg-nc-os-1.0"
_NODE_DID = "did:web:node.example"


def _key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_SEED)


def _sync_session():
    # Seed where the ROUTER reads: it uses settings.DATABASE_URL (test-aware, ->
    # the test DB during pytest), NOT os.environ["DATABASE_URL"] (the dev DB).
    from app.core.config import settings

    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    return sessionmaker(bind=create_engine(url))()


@pytest.fixture()
def configured(monkeypatch):
    """Configure a signing identity on the live settings object for the router."""
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_ENABLED", True)
    monkeypatch.setattr(live, "FEDERATION_DID", _NODE_DID)
    monkeypatch.setattr(
        live, "FEDERATION_SIGNING_KEY", base64.b64encode(_SEED).decode("ascii")
    )
    return live


@pytest.fixture()
def client(configured):
    app = FastAPI()
    app.include_router(federation_router, prefix="/api/v1")
    return TestClient(app)


@pytest.fixture()
def seeded_log():
    """Seed the log with 5 activities; yield the count. Truncates around the test."""
    session = _sync_session()
    session.execute(text("TRUNCATE federation_log"))
    session.commit()
    for i in range(5):
        log.append(
            session,
            activity_type="Update",
            federation_id=f"node.example:loc-{i}",
            obj={"id": f"loc-{i}", "name": f"Pantry {i}", "latitude": 40.0 + i},
            origin_did=_NODE_DID,
            signing_key=_key(),
            context=_CONTEXT,
            license=_LICENSE,
            published="2026-06-06T00:00:00Z",
        )
    yield 5
    session.execute(text("TRUNCATE federation_log"))
    session.commit()
    session.close()


def test_export_returns_signed_objects_with_inclusion_proofs(client, seeded_log):
    r = client.get("/api/v1/federation/export?_since=0")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    rows = [json.loads(line) for line in r.text.splitlines() if line]
    assert len(rows) == seeded_log
    assert int(r.headers["X-Federation-Sequence"]) == seeded_log
    pub = _key().public_key()
    for row in rows:
        assert "proof" in row and "inclusion_proof" in row
        # The row minus the inclusion proof is the exact signed envelope.
        env = {k: v for k, v in row.items() if k != "inclusion_proof"}
        assert envelope_mod.verify_envelope(env, pub) is True
        # The inclusion proof verifies against the checkpoint root.
        leaf = {k: v for k, v in env.items() if k not in ("id", "proof")}
        from app.federation.canonical import jcs_bytes

        proof = [bytes.fromhex(h) for h in row["inclusion_proof"]]
        # recompute root over all 5 leaves for the assertion
        sess = _sync_session()
        try:
            root = merkle.merkle_root(log.leaf_data(sess, seeded_log))
        finally:
            sess.close()
        assert merkle.verify_inclusion(
            jcs_bytes(leaf), row["sequence"] - 1, seeded_log, proof, root
        )


def test_delta_pull_returns_only_newer(client, seeded_log):
    r = client.get("/api/v1/federation/export?_since=3")
    rows = [json.loads(line) for line in r.text.splitlines() if line]
    assert [row["sequence"] for row in rows] == [4, 5]
    assert all(row["sequence"] > 3 for row in rows)


def test_export_pagination_next_cursor(client, seeded_log):
    r = client.get("/api/v1/federation/export?_since=0&limit=2")
    rows = [json.loads(line) for line in r.text.splitlines() if line]
    assert [row["sequence"] for row in rows] == [1, 2]
    assert r.headers["X-Federation-Next-Cursor"] == "2"
    # The last page carries no next-cursor.
    r2 = client.get("/api/v1/federation/export?_since=4")
    assert "X-Federation-Next-Cursor" not in r2.headers


def test_below_window_floor_returns_410(client, seeded_log):
    # Simulate an archived prefix: delete sequences 1..3 so the floor rises to 4.
    sess = _sync_session()
    try:
        sess.execute(text("DELETE FROM federation_log WHERE sequence <= 3"))
        sess.commit()
    finally:
        sess.close()
    r = client.get("/api/v1/federation/export?_since=1", follow_redirects=False)
    assert r.status_code == 410
    assert r.json()["detail"]["live_window_floor"] == 4


def test_export_pinned_tree_size_verifies_against_held_checkpoint(client, seeded_log):
    """Gauntlet round-3 HIGH regression: the §6.6 pull contract. A consumer fetches
    /checkpoint (N, root@N), then /export?tree_size=N, and every inclusion proof
    verifies against the HELD root@N — even though the head keeps advancing. This is
    the only way proofs are verifiable on a live (continuously-appending) node."""
    from app.federation.canonical import jcs_bytes

    cp = client.get("/api/v1/federation/checkpoint").json()
    n, root = cp["tree_size"], bytes.fromhex(cp["root_hash"])

    # Head advances after the consumer pinned the checkpoint.
    sess = _sync_session()
    try:
        log.append(
            sess,
            activity_type="Update",
            federation_id="node.example:loc-new",
            obj={"id": "loc-new", "name": "New"},
            origin_did=_NODE_DID,
            signing_key=_key(),
            context=_CONTEXT,
            license=_LICENSE,
            published="2026-06-06T00:00:00Z",
        )
    finally:
        sess.close()
    assert client.get("/api/v1/federation/checkpoint").json()["tree_size"] == n + 1

    # Pull pinned to N: every proof verifies against the held root@N.
    r = client.get(f"/api/v1/federation/export?_since=0&tree_size={n}")
    assert int(r.headers["X-Federation-Sequence"]) == n
    rows = [json.loads(line) for line in r.text.splitlines() if line]
    assert len(rows) == n  # the new row (n+1) is excluded — pinned to N
    for row in rows:
        env = {k: v for k, v in row.items() if k != "inclusion_proof"}
        leaf = {k: v for k, v in env.items() if k not in ("id", "proof")}
        proof = [bytes.fromhex(h) for h in row["inclusion_proof"]]
        assert merkle.verify_inclusion(
            jcs_bytes(leaf), row["sequence"] - 1, n, proof, root
        )


def test_export_tree_size_beyond_head_is_400(client, seeded_log):
    """A pinned tree_size beyond the head can't be proven — client error, not 410."""
    r = client.get(f"/api/v1/federation/export?tree_size={seeded_log + 10}")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "tree_size_exceeds_head"


def test_checkpoint_consistency_proof_410_not_500_on_trimmed_prefix(client, seeded_log):
    """Gauntlet round-4 MEDIUM regression: /checkpoint?from_tree_size= must 410
    (not 500) when the prefix it needs has been trimmed."""
    sess = _sync_session()
    try:
        sess.execute(text("DELETE FROM federation_log WHERE sequence <= 2"))
        sess.commit()
    finally:
        sess.close()
    # from_tree_size=3 needs leaves 1..3 (1,2 trimmed) -> consistency proof can't build.
    r = client.get("/api/v1/federation/checkpoint?from_tree_size=3")
    assert r.status_code == 410
    assert r.json()["detail"]["error"] == "below_live_window"


def test_checkpoint_state_history_410_not_500_on_trimmed_prefix(client, seeded_log):
    """Gauntlet round-3 HIGH regression: a trimmed prefix must yield a clean 410 on
    /checkpoint, /state.txt, AND /history — not a 500 (I only fixed /export before)."""
    sess = _sync_session()
    try:
        sess.execute(text("DELETE FROM federation_log WHERE sequence <= 2"))
        sess.commit()
    finally:
        sess.close()
    for path in (
        "/api/v1/federation/checkpoint",
        "/api/v1/federation/state.txt",
        "/api/v1/federation/history/node.example:loc-3",
    ):
        r = client.get(path)
        assert r.status_code == 410, f"{path} -> {r.status_code} (want 410)"


def test_export_above_floor_with_trimmed_prefix_returns_410_not_500(client, seeded_log):
    """Gauntlet HIGH regression: a trimmed prefix (proofs can't be rebuilt) must
    yield a clean 410, never a 500, even for _since at/above the floor."""
    sess = _sync_session()
    try:
        sess.execute(text("DELETE FROM federation_log WHERE sequence <= 3"))
        sess.commit()
    finally:
        sess.close()
    # _since=4 is at the floor; the tree can't be rebuilt (leaves 1..3 gone).
    r = client.get("/api/v1/federation/export?_since=4", follow_redirects=False)
    assert r.status_code == 410
    assert r.json()["detail"]["error"] == "below_live_window"


def test_checkpoint_from_tree_size_beyond_head_flags_regression(client, seeded_log):
    """A from_tree_size larger than the current head signals log regression /
    truncation (possible equivocation) — flagged, not silently dropped."""
    cp = client.get(
        f"/api/v1/federation/checkpoint?from_tree_size={seeded_log + 5}"
    ).json()
    assert cp["log_regression"] is True
    assert "consistency_proof" not in cp


def test_checkpoint_and_state_txt_signed(client, seeded_log):
    cp = client.get("/api/v1/federation/checkpoint").json()
    assert {"origin", "tree_size", "root_hash", "timestamp", "signature"} <= set(cp)
    assert cp["tree_size"] == seeded_log
    # The note is a Go-verifiable C2SP signed note under the node key + DID.
    assert checkpoint_mod.verify_note(cp["note"], _key().public_key(), _NODE_DID)
    state = client.get("/api/v1/federation/state.txt")
    assert state.status_code == 200
    assert state.headers["content-type"].startswith("text/plain")
    assert state.text == cp["note"]


def test_checkpoint_and_state_txt_expose_retention_horizon(client, seeded_log):
    """The retention horizon (the sequence below which leaves are archived, =
    live_window_floor) is advertised UNSIGNED so peers learn the floor: a JSON
    sibling on /checkpoint and an X-Federation-Retention-Horizon header on
    /state.txt — never inside the rigid C2SP signed note body (Go-witness interop).
    Unpruned here, so it equals the floor of 1."""
    cp = client.get("/api/v1/federation/checkpoint").json()
    assert cp["retention_horizon_sequence"] == 1
    assert cp["retention_horizon_sequence"] == cp["live_window_floor"]
    state = client.get("/api/v1/federation/state.txt")
    assert state.headers["X-Federation-Retention-Horizon"] == "1"
    # The signed note body itself is untouched (still the rigid C2SP 4-line shape).
    assert state.text == cp["note"]


def test_consistency_proof_detects_rewritten_log(client, seeded_log):
    """A consumer holding the pre-tamper checkpoint detects a rewritten leaf via
    the consistency proof the endpoint serves — provable, not alleged."""
    old = client.get("/api/v1/federation/checkpoint").json()
    old_size, old_root = old["tree_size"], bytes.fromhex(old["root_hash"])

    # Adversary rewrites a committed leaf (mutate preimage_canonical of seq 1).
    sess = _sync_session()
    try:
        forged = envelope_mod.build_preimage(
            context=_CONTEXT,
            activity_type="Update",
            actor=_NODE_DID,
            attributed_to=_NODE_DID,
            origin=_NODE_DID,
            federation_id="node.example:loc-0",
            obj={"id": "loc-0", "name": "FORGED", "latitude": 40.0},
            sequence=1,
            published="2026-06-06T00:00:00Z",
            license=_LICENSE,
        )
        from app.federation.canonical import jcs_bytes

        sess.execute(
            text(
                "UPDATE federation_log SET preimage_canonical = :pb WHERE sequence = 1"
            ),
            {"pb": jcs_bytes(forged)},
        )
        sess.commit()
    finally:
        sess.close()

    new = client.get(f"/api/v1/federation/checkpoint?from_tree_size={old_size}").json()
    new_root = bytes.fromhex(new["root_hash"])
    proof = [bytes.fromhex(h) for h in new["consistency_proof"]]
    # The tampered tree is NOT a consistent extension of the held checkpoint.
    assert (
        merkle.verify_consistency(old_size, new["tree_size"], proof, old_root, new_root)
        is False
    )


def test_history_is_bounded(client, seeded_log, monkeypatch):
    """Gauntlet round-4: /history caps its result set (no unbounded payload /
    proof-generation for a hot federation_id)."""
    monkeypatch.setattr(log, "_HISTORY_MAX_ROWS", 2)
    sess = _sync_session()
    try:
        for i in range(4):  # 4 activities for one federation_id
            log.append(
                sess,
                activity_type="Update",
                federation_id="node.example:hot",
                obj={"id": "hot", "name": f"v{i}"},
                origin_did=_NODE_DID,
                signing_key=_key(),
                context=_CONTEXT,
                license=_LICENSE,
                published="2026-06-06T00:00:00Z",
            )
    finally:
        sess.close()
    r = client.get("/api/v1/federation/history/node.example:hot")
    body = r.json()
    assert len(body["activities"]) == 2  # capped
    # Most-recent kept, returned oldest-first within the cap.
    seqs = [a["sequence"] for a in body["activities"]]
    assert seqs == sorted(seqs)


def test_history_returns_proof_backed_activities(client, seeded_log):
    r = client.get("/api/v1/federation/history/node.example:loc-2")
    assert r.status_code == 200
    body = r.json()
    assert body["federation_id"] == "node.example:loc-2"
    assert len(body["activities"]) == 1
    # Proofs are anchored: tree_size in body + header (else unverifiable on a live node).
    assert body["tree_size"] == seeded_log
    assert int(r.headers["X-Federation-Sequence"]) == seeded_log
    act = body["activities"][0]
    assert act["federation_id"] == "node.example:loc-2"
    assert "inclusion_proof" in act
    assert envelope_mod.verify_envelope(
        {k: v for k, v in act.items() if k != "inclusion_proof"}, _key().public_key()
    )


def test_federation_data_routes_reach_the_slim_lambda() -> None:
    """Principle XV: the /export|checkpoint|state.txt|history routes must be present
    in the slim Lambda app (it includes v1_router), not just the full app."""
    import app.api.lambda_app as lambda_app

    paths = {getattr(r, "path", None) for r in lambda_app.app.routes}
    for p in (
        "/api/v1/federation/export",
        "/api/v1/federation/checkpoint",
        "/api/v1/federation/state.txt",
    ):
        assert p in paths, f"{p} missing from the slim Lambda app"
    # history uses a :path converter, so match the registered prefix form.
    assert any(
        str(p).startswith("/api/v1/federation/history/") for p in paths
    ), "history route missing from the slim Lambda app"


def test_kill_switch_404s_every_route(client, seeded_log, monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_ENABLED", False)
    for path in (
        "/api/v1/federation/export?_since=0",
        "/api/v1/federation/checkpoint",
        "/api/v1/federation/state.txt",
        "/api/v1/federation/history/node.example:loc-0",
    ):
        assert client.get(path).status_code == 404, path
