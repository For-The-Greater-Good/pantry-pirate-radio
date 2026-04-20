# Implementation Plan: Nearby Locations on Zip & City Pages

**Branch**: `001-nearby-locations-beacon` | **Date**: 2026-04-19 | **Spec**: nearby locations for thin zip/city pages
**Input**: User request — show nearby food pantries when a zip or city page has few or no results

## Summary

When a zip code or city page has few results (threshold: <5 locations), show "Nearby Food Pantries" from surrounding areas. Computed at static site generation time using haversine distance from the page's centroid. No runtime queries needed — nearby locations are baked into the HTML.

This addresses a real UX gap: many zip codes have 0-2 locations, and neighborhoods in metro areas are split into separate "cities" (e.g., Brooklyn neighborhoods each appearing as their own city). Users hitting these thin pages see almost nothing and bounce.

## Technical Context

**Language/Version**: Python 3.11 (beacon builder runs in Docker/Fargate)
**Primary Dependencies**: Pydantic models, Jinja2 templates, boto3 S3 upload
**Storage**: Static HTML to S3, DynamoDB build tracker
**Testing**: pytest (existing `tests/` in ppr-beacon plugin)
**Target Platform**: Static site generator → S3 + CloudFront
**Performance Goals**: Incremental build stays under 20 minutes; no regression on full build (~2.5 hrs with maps)
**Constraints**: 67K+ locations, ~16K zip pages, ~6K city pages. Nearby computation must be O(n) per page, not O(n²) total.
**Scale/Scope**: ~166K total aggregate pages across zip/city/state/org

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Docker-First | PASS | No new local deps — all runs via bouy |
| III. TDD | PASS | Tests written for haversine, nearby computation, templates |
| IX. File Size/Complexity | PASS | Changes spread across 4-5 files, no new files >600 lines |
| X. Quality Gates | PASS | black + ruff + mypy + pytest must pass |
| XIII. Documentation | PASS | CLAUDE.md not affected; this plan documents the feature |

## Design

### Approach: Centroid + Haversine at Index Time

**Phase 1: Compute centroids for each zip and city during `_build_indexes()`**

Each zip/city group already has its locations in `by_zip` and `by_city` indexes. Compute the centroid (average lat/lng of all locations in the group) and store it alongside the summary.

**Phase 2: Build a flat spatial lookup for all locations**

During `_build_indexes()`, build a list of `(lat, lng, location_id)` tuples for all locations with coordinates. This is the "nearby pool."

**Phase 3: For thin pages, find nearest locations not already on the page**

In `_rebuild_aggregates()`, when rendering a zip or city page:
1. Always compute nearby locations (user decision: show on every page)
2. Compute haversine distance from the page centroid to all locations in the nearby pool
3. Filter out locations already on the page
4. Take the closest N (default: 10) within a max radius (default: 25 miles)
5. Pass as `nearby_locations` to the template

**Phase 4: Template rendering**

Add a "Nearby Food Pantries" section to `city.html` and `zip.html` that only renders when `nearby_locations` is non-empty. Each card shows the location name, address, and distance (e.g., "2.3 mi").

### Performance Analysis

**Haversine per page**: O(N) where N = total locations with coords (~67K). For 67K locations, this is ~67K float multiplications per thin page — microseconds in Python.

**Number of thin pages**: Most zip pages are thin (likely 80%+). If 13K zip pages need nearby computation, that's 13K × 67K = ~870M distance calculations. At ~1M/sec in Python, that's ~15 minutes.

**Optimization**: Pre-sort locations by latitude. For each centroid, only consider locations within ±0.5° latitude (~35 miles). This reduces the search space to ~2-5K per page instead of 67K. Estimated: <1 minute total.

### Files to Modify

| File | Change |
|------|--------|
| `plugins/ppr-beacon/app/models.py` | Add `latitude`, `longitude` to `LocationSummary`. Add `centroid_lat`, `centroid_lng` to `ZipSummary` and `CitySummary`. |
| `plugins/ppr-beacon/app/data_source.py` | Compute centroids in `build_zip_summaries()` and `build_city_summaries()`. Pass lat/lng through to `_to_location_summary()`. |
| `plugins/ppr-beacon/app/builder.py` | In `_build_indexes()`, build spatial lookup. In `_rebuild_aggregates()`, compute nearby for thin pages. Add `NEARBY_THRESHOLD` and `NEARBY_MAX_DISTANCE_MI` constants. |
| `plugins/ppr-beacon/app/renderer.py` | Update `render_city()` and `render_zip()` to accept `nearby_locations` param. Add `haversine()` utility and `format_distance` Jinja2 filter. |
| `plugins/ppr-beacon/templates/city.html` | Add "Nearby Food Pantries" section with distance badges. |
| `plugins/ppr-beacon/templates/zip.html` | Same as city.html. |
| `plugins/ppr-beacon/locales/en.json` | Add `section_nearby`, `nearby_distance` locale strings. |

### New Utility: Haversine

```python
import math

def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in miles between two points."""
    R = 3959  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))
```

### Template Mock

```jinja2
{% if nearby_locations %}
<section class="card card--mt">
  <h2>{{ t('section_nearby') }}</h2>
  <div class="listing-grid">
    {% for loc in nearby_locations %}
    <div class="location-card">
      <h3><a href="{{ loc.url }}">{{ loc.name }}</a></h3>
      <p class="address">{{ loc.address_1 }}, {{ loc.city }}, {{ loc.state }}</p>
      <span class="distance-badge">{{ loc.distance | format_distance }}</span>
    </div>
    {% endfor %}
  </div>
</section>
{% endif %}
```

## Verification

1. **Unit tests**: haversine accuracy, centroid computation, nearby filtering (threshold, max distance, dedup)
2. **Integration test**: Build a small set of locations, verify thin zip page gets nearby section in HTML output
3. **Manual check**: Deploy to prod, visit a thin zip page (user's own zip), confirm nearby locations appear with correct distances
4. **Performance**: Run full build locally, compare timing vs baseline (should add <2 minutes)
5. **Regression**: Existing sitemap/city/zip tests still pass
