# Adjacent Federation Protocols for HSDS Data Exchange

Research for Pantry Pirate Radio / Lighthouse federation design. Focus: protocols **not** ActivityPub or OpenProductRecovery, with real-world deployments in reference-data domains (places, orgs, services, identifiers).

---

## 1. Open Referral / HSDS itself

**What it is, who runs it, scale.** HSDS (Human Services Data Specification) is an exchange *format* — JSON schema for organizations, services, locations, and accessibility info — maintained by the Open Referral Initiative. As of v3.x, it explicitly declares JSON as the canonical wire format and ships an OpenAPI "API Reference" plus a "Profiles" mechanism for jurisdictional extensions (e.g., Open Referral UK profile). Deployments: 211 systems, Drupal/WordPress publisher plugins, regional aggregators (Open Referral UK, Connect Our Kids), and PPR itself as a multi-source aggregator.

**Federation story (the gap).** The Open Referral 3.0.1 FAQ explicitly acknowledges federation as an *aspiration* rather than a solved problem: aligning JSON outputs across publishers "would make data federation/syncing feasible" — i.e., the spec gets you a wire shape and an API surface, but **not a registry, not an identity model, not a conflict-resolution rule, not an incremental-sync watermark.** Identifiers are UUIDs scoped per-publisher (no global namespace), so cross-publisher dedup is left as an exercise.

**Working multi-publisher implementations.** Open Referral UK's `developers.openreferraluk.org` documents a real aggregation, deduplication, and validation pipeline against multiple LA/charity publishers — but the matching is done by the aggregator using its own heuristics (string + geo). This is precisely PPR's reconciler model. There is no community-blessed federation protocol; everyone builds their own scrapers and matchers.

**Identity model:** UUIDs per publisher (collision-prone across federation).
**Update propagation:** Pull (bulk JSON or paginated API).
**Conflict resolution:** Aggregator-side, ad-hoc.
**Trust model:** Open; consumer chooses which publishers to trust.

**Steal:** The **Profiles** mechanism — JSON Merge Patch on canonical schema for jurisdictional extension — is genuinely good and Lighthouse should adopt the exact pattern for FANO-specific or operator-specific fields without forking HSDS.

**Avoid:** Don't replicate HSDS's silence on identity. The lack of a globally-unique location identifier is the single biggest cause of integration pain in this space.

