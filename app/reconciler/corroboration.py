"""Source-corroboration counting for canonical location merges.

Extracted from ``merge_strategy.merge_location`` (Principle IX responsibility
boundary, federation P2 Slice 1). This is the single seam where multi-source
confidence corroboration is computed — and where P2 Slice 7a will widen the
"distinct source" notion from distinct ``scraper_id`` to distinct ORIGIN DID
(the §12.1 citogenesis fix: three peers re-announcing one origin must count as
one, not three). Keeping it here co-locates that change with its only call site.

This slice is a behaviour-preserving extraction: ``count_distinct_sources`` and
``apply_corroboration`` reproduce the prior inline logic exactly (distinct
non-empty ``scraper_id``; bonus applied only when >1; ``None`` when no bonus).
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def count_distinct_sources(records: list[dict[str, Any]]) -> int:
    """Number of distinct corroborating sources among ``records``.

    Today: distinct non-empty ``scraper_id`` (matches the historic inline count).
    P2 Slice 7a widens this to dedup by the envelope's carried ORIGIN DID so a
    record relayed by N peers from one origin counts once.
    """
    return len({r.get("scraper_id") for r in records if r.get("scraper_id")})


def apply_corroboration(
    current_confidence_score: int, records: list[dict[str, Any]]
) -> int | None:
    """Apply the multi-source corroboration bonus, or ``None`` if no bonus applies.

    Returns the updated score only when more than one distinct source corroborates
    the location; otherwise ``None`` (no change), exactly as the prior inline path.
    """
    distinct = count_distinct_sources(records)
    if distinct <= 1:
        return None

    from app.validator.scoring import ConfidenceScorer

    updated = ConfidenceScorer().apply_source_corroboration(
        current_confidence_score, distinct
    )
    logger.info(
        "source_corroboration_applied",
        distinct_sources=distinct,
        from_score=current_confidence_score,
        to_score=updated,
    )
    return updated
