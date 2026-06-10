"""Task 7 (PR-C): the federation publish-read data router (design §6.3).

Read-only. Imports only ``app/federation/{log,identity,checkpoint}`` + the DB — no
Redis/LLM — so it stays inside the slim read Lambda (Principle XV). The v1 router
(mounted by both ``app/main.py`` and ``app/api/lambda_app.py``) includes it, so all
four routes serve identically in Uvicorn and the slim Lambda.

Four routes (§6.3), all gated on ``FEDERATION_ENABLED`` (the publish kill switch,
fully enforced in P1 — a disabled node publishes nothing → 404):

  - ``GET /export?_since=<seq>`` — keyset NDJSON of signed envelopes + inclusion
    proofs; headers ``Federation-Sequence`` (= checkpoint tree_size),
    ``Federation-Next-Cursor``, ``Federation-Retention`` (RFC 6648: no ``X-``
    prefix). ``_since`` below the live-window floor → ``410`` + archive pointer.
  - ``GET /checkpoint`` — the current C2SP signed checkpoint as JSON.
  - ``GET /state.txt`` — the same checkpoint as the raw C2SP note (text/plain).
  - ``GET /history/{federation_id}`` — per-aggregate activity history + proofs.

The ``log`` helpers are SYNC (built for the reconciler/scripts). These handlers are
declared ``def`` (not ``async def``) so FastAPI runs them in its threadpool — no
event-loop blocking — using a lazily-built sync session.
"""

from __future__ import annotations

import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.federation import checkpoint as checkpoint_mod
from app.federation import identity, log

router = APIRouter(prefix="/federation", tags=["federation"])

_maker: sessionmaker | None = None


def _session() -> Session:
    """A sync session on the configured DB (the substrate is sync-only)."""
    global _maker
    if _maker is None:
        url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        _maker = sessionmaker(bind=create_engine(url, pool_pre_ping=True))
    return _maker()


def _require_enabled() -> None:
    # Publish kill switch (§6.2d, Principle XI): a disabled node publishes nothing.
    if not settings.FEDERATION_ENABLED:
        raise HTTPException(status_code=404, detail="federation disabled")


def _signing_key() -> Ed25519PrivateKey | None:
    """The node's Ed25519 signing key, or ``None`` if unset/malformed (→ 404)."""
    try:
        return identity.load_signing_key(settings.FEDERATION_SIGNING_KEY)
    except ValueError:
        return None


def _note_signature(note: str) -> str:
    """Extract the base64 signature blob from a single-signer C2SP note."""
    for line in reversed(note.splitlines()):
        if line.startswith("— "):
            parts = line.split(" ")
            if len(parts) == 3:
                return parts[2]
    return ""


@router.get("/export")
def export(
    since: int = Query(0, ge=0, alias="_since"),
    limit: int | None = Query(None, ge=1, le=10_000),
    tree_size: int | None = Query(None, ge=1),
) -> Response:
    _require_enabled()
    page = limit or settings.FEDERATION_EXPORT_PAGE_SIZE
    session = _session()
    try:
        floor = log.live_window_floor(session)
        # A pinned tree_size beyond the current head can't be proven (the tree
        # doesn't exist yet) — a client error, distinct from the trimmed-prefix
        # 410 below.
        if tree_size is not None and tree_size > log.safe_high_water(session):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "tree_size_exceeds_head",
                    "head": log.safe_high_water(session),
                },
            )
        # Below the live window: the requested prefix has been archived (§6.2g).
        # The verifiable cold-start snapshot (Task 9) is the archive surface.
        if floor > 0 and since + 1 < floor:
            raise HTTPException(
                status_code=410,
                detail={
                    "error": "below_live_window",
                    "live_window_floor": floor,
                    "archive": "cold-start snapshot (see discovery doc; §6.3)",
                },
            )
        try:
            # tree_size PINS proofs to a checkpoint the consumer holds (§6.6 pull
            # contract): GET /checkpoint -> (N, root@N) then /export?tree_size=N so
            # every inclusion proof verifies against root@N. Unpinned defaults to
            # the head (proofs only verifiable if the caller pins separately).
            rows, tree_size, next_cursor = log.read_export(
                session, since=since, limit=page, tree_size=tree_size
            )
        except ValueError:
            # The live window can't rebuild the requested tree (the prefix has
            # been archived/trimmed — proofs need leaves the live log no longer
            # holds). Treat as below-window: 410 + archive pointer, never a 500.
            # (Archive serving of trimmed leaves is Task 9.)
            raise _below_window_410(floor)
    finally:
        session.close()

    # Kill-switch TOCTOU: if FEDERATION_ENABLED flipped to False during the read,
    # do not serve (re-check the live value, mirroring signed_checkpoint).
    _require_enabled()

    body = "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows)
    headers = {
        "Federation-Sequence": str(tree_size),
        "Federation-Retention": str(settings.FEDERATION_RETENTION_DAYS),
    }
    if next_cursor is not None:
        headers["Federation-Next-Cursor"] = str(next_cursor)
    return Response(content=body, media_type="application/x-ndjson", headers=headers)


