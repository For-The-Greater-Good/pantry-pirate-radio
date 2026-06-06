"""Federation publish hooks — append an ``Update``/``Delete`` to the verifiable
log at the reconciler / dedup / submarine commit sites (design §6.2d/e, §10).

One guarded path shared by every call site (reconciler matched/new, submarine,
dedup-Delete) so the kill switch, echo suppression, publish gate, and Principle-XI
fail-soft are defined once. These functions NEVER raise: a federation-publish
failure must never abort the reconciler/dedup job that called it.

Guards (in order):
  1. ``FEDERATION_ENABLED`` off  → no-op (§6.2d hard kill switch, before any work).
  2. echo: a commit driven by ``federated_node`` sources is a re-echo (§10) → skip.
  3. no signing identity (DID / key) configured → skip.
  4. publish gate: only ``is_canonical`` rows are published (Beacon serve gate;
     the equity floor §11.6a means we do NOT hard-gate on confidence — a
     plausibly-real low-confidence row is served with a caveat, not hidden).
"""

from __future__ import annotations

import contextlib

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.federation import identity, log
from app.federation.aggregate import build_location_aggregate

logger = structlog.get_logger(__name__)

#: ``location_source.source_type`` value carried by federated peers' records.
FEDERATED_SOURCE_TYPE = "federated_node"

#: Max dead->survivor hops before giving up (cycle/runaway guard); mirrors
#: Beacon's ``_MAX_SURVIVOR_CHAIN_DEPTH``.
_MAX_SURVIVOR_CHAIN_DEPTH = 25


def _node_host() -> str | None:
    """The publisher host for the ``federation_id`` grammar (§7), or ``None``."""
    from app.core.config import settings

    if settings.FEDERATION_DOMAIN:
        return settings.FEDERATION_DOMAIN
    did = settings.FEDERATION_DID
    if did and did.startswith("did:web:"):
        return did[len("did:web:") :]
    return None


def _is_canonical(db: Session, location_id: str) -> bool:
    """Publish gate: only canonical (not soft-deleted) rows are published."""
    row = db.execute(
        text("SELECT is_canonical FROM location WHERE id = :id"),
        {"id": location_id},
    ).first()
    # Default-publish when the column is NULL/absent (older rows); skip only an
    # explicit FALSE (a dedup soft-delete).
    return row is not None and row[0] is not False


def _append(
    db: Session, *, activity_type: str, federation_id: str, obj: dict
) -> int | None:
    """Shared append with identity + kill-switch + fail-soft. None if skipped."""
    from app.core.config import settings

    if not settings.FEDERATION_ENABLED:  # §6.2d — first, before any work
        return None
    if settings.FEDERATION_DID is None:
        return None
    host = _node_host()
    if host is None:
        return None
    try:
        key = identity.load_signing_key(settings.FEDERATION_SIGNING_KEY)
        if key is None:
            return None
        return log.append(
            db,
            activity_type=activity_type,
            federation_id=federation_id,
            obj=obj,
            origin_did=settings.FEDERATION_DID,
            signing_key=key,
            context=settings.FEDERATION_PROFILE_URI,
            license=settings.FEDERATION_LICENSE,
        )
    except Exception as exc:  # never abort the caller (Principle XI)
        # Roll back the failed append so the caller's session is not left in an
        # aborted-transaction state (Gauntlet HIGH: fail-soft must not poison the
        # caller). Safe because every call site invokes the append AFTER its own
        # resource commit, so there is no pending caller work to lose.
        with contextlib.suppress(Exception):  # rollback of a dead session
            db.rollback()
        logger.warning(
            "federation_append_failed",
            activity_type=activity_type,
            federation_id=federation_id,
            error=str(exc),
        )
        return None


def publish_location_update(
    db: Session, location_id: str, *, source_type: str | None
) -> int | None:
    """Append an ``Update`` for a just-committed canonical location.

    Returns the dense sequence, or ``None`` when skipped (disabled / echo / no
    identity / non-canonical / not found / failure). Never raises.
    """
    from app.core.config import settings

    if not settings.FEDERATION_ENABLED:  # cheap pre-check before any DB work
        return None
    if source_type == FEDERATED_SOURCE_TYPE:  # §10 echo suppression
        return None
    host = _node_host()
    if host is None or settings.FEDERATION_DID is None:
        return None
    try:
        if not _is_canonical(db, location_id):  # publish gate
            return None
        obj = build_location_aggregate(db, location_id)
    except Exception as exc:  # never abort the caller (Principle XI)
        with contextlib.suppress(Exception):
            db.rollback()
        logger.warning(
            "federation_append_failed", location_id=location_id, error=str(exc)
        )
        return None
    return _append(
        db,
        activity_type="Update",
        federation_id=f"{host}:{location_id}",
        obj=obj,
    )


def _load_soft_delete_chain(db: Session) -> dict[str, str]:
    """Build the dead->survivor map from ``dedup_run_audit`` (latest per dead).

    Tolerates a missing audit table (returns ``{}``) — the table is created lazily
    by the dedup scripts on first ``--apply``."""
    exists = db.execute(text("SELECT to_regclass('public.dedup_run_audit')")).scalar()
    if not exists:
        return {}
    rows = db.execute(
        text(
            "SELECT DISTINCT ON (row_id) row_id, survivor_id FROM dedup_run_audit"
            " WHERE table_name = 'location' AND action = 'soft_delete'"
            " ORDER BY row_id, id DESC"
        )
    ).fetchall()
    return {str(r.row_id): str(r.survivor_id) for r in rows}


