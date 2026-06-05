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
- `openapi.json` — merge patch over the HSDS API specification.

## Permitted modifications only

Per the HSDS Profiles "Permitted Modifications" rules, this Profile only
**adds new OPTIONAL properties** to the core schemas. It does **not** add any
property to a schema's `required` array, does not override or remove any core
property, and the added terms do not overlap semantically with existing HSDS
terms.

The added optional properties on both `location` and `service` are:

| Property           | Type             | Notes                                                                                  |
| ------------------ | ---------------- | -------------------------------------------------------------------------------------- |
| `confidence_score` | integer (0–100)  | PPR data-quality confidence. Scraped data capped at 90; 91–100 are human corrections.  |
| `verified_by`      | string enum      | `auto` / `admin` / `source` / `claimed` / `network` — provenance of the verification.  |
| `sources`          | array of strings | Scraper / network identifiers that corroborated the record (multi-source corroboration). |

These mirror fields PPR already emits. The `openapi.json` patch documents the
forthcoming `/api/v1/federation/*` endpoints (`/export`, `/actor`, `/inbox`,
`/history`); those operations land fully in later federation phases (P1/P3) — the
Profile documents them now as new optional API endpoints.

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
