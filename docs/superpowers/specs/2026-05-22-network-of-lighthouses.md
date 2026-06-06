# Network of Lighthouses — A Federation Design for HSDS Directory Data

**Status**: research synthesis / design brief. Not a plan, not in scope for any current ticket.
**Date**: 2026-05-22
**Supersedes**: the "Federation Evolution Path" appendix in [`2026-03-25-lighthouse-design.md`](2026-03-25-lighthouse-design.md). That appendix sketched stages 0–5 in prose; this document picks the protocol primitives and writes the wire-level spec.

---

## Why this exists

The lighthouse-design doc named OPR and ActivityPub as inspiration and reserved three schema fields (`feed_url`, `push_enabled`, `org_api_key`) on `OutreachConfig` for a future federation. It deliberately did not say what federation actually *is* at the protocol level. This doc is the technical investigation that the appendix deferred.

The question the lighthouse tenets force (Tenet 7: "we invite everyone to federate") and the Lighthouse PRFAQ promises ("the barrier is the lowest we can make it") needs a real answer before we ship Stages 1–5. The promise we made — *"take the public HSDS feed, send your updates back, you're federated. No agreement, no platform migration, no fee."* — has to map onto a concrete protocol that:

1. Identifies federated peers without a central registry
2. Lets multiple parties verify the same Location (multi-source corroboration, not single-author)
3. Stays small enough that a Vivery / FreshTrak / county GIS / 211 node could implement it in days, not months
4. Survives one peer going rogue without taking the network down
5. Does not require us to host or vouch for anyone else's data
6. Composes with the existing PPR primitives — HSDS, `confidence_score`/`verified_by`, `caller_context`, `change_audit`/`location_source`, `/api/v1/partners/ptf/*`, Beacon, Lighthouse — rather than replacing them

This doc proposes one such protocol, named **the Network of Lighthouses**, built from picked pieces of four prior traditions.

## The three research artifacts behind this synthesis

Full reports live alongside this doc; read them first if any of the conclusions below look unmotivated.

- [`../research/2026-05-22-federation/opr-report.md`](../research/2026-05-22-federation/opr-report.md) — Google/CaravanStudios Open Product Recovery. Cloned at SHA `0eeb4afa…`; project is effectively frozen since Nov 2022. Two genuinely portable ideas (URL-as-identity-with-JWKS, SNAPSHOT/DIFF watermarked sync). The `accept`/`reserve`/`reject` lifecycle is a category error for directory data and should be replaced with verify/claim/dispute verbs.
- [`../research/2026-05-22-federation/activitypub-report.md`](../research/2026-05-22-federation/activitypub-report.md) — W3C ActivityPub, Mastodon implementation, FEPs. Authoritative-source rule, HTTP Signatures (Cavage), WebFinger + NodeInfo, Group actors (FEP-1b12), Tombstones. The single biggest design tension: AP assumes one writer per object, but HSDS data is *irreducibly multi-source*. Solution: pair an origin-only `Update` channel with an open `Announce` channel that feeds the existing multi-source confidence bonus.
- [`../research/2026-05-22-federation/adjacent-protocols-report.md`](../research/2026-05-22-federation/adjacent-protocols-report.md) — FHIR Bulk, IATI, AT Protocol, OSM diffs, W3C VCs/DIDs, HSDS Profiles. FHIR Bulk `$export?_since` is the closest production analogue to HSDS federation (VhDir is the existence proof). IATI's prefix-your-IDs gives global uniqueness without a central registrar. AT's `did:web` gives DNS-verified portable identity. OSM's `state.txt` + sequence numbers strictly beat timestamp `_since` for incremental sync.

---

## Core insight: directory federation is not social federation

Every protocol surveyed is, structurally, one of three things:

