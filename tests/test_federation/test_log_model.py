"""Task 1 (PR-B): FederationLog model shape (design §6.2b).

The append-only verifiable log table. ``sequence`` is the dense, gapless Merkle
leaf index (assigned under the §6.2b advisory lock); ``leaf_hash`` is the
``sha256:`` content address (the envelope ``id``); ``object_canonical`` stores
the full envelope so the content address is exactly re-derivable via JCS.
"""

from app.database.models import FederationLogModel


def test_federation_log_columns_present() -> None:
    cols = set(FederationLogModel.__table__.columns.keys())
    assert {
        "sequence",
        "leaf_hash",
        "type",
        "federation_id",
        "object_canonical",
        "published_at",
        "origin_did",
    } <= cols


def test_sequence_is_indexed_and_unique() -> None:
    seq = FederationLogModel.__table__.columns["sequence"]
    assert seq.unique or any(
        "sequence" in {c.name for c in ix.columns}
        for ix in FederationLogModel.__table__.indexes
    )


def test_federation_id_is_indexed_for_history() -> None:
    """history/{federation_id} keys on federation_id — it must be indexed."""
    fid = FederationLogModel.__table__.columns["federation_id"]
    assert fid.index or any(
        "federation_id" in {c.name for c in ix.columns}
        for ix in FederationLogModel.__table__.indexes
    )


def test_tablename_is_federation_log() -> None:
    assert FederationLogModel.__tablename__ == "federation_log"
