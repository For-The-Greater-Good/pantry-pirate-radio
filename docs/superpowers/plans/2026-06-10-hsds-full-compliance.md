# HSDS Full Compliance — model + serve + federate the complete official object graph (bite-sized plan)

> Sibling of the federation plans [`2026-06-03-hsds-federation-core.md`](2026-06-03-hsds-federation-core.md) and [`2026-06-09-hsds-federation-p2-pull-ingest.md`](2026-06-09-hsds-federation-p2-pull-ingest.md) (the P2 plan), and of the design of record [`../specs/2026-06-03-hsds-federation-core-design.md`](../specs/2026-06-03-hsds-federation-core-design.md). Build slice-by-slice: TDD red-first → per-slice Gauntlet (RED-tier where marked) → PR → owner-override-merge on green (standing owner authorization applies to the federation-touching slices).

> **DRAFT (2026-06-10) — produced by the adversarial DESIGN phase.** Synthesized from 6 cluster analysts + a contract/conformance analyst + an extensions/projection analyst. Owner-locked scope 2026-06-10. Not yet started.
>
> **REVISION 1 (2026-06-10, same day) — final analyst outputs folded in:** new slice **L7** (location-graph reconciler fidelity — the canonical-write drops the cluster analysts found: address commit path passes 6 of 11 fields behind a none-exist guard, `create_location` hardcodes `location_type='physical'` and drops alternate_name/transportation, location-level languages have NO write path, schedule call sites drop 6 more fields than the writer, accessibility only writes on the new-location branch); matrix Recon column corrected (9 of the 10 existing writers are partial — only `service_at_location` is field-complete); T2 gains the `UNIQUE(taxonomy_id, code)` relaxation; X1 gains the per-source confidence fidelity fix + the P2 Slice W dep; D10 added (export-graph scope for contacts/attributes).
>
> **REVISION 2 (2026-06-10 — adversarial critic pass folded in; verdict was "needs-revision", entity count verified clean 24/24):** **(HIGH-1)** G1's "NO strip-list needed" was wrong-in-effect — the owner-deferred v3.1 fields (`additional_websites`/`additional_urls`) appear in all three `*_full.json` examples, so Tier-A `model_validate` under `extra='forbid'` fails on them until D4 resolves; G1 now carries them as explicit fixture-level xfail/strip rows. **(HIGH-2)** `organization.services` and `service_at_location.service` are **CORE** per `compiled/organization.json` + `compiled/service_at_location.json` (and the `*_full.json` examples), NOT undeclared extensions — only `service.locations` is genuinely non-core (spec shape = `service_at_locations`); the locked-scope/G4/D5 lists are corrected. **(HIGH-3)** O1 was mis-decomposed ("flips `organization_full.json` Tier A" is impossible at Dep=G1 — that fixture embeds full `services[]`+`locations[]` graphs); O1 is now scalars + `website` rename + logo/uri/parent + empty-capable array SEAMS, and a new **O4** does the full `/organizations/{id}` compiled assembly after the child slices. **(MEDIUM)** S5 gains a T2 dep (`service_full.json` carries top-level `attributes[]`/`metadata[]`); the line-32 scope flag now also covers attributes/metadata (3.0-era per changelog, so the lock's "3.2-only" premise was void — they are IN scope via T2); Z1 noted that `compiled/` has no taxonomy file and the openapi `$ref`s are remote/moving (Tier-C validates taxonomy against `taxonomy*.json` examples instead); L7's default-ZIP fabrication flagged against `address.postal_code` being spec-required; X1 must honor P2 Slice 5.5's perf budget. **(LOW)** numeric drift corrected (schedule = 25 props / 23 in-scope; org = 7 nested arrays incl. the core `services`); the P2 reconciliation table gains Slice 14 (the plain-HSDS §6.6a consumer is the real foreign-shape consumer of I2's tolerant models).

## ▶ RESUME POINTER (start here — for the next session / Opus)

**Status:** plan drafted, no slices built. **Next action:** owner reviews the OPEN OWNER DECISIONS at the bottom, then build **G1 (the conformance-fixture gate)** first — it gates every other slice.

**What this epic is:** PPR's DB already has ALL ~24 official HSDS entity tables (`init-scripts/01-hsds-schema.sql`), but the layers above are thin: ORM ≈6 entities, Pydantic ≈4 first-class, served responses carry a fraction of the official compiled-schema nesting, the reconciler writes ~10 entities, the signed federation export emits only the curated `LocationResponse` set, and federation ingest (P2 Slices 5/6) has no models to validate a peer's full HSDS graph into. This epic closes the gap **structurally** (model + store + serve + federate + ingest), making PPR the first/reference HSDS-FX implementation. **No scraper changes** — populate only what the pipeline already produces; everything else is faithful pass-through (especially federation-fed data on non-food service types).

**Lockstep:** the P2 plan's RESUME POINTER already banners this epic. This epic **absorbs** the HSDS-validation substance of P2 Slice 5 and **supersedes/implements** P2 Slice 6.5 (see “P2 reconciliation” below). The live two-node demo (P2 Slices 16/17) is the forcing function: the DEMO-BLOCKER column below is the set that must land before a peer pins bytes.

**How:** each slice = ONE PR, ≤600-line app files (constitution §IX), TDD red-first, Gauntlet per slice (RED-tier mandatory where flagged — anything touching `app/federation/` signed bytes or the ingest path). Vendored-official-fixtures rule (constitution Principle III v1.7.0) is satisfied by G1.

## Objective & acceptance

Every entity in the official HSDS spec (`docs/HSDS` submodule, tag v3.2.3, commit `74fcf85b0534fd8c6e61eae13d246b4b375a4495`) is modeled, stored, served at its spec-correct nesting position, written by the reconciler (pass-through where PPR originates no data), carried in the signed federation export, and accepted loss-free by federation ingest.

**Acceptance:**
1. **Reference-impl bar:** our response models validate the official worked examples (`docs/HSDS/examples/*_full.json`, vendored + pinned) — Tier A (representation) + Tier B (byte-stable round-trip via `jcs_bytes`) + Tier C (live endpoints vs `docs/HSDS/schema/compiled/*.json`).
2. **Projection-out clean:** every served/exported key is HSDS-core or declared in `profiles/hsds-ppr/` (hard leak test). Internal tables (`*_source`, `record_version`, audit tables, `federation_log`) never surface as HSDS entities.
3. **Projection-in loss-free:** a peer's plain-HSDS 3.1.1 object graph (including non-food entities PPR never originates: `cost_option`, `service_capacity`+`unit`, `funding`, `program`, `required_document`, `service_area`, `contact`, taxonomy linkage) validates and lands with per-origin provenance, and re-exports byte-faithfully.
4. **Demo honesty:** the P2 two-node demo round-trips nested data (addresses/phones/schedules/languages/accessibility/services-at-location/org+identifiers) with zero silent drops.

## Locked scope (owner, 2026-06-10 — do not relitigate)

- **TARGET = HSDS 3.1.1 field-level completeness**, anchored on the official artifacts: `docs/HSDS/schema/openapi.json` (5 resource endpoints — `/organizations`, `/services` (the only REQUIRED one), `/service_at_locations`, `/taxonomies`, `/taxonomy_terms`, + `/`), `docs/HSDS/schema/compiled/*.json` (the authoritative nested response graphs), `docs/HSDS/schema/<entity>.json` (field sets), `docs/HSDS/examples/` (conformance fixtures), `docs/HSDS/datapackage.json` (relational truth). HSDS does NOT do endpoint-per-entity — the gap is **nesting completeness**, not endpoints.
- **3.2-only additions are OUT** (tracked follow-on epic). ⚠️ **SCOPE FLAG (raised by two analysts, owner must see):** per `docs/HSDS/docs/hsds/changelog.md`, `additional_websites`/`additional_urls`/the `url` entity/`capacities`+`service_capacity`+`unit`/`service_at_location.service_areas` were added in **v3.1**, not 3.2 — the only true 3.2 deltas are API-level (`GET /` optional `publisher`/`data_guide` + endpoint-requirement tags). Capacities/unit/SAL-service-areas are therefore IN scope here (slices S2/S3/A1). ⚠️ REVISION 2: the `attributes[]` and `metadata[]` embedded arrays are likewise 3.0-era (not 3.2) per the changelog — so the lock's "3.2-only" premise was void for them too; they are IN scope via T2 (greenfield taxonomy linkage + change-record entity). `additional_websites`/`additional_urls`/`url`-entity stay EXCLUDED per the owner lock, but relabeled “deferred 3.1 fields” (owner decision D4 below offers re-admission).
- **STRUCTURAL ONLY.** No scraper changes. No synthesizing data (e.g., never derive `cost_options` from `fees_description` or vice versa).
- **PPR extensions are legitimate, not gaps** — when DECLARED. The PPR Profile (`profiles/hsds-ppr/`, RFC 7386 merge patches) declares `confidence_score`/`verified_by`/`sources`. Internal provenance tables and extension columns (`is_canonical`, `source_count`, `scraper_id`, P2 federation columns) stay internal. **Undeclared extension leaks ARE conformance bugs** (four confirmed: `source_count`, `distance`, `sources`-as-objects vs declared strings, the `metadata` core-term shape collision; plus `last_modified` on non-service entities and the one genuinely non-core nesting key `service.locations` — spec shape is `service_at_locations`). ⚠️ REVISION 2: `organization.services` and `service_at_location.service` are **CORE** per the compiled schemas + official examples — they are NOT extensions and must be served, not stripped.
- **Each unit of work = its own PR** (owner instruction). RED-tier Gauntlet wherever federation ingest/canonical/signed-aggregate is touched.

## Master gap matrix (entity × layer)

Legend: ✓ complete · ◐ partial · ✗ absent · S stub-endpoint (200 “not_implemented”) · — n/a (no PPR pipeline producer; validator passes job payload through). Layers: DB (`init-scripts/01-hsds-schema.sql`) / ORM (`app/database/models.py`) / Pyd (`app/models/hsds/`) / Serve (nested per `docs/HSDS/schema/compiled/`) / Recon (`app/reconciler/` writer) / Val (`app/validator/`) / F-out (signed export, `app/federation/aggregate.py`) / F-in (ingest, P2).

| entity | DB | ORM | Pyd | Serve | Recon | Val | F-out | F-in | note |
|---|---|---|---|---|---|---|---|---|---|
| organization | ✓ | ◐ | ◐ | ◐ | ◐ | ✓ | ✗ | ✗ | ORM/serve miss logo/uri/parent_organization_id; zero nested arrays; `website` served via fragile `url` alias; writer drops alternate_name/logo |
| organization_identifier | ✓ | ✗ | ✗ | ✗ | ◐ | — | ✗ | ✗ | LIVE data (LLM aligner emits, writer inserts) but writer drops identifier_scheme + dupes on re-scrape |
| funding | ✓ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ | pure pass-through (no PPR producer) |
| program | ✓ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ | pass-through; dual shape: org.programs[] + singular service.program{} |
| service | ✓ | ◐ | ◐ | ◐ | ◐ | ✓ | ✗ | ✗ | THE required endpoint; 10 scalars missing in serve; writer hardcodes status='active' (corrupts a peer's value); description wrongly required in model |
| service_at_location | ✓ | ✓ | ◐ | ◐ | ✓ | — | ✗ | ✗ | path mismatch (/service-at-location); detail nesting only behind ?include_details, shallow |
| service_area | ✓ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ | aligner ALREADY emits it; reconciler drops — live silent-drop |
| service_capacity | ✓ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ | requires nested unit{}; v3.1 entity, IN scope |
| unit | ✓ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ | required sub-object of service_capacity |
| required_document | ✓ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ | aligner ALREADY emits it; reconciler drops |
| cost_option | ✓ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ | pass-through; JCS number-stability matters for `amount` |
| location | ✓ | ◐ | ◐ | ◐ | ◐ | ✓ | ◐ | ✗ | only exported entity; serve/model drop DB url + organization_id; writer hardcodes location_type='physical', drops alternate_name/transportation (L7) |
| address | ✓ | ✓ | ✗ | ✗ | ◐ | ✓ | ✗ | ✗ | most user-visible gap: NO address in any HSDS response or export; commit path passes 6/11 fields behind a none-exist guard + synthesizes default ZIPs (L7) |
| phone | ✓ | ✗ | ◐ | ◐ | ◐ | — | ◐ | ✗ | PhoneInfo = 2 of 10 fields; export leaks one number as sources[].phone string; call sites drop extension/description the writer accepts |
| schedule | ✓ | ✓ | ◐ | ◐ | ◐ | — | ◐ | ✗ | ScheduleInfo = 9 of 24 fields, missing spec-REQUIRED id; exported without id; writer omits 6 columns, call sites drop 6 more — export carries notes/valid_from/valid_to that ingest would lose TODAY |
| language | ✓ | ✗ | ✗ | ✗ | ◐ | — | ✗ | ✗ | writer exists for service/phone level; location-level languages have NO write path (total loss); `note` never passed |
| accessibility | ✓ | ✗ | ✗ | ✗ | ◐ | — | ✗ | ✗ | writer full-field but fires only on the new-location branch — matched/merged locations never gain or update accessibility |
| contact | ✓ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ | greenfield (model+writer+nesting under org/service/SAL) |
| taxonomy | ✓ | ✗ | ✗ | S | ✗ | — | ✗ | ✗ | stub returns 200 “not_implemented”; {id} never 404s |
| taxonomy_term | ✓ | ✗ | ✗ | S | ✗ | — | ✗ | ✗ | stub + path mismatch (/taxonomy-terms) |
| attribute | ✓ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ | attributes[] (taxonomy linkage) absent on EVERY entity since 3.0 |
| metadata (entity) | ✓ | ✗ | ✗ | ✗! | ✗ | — | ✗ | ✗ | WORSE than absent: MetadataResponse object collides with the core `metadata` array term — forbidden by our own Profile rules |
| meta_table_description | ✓ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ | tabular-only entity; owner decision D8 |
| url (3.1 entity, deferred) | ✓ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ | excluded per owner lock (relabeled “deferred 3.1”) |

**Headline counts:** DB **24/24** complete (the premise holds). ORM **6/24** (3 of those partial). Pydantic **4 first-class + 2 partial embeds** (PhoneInfo 2/10, ScheduleInfo 9/24-no-id). Serve **0/24 fully conformant** — every list response fails the official Page envelope (`total_items/total_pages/page_number/size/first_page/last_page/empty/contents` vs our `count/total/.../data`) before per-entity nesting is even reached. Reconciler **10/24** writers — **9 of the 10 are partial** (only `service_at_location` is field-complete); 2 entities the aligner ALREADY emits get silently dropped (service_area, required_document). Validator: job-payload level (org/service/location/address primary). Federation export **1 partial entity**; ingest **0/24** (unbuilt; current models would hard-reject any full-graph peer object via `extra='forbid'`).

**Cross-cutting wire bugs (fix once, early):** official Page envelope; `metadata` core-term collision; 4 undeclared extension leaks + `last_modified`/non-core nesting keys; 2 path mismatches (`/service-at-location`, `/taxonomy-terms`); `OrganizationResponse.url`↔`website` alias fragility; Profile declares fields never served (`confidence_score`/`verified_by` at top level) and a `'network'` enum the DB CHECK rejects.

## Slices (dependency-ordered — ONE PR each)

`RED` = RED-tier Gauntlet mandatory (touches federation ingest / signed aggregate / canonical bytes). `🎯` = DEMO BLOCKER (must land before P2 Slice 16 pins bytes). `🧩` = partner-gate (before the partner integrates, after the demo).

### Phase G — Gates: conformance machinery + wire hygiene

| # | Slice | RED | 🎯 | Dep |
|---|-------|-----|----|-----|
| G1 | **Conformance-fixture gate (test-only).** Vendor `docs/HSDS/examples/*.json` + `examples/csv/*` (resolve the datapackage symlink) → `tests/test_hsds_conformance/vendor/hsds_official_examples/`, README pinning source repo, commit `74fcf85b0534fd8c6e61eae13d246b4b375a4495` (tag v3.2.3), license CC BY-SA 4.0, retrieval date + REGISTRY.md row (pattern: `tests/test_federation/vendor/`). Submodule-pin guard test (CI fails if `docs/HSDS` drifts from the vendored pin). Tier A KATs: each `*_full.json` must `model_validate` into our response models (`extra='forbid'` kept — it IS the ratchet). Tier B KATs: `model_dump(mode="json", by_alias=True, exclude_none=True)` byte-equals the example via `app/federation/canonical.py:jcs_bytes`. Shrink-only xfail manifest + meta-test (constitution coverage-ratchet style); today everything xfails — each entity slice flips its rows. ⚠️ REVISION 2: there are zero 3.1.1→3.2.3 schema-field deltas, BUT the owner-deferred v3.1 fields (`additional_websites`/`additional_urls`) DO appear in the `*_full.json` examples, so Tier-A under `extra='forbid'` fails on them — carry those specific fields as explicit fixture-level xfail (or a documented pre-validation strip) until owner decision D4 resolves; this is NOT a general strip-list, it is the deferred-3.1 carve-out. | | 🎯 | — |
| G2 | **Profile truth-up (docs-only).** `profiles/hsds-ppr/`: declare `sources` real object shape (SourceInfo fields); add `source_count` (+ unify its two definitions: serve=len(sources) vs export=distinct scrapers); decide/declare `distance`; add organization + service_at_location patches for surviving extension keys; annotate `verified_by='network'` (lands with P2 Slice 3 / I1); declare additive `/locations` + `/search` in the openapi patch. Acceptance: every key the X1 leak test finds is core-or-declared. **Must merge before any peer pins export bytes.** | | 🎯 | — |
| G3 | **Official Page envelope.** Replace the bespoke `Page` (`app/models/hsds/response.py`) wire shape with the official `total_items/total_pages/page_number/size/first_page/last_page/empty/contents` on all 5 HSDS list endpoints (+ POST list variants = owner decision D2 rider). KAT: `organization_list.json` envelope fixture. | | | G1 |
| G4 | **`metadata` core-term collision + emission hygiene.** Stop emitting `MetadataResponse` under `metadata` (owner decision D3: rename wrapper vs serve genuine HSDS `metadata[]` derived from `record_version`/`change_audit` — recommend the latter, flagship move); null-only undeclared keys vanish (`exclude_none` hygiene); `distance` only on radius-search responses; ⚠️ REVISION 2 — only `service.locations` is the non-core key to align/declare (`organization.services` + `SAL.service` are CORE — serve them); align per G2 declarations. Export bytes UNCHANGED (`exclude_none` already drops offenders) — not RED. | | | G2 |
| G5 | **Spec paths.** Mount `/service_at_locations` + `/taxonomy_terms` (underscore, plural) as primary; keep `/service-at-location` + `/taxonomy-terms` as deprecated additive aliases. | | | — |

### Phase T — Taxonomy backbone (greenfield; enables attributes[] everywhere)

| # | Slice | RED | 🎯 | Dep |
|---|-------|-----|----|-----|
| T1 | **taxonomy + taxonomy_term verticals.** ORM + Pydantic + REAL `/taxonomies`, `/taxonomy_terms` endpoints (replace the 200-“not_implemented” stubs; proper 404; Page envelope; `taxonomy_detail` nesting; `top_only`/`parent_id` params) + pass-through writers. Fixture flips: `taxonomy*.json`. | | 🧩 | G1,G3,G5 |
| T2 | **attribute + metadata-entity models.** ORM + Pydantic for `attribute` (with nested `taxonomy_term{}`) and the `metadata` change-record entity; `attributes[]`/`metadata[]` seams on all response models (empty-capable); writers pass-through (attribute upsert in FK order taxonomy → taxonomy_term → attribute; `link_id` remapped to the post-reconciliation canonical row — the one documented non-byte-stable field on re-export; survivor-merge scripts learn to repoint `attribute.link_id` like other FK children). **Relax the global `UNIQUE(code)` on taxonomy_term to `UNIQUE(taxonomy_id, code)`** — the spec's own prose says code+taxonomy_id combined define the term, and the global constraint would reject legitimate same-code terms from two different peers' taxonomies at ingest (document the spec tension). If D3 chose “genuine metadata[]”, the record_version derivation lands here. | | 🧩 | T1,G4 |

### Phase L — Location graph (the demo wire’s payload)

| # | Slice | RED | 🎯 | Dep |
|---|-------|-----|----|-----|
| L1 | **location core scalars.** Add `url` + `organization_id` (DB has both; model/serve drop them) to ORM/Pydantic/serve; flip `location.json` fixture. | | 🎯 | G1 |
| L2 | **address vertical.** Pydantic Address (full 3.1.1 field set) + `addresses[]` nested in LocationResponse (ORM + writer exist). Most user-visible gap. | | 🎯 | L1 |
| L3 | **phone vertical.** Full 10-field Phone model + `languages[]` sub-array + ORM + nesting seams under location/service/organization/SAL/contact + writer pass-through (writer exists). Retire 2-field PhoneInfo. | | 🎯 | L1 |
| L4 | **schedule completeness.** ScheduleInfo → full 24-field Schedule (spec-REQUIRED `id`, dtstart/timezone/until/count/wkst/interval/byweekno/byyearday/schedule_link/attending_type + FKs); DB+ORM complete, but the writer omits 6 columns (timezone/byweekno/byyearday/schedule_link/attending_type/notes) and both call sites drop 6 more the writer accepts (interval/count/dtstart/until/valid_from/valid_to) — full writer+call-site pass-through lands HERE (the round-trip loss is live: today's export carries notes/valid_from/valid_to that ingest discards). Serve at every nesting position. **Export-byte stability:** new model fields default None + `exclude_none` keeps today's aggregate bytes unchanged; schedule `id` enters the SIGNED bytes only at X1 — else this slice would be RED. **Schedule shape freezes at first peer byte-pin — must precede X1.** | | 🎯 | L1 |
| L5 | **language + accessibility verticals.** Models + ORM + nesting (language under phone/location/service; accessibility under location). Writers PARTIALLY exist: `create_language` covers the columns but has NO location-level call site (LocationDict.languages is total loss) and never passes `note`; `create_accessibility` is full-field but new-location-branch-only — the behavior fixes ride L7, this slice is model+serve. | | 🎯 | L1,L3 |
| L6 | **contact vertical (greenfield).** Model + ORM + writer + nesting under organization/service/SAL (+ phones-on-contacts via the existing unused `create_phone(contact_id=)` param). No live data → partner-gate, BUT its model is a dependency of A1/S5 typing — sequence before them. | | 🧩 | L3 |
| L7 | **location-graph reconciler fidelity (canonical-write behavior — own PR per the analysts' isolation call).** (a) `create_location` pass-through: persist alternate_name/transportation/location_type from the job (kill the hardcoded `'physical'`; LocationDict already carries all three). (b) Address commit path: pass ALL 11 fields (today `_create_new_location_addresses` drops attention/address_2/region); revisit the state-capital default-ZIP fabrication (synthetic postal_codes in canonical data); define the matched-location address update policy (the none-exist guard means a peer/later source can never correct a stale address). (c) Location-level language write path (new `create_language(location_id=)` call) + `note` pass-through + parent-tuple dedup. (d) Accessibility matched-location policy (today only the location-creating source's accessibility persists). (e) Phone call sites pass extension/description (writer already accepts). Drift events + full regression suite — this changes canonical rows. | | 🎯 | L1–L5 |

### Phase S — Service graph (the only REQUIRED endpoint)

| # | Slice | RED | 🎯 | Dep |
|---|-------|-----|----|-----|
| S1 | **service core completeness (anchor).** ORM add licenses/alert/last_modified; Pydantic full 3.1.1 scalar set with spec-true required `{id,name,status}` (description becomes optional); rename non-spec `locations` → `service_at_locations`; reconciler scalar pass-through **including status** (kill the hardcoded 'active' — silently corrupts a peer's `temporarily closed`); fix merge_service to carry the full scalar set. | | 🎯 | G1 |
| S2 | **service_area vertical.** Dual-parent nesting (service.service_areas[] + SAL.service_areas[]); dual-FK writer; un-drop the aligner output (`job_processor` already receives the key and discards it). | | 🧩 | S1 |
| S3 | **service_capacity + unit vertical.** Both entities in one PR (unit{} is a REQUIRED sub-object); capacities[] on service; writer upsert keyed (service_id, unit_id); preserve peer `updated` verbatim (it is data, not bookkeeping). | | 🧩 | S1 |
| S4 | **required_document + cost_option verticals.** Identical mechanical pattern (id-only-required, single FK, scalar-only); un-drop aligner required_documents; cost_option amount must be JCS/ES6-number byte-stable. | | 🧩 | S1 |
| S5 | **/services/{id} full compiled assembly.** organization{}, program{}, service_at_locations[], contacts[], phones[], languages[], schedules[], funding[], cost_options[], required_documents[], capacities[] per `compiled/service.json`; `service_list.json` embeds (organization{}/program{}); spec params (`taxonomy_term_id`/`modified_after`/`minimal`/`full`) as feasible. Flips `service_full.json` Tier A+B. ⚠️ REVISION 2: `service_full.json` also carries top-level `attributes[]`+`metadata[]` → add **T2** dep (else its Tier-A flip can't pass). | | 🧩 | S1–S4,L3–L6,O1,O3,T2 |

### Phase O — Organization graph

| # | Slice | RED | 🎯 | Dep |
|---|-------|-----|----|-----|
| O1 | **organization core (anchor).** ⚠️ REVISION 2 — scoped to scalars + SEAMS only (the full `organization_full.json` Tier-A flip moves to O4; that fixture embeds full `services[]`+`locations[]` graphs needing O2/O3/S-graph/L-graph types, impossible at Dep=G1). Here: rename `url`-aliased field to `website` outright (alias only survives under FastAPI's by_alias); ORM+serve logo/uri/parent_organization_id; the six nested-array SEAMS on Organization/OrganizationResponse as empty-capable (`funding[]`/`contacts[]`/`phones[]`/`locations[]`/`programs[]`/`organization_identifiers[]` — populated by their entity slices); reconciler pass-through alternate_name+logo; the singular `organization{}` embed seam for service responses. | | 🎯 | G1 |
| O4 | **/organizations/{id} full compiled assembly.** Populate the O1 seams + embed `services[]` (full service objects) and `locations[]` per `compiled/organization.json`; flips `organization_full.json` Tier A+B. Depends on the child entities that fill the arrays. Partner-gate (not demo wire). | | 🧩 | O1,O2,O3,S5,L2–L6 |
| O2 | **organization_identifier end-to-end.** LIVE-data entity: Pydantic + ORM + nest into OrganizationResponse + writer fixes — write identifier_scheme (currently dropped), idempotent upsert on (organization_id, identifier_scheme, identifier_type, identifier) instead of fresh-uuid4-per-job dup inserts, skip-and-log instead of empty-string required fields, preserve peer-supplied id for federated rows. | | 🎯 | O1 |
| O3 | **funding + program pass-through verticals.** Models + ORM + nesting under org AND service (funding both parents; program = org array + singular service.program{} via existing service.program_id) + idempotent peer-id-preserving writers; program FK ordering (org-before-program-before-service, orphan → reject-and-log). | | 🧩 | O1 |

### Phase A — service_at_location resource

| # | Slice | RED | 🎯 | Dep |
|---|-------|-----|----|-----|
| A1 | **SAL full compiled nesting.** service_areas[]/contacts[]/phones[]/schedules[] at SAL level + always-embedded full location{} (with addresses/accessibility/languages/phones/schedules/contacts) + service{} per `compiled/service_at_location.json`; retire shallow `?include_details` dicts. Geo params postcode/proximity = owner decision D7. Flips `service_at_location_full.json`. | | 🎯 | G5,S1,L2–L6,S2 |

### Phase I — Projection-IN: per-origin landing + ingest validation (RED)

| # | Slice | RED | 🎯 | Dep |
|---|-------|-----|----|-----|
| I1 | **Per-origin loss-free landing.** `location_source.hsds_payload JSONB` (the origin's full validated HSDS object, verbatim — loss-free even before satellite writers exist); widen `location_verified_by_check` to admit `'network'` (Profile declares it; DB CHECK currently rejects — would otherwise explode at P2 Slice 8 runtime); satellite source-attribution columns (schedule/address/phone — also unblocks the schedule-orphan cleanup follow-up and makes P2 Slice 7b's CvRDT property satisfiable beyond name/desc/coords). **Coordinate as ONE migration window with P2 Slice 3's federation columns.** | RED | 🎯 | (P2 Slice 3) |
| I2 | **Ingest full-graph validation + storage.** Tolerant ingest-validation variant (profile-aware `extra='ignore'` allowlist — the strict `extra='forbid'` response models stay serve/export-side as the leak guard); spec-true required sets so a conformant peer object (e.g. service without description) is never rejected; ingest path invokes the satellite writers so a peer's nested graph (incl. non-food entities) lands per-origin and re-exports faithfully (L7's fidelity fixes are load-bearing here — the writers the ingest path calls must not drop fields). **ABSORBS the “validate against the HSDS Pydantic models” layer of P2 Slice 5** (Slice 5 keeps the enqueue/routing plumbing). | RED | 🎯 | I1, L1–L5, L7, S1, O1, O2 (full graph: S2–S4, O3, L6, T1–T2) |

### Phase X — Projection-OUT: federation export widening (RED)

| # | Slice | RED | 🎯 | Dep |
|---|-------|-----|----|-----|
| X1 | **Widened signed §8.2 aggregate (IMPLEMENTS P2 Slice 6.5).** Structured addresses, phones, languages, accessibility, services-at-location (embedded service) + schedule `id` in `build_location_aggregate`; hard EXPORT-LEAK test (emitted keys ⊆ core ∪ profile-declared — `source_count`/`sources` shape must be G2-declared by then); cold-start parity guard re-run as the gate (`tests/test_federation/test_coldstart_parity.py` precedent). **Per-source confidence fidelity fix rides along** (the shape is being re-baked anyway): `_SOURCES_SQL` stamps the CANONICAL `l.confidence_score` on every SourceInfo instead of the per-origin `location_source.confidence_score` — per-origin provenance flattened to the merged value. Contacts/attributes in the aggregate = owner decision D10, NOT silently added here. | RED | 🎯 | G2,L2–L5,A1,S1 (+P2 Slice W merged — proof suite frozen first) |
| X2 | **Organization graph in export.** Canonical organization + organization_identifiers (+ funding/programs when present) embedded HSDS-core-only (strip/declare normalized_name, confidence_score, validation_* — no org Profile patch exists pre-G2); replaces the org-as-SourceInfo-strings leak. Live org_identifier data on both demo nodes must not be lost. | RED | 🎯 | O1,O2,X1 |

### Phase Z — Conformance closure

| # | Slice | RED | 🎯 | Dep |
|---|-------|-----|----|-----|
| Z1 | **Tier C live-endpoint schema gate.** TestClient + seeded DB; `jsonschema` (Draft 2020-12) validation of all 5 endpoints against `docs/HSDS/schema/compiled/*` (read from the pinned submodule, loud-skip if absent — the pin-guard still fails CI on drift) + the Page component. Catches router-level bugs no model KAT can. | | | G3–G5,T1,S5,O1–O3,A1 |
| Z2 | **CSV/datapackage tabular gate (advisory).** Validate HAARRRvest/reconciler tabular output with frictionless against `docs/HSDS/datapackage.json`, worked example `examples/csv/`. Owner decision D8 scopes it. | | | Z1 |
| Z3 | **Docs + ratchet flip + P2 lockstep scrub.** CLAUDE.md HSDS section; Profile final pass; flip the G1 xfail manifest to a full-pass HARD gate (owner decision D1); banner-edit the P2 plan rows 5/6.5 with final pointers; status comments on #519/#523; close the epic issue. | | | all |

**Suggested build order:** G1 → G2 → {G3,G4,G5 ∥ L1} → L2–L5 → L7 → S1 → O1 → O2 → I1 (with P2 Slice 3) → L6 → A1 → X1 → I2(demo subset) → X2 → **[P2 Slice 16 demo]** → T1 → T2 → S2–S4 → O3 → S5 → I2(full graph) → Z1 → Z2 → Z3.

## The conformance gate (G1) — how it gates everything

G1 is the constitution-Principle-III “machinery, not memory” move for HSDS itself (same class as the cyberphone JCS suite and the W3C eddsa KAT): the OFFICIAL worked examples become executable conformance fixtures, pinned to the exact submodule commit, with a guard test preventing silent drift between the vendored copies and `docs/HSDS`. Downstream gating mechanics:

1. Every entity slice's Definition of Done includes flipping its fixture rows in the shrink-only xfail manifest (a meta-test fails CI if the manifest ever GROWS — regressions cannot hide).
2. `extra='forbid'` on `HSDSBaseModel` stays — official fields we have not modeled RAISE in Tier A instead of silently passing; that is the ratchet mechanism, not an obstacle.
3. Tier B's `jcs_bytes` comparison catches lossy collapse and key-naming drift (`website` vs `url`) — the cold-start-parity-guard precedent applied to serve-side models.
4. Tier C (Z1) is the only tier that catches router bugs (envelope, paths, include_* defaults) — it closes the loop at the end.
5. The strict KAT models are NEVER reused verbatim for ingest (I2 builds the tolerant variant) — peer payloads may carry their own declared extensions.

## P2 reconciliation (keep the two plans in lockstep)

| P2 slice | Relationship | Mechanics |
|---|---|---|
| Slice 5 (inverted no-LLM ingest) | **ABSORBED (validation layer)** | Slice 5 keeps the plumbing (verify→enqueue-at-validator, `VALIDATOR_ENABLED` routing, `enqueue_to_validator` precedent). Its “validate against the HSDS Pydantic models” step is supplied by **I2** (tolerant full-graph variant + spec-true required sets). If Slice 5 lands first, it validates the current curated shape and carries a banner pointing at I2 for the widening. |
| Slice 6 (verify-before-enqueue) | **COMPLEMENTS** | Pure crypto/transport — untouched here. This epic only defines WHAT validates after verify succeeds. |
| Slice 6.5 (wire-shape aggregate hardening) | **SUPERSEDED / implemented by X1** | Same acceptance (cold-start parity gate) plus the leak test, schedule `id`, and the G2 Profile declarations. Banner-annotate the P2 row: “implemented by HSDS-completeness X1 (+X2 for the org graph)”. |
| Slice 3 (models/migration) | **COORDINATE** | I1's `location_source` columns land in the SAME migration window as Slice 3's federation columns (one migration or explicitly sequenced — never two competing edits). |
| Slice 7b (CvRDT property) | **COMPLEMENTS** | I1's satellite attribution columns are what make the order-shuffle property satisfiable beyond name/desc/coords. |
| Slices 16/17 (live two-node demo) | **CONSUMES** | The 🎯 set below is added to Slice 16's dependency row. |

**Lockstep protocol:** on acceptance of this plan — status comments on #519 (cross-phase ledger) and #523 (P2 ledger); banner-correct P2 rows 5/6.5 in place (never silently rewrite); every absorbed/superseding PR description references BOTH plans; Z3 performs the final scrub.

## Demo-blocker subset (must land before P2 Slice 16 pins bytes)

**Blockers (16):** G1, G2 (wire shapes must be declared before a peer pins export bytes), L1–L5 (the widened aggregate's payload: location scalars, addresses, phones, schedules-with-id, languages, accessibility), L7 (write-side fidelity — without it the ingest path stores a peer's addresses minus attention/address_2/region, drops their location languages entirely, and corrupts location_type: "round-trips with zero silent drops" would be false), S1 (SAL embeds service; status fidelity at ingest), O1+O2 (live organization_identifier data on both nodes must round-trip), A1 (services-at-location nesting), I1+I2-demo-subset (per-origin landing + tolerant validation for the demo wire shape), X1+X2 (the widened signed aggregate itself). L6 (contact model) sits on the critical path only as a typing dependency of A1 — sequence it before A1, but it carries no demo data. **Borderline (owner decision D9):** if the owner scopes the demo wire to the P2-Slice-6.5 list exactly (no org embed), O1/O2/X2 slip to partner-gate.

**Partner-gate (before the partner integrates, after the demo):** T1, T2, S2–S5, O3, L6, full-graph I2 — these make a peer's NON-FOOD nested data (cost_options, capacities, funding, programs, required_documents, service_areas, contacts, taxonomy linkage) land loss-free; the two-PPR-node demo datasets don't contain them.

**Polish (anytime):** G3, G4, G5, Z1–Z3 serve-richness and closure.

## GitHub tracking

- **Epic issue: #584** — the ledger for this plan; status comment per phase transition; cross-links #519/#523.
- **Phase issues (8): G #585 · T #586 · L #587 · S #588 · O+A #589 · I #590 · X #591 · Z #592** — checklists of their slices.
- **Per-slice issues:** created when the slice STARTS (not batch up front — the P2 precedent); title `HSDS <id> — <name>`; PR says `Closes #<slice-issue>` and references the epic + (for I/X slices) #523.
- **Cross-references:** I1/I2 PRs reference the P2 plan Slice 3/5 rows; X1 references Slice 6.5; the demo blockers get a tracking comment on the P2 Slice 16 issue when it exists.

## Open owner decisions (outcome-framed)

- **D1 — Conformance gate hardness:** shrink-only ratchet now, flip to HARD full-pass CI gate at Z3 (recommended) — or hard-gate each vendored fixture from day one (blocks every entity slice on its neighbors)?
- **D2 — Page envelope cutover:** consumers see the official envelope in one release (breaking for any client parsing `data`/`count`), or a dual-emit transition window? Also: ship the spec's POST list variants now or defer?
- **D3 — `metadata` strategy:** rename the wrapper to a declared `ppr_meta` (cheap), or serve genuine HSDS `metadata[]` change-records derived from `record_version`/`change_audit` (flagship: our provenance machinery becomes the spec's audit surface — recommended)?
- **D4 — Deferred 3.1 fields:** the changelog shows `additional_websites`/`additional_urls`/the `url` entity are v3.1, not 3.2. Re-admit them to this epic (one extra small vertical: url entity + two array fields), or re-affirm deferral with corrected labels? (Peers will/won't see org websites beyond the primary one.)
- **D5 — Beyond-spec surfaces:** keep+declare `/locations` and `/search` in the Profile (recommended), or retire them as the spec nesting lands? (⚠️ REVISION 2: dropped the nesting-key half of this question — `organization.services`/`SAL.service` are CORE, not beyond-spec; only `service.locations` is non-core, handled in G4.)
- **D6 — `distance`/`source_count` on HSDS endpoints:** declare both in the Profile and keep serving, or suppress from HSDS responses (serve only on additive endpoints)?
- **D7 — Official geo params:** adopt `postcode`/`proximity` on `/service_at_locations` (where the spec puts geo search) in A1, or keep geo on additive `/locations/search` only for now?
- **D8 — Tabular tail:** implement `meta_table_description` + the Z2 frictionless CSV gate, or explicitly document both as out-of-scope-until-HAARRRvest-asks?
- **D9 — Demo wire scope:** must the org graph (O1/O2/X2) be in the demo's signed bytes, or is the Slice-6.5 list (X1) sufficient with the org embed landing pre-partner? (Resolves the borderline demo-blocker set.)
- **D10 — Export-graph scope beyond the Slice-6.5 list:** do `contacts[]` and the `attributes[]`→taxonomy_term→taxonomy chain enter the SIGNED aggregate in this epic (each is a RED wire-shape re-bake: parity guard + vectors), or stay export-deferred until a partner dataset actually carries them? Neither is in P2 Slice 6.5's enumerated list; ingest/storage lands regardless (L6/T2) — this decision is only about the signed export bytes. Recommend: defer, revisit at partner onboarding (one re-bake, not two).