- **Transactional offer exchange** (OPR, retail inventory): time-bound resource, single owner who transfers responsibility. Accept/Reserve/Reject lifecycle.
- **Social messaging** (ActivityPub, Nostr, Bluesky): single author per object, follower-driven fan-out, last-write-wins.
- **Reference-data exchange** (FHIR Bulk + VhDir, IATI, OSM diffs, CKAN/DCAT): slowly-changing facts about real-world entities, multiple authorities asserting their own identifiers and values for the same logical thing.

PPR + Lighthouse + Beacon is the third kind. We are not Mastodon-for-food-banks. We are FHIR-for-public-charitable-food.

This means three structural decisions are settled before we start picking primitives:

1. **The unit of identity is the Organization, not the User.** A 211 node is an actor; a volunteer at a 211 node is not.
2. **The unit of content is the HSDS resource (`Location`, `Service`, `Organization`, `Schedule`)**, not the post. These are slowly-changing reference data; the entire wire shape should optimize for incremental sync, not real-time fan-out.
3. **Multiple actors will assert facts about the same Location simultaneously**, and that is a feature. The protocol has to carry both *authoritative* updates ("I, North Jersey Food Bank, set our hours to X") and *corroborating* assertions ("I, 211 NJ, independently verified those hours on 2026-05-20"). Treating either as the only mechanism breaks the model.

---

## The architecture in one paragraph

A Lighthouse is a node. It has a stable identity (`did:web:&lt;domain&gt;` or, for non-DID-capable peers, an org-description-URL à la OPR). It publishes a discovery document at `/.well-known/lighthouse`, an org actor at a canonical URL, and an HSDS-typed activity stream of `Update(Location)`, `Announce(Location)`, `Delete(Location)`, and `Flag(Location)` activities. Peers read each other's streams in two modes: a **bulk path** (`GET /federation/export?_since=&lt;seq&gt;` returning NDJSON of HSDS changes since a sequence-numbered watermark — FHIR Bulk + OSM diff stream patterns combined) and a **push path** (signed-body webhook POST to `/federation/inbox` — the thing OPR specced but never shipped). Trust is **explicit allow-list per node** (OPR pattern, deliberate inversion of Mastodon default); membership in trust circles is signaled by **Verifiable Credentials** issued out-of-band by network authorities (Feeding America for FANO; Open Referral for HSDS profile conformance). Discovery is **mention-driven**, not registry-driven — you find a peer by reading a Location whose `attributedTo` you want to follow up on, or by being invited into someone's allow-list. There is no central directory and no node is special, including ours.

---

## Twelve decisions

Each decision lists the alternative it picks against, the rationale, and the existing PPR primitive it composes with.

### 1. Identity: `did:web:&lt;domain&gt;` first, org-URL fallback

A federated org is identified by a DID. Default method is `did:web` — `did:web:northjerseyfoodbank.org` resolves to `https://northjerseyfoodbank.org/.well-known/did.json`, which contains the org's signing public keys and an `alsoKnownAs` array pointing at the canonical org actor URL (`https://northjerseyfoodbank.org/lighthouse/org`).

**Alternative considered**: OPR's "org URL is the ID, fetch JWKS at `&lt;orgURL&gt;.jwksURL`". Functionally equivalent for routing, but DIDs win on **portability**: an org that moves from `wix-hosted-site.com` to a self-hosted domain can rotate the DID's `service` endpoint without breaking every cached reference to its locations. Pragmatic compromise: every Lighthouse implementation MUST accept both DIDs and raw HTTPS URLs as actor identifiers; resolution treats `https://…` and `did:web:…/path` as the same thing under the hood.

**Composes with**: `OutreachConfig.org_api_key` becomes `OutreachConfig.org_did`. `caller_context.source_type` gains a value `federated_node` distinct from `scraper`/`submarine`/`admin`.

### 2. Discovery: WebFinger + `.well-known/lighthouse`, no registry

`/.well-known/lighthouse` is a single JSON document advertising: DID, JWKS URL, supported HSDS version, activity-stream endpoint, federation-inbox endpoint, federation-export endpoint, allow-list policy (open / mutual / private), retention SLA, contact email, FA membership VC ID if applicable.

