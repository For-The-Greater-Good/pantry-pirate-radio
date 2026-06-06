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

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.federation import identity, log
from app.federation.aggregate import build_location_aggregate

logger = structlog.get_logger(__name__)

#: ``location_source.source_type`` value carried by federated peers' records.
FEDERATED_SOURCE_TYPE = "federated_node"


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
    return bool(row) and row[0] is not False


def _append(db: Session, *, activity_type: str, federation_id: str, obj: dict) -> int | None:
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
