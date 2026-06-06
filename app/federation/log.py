"""The federation verifiable-log engine: append, head, checkpoints, proofs.

Design §6.2a/b; the P0.5 spike returned **GO** on exactly this append shape and
P1 implements it unchanged (memo Proof 1/4):

  - ``append`` assigns the **dense, gapless sequence** under
    ``pg_advisory_xact_lock(_APPEND_LOCK_KEY)`` scoped to ONLY
    ``SELECT COALESCE(MAX(sequence),0)+1 -> INSERT -> COMMIT`` (the lock
    auto-releases at commit). The caller's *resource* commit happens OUTSIDE
    this lock — the parallel canonical write path is preserved; only the tiny
    append serializes. A SERIAL/SEQUENCE was deliberately rejected: it gaps on
    rollback, and a gap breaks the Merkle leaf indexing.
  - Because the lock makes sequences dense and a higher sequence cannot even be
    *allocated* until the lower one commits (the M5 hazard is impossible by
    construction), ``safe_high_water`` — the top of the gap-free committed
    prefix — is simply ``MAX(sequence)`` over committed rows.
  - ``append`` takes a **plain sync Session** so the offline dedup scripts
    (the §6.2e ``Delete`` hook sites) can call it outside the reconciler.
  - Kill switch (§6.2d, Principle XI): ``FEDERATION_ENABLED=False`` makes both
    signing entry points — ``append`` AND ``signed_checkpoint`` — hard no-ops
    before any work (neither writes a row nor produces an Ed25519 signature over
    the node's data while disabled). The read-only proof/leaf builders are
    intentionally ungated (no crypto action). Hook sites (PR-C) check it too;
    this is defense in depth.

Checkpoints/proofs recompute the RFC-6962 tree from the committed rows (always
correct across the many writer processes — reconciler workers, scripts; a
per-process in-memory frontier cache is a later optimization, not a
correctness substrate).
"""

from __future__ import annotations

from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.federation import envelope as envelope_mod
from app.federation import merkle
from app.federation.checkpoint import build_checkpoint

#: Advisory-lock key for the append critical section (xact-scoped; arbitrary
#: but MUST stay stable forever — all writers must contend on the same key).
_APPEND_LOCK_KEY = 0x46454445_0001  # "FEDE" + 1

_INSERT_SQL = text(
    """
    INSERT INTO federation_log
        (leaf_hash, sequence, type, federation_id, object_canonical,
         preimage_canonical, published_at, origin_did)
    VALUES
        (:leaf_hash, :sequence, :type, :federation_id,
         CAST(:object_canonical AS jsonb), :preimage_canonical,
         CAST(:published_at AS timestamptz), :origin_did)
    """
)


def append(
    session: Session,
    *,
    activity_type: str,
    federation_id: str,
    obj: dict[str, Any],
    origin_did: str,
    signing_key: Ed25519PrivateKey,
    context: str,
    license: str,
    published: str | None = None,
    actor: str | None = None,
    attributed_to: str | None = None,
) -> int | None:
    """Append one signed activity envelope; return its dense sequence.

    Returns ``None`` (hard no-op, §6.2d) when ``FEDERATION_ENABLED`` is off.
    Commits the session (the advisory lock is released by that commit) — call
    AFTER the resource commit, never inside the caller's open transaction.
    For our own publishes ``actor``/``attributedTo`` default to ``origin_did``.
    """
    from app.core.config import settings  # late import: kill-switch reads live value

    if not settings.FEDERATION_ENABLED:
        return None

    import json

    actor = actor or origin_did
    attributed_to = attributed_to or origin_did
    published = published or envelope_mod.published_now()

    # ---- critical section: lock -> MAX+1 -> INSERT -> COMMIT (lock released)
    session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": _APPEND_LOCK_KEY}
    )
    sequence = session.execute(
        text("SELECT COALESCE(MAX(sequence), 0) + 1 FROM federation_log")
    ).scalar_one()
    preimage = envelope_mod.build_preimage(
        context=context,
        activity_type=activity_type,
        actor=actor,
        attributed_to=attributed_to,
        origin=origin_did,
        federation_id=federation_id,
        obj=obj,
        sequence=sequence,
        published=published,
        license=license,
    )
    env, preimage_bytes = envelope_mod.finalize_with_bytes(preimage, signing_key)
    session.execute(
        _INSERT_SQL,
        {
            "leaf_hash": env["id"],
            "sequence": sequence,
            "type": activity_type,
            "federation_id": federation_id,
            # object_canonical is for QUERYABILITY ONLY and is NOT byte-faithful:
            # a JSONB round-trip normalizes extreme-magnitude floats (>=1e21), so
            # verify_envelope over an envelope reconstructed from object_canonical
            # can fail. The PR-C /export surface MUST serve the signed bytes from
            # preimage_canonical (+ the proof), never re-serialize object_canonical.
            "object_canonical": json.dumps(env),
            # The exact signed bytes, stored verbatim (see leaf_data): the leaf
            # must never depend on JSONB number normalization.
            "preimage_canonical": preimage_bytes,
            "published_at": published,
            "origin_did": origin_did,
        },
    )
    session.commit()
    return int(sequence)