WebFinger (`/.well-known/webfinger?resource=acct:&lt;slug&gt;@&lt;domain&gt;`) returns the org actor URL for human-friendly references like `acct:north-jersey-fb@plentiful.org`.

Crucially, **there is no central registry of Lighthouses.** Peers find each other three ways: (a) by being mentioned as `attributedTo` on a Location they fetch, (b) by being invited via out-of-band channel into a peer's allow-list, (c) optionally by being aggregated in HAARRRvest's "peers we know about" catalog (which is *informational, not normative* — every node decides who it talks to).

**Alternative considered**: a central PPR-hosted registry (IATI pattern). Rejected: violates Tenet 7's "we replace nobody" — the moment we run the registry, we are the network, which is what we just said we aren't. The CKAN-style catalog idea is fine as an optional convenience; it is not the source of truth.

**Composes with**: Beacon static site already serves arbitrary `.well-known/*` files via CloudFront. Adding `/.well-known/lighthouse` and `/.well-known/webfinger` is a config change, not a service.

### 3. ID scheme: IATI-style publisher-prefixed UUIDs

Every HSDS Location ID published into the federation MUST be of the form `&lt;publisher-prefix&gt;:&lt;publisher-internal-id&gt;` where `publisher-prefix` is the DID method-specific identifier (e.g. `northjerseyfoodbank.org`) or an assigned short-prefix (e.g. `FA-CFB-NJ`). Internal IDs may be UUIDs, ULIDs, integers — publisher's choice.

This solves the perennial HSDS pain (UUID collisions across publishers, no global identity) at the cost of one rule: prefix your IDs.

**Composes with**: PPR's existing UUID-based `location.id` keeps working internally. The federation wire-format introduces `location.federation_id` derived as `&lt;ppr-did&gt;:&lt;location.id&gt;` for outbound, and incoming federation IDs become rows in `location_source` (one row per `(location.id, federated_id)` pair, with `source_type='federated_node'` and the publisher DID).

### 4. Activity vocabulary: HSDS-typed, not Note-typed

Six activity verbs, all carrying an HSDS resource as `object`:

| Verb | Direction | Authorization | Effect on receiver |
|---|---|---|---|
| `Update` | origin → peers | only `attributedTo` may issue | **Authoritative replace** of receiver's copy of that Location; bumps `last_modified`. `verified_by` = `source` if the publisher is the canonical owner. |
| `Announce` | any verified peer → peers | publisher in receiver's allow-list | **Corroboration** of an existing Location from another publisher's stream. Recorded as a row in `location_source`, contributes to the existing multi-source confidence bonus (+5 for 2 sources, +10 for 3+). Does **not** overwrite fields. |
| `Delete` | origin → peers | only `attributedTo` | Tombstone — sets `is_active=false`, retains `change_audit` row. Receiver MAY keep showing the Location as historically-existed. |
| `Flag` | any peer → origin (private) | open | Asynchronous bug report. Maps to the existing Lighthouse claim/dispute queue. No side effect on the public stream. |
| `Verify` | any verified peer → peers | publisher in allow-list, presents VC | "I have a VC from Feeding America asserting this Location is a FANO member, valid through 2027-01." Treated as a special corroboration that bumps `verified_by` (currently `auto`/`source`/`admin`/`claimed`; add `network`). |
| `Move` | origin → peers | only `attributedTo`, paired with `alsoKnownAs` on new actor | Account migration. Peers retire follows of old actor, follow new actor, do not re-fetch old Locations. |

**Alternative considered**: copying ActivityPub's full Note vocabulary plus `Create`/`Add`/`Remove`. Rejected: `Create` is implicit in `Update` for a resource that doesn't exist yet on the receiver. `Add`/`Remove` only matter for collections; we don't model collections at the wire level — Regions (see decision 8) are query-time aggregations.

