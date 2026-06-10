"""Unit tests for the extracted source-corroboration counter (P2 Slice 1).

Behaviour-preserving extraction from merge_strategy.merge_location: distinct
non-empty scraper_id, bonus only when >1, None when no bonus. (Slice 7a will add
origin-DID dedup tests here.)
"""

from app.reconciler.corroboration import apply_corroboration, count_distinct_sources


def test_count_distinct_sources_ignores_empty_and_dedups():
    records = [
        {"scraper_id": "a"},
        {"scraper_id": "a"},  # duplicate source
        {"scraper_id": "b"},
        {"scraper_id": None},  # ignored
        {"scraper_id": ""},  # ignored
        {},  # ignored
    ]
    assert count_distinct_sources(records) == 2


def test_apply_corroboration_none_when_single_source():
    assert apply_corroboration(60, [{"scraper_id": "a"}]) is None
    assert apply_corroboration(60, [{"scraper_id": "a"}, {"scraper_id": "a"}]) is None
    assert apply_corroboration(60, []) is None


def test_apply_corroboration_applies_bonus_for_multiple_distinct_sources():
    from app.validator.scoring import ConfidenceScorer

    records = [{"scraper_id": "a"}, {"scraper_id": "b"}, {"scraper_id": "c"}]
    expected = ConfidenceScorer().apply_source_corroboration(60, 3)
    got = apply_corroboration(60, records)
    assert got == expected
    assert got is not None and got > 60  # corroboration raises confidence