def _below_window_410(floor: int) -> HTTPException:
    """410 for a request that needs leaves the live log has trimmed (§6.2g).
    Consistent across /export, /checkpoint, /state.txt, /history — never a 500."""
    return HTTPException(
        status_code=410,
        detail={
            "error": "below_live_window",
            "live_window_floor": floor,
            "archive": "cold-start snapshot (see discovery doc; §6.3)",
        },
    )


def _current_note() -> str:
    """Sign the current checkpoint, or 404 if no identity / disabled.

    A trimmed prefix (leaf_data can't rebuild the tree — Task 9 archival) raises
    ValueError inside signed_checkpoint; surface it as a clean 410, never a 500
    (mirrors /export), so a Go note tool gets a defined error, not a 500.
    """
    key = _signing_key()
    if settings.FEDERATION_DID is None or key is None:
        raise HTTPException(status_code=404, detail="no federation signing identity")
    session = _session()
    try:
        try:
            note = log.signed_checkpoint(
                session, origin_did=settings.FEDERATION_DID, signing_key=key
            )
        except ValueError:
            raise _below_window_410(log.live_window_floor(session))
    finally:
        session.close()
    if note is None:  # kill switch raced between _require_enabled and here
        raise HTTPException(status_code=404, detail="federation disabled")
    return note


@router.get("/checkpoint")
def checkpoint(
    from_tree_size: int | None = Query(None, ge=1, alias="from_tree_size"),
) -> JSONResponse:
    _require_enabled()
    note = _current_note()
    parsed = checkpoint_mod.parse_checkpoint(note)
    if parsed is None:  # pragma: no cover - signed_checkpoint always parses
        raise HTTPException(status_code=500, detail="checkpoint parse failed")
    tree_size = parsed["tree_size"]
    body = {
        "origin": parsed["origin"],
        "tree_size": tree_size,
        "root_hash": parsed["root_hash"].hex(),
        "timestamp": parsed["timestamp"],
        "signature": _note_signature(note),
        "note": note,
    }
    session = _session()
    try:
        floor = log.live_window_floor(session)
        body["live_window_floor"] = floor
        # The retention horizon == the live-window floor (the sequence below which
        # leaves are archived, §6.2g). Exposed UNSIGNED here under the spec name so a
        # peer learns the floor; NOT added to the signed C2SP note body (rigid 4-line
        # shape — a Go witness would reject an extra line). One source: live_window_floor.
        body["retention_horizon_sequence"] = floor
        # §6.3: serve the proof material a consumer needs to verify the log only
        # GREW (RFC-6962 consistency) from a prior checkpoint it holds.
        if from_tree_size is not None and 0 < from_tree_size <= tree_size:
            try:
                proof = log.build_consistency_proof(
                    session, first_size=from_tree_size, second_size=tree_size
                )
            except ValueError:
                # Trimmed prefix (Task 9): the proof needs trimmed leaves -> 410,
                # never a 500 (mirrors /export, /history, _current_note).
                raise _below_window_410(floor)
            body["consistency_from"] = from_tree_size
            body["consistency_proof"] = [h.hex() for h in proof]
        elif from_tree_size is not None and from_tree_size > tree_size:
            # The consumer holds a LARGER checkpoint than we now advertise: the
            # log regressed/truncated (a possible equivocation). Flag it loudly
            # rather than silently omitting the proof.
            body["consistency_from"] = from_tree_size
            body["log_regression"] = True
    finally:
        session.close()
    return JSONResponse(body)


@router.get("/state.txt")
def state_txt() -> PlainTextResponse:
    _require_enabled()
    note = _current_note()
    # The retention horizon rides as an UNSIGNED header (the body stays the pure
    # C2SP signed note — never add a line to it, §6.2b / Go-witness interop).
    session = _session()
    try:
        horizon = log.live_window_floor(session)
    finally:
        session.close()
    return PlainTextResponse(
        note,
        media_type="text/plain",
        headers={"Federation-Retention-Horizon": str(horizon)},
    )


@router.get("/history/{federation_id:path}")
def history(federation_id: str) -> JSONResponse:
    _require_enabled()
    session = _session()
    try:
        try:
            activities, tree_size = log.read_history(session, federation_id)
        except ValueError:
            # Trimmed prefix (Task 9): proofs need trimmed leaves -> clean 410.
            raise _below_window_410(log.live_window_floor(session))
    finally:
        session.close()
    _require_enabled()  # kill-switch TOCTOU re-check after the read
    # tree_size anchors the inclusion proofs (verify against the matching
    # checkpoint root); without it the proofs are unverifiable on a live node.
    return JSONResponse(
        {
            "federation_id": federation_id,
            "tree_size": tree_size,
            "activities": activities,
        },
        headers={"Federation-Sequence": str(tree_size)},
    )
