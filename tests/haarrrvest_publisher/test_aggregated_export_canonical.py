"""PUB-3 regression guard: aggregated map export filters is_canonical.

The aggregated map exporter (the production map export) fetched locations for
PostGIS clustering without an is_canonical filter, while every sibling map
export has one. Soft-deleted duplicates (is_canonical=FALSE) would be fetched,
participate in clustering, and a cluster of only-non-canonical rows would emit a
soft-deleted pin into the published map data.
"""

from unittest.mock import MagicMock

from app.haarrrvest_publisher.export_map_data_aggregated import (
    AggregatedMapDataExporter,
)


def test_aggregated_fetch_sql_filters_is_canonical(tmp_path):
    exporter = AggregatedMapDataExporter(
        data_repo_path=tmp_path,
        pg_conn_string="postgresql://unused",
        grouping_radius_meters=150,
    )

    captured: dict[str, str] = {}

    cursor = MagicMock()

    def _execute(sql, params=None):
        captured["sql"] = sql

    cursor.execute.side_effect = _execute
    # `for row in cursor` must yield no rows.
    cursor.__iter__.return_value = iter([])

    cursor_cm = MagicMock()
    cursor_cm.__enter__.return_value = cursor
    cursor_cm.__exit__.return_value = False

    conn = MagicMock()
    conn.cursor.return_value = cursor_cm

    rows = exporter._fetch_all_locations_with_sources(conn)

    assert rows == []
    sql = captured["sql"].lower()
    assert "l.is_canonical = true" in sql
    # And it must keep the existing rejected filter.
    assert "validation_status" in sql