**Composes with**: `caller_context.source_type` already distinguishes how data arrived. Add `federated_update`, `federated_announce`, `federated_verify`, `federated_flag` as values. `change_audit` already records who-changed-what-when; federation activities are just rows in `change_audit` whose actor is a DID instead of a Cognito sub.

### 5. The bulk read path: `GET /federation/export?_since=&lt;seq&gt;`

Steals directly from FHIR Bulk Data + OSM diffs:

```
GET /federation/export?_since=4729&_type=Location,Service&format=ndjson
  → 200 OK
  Content-Type: application/x-ndjson
  X-Federation-Sequence: 4901
  X-Federation-Retention: 90d

  {"activity":"Update","sequence":4730,"object":{…HSDS Location…}, …}
  {"activity":"Update","sequence":4731,"object":{…}, …}
  {"activity":"Delete","sequence":4732,"object":{"id":"…","type":"Tombstone"}}
  …

GET /federation/state.txt
  → 200 OK
  sequence: 4901
  timestamp: 2026-05-22T18:33:11Z
  retention_horizon_sequence: 3201
```

`_since=0` returns a full snapshot; `_since=&lt;N&gt;` returns everything since sequence `N`. If `N &lt; retention_horizon_sequence`, server responds 410 Gone — the consumer must do a fresh snapshot.

**Sequence numbers, not timestamps**, because clocks drift, within-second ordering matters, and OSM has proven the pattern at scale for 15+ years. **NDJSON, not JSON arrays**, because consumers stream-parse without holding the whole response in memory.

**Alternative considered**: OPR's SNAPSHOT/DIFF with RFC 6902 JSON Patch. JSON Patch is great for in-place mutation of a known document; it is the wrong shape for "here are the records that changed" because the receiver does not necessarily have the prior version. Wholesale replacement per record is simpler and matches FHIR Bulk.

**Composes with**: HAARRRvest already publishes a daily SQLite snapshot. Adding a `/federation/export` endpoint on the Lambda API is the same data, served incrementally with sequence numbers. The publisher Lambda writes `(sequence, activity, object_json)` rows to a new `federation_log` table on each reconciler commit.

### 6. The push path: signed-body webhooks (the thing OPR didn't ship)

```
POST /federation/inbox
Content-Type: application/activity+json
Signature: keyId="did:web:northjerseyfoodbank.org#main-key",
           algorithm="ed25519",
           headers="(request-target) host date digest",
           signature="…"
Digest: SHA-256=…

{
  "@context": "https://hsds.openreferral.org/3.1.1",
  "type": "Update",
  "actor": "did:web:northjerseyfoodbank.org",
  "object": { … HSDS Location, federation_id: "northjerseyfoodbank.org:abc-123" },
  "published": "2026-05-22T18:33:11Z",
  "sequence": 4730
}
```

Receiver verifies HTTP Signature (decision 7), checks `actor` matches its allow-list, checks `actor` matches `object.attributedTo` for `Update`/`Delete`, processes the activity, returns `202 Accepted` with `Location:` header pointing at the receiver's eventual representation.