def safe_high_water(session: Session) -> int:
    """Top of the gap-free committed prefix (= MAX(sequence); 0 when empty)."""
    return int(
        session.execute(
            text("SELECT COALESCE(MAX(sequence), 0) FROM federation_log")
        ).scalar_one()
    )


def leaf_data(session: Session, tree_size: int) -> list[bytes]:
    """The RFC-6962 leaf data (JCS pre-image bytes) for sequences 1..tree_size.

    Returns the canonical pre-image bytes EXACTLY as they were hashed and signed
    at append time (``preimage_canonical``, stored verbatim). We deliberately do
    NOT re-derive from ``object_canonical`` (JSONB): a JSONB round-trip
    normalizes extreme-magnitude numbers (e.g. ``1e21`` -> a big integer) so a
    re-canonicalized leaf would diverge from the signed bytes and silently break
    inclusion/consistency proofs. ``object_canonical`` is retained for
    queryability only.
    """
    rows = session.execute(
        text(
            "SELECT sequence, preimage_canonical FROM federation_log"
            " WHERE sequence <= :n ORDER BY sequence"
        ),
        {"n": tree_size},
    ).all()
    if len(rows) != tree_size:
        raise ValueError(
            f"tree_size {tree_size} exceeds committed prefix ({len(rows)} rows)"
        )
    # psycopg2 returns BYTEA as memoryview; normalize to bytes.
    return [bytes(row.preimage_canonical) for row in rows]


def signed_checkpoint(
    session: Session,
    *,
    origin_did: str,
    signing_key: Ed25519PrivateKey,
    timestamp: str | None = None,
) -> str | None:
    """A C2SP signed-note checkpoint over the committed prefix (§6.2b).

    Returns ``None`` (hard no-op, §6.2d) when ``FEDERATION_ENABLED`` is off.
    The kill switch is NOT append-only: a checkpoint is an Ed25519 signature over
    the node's committed data, so the substrate must refuse to sign anything while
    federation is disabled — defense in depth, mirroring ``append`` (the read-only
    proof builders below take no crypto action and are intentionally left ungated).
    """
    from app.core.config import settings  # late import: kill-switch reads live value

    if not settings.FEDERATION_ENABLED:
        return None

    timestamp = timestamp or envelope_mod.published_now()
    tree_size = safe_high_water(session)
    root = merkle.merkle_root(leaf_data(session, tree_size))
    return build_checkpoint(
        origin=origin_did,
        tree_size=tree_size,
        root_hash=root,
        timestamp=timestamp,
        signing_key=signing_key,
    )


def build_inclusion_proof(
    session: Session, *, sequence: int, tree_size: int
) -> list[bytes]:
    """RFC-6962 audit path for ``sequence`` (1-based) in the size-``tree_size`` tree."""
    if not 1 <= sequence <= tree_size:
        raise ValueError(f"sequence {sequence} outside tree of size {tree_size}")
    leaves = leaf_data(session, tree_size)
    return merkle.inclusion_proof(leaves, sequence - 1)


def build_consistency_proof(
    session: Session, *, first_size: int, second_size: int
) -> list[bytes]:
    """RFC-6962 consistency proof between two committed prefixes."""
    if not 0 < first_size <= second_size:
        raise ValueError(
            f"invalid sizes: first_size={first_size} second_size={second_size}"
        )
    leaves = leaf_data(session, second_size)
    return merkle.consistency_proof(leaves, first_size)