def _resolve_terminal_survivor(
    db: Session,
    dead_id: str,
    fallback_survivor_id: str | None,
    *,
    chain: dict[str, str] | None = None,
) -> str | None:
    """Follow ``dead_id`` through the soft-delete chain to the terminal survivor
    (mirrors Beacon ``_resolve_terminal``), falling back to the caller-supplied
    immediate survivor when ``dead_id`` is not yet in the audit chain. Returns the
    terminal id only if it is still canonical; otherwise ``None`` (→ redirectTo
    null) on a cycle, excessive depth, or a non-canonical/missing terminal.

    ``chain`` may be supplied pre-loaded (batch replay) to avoid an O(N^2)
    full-table scan per Delete; otherwise it is loaded once here.
    """
    if chain is None:
        chain = _load_soft_delete_chain(db)

    def _walk(start: str) -> str | None:
        """Follow start -> ... to the terminal not-further-merged id; None on a
        cycle or excessive depth. ``start`` itself need not be in the chain."""
        seen = {start}
        current = start
        depth = 0
        while current in chain:
            nxt = chain[current]
            if nxt in seen or depth >= _MAX_SURVIVOR_CHAIN_DEPTH:
                return None
            seen.add(nxt)
            current = nxt
            depth += 1
        return current

    if dead_id in chain:
        terminal = _walk(dead_id)
    elif fallback_survivor_id is not None:
        # The dead id has no audit row (e.g. the same-org script writes none), but
        # the immediate survivor may itself have been merged onward by a different
        # run that DID write audit — follow ITS chain to the terminal too, so we
        # never redirect to a now-non-canonical intermediate (Gauntlet MEDIUM).
        terminal = _walk(fallback_survivor_id)
    else:
        terminal = None
    if terminal is None:
        return None
    row = db.execute(
        text("SELECT is_canonical FROM location WHERE id = :id"),
        {"id": terminal},
    ).first()
    if not row or row[0] is False:
        return None
    return terminal


def publish_location_delete(
    db: Session,
    *,
    dead_location_id: str,
    survivor_location_id: str | None,
    chain: dict[str, str] | None = None,
) -> int | None:
    """Append a ``Delete`` (Tombstone) for a dedup-script soft-deleted location.

    The object is ``{"type": "Tombstone", "federation_id": "<dead>",
    "redirectTo": "<survivor fed-id | null>"}`` (§9). ``redirectTo`` resolves
    through the ``dedup_run_audit`` survivor chain to the terminal still-canonical
    row. No echo suppression — Deletes are produced only by PPR's own dedup
    scripts, never relayed peer data. Never raises (Principle XI).

    MUST be called AFTER the dedup run's transaction has COMMITTED (the append
    commits the session, which would fold an open dedup savepoint mid-run — the
    dedup scripts collect pairs and replay via :func:`publish_pending_deletes`).
    """
    from app.core.config import settings

    if not settings.FEDERATION_ENABLED:
        return None
    host = _node_host()
    if host is None or settings.FEDERATION_DID is None:
        return None
    try:
        # Defensive: a Tombstone is only for an actually soft-deleted row. If the
        # dead id is still canonical, do not tombstone a live location. (Inside the
        # try so a poisoned-session gate query is swallowed, not raised — the
        # documented never-raises contract; mirrors publish_location_update.)
        if _is_canonical(db, dead_location_id):
            return None
        terminal = _resolve_terminal_survivor(
            db, dead_location_id, survivor_location_id, chain=chain
        )
        dead_fid = f"{host}:{dead_location_id}"
        obj = {
            "type": "Tombstone",
            "federation_id": dead_fid,
            "redirectTo": f"{host}:{terminal}" if terminal else None,
        }
    except Exception as exc:  # never abort the caller (Principle XI)
        with contextlib.suppress(Exception):
            db.rollback()
        logger.warning(
            "federation_append_failed", location_id=dead_location_id, error=str(exc)
        )
        return None
    return _append(db, activity_type="Delete", federation_id=dead_fid, obj=obj)


def publish_pending_deletes(db: Session, deletes: list[tuple[str, str | None]]) -> None:
    """Replay collected ``(dead_id, survivor_id)`` Deletes AFTER the dedup run's
    outer transaction has committed.

    The dedup scripts batch a whole run in one transaction with per-cluster
    savepoints; an inline append (which commits) would fold that transaction and
    abort the run (Gauntlet CRITICAL). So the scripts COLLECT pairs during the run
    and call this once post-commit. The survivor chain is loaded ONCE here (not
    per Delete — avoids the O(N^2) scan). Never raises (Principle XI).

    KNOWN CRASH WINDOW (documented, follow-on): the soft-delete is committed before
    this replay, so a process death (OOM/SIGKILL) between the commit and the append
    leaves a soft-deleted row with a published Update but no Tombstone. A peer's
    record goes stale rather than redirected — bounded, not data loss, and
    correctable: a reconciliation pass (find is_canonical=FALSE rows that have an
    Update but no Delete in federation_log and emit the missing Tombstones) is the
    fix, tracked alongside the Task 9 archive work — the same offline-backfill shape
    as the existing dedupe_* scripts. Re-running the dedup script does NOT re-emit
    (the soft-delete is idempotent), so the backfill is the recovery path."""
    if not deletes:
        return
    try:
        chain = _load_soft_delete_chain(db)
    except Exception as exc:  # never raise post-commit into the dedup script
        with contextlib.suppress(Exception):
            db.rollback()
        logger.warning("federation_append_failed", error=str(exc))
        return
    for dead_id, survivor_id in deletes:
        publish_location_delete(
            db,
            dead_location_id=dead_id,
            survivor_location_id=survivor_id,
            chain=chain,
        )