**Polling is the fallback**, not the default. Peers in active mutual federation use webhooks; peers we only consume from (county GIS that publishes a feed but won't accept our webhooks) get polled.

**Alternative considered**: OPR's "polling only" plus a vaporware `pushChanges`. Rejected on the OPR report's own evidence — polling at 10-minute cadence is wrong both directions (too slow for "this pantry closed permanently," too aggressive when nothing changed).

**Composes with**: existing `ppr-ptf-sync` is already a webhook-style outbound push (to Plentiful's `/api/v0-broker/organizations/upsert`). The patterns generalize. Inbound `/federation/inbox` is a new Lambda; idempotency comes for free from `(actor, sequence)` deduplication in a state ledger that copies `ptf_broker_sync_state`'s design.

### 7. Auth: HTTP Signatures (Cavage), Ed25519, mandatory on POST

Every POST to `/federation/inbox` MUST carry a `Signature:` header covering `(request-target) host date digest`. `Digest:` is `SHA-256=base64(sha256(body))`. The `keyId` is a DID URL or actor-URL fragment; receiver resolves the DID document or actor doc, extracts the public key, verifies.

Ed25519 only — RSA-2048 is a 2010s legacy choice and the fediverse is paying for it. New protocol, new keys.

**Alternative considered**: bearer JWTs (OPR pattern), API keys (current PPR pattern for Write API). JWTs add issuer/audience claims we don't need (the URL is the audience; the HTTP Signature covers it). API keys force a shared-secret distribution problem we already know is painful (see PTF broker credentials). HTTP Signatures + JWKS-from-DID is the minimum thing that works.

**Optional**: Linked-Data Signatures (a.k.a. FEP-8b32 Object Integrity Proofs) on the activity body, separate from the HTTP Signature on the transport, for the relay-forwarding case (decision 9). Not required in v1; pencil in for v2.

**Composes with**: `app/api/v1/partners/ptf/*` already uses Basic auth — that's fine for the bilateral Plentiful relationship. Federation is a wider network and needs the asymmetric-crypto story from day one.

### 8. Regions as Group actors (FEP-1b12)

A Lighthouse MAY publish Region actors keyed on geography: `acct:zip-07030@plentiful.org`, `acct:county-essex-nj@plentiful.org`, `acct:h3-cell-8a283082@plentiful.org`. A peer `Follow`s a Region; the Region's owner re-`Announce`s every member Location's `Update` (with the original publisher's LD signature intact, so the consumer trusts the origin not the relay).

This is how Vivery / FreshTrak / a 211 node subscribes to "everything in our service area" with one Follow, instead of N follows of N member orgs.

HAARRRvest naturally becomes **the universal Region actor** — a Group that re-Announces every public activity from every consenting publisher. Small Lighthouses that don't want to maintain their own peer mesh can Follow HAARRRvest and call it done.

**Alternative considered**: subscriber-side filtering — every consumer pulls every publisher's full stream and filters locally. Doesn't scale once we have more than ~20 active publishers; pushes the cost onto consumers.

**Composes with**: PPR already has bounded-box queries on `/api/v1/partners/ptf/locations` (`lat1/lng1/lat2/lng2`). Region actors are the federation-visible projection of those queries.

### 9. Trust: allow-list default, VCs for membership signals

**Default federation policy: allow-list.** A Lighthouse explicitly enumerates the DIDs it accepts `Update`/`Announce`/`Verify`/`Flag` from. Constitution Principle VI (data quality for vulnerable populations) trumps network effects; one bad-actor `Update` (fake address, scam phone, deliberate misinformation) is catastrophic.

**Allow-list entries are durable.** They survive key rotation (the DID document changes, not the DID). Removing an entry is instantaneous.

**Membership in well-known trust circles is signaled by Verifiable Credentials.** Feeding America issues a VC to each FANO member; the bank attaches the VC to its `/.well-known/lighthouse` document; PPR (and any other consumer) verifies FA's signature on the VC without needing to call FA. This is the replacement for `app/api/v1/partners/ptf/fano_allowlist.tsv` — instead of PPR maintaining a manual list, FA's signature on a VC is the source of truth.

Other VCs likely useful:

- Open Referral conformance ("this publisher emits HSDS 3.1.1, profile X")
- 211 network membership (signed by United Way)
- State / county recognition ("registered nonprofit food provider in NJ")

**Alternative considered**: open-federation-by-default with a Fediblock-style shared blocklist. Rejected for the data-quality reason above, plus Fediblock has never landed at the protocol level after 8 years of trying.

**Composes with**: the existing FANO allowlist TSV becomes a generated artifact from FA-issued VCs. The Lighthouse admin UI gains a "trusted peers" page (decision 12).

### 10. Conflict resolution: PPR's existing confidence model, no new logic

This is the design's most important reuse. We do not invent CRDTs, vector clocks, or last-writer-wins. We use what we already have:

- **Origin `Update`**: writes the canonical fields. `verified_by` set to `source` if the publisher is the location's `attributedTo` (else `auto`).
- **Peer `Announce`**: adds a row to `location_source` (`source_type='federated_node'`, the publisher DID, the corroborated fields hash). Confidence scoring picks up the multi-source bonus on the next reconciler pass.
- **VC-backed `Verify`**: bumps `verified_by` to `network` (a new tier between `source` and `admin`) when the VC is valid.
- **Conflict between two origin Updates** (e.g. two publishers both claim `attributedTo` for the same logical location): treated as a data-quality flag. Reconciler emits `federation_conflicting_attribution` structlog event, falls back to existing dedup heuristics, lower-confidence side gets demoted.

**The model is: every assertion is a row, confidence aggregates rows, no row is destroyed.** This is already how PPR works internally; federation just adds one more `source_type`.

### 11. Audit: history endpoint with retention SLA

```
GET /federation/history/{federation_id}?_since=<timestamp>
  → 200 OK
  { "activities": [
      { "type":"Update", "actor":"did:web:…", "published":"…", "sequence":… },
      { "type":"Announce", "actor":"did:web:…", "published":"…", "sequence":… },
      …
    ]
  }
```

Per-location activity history, retention horizon advertised in `/.well-known/lighthouse`. PPR's default: 1 year (OPR's recommended SLA).

This is the single feature that makes the network self-correcting. "Show me every assertion any peer has made about this Location in the past 90 days, who made it, and which were corroborated" is the moderation tool the network lives or dies on.

**Composes with**: `change_audit` and `location_source` already record everything we need. Endpoint is a thin SELECT.

### 12. Onboarding: a peer-add wizard in Lighthouse admin

Federation membership is operationally a five-minute task: an admin pastes a peer DID, the Lighthouse fetches `/.well-known/lighthouse` for that DID, displays the public key fingerprint + advertised retention SLA + VC list + recent activity sample, and asks "approve?". On approve, the DID is added to the allow-list; the peer is notified out-of-band; mutual subscription is exchanged.

This is the protocol-level realization of the Lighthouse PRFAQ promise: *"no agreement to sign, no platform to migrate to, no fee."*

---

## What this doesn't do

To be specific about the things we are deliberately not building:

- **No central registry.** No `directory.lighthouse.network`. Discovery is mention-driven and allow-list-driven.
- **No JSON-LD context expansion.** `@context` is a version tag. Documents are validated by Pydantic against HSDS schema, not by JSON-LD processors. (Fediverse spent 8 years discovering remote-context-expansion is a security hole; we skip the lesson.)
- **No client-to-server protocol.** Humans use the existing PPR REST API, Write API, and Lighthouse UI. Federation is server-to-server only. (Mastodon C2S adoption failure is the cautionary tale.)
- **No transactional offer lifecycle.** No `accept`/`reserve`/`reject`. We are not OPR; we don't move surplus goods.
- **No single-author-per-record rule.** AT Protocol's structural limit doesn't fit; multiple parties verifying the same Location is a feature, not a conflict.
- **No real-time fan-out optimization.** Most orgs have ~10–100 peers. We don't need shared-inbox tricks until we have ten thousand.
- **No reshare-chain JWTs re-signed per poll.** OPR's design is cryptographically clever and operationally expensive at directory scale. We use batch-signed daily attestations if cross-network provenance ever becomes a hot path.

---

## Migration from where we are today

The existing lighthouse-design appendix lists stages 0–5. Here is the same trajectory restated in protocol-primitive terms, with concrete prerequisites:

| Stage | Trigger | Primitives needed | PPR work |
|---|---|---|---|
| **0** (now) | Lighthouse outreach + portal | None of this doc. `OutreachConfig.{feed_url, push_enabled, org_did}` reserved fields. | already shipping |
| **1: Discovery** | First external party asks "how do I follow you?" | `/.well-known/lighthouse`, `/.well-known/webfinger`, `did.json`, public actor URL | Beacon serves three new static files; PPR Lambda emits actor JSON |
| **2: Bulk read** | Partner says "I want incremental sync, not your nightly SQLite" | `/federation/export?_since=&lt;seq&gt;`, `/federation/state.txt`, sequence-numbered NDJSON, `federation_log` table | new Lambda endpoint, reconciler writes log rows |
| **3: VC-based trust** | FA willing to issue a FANO membership VC | VC verification at FANO gate, `network` tier added to `verified_by` | replaces `fano_allowlist.tsv` over time |
| **4: Push** | A high-frequency publisher (Vivery, a state SNAP outreach team) wants real-time | `/federation/inbox` with HTTP Signatures, signed-body webhook send, idempotency ledger (`federation_inbox_state`) | new Lambda, copies `ppr-ptf-sync` patterns |
| **5: Group actors** | Aggregator (211 node, a regional FB) wants "everything in our area" | Region actor JSON, `Follow`/`Announce` semantics, FEP-1b12 group federation | HAARRRvest becomes the universal Group actor first; geographic Groups follow |
| **6: Mutual federation** | Second Lighthouse exists somewhere | allow-list UI, peer-add wizard, mutual subscription | Lighthouse admin work |

Each stage is independently useful. Stages 1 and 2 ship something we have anyway in a federation-shaped wrapper. Stages 3–5 require external buy-in (FA, Vivery, a partner aggregator) and should not be pre-built. Stage 6 only happens once a second node exists, which is the entire point.

---

## What we're stealing from each tradition

For the record, so future contributors don't relitigate the choices:

**From OPR**: URL-as-identity-with-JWKS pattern (generalized to DIDs). The history endpoint with retention SLA. JSON Schema as canonical spec with generated TS/Pydantic types. The peer-ACL trust model. Sequence-numbered watermarked sync (with corrections — see OSM).

**Not from OPR**: accept/reserve/reject lifecycle, per-poll reshare-chain re-signing, polling-only with vaporware push.

**From ActivityPub**: HTTP Signatures (Cavage flavour) on POST. WebFinger discovery (`acct:` URIs). NodeInfo for server-level metadata. Group actors / FEP-1b12 for region subscription. Tombstone for delete. Move activity for portability. Authoritative-source rule for `Update`/`Delete` authorization.

**Not from ActivityPub**: JSON-LD context expansion, C2S protocol, single-author-per-record rule, open-federation default, O(followers) fan-out, RsaSignature2017 / RSA generally.

**From FHIR Bulk + VhDir**: `$export?_since=<watermark>` async kickoff pattern (simplified to sync NDJSON for our scale). `identifier[]` with `system`+`value` for multiple authorities on one entity. Reference-data federation as a deployed reality.

**Not from FHIR**: SMART Backend Services / mTLS / OAuth client credentials (overkill for public charitable-food data). The full FHIR resource model (we already have HSDS).

**From IATI**: `<publisher-prefix>-<internal-id>` global uniqueness scheme. Registry-as-metadata-only philosophy.

**Not from IATI**: static-XML-no-incremental-semantics; cross-activity provider/receiver references (we have one logical entity per Location, not two perspectives on a transaction).

**From AT Protocol**: `did:web` for portable, hosting-independent publisher identity. The structural separation of "where the data is signed" (origin) from "where the data is rendered" (consumer) — PPR is already structurally a relay+app-view.

**Not from AT Protocol**: `did:plc` (we don't need a hosted ledger), Merkle Search Trees on the wire, single-author-per-record.

**From OSM**: `state.txt` + sequence-numbered NDJSON diffs at multiple cadences. Augmented diffs (pre+post images) for local audit.

**Not from OSM**: centralized master DB.

**From W3C VCs**: out-of-band trust signals from external authorities (FA, Open Referral, United Way) carried in-band on the wire.

**Not from W3C VCs**: the full DIF/EBSI verifier ecosystem; revocation registries (we lean on short-lived VCs and re-fetching).

**From HSDS**: the entire payload schema and the Profiles mechanism for jurisdictional extension.

---

## Open questions

Things the research deliberately did not resolve and that any "let's actually do this" project would need to answer:

1. **Versioning.** When HSDS goes 3.1.1 → 3.2.0, how do mixed-version peers interoperate? Probably: `Accept: application/hsds+json; version=3.1.1` content-negotiation at every endpoint, with the discovery doc advertising supported versions.
2. **Deletion under GDPR.** AP's Delete is best-effort; reference data isn't PII but a Location's `email`/`phone` could be a sole-proprietor's. Probably: the FANO + Open Referral allowlists cover the common case; high-sensitivity per-field redaction is an unsolved problem and is fine to defer.
3. **Disputes that don't reach consensus.** Two peers disagree on a Location's hours; both have VCs; both have history. Reconciler emits `federation_unresolved_conflict`; admin queue handles it; no protocol-level resolution. Is that enough? Probably yes for v1, revisit if it ever happens.
4. **Spam / DoS on `/federation/inbox`.** Rate limits per allow-listed DID, exponential backoff, suspension on signature-mismatch. Standard hygiene; nothing protocol-specific.
5. **What does a non-PPR Lighthouse look like in practice?** Reference impl in Python (FastAPI Lambda) lives in PPR. A second reference impl in TypeScript (next.js Lambda or a Cloudflare Worker) would prove the wire shape is implementation-independent. ~2 weeks of work if/when a real partner volunteers.
6. **Bridging.** Does the network bridge to existing fediverse software (a Mastodon bot that announces new Locations)? Possible; not required; explicitly out of scope for v1.

---

## Bottom line

We don't need to invent federation for HSDS. Four mature traditions (OPR, ActivityPub, FHIR Bulk, IATI/OSM) have collectively solved every primitive we need. Our job is to **pick the right four pieces, drop the wrong twelve, and write a 30-page spec that a partner aggregator can implement in a week.**

The picks above are opinionated and defensible. The drops are equally important — the cumulative weight of declined complexity (no JSON-LD, no C2S, no RSA, no central registry, no reshare-chain re-signing, no open-federation default, no transactional offer lifecycle) is what keeps the protocol small enough that the Tenet 7 promise — *"the barrier is the lowest we can make it"* — is achievable.

The federation doesn't need to be planned. It emerges from making each stage useful on its own.

---

## See also

- [`2026-03-25-lighthouse-design.md`](2026-03-25-lighthouse-design.md) — Lighthouse design, including the original "Federation Evolution Path" appendix this doc supersedes
- [`../research/2026-05-22-federation/opr-report.md`](../research/2026-05-22-federation/opr-report.md) — OPR technical reference
- [`../research/2026-05-22-federation/activitypub-report.md`](../research/2026-05-22-federation/activitypub-report.md) — ActivityPub / fediverse technical reference
- [`../research/2026-05-22-federation/adjacent-protocols-report.md`](../research/2026-05-22-federation/adjacent-protocols-report.md) — FHIR Bulk, IATI, AT Protocol, OSM, W3C VCs, HSDS Profiles
- `plugins/ppr-lighthouse/docs/tenets.md` — Tenet 7 ("we invite everyone to federate") is the strategic anchor for this design
- `plugins/ppr-ptf-sync/CLAUDE.md` — existing 1-to-1 outbound sync to Plentiful; serves as the implementation precedent for `/federation/inbox` and the per-row state ledger pattern
- `app/api/v1/partners/ptf/` — existing inbound partner endpoint; precedent for the FANO allowlist gate that VC-based trust replaces
