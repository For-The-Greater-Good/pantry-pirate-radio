# Pantry Pirate Radio HSDS Profile

This directory is the Pantry Pirate Radio (PPR) **HSDS Profile**: a set of
modifications to the Human Services Data Specification (HSDS) that PPR declares
itself conformant to.

## What this is

Per the HSDS Profiles Specification, a Profile is expressed as a set of files
that describe changes to the canonical HSDS schema files via **JSON Merge Patch
([RFC 7386](https://datatracker.ietf.org/doc/html/rfc7386))**. Each file shares
the filename of the HSDS schema it modifies; merging the patch over the canonical
HSDS schema must produce valid JSON Schema (object schemas) or a valid OpenAPI 3.1
document (`openapi.json`).

Files in this Profile:

- `location.json` — merge patch over the HSDS `location` schema.
- `service.json` — merge patch over the HSDS `service` schema.
- `organization.json` — merge patch over the HSDS `organization` schema.
- `service_at_location.json` — merge patch over the HSDS `service_at_location` schema.
- `openapi.json` — merge patch over the HSDS API specification.

## Permitted modifications only

Per the HSDS Profiles "Permitted Modifications" rules, this Profile only
**adds new OPTIONAL properties** to the core schemas. It does **not** add any
property to a schema's `required` array, does not override or remove any core
property, and the added terms do not overlap semantically with existing HSDS
terms.

### Uniform PPR extension surface

`location.json`, `service.json`, `organization.json`, and
`service_at_location.json` all declare the same core extension surface
(`confidence_score`, `verified_by`, `sources`, `source_count`).
`location.json` additionally declares `distance`, which is location- and
search-specific.

| Property           | Type             | Notes                                                                                  |
| ------------------ | ---------------- | -------------------------------------------------------------------------------------- |
| `confidence_score` | integer (0–100)  | PPR data-quality confidence. Scraped data capped at 90; 91–100 are human corrections. **Reserved / not currently served at the entity level**: NOT emitted by current HSDS read responses or the federation export as a top-level field for any of the four entities — it is surfaced today only per-source inside each `sources[]` item (`LocationResponse.sources[].confidence_score`). An entity-level value is reserved for the forthcoming federation export surface (epic slices X1/X2). |
| `verified_by`      | string enum      | `auto` / `admin` / `source` / `claimed` / `network` — provenance of the verification. `network` denotes federation-corroborated provenance, operational with P2 Slice 3 / I1. **Reserved / not currently served**: not surfaced by any current HSDS read response for any of the four entities; reserved for the federation/provenance surface. |
| `sources`          | array of objects | Per-source corroboration details (multi-source). Each item mirrors `app.models.hsds.response.SourceInfo`: `scraper`, `name`, `phone`, `email`, `website`, `address` (strings), `confidence_score` (integer 0-100), `last_updated`, `first_seen` (strings). All item properties are optional. **Currently served only for `location`** (`LocationResponse.sources`, and the federation Location aggregate); for `service`, `organization`, and `service_at_location` this declaration is forward-looking and not yet emitted by any read endpoint. |
| `source_count`     | integer (>= 0)   | Count of distinct corroborating sources (scraper/network identifiers). **Currently served only for `location`** — see "source_count: two definitions" below. For `service`, `organization`, and `service_at_location`, NOT currently emitted by the read API; reserved for the federation export surface, where it is the distinct-scraper count (`app/federation/aggregate.py`). |
| `distance`         | string           | **`location.json` only.** Great-circle distance from the search origin. Appears ONLY on radius/proximity search responses — it is search-result metadata, not a stored property of the location. |

Of the four entities, **only `location` currently emits `sources` and
`source_count`** via `LocationResponse` (and the federation Location
aggregate). `confidence_score` and `verified_by` are not emitted at the
entity level for ANY of the four entities today — `confidence_score` is
visible only per-source inside `sources[]`. The `service.json`,
`organization.json`, and `service_at_location.json` patches declare the same
uniform extension surface as `location.json` as **forward declarations**: a
deliberately uniform shape that unblocks a future federation export carrying
org/SAL/service provenance without requiring a second Profile revision to add
the fields then. Declaring an optional property that the implementation does
not yet populate is conformant (HSDS Profiles "Permitted Modifications");
this README and the per-field descriptions in each schema patch say plainly
which fields are served today versus reserved.

#### `sources` is an array of objects (not strings)

Earlier revisions of this Profile declared `sources` as `array of strings`
(scraper identifiers only). The read API actually serves `sources` as an array
of `SourceInfo` objects (`app/models/hsds/response.py`). This Profile now
declares the object shape to match what is actually served; a machinery test
(`tests/test_federation/test_profile_merge.py::test_location_sources_items_match_source_info_model`)
pins the declared `sources[].items.properties` keys to `SourceInfo`'s field set
so the two cannot silently drift again.

#### `source_count`: two definitions (documented, not yet unified)

The canonical definition of `source_count` is **the count of distinct
corroborating sources (scraper/network identifiers)** for the record — this
matches the corroboration-bonus semantics (`app/reconciler/location_commit.py`)
and the federation Location aggregate (`app/federation/aggregate.py`, which
computes `len({s.scraper for s in sources})`). The read API
(`app/models/hsds/response.py::LocationResponse.source_count`) currently sets
this field to `len(sources)`, which is equivalent **when `sources` is already
de-duplicated by source identifier** (the normal case). Unifying the two
code paths onto one definition is tracked for a later slice; this Profile
documents the canonical definition now so a federation peer's expectation is
set correctly even before that unification lands.

The `openapi.json` patch documents the `/api/v1/federation/*` endpoints
(`/export`, `/actor`, `/inbox`, `/history`); those operations land fully in
later federation phases (P1/P3). It also documents the additive PPR read
endpoints `/api/v1/locations`, `/api/v1/locations/{location_id}`,
`/api/v1/locations/search`, `/api/v1/organizations/search`, and
`/api/v1/services/search` — these are not part of the core HSDS OpenAPI
specification (which has no `/locations` or `/search` paths) but are existing,
shipped PPR API surface that the Profile now documents as optional additive
endpoints. Only the `/locations*` endpoints currently emit any PPR profile
extension fields (`sources`, `source_count`, and — on `/locations/search`
radius results — `distance`); `/organizations/search` and `/services/search`
return the core HSDS `Organization`/`Service` shape with no PPR extension
fields today.

## HSDS baseline: 3.1.1 (honest)

This Profile is pinned to the **HSDS 3.1.1** baseline. PPR's Pydantic models
(`app/models/hsds/`) are genuinely 3.1.1-shaped: they intentionally omit the
decisive HSDS 3.2 additions (`additional_websites`, `additional_urls`, the
`attributes` collection, and `metadata`). The vendored HSDS specification
submodule under `docs/HSDS/` is pinned at v3.2.3, but the running implementation
is 3.1.1 — so this Profile and the API root metadata both honestly advertise
**3.1.1** rather than the submodule's tag. Revisit the baseline when the models
are upgraded to 3.2.

Adding only optional properties is itself version-agnostic, but the patches are
authored against the 3.1.1 schema shape that the models actually implement; they
do not assume any 3.2 field exists.

## Canonical Profile URI

```
https://hsds-federation.pantrypirateradio.org/profile
```

The API root (`GET /api/v1/`) advertises this URI as the value of its `profile`
field, sourced from `settings.FEDERATION_PROFILE_URI` so the router and the
federation discovery document stay in lockstep.

## Hosting (future work)

The HSDS Profiles spec recommends serving the modification files (and
pre-generated `/schema` compilations) under the Profile's canonical URI, on a
publicly accessible host. Hosting this Profile on the neutral HSDS-FX domain
(design §8.5) is future work; for now the files live in-repo and the router
points at the canonical URI.