Sources:
- [HSDS 3.0.1 FAQ](http://docs.openreferral.org/en/latest/hsds/hsds_faqs.html)
- [HSDS Profiles Reference](https://docs.openreferral.org/en/latest/hsds/profiles.html)
- [Open Referral UK developers](https://openreferraluk.org/developers)

---

## 2. HL7 FHIR Bulk Data Access ("Flat FHIR") + Validated Healthcare Directory

**What it is, who runs it, scale.** FHIR Bulk Data Access (currently STU 3, v3.0.0) is HL7's spec for asynchronous bulk export of FHIR resources as NDJSON. Built on FHIR R4. Deployed at population scale: CMS Blue Button 2.0, every major US EHR vendor (Epic, Cerner/Oracle, Athena), national payer-to-payer exchange (Da Vinci PDex), and crucially **VhDir** (Validated Healthcare Directory) — the FHIR profile for provider directories of `Organization`, `Location`, `HealthcareService`, `Practitioner`. This is the closest deployed analogue to what HSDS aspires to be.

**Identity model.** Every resource has a server-assigned `id` plus an arbitrary number of `identifier` entries with `system` (URI namespace) + `value` — explicit support for multiple authorities asserting their own ID for the same real-world entity. NPI, tax ID, internal IDs coexist on one `Organization` resource. This is the pattern PPR's `location_source` table is reinventing.

**Update propagation.** Asynchronous kick-off pattern:
1. Client `GET $export?_type=Organization,Location&_since=<watermark>` → HTTP 202 + `Content-Location` header
2. Client polls the status URL
3. Server returns a manifest with NDJSON file URLs + a `transactionTime` (the new watermark)
4. Client uses `transactionTime` on the next poll

Plus FHIR Subscriptions for push notifications on specific criteria (e.g., "any Practitioner whose certification was revoked").

**Conflict resolution / authoritative source.** Each resource has a `meta.source` URL and `meta.versionId`. The pattern is **"authoritative for own records, contributory for references"** — a hospital's FHIR server is authoritative for its own `Organization`, but when it references a `Practitioner` that's authoritatively published by a state licensing board, the hospital's copy is treated as a cache. Authority is asserted by `identifier.system`.

**Trust model.** SMART Backend Services: signed JWT client assertions with pre-registered public keys per consumer. Not open; trust is per-pair allowlist with revocable keys.

**Steal — the big one:** The `$export?_since=<transactionTime>` watermark pattern. Replace PPR's "publish full HAARRRvest SQLite nightly" with an HSDS-shaped `$export?_since=` endpoint that returns NDJSON of changed `location`/`organization`/`service` records. The watermark is server-assigned (not client clock), and the polling/manifest pattern handles backpressure gracefully. Also steal the `identifier[]` array (multiple `system`+`value` pairs on one resource) — this is exactly what `location_source` should serialize as.

**Avoid:** SMART Backend Services-style mandatory mTLS/JWT for an open directory of pantries is overkill. FHIR's auth model assumes PHI; ours doesn't.

Sources:
- [FHIR Bulk Data Export v3.0.0](https://build.fhir.org/ig/HL7/bulk-data/export.html)
- [VhDir Bulk Data & Subscriptions](https://build.fhir.org/ig/HL7/VhDir/bulk-data.html)
- [Da Vinci Payer-to-Payer Bulk Exchange](https://build.fhir.org/ig/HL7/davinci-epdx/payertopayerbulkexchange.html)

---

## 3. IATI (International Aid Transparency Initiative)

**What it is, who runs it, scale.** Since 2008, IATI has been the de-facto standard for publishing international aid flows. ~1,500 publishers (donors, NGOs, multilaterals, recipient governments) each host their own XML file at their own URL; the IATI Registry at `iatiregistry.org` (a CKAN instance) is **metadata-only** — it indexes who publishes what, where, and when, but never holds the data itself. d-portal, IATI Studio, and others harvest the registry to build aggregated views.

**Identity model.** Globally unique activity IDs by construction: `<publisher-org-ref>-<publisher-internal-id>` (e.g., `GB-GOV-1-300123-ABCD`). The org-ref prefix is the publisher's IATI registry ID. Immutable once published. **This solves the federation identity problem at the cost of one rule: publishers must prefix their IDs.**

**Update propagation.** Pull-only. Publisher hosts XML at a stable URL; aggregators harvest on a schedule (typically daily). No watermark — the file is the whole truth. d-portal computes diffs locally.

**Conflict resolution.** This is IATI's most interesting pattern: **donor and recipient publish the *same* activity from different perspectives**, and the schema acknowledges this via `transaction/@provider-activity-id` and `transaction/@receiver-activity-id` — each transaction explicitly references the *other side's* activity ID, forming a linked traceability graph. There's no authoritative version; consumers reconcile by transaction matching. The community explicitly discourages `<related-activity>` for cross-org relationships (parent/child is intra-org only).

**Trust model.** Fully open. The registry is allowlist (publishers must register) but data is take-it-or-leave-it; consumers re-weight by source.

**Steal:** **The prefix-your-IDs identifier scheme.** For Lighthouse, if every federated publisher's location ID is `<publisher-fano-id>-<their-uuid>`, you get global uniqueness for free, no central registrar of UUIDs, and the prefix tells you who's authoritative. Also steal **registry-as-metadata-only**: a tiny CKAN-shaped registry of "who publishes HSDS at what URL, last harvested when" is achievable in a weekend; trying to be a federated *data* registry takes years.

**Avoid:** XML at a static URL with no incremental semantics scales poorly — IATI files routinely hit hundreds of MB and harvesters re-download the world daily. Don't repeat that mistake; pair the registry pattern with FHIR-style `_since`.

Sources:
- [IATI Registry overview](https://iatistandard.org/en/iati-tools-and-resources/iati-registry/)
- [IATI activity identifier rules](https://iatistandard.org/en/iati-standard/202/activity-standard/iati-activities/iati-activity/iati-identifier/)
- [How to link donor activities to implementing partner activities](https://www.iaticonnect.org/discussion/how-link-donor-activities-implementing-partner-activities)

---

## 4. AT Protocol (Bluesky)

**What it is, who runs it, scale.** Bluesky's federation protocol, deliberately designed as a critique of ActivityPub. ~30M users at deployment scale. Three roles: **PDS** (Personal Data Server — hosts a user's signed repo), **Relay** (firehose aggregator that crawls PDSes), **App View** (reads from relays, renders product). The relay is structurally a CDN for the social graph; it does not own data.

**Identity model.** **DIDs (Decentralized Identifiers) — `did:plc` (Bluesky's hosted ledger) or `did:web` (DNS-hosted).** Each DID document publishes a signing key and a recovery key. The signing key lives with the PDS; the recovery key is held by the user as a backup. Account portability is achieved by updating the DID document to point at a new PDS — followers don't notice. This is **the single best identity primitive in the entire decentralized-data space.**

**Update propagation.** Push: every PDS streams signed commits to relays via firehose websocket; relays fan out to App Views. Repos are Merkle Search Trees, so any consumer can verify a record was signed by the DID's current key without trusting the PDS or relay.

**Conflict resolution.** Each record is authored by exactly one DID; no conflict by construction. There is no model for "two parties asserting facts about the same external entity" — every record is a first-party statement. This is the structural limitation for HSDS use.

**Trust model.** Open. Anyone can run a PDS, relay, or App View. App Views apply their own moderation labels.

**Lexicons.** Typed JSON schemas, namespaced via reverse DNS (e.g., `org.openreferral.location`), with open unions for extensibility. Paul Frazee's [blog post explicitly rejects RDF](https://www.pfrazee.com/blog/why-not-rdf) for being verbose and developer-hostile; lexicons are deliberately TypeScript-shaped. Versioning is acknowledged as unsolved.

**Steal:** **DIDs for publisher identity.** A food bank could be `did:web:foodbank.org` — their TXT record proves they own the identity, their signed records prove provenance, and if they migrate hosting providers their identity moves with them. Also steal the **firehose + relay + app-view separation**: PPR is structurally already a relay (aggregator) + app-view (API); making the "PDS" role explicit (each publisher owns their signed feed) is a clean refactor.

**Avoid:** The single-author rule. HSDS data is fundamentally multi-author (a pantry's existence is asserted by the pantry, the food bank, the 211, and the volunteer scraper). Don't force a single-DID-per-record model — IATI's "everyone publishes their view, consumer reconciles" is the better fit.

Sources:
- [AT Protocol federation architecture](https://docs.bsky.app/docs/advanced-guides/federation-architecture)
- [Account migration spec](https://atproto.com/guides/account-migration)
- [Why not RDF — Paul Frazee](https://www.pfrazee.com/blog/why-not-rdf)
- [Bluesky and AT Protocol academic analysis (arXiv)](https://arxiv.org/html/2402.03239v2)

---

## 5. OpenStreetMap diff/changeset model

**What it is, who runs it, scale.** OSM is *centralized* (single Rails app, single Postgres at openstreetmap.org) but publishes its mutation log as a public replication stream at three cadences: **minutely, hourly, daily**. Sequence numbers in nine-digit hierarchical paths (`AAA/BBB/CCC.osc.gz`); `state.txt` files publish the current sequence + timestamp. Hundreds of downstream consumers (Mapbox, Overpass, every routing engine) hold full local replicas synced via these diffs. **This is the most battle-tested "changes feed" pattern in the OSS world.**

**Identity model.** Centralized integer IDs assigned by the master. Not federated.

**Update propagation.** Pull, with explicit sequence numbers. Consumer reads `state.txt`, fetches diff files in order, applies to local DB. "Augmented diffs" (adiffs) include both pre- and post-images plus indirectly-modified entities — strictly better than FHIR's "only changed resources" because it solves cascading-update queries.

**Conflict resolution.** Single master, optimistic concurrency on changeset upload. No federation conflicts.

**Trust model.** Open writes (anyone with an OSM account), gated by community moderation (DWG, OSMCha).

**Steal:** **Three-tier replication cadence with explicit sequence numbers in state files.** PPR could publish `/replication/minutely/state.txt` + numbered `.ndjson.gz` files of HSDS deltas — a downstream consumer (Lighthouse partner, 211 system, FANO member) just reads state.txt, fetches sequence files in order, and never has to coordinate. The sequence-number watermark is **strictly more reliable than a timestamp `_since`** because it survives clock skew and handles ordering of within-second events. Also steal **augmented diffs** (pre+post images) for any record-level updates so consumers can audit changes locally.

**Avoid:** Centralized master DB. OSM works because there's one truth; HSDS has many.

Sources:
- [Planet.osm/diffs](https://wiki.openstreetmap.org/wiki/Planet.osm/diffs)
- [Osmosis/Replication](https://wiki.openstreetmap.org/wiki/Osmosis/Replication)
- [OSMCha augmented diff service](https://github.com/OSMCha/osm-adiff-service)

---

## 6. Briefer notes on the rest

**Solid (Tim Berners-Lee).** Pods + WebID + linked-data RDF. Real deployments exist (Inrupt, Flanders Solid project, NHS pilots) but adoption is thin and the RDF/JSON-LD tax is real. Relevance to HSDS is conceptual ("each food bank owns its pod") but RDF tooling is hostile to the existing HSDS-JSON ecosystem; AT Protocol's lexicon approach is a strictly better fit. **Skip.**

**W3C Verifiable Credentials + DIDs.** Mature spec, real deployments (EBSI in EU, NACS TruAge, Microsoft Entra Verified ID). **Highly relevant for a specific narrow use case:** Feeding America could issue a VC to each member food bank stating "this entity is a FANO member as of <date>"; the food bank attaches the VC to its HSDS publication; aggregators verify the FA signature without calling FA. This decouples FANO membership verification from PPR's allowlist TSV (which currently has to be manually maintained). **Steal:** the issuer/holder/verifier triangle for FANO affiliation claims.

**Nostr.** Relay-based, every event signed by author keypair, no instance affinity (your event lives on every relay you push to). Genuinely the most "no lock-in" decentralized protocol. **Probably too anarchic for HSDS** — the lack of any moderation hooks at protocol level means spam/malicious-data resistance is purely social, which doesn't match the care needed around food access for vulnerable populations. But the **"any consumer can run a relay, identity is pure keypair, no enrollment"** pattern is worth understanding as the extreme end of the design space.

**CKAN harvester + DCAT.** This is what IATI's registry runs on, what data.gov runs on, what publidata.eu uses to federate 18 European catalogues. DCAT (W3C Data Catalog Vocabulary, v3 as of 2026) is the metadata schema; CKAN's harvester is the implementation. **Highly transferable:** PPR's existing scraper architecture is structurally a CKAN harvester — same pattern of "go fetch from N publishers, normalize, dedup." A DCAT catalog feed describing what PPR publishes (and what each scraper-source publishes upstream) is essentially free to add.

**NIEM / Open211.** NIEM is XML-heavy DOJ/DHS interagency exchange — overengineered for our scale and largely abandoned outside specific compliance domains. Open211 was a 2010s 211-industry attempt that essentially became HSDS. **No usable pattern here that HSDS doesn't already have.**

---

## Synthesis

### Pattern matrix

| Protocol | Identity | Transport | Auth | Trust | Conflict resolution | Portability |
|---|---|---|---|---|---|---|
| HSDS | Per-publisher UUID | JSON pull (API or bulk) | None / consumer choice | Open | Aggregator-side | None |
| FHIR Bulk | `identifier[]` (system+value) | Async kickoff → NDJSON manifest, `_since` watermark | SMART JWT, mTLS | Allowlist | `meta.source` + authoritative system | Resource-level via `identifier` |
| IATI | `<publisher-ref>-<internal-id>` prefix | XML at stable URL, registry index | None | Registry-gated publishers, open consumers | Cross-references via `provider-activity-id` | None |
| AT Protocol | DID (did:plc / did:web) | Signed Merkle repo, firehose websocket | DID-key signatures | Open | Single-author per record | First-class (DID portability) |
| OSM diffs | Centralized integer IDs | Sequence-numbered NDJSON-shaped diffs, `state.txt` | API key (writes) | Open writes, community moderation | Master DB, optimistic locking | N/A |
| Solid | WebID URI | RDF over HTTP | OIDC | Per-pod ACLs | RDF graph merge | Pod-level |
| VC/DID | DID | Any | Cryptographic signature | Issuer reputation | N/A | First-class |
| Nostr | Pure pubkey | Relay websocket, signed events | Keypair signatures | Open | Last-write-wins per author | Trivial |
| CKAN/DCAT | Per-catalog | DCAT RDF/JSON-LD harvest | None | Open | Aggregator-side | None |

### Top 3 protocols that should most influence Lighthouse federation

**1. FHIR Bulk Data Access (`$export?_since`).** The closest production analogue to what HSDS should be. The async-kickoff-NDJSON-manifest pattern is correct, the `_since` watermark is correct, the `identifier[]` array with `system`+`value` is exactly the model PPR's `location_source` already wants to expose. Implementing an HSDS `$export?_since=<transactionTime>` endpoint that returns NDJSON of changed records, with a manifest URL and async polling, is the single highest-leverage federation primitive PPR could ship. VhDir is the existence proof that this works for a directory of organizations/locations/services.

**2. IATI's prefix-your-IDs + registry-as-metadata-only.** Solves the global-uniqueness problem without a central UUID authority. Each federated HSDS publisher gets a short prefix (FANO member code, ISO country code, or similar) and their location IDs become `<prefix>-<their-uuid>`. The PPR registry becomes a thin catalog of "who publishes HSDS at what URL with what prefix" — easy to build, easy for partners to audit, no central database of records. Combined with FHIR-style incremental export, you get IATI's federation model without IATI's bulk-XML pain.

**3. AT Protocol's DIDs for publisher identity + OSM's replication sequence numbers.** Together these give you (a) cryptographic, portable, host-independent publisher identity (a food bank is `did:web:foodbank.org` and proves it via DNS), and (b) a battle-tested replication-stream wire format that's strictly better than timestamp watermarks. The combination is what an HSDS-3.x federation profile *should* look like.

### Top 3 anti-patterns to deliberately avoid

**1. Single-authoritative-author per record (AT Protocol's structural limit, Nostr's entire model).** HSDS data is irreducibly multi-source: a pantry's existence is asserted by the pantry, the food bank, the 211, and the scraper. PPR already gets this right with `location_source` and confidence scoring; don't regress by adopting a federation model that forces single authorship.

**2. RDF/JSON-LD as the wire format (Solid, DCAT in its purest form).** The Open Referral community already rejected RDF in v3 by moving to plain JSON. Paul Frazee's argument applies directly: developer hostility kills adoption, and federation that nobody implements is no federation. Keep HSDS-JSON as the wire format and let CKAN/DCAT integrations be optional metadata-layer adapters, not the core protocol.

**3. Full-file daily re-download with no incremental semantics (IATI, naive CKAN harvest, current HAARRRvest SQLite publication).** It works at small scale and falls over at the scale of "every 211 in the US plus every FA member bank." The cost is paid in bandwidth, in aggregator complexity, and in the staleness window. Pair any bulk publication with sequence-numbered incremental diffs from day one; retrofitting it later is much harder.

---

*Word count: ~2,400. Saved to `/tmp/federation-research/adjacent-protocols-report.md`.*
