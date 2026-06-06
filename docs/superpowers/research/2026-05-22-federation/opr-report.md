# Open Product Recovery (OPR) — Technical Reference for PPR/Lighthouse Federation

Research target: map OPR's federation design onto a charitable-food **directory** federation (HSDS data — pantry locations, hours, services, verification signals) rather than OPR's native domain of time-bound surplus offers.

---

## 1. Repos & Canonical URLs

The URLs in the original brief (`google/openproductrecovery`, `google/openproductrecovery-protocol`) both 404. The actual canonical repo is:

| Project | URL | Commit SHA read |
|---|---|---|
| OPR monorepo (specs + reference impl) | `https://github.com/google/open-product-recovery` (redirects to `CaravanStudios/open-product-recovery`) | `0eeb4afa5477bb2dad13ace5f6881ccbfa273f28` |

There is **no separate "protocol" repo**. Spec docs live inside the monorepo at `/standards/`. Project is npm-organized under `opr-*` packages (`opr-core`, `opr-models`, `opr-sql-database`, `opr-google-cloud`). Discord: `chat.opr.dev`. Last meaningful spec update: November 2022 (v0.5.2 of Transfer API). Reference implementation has been quiet — the org moved from `google/` to `CaravanStudios/`, suggesting Google handed the project to a smaller maintainer.

Top 5 files to read:

1. `standards/transfer_api.md` (829 lines) — **the protocol spec**. Auth, endpoints, reshare chain, history.
2. `standards/description_format.md` (296 lines) — JSON shape of an Offer/Product/ProductBundle.
3. `components/models/src/offer.schema.json` + sibling `*.schema.json` files — **canonical JSON Schemas**; all payloads validate against these via `Validator.validate()`.
4. `components/core/src/server/oprtenantnode.ts` (540 lines) and `oprserver.ts` (291 lines) — the multi-tenant Express server; one server process, many "tenant nodes" each with its own org URL/keys/ACL.
5. `components/core/src/auth/standardverifier.ts` (214 lines) — the JWT + reshare-chain verifier; the cryptographic heart of the protocol.

---

## 2. Protocol Primitives (with concrete schemas)

### 2.1 Node identity

A node = an **Organization**, identified by an **organization description URL** (`organizationURL`). Quote from `transfer_api.md` §5.3.1:

> "The public URL to an organization's description file uniquely identifies this organization. … Organization identification URLs must be hosted using the https protocol and begin with 'https.'"

There is no `/.well-known/` convention — the URL is *arbitrary*, e.g. `https://albertafoodcharities.org/opr/org.json`. The file is a plain JSON map fetched unauthenticated. Required fields (`transfer_api.md` §5.3.2): `name`, `organizationURL`, plus optional endpoint URLs (`listProductsEndpointURL`, `acceptProductsEndpointURL`, `reserveProductsEndpointURL`, `rejectProductsEndpointURL`, `acceptHistoryEndpointURL`, `pushChangesEndpointURL`), `jwksURL`, `enrollmentURL`, `scopesSupported`.

Note: **the org URL IS the org ID** in every place an ID is needed — `iss`/`aud` claims, ACL entries, reshare-chain `iss`/`sub` fields, `offeredBy` on offers. No DIDs, no UUIDs, no domain-only identifiers. This is a deliberate "PKI-lite via DNS+HTTPS" play.

### 2.2 Actor/Org model

Two roles per request (`transfer_api.md` §5):

- **Offering Organization** — publishes a feed of available offers.
- **Recipient Organization** — reads feeds, can accept/reserve/reject.

Real-world orgs are usually both. A third de-facto role is **Resharing Organization** — an org that re-publishes someone else's offers to its own ACL ("friend of a friend"). The reference impl has a notion of **TenantNode** (one Express process can host many org URLs) and **OfferProducer** (pluggable adapter that pulls offers from inventory systems or from upstream OPR nodes' `listProducts`).

### 2.3 Authentication & signing

**JWT bearer tokens with self-served JWKS.** Quote from §6.2.1.1:

> `Authorization: Bearer <accesstoken>` … The access token must be a Base64 encoded, signed Json Web Token.

Required JWT claims: `iss` = caller's org description URL, `aud` = callee's org description URL, `exp` ≤ 1 hour future. Verification recipe (`standardverifier.ts`):

1. Decode JWT, read `iss`.
2. `fetch(iss)` → org description file.
3. `fetch(orgDesc.jwksURL)` → JWKS public-key set (RFC 7517).
4. Verify signature with `jose`'s `jwtVerify(token, createLocalJWKSet(jwks))`.

This is **self-signed certs over HTTPS** — there is no CA, no central registry of orgs. The DNS/HTTPS PKI substitutes for an OPR-specific PKI. Algorithm is recommended `HS256` (spec text) but reference impl uses RS-* via `jose`. Optional `scope` claim with named scopes: `LISTPRODUCTS`, `ACCEPTPRODUCT`, `PRODUCTHISTORY`, `PUSHCHANGES`. **No mTLS, no HTTP Message Signatures (RFC 9421), no Linked Data Signatures.**

### 2.4 Discovery

**Polling only.** Recipients poll offering organizations' `listProducts` endpoint. Reference impl: `OprFeedProducer` (`components/core/src/offerproducer/oprfeedproducer.ts`) polls every 10 minutes by default and supports incremental `DIFF` format via `diffStartTimestampUTC`. A `pushChanges` endpoint exists in the spec (§6.3.6) but is **explicitly "Additional details TBD" / "TBD"** — not implemented. There is no pub/sub, no webhook framework, no service discovery. Each node statically configures the list of upstream feeds it polls.

### 2.5 Data exchange shape

**Plain REST over POST**, JSON bodies, JSON Schema validation on both request and response. From §6.3:

> "All REST requests must be POST requests."

Required endpoints (all on URLs declared in the org description file, no path conventions enforced):

| Operation | Scope | Request | Response |
|---|---|---|---|
| `listProducts` | LISTPRODUCTS | `{pageToken?, requestedResultFormat?, diffStartTimestampUTC?, maxResultsPerPage?}` | `{responseFormat, resultsTimestampUTC, nextPageToken?, offers? \| diff?}` |
| `acceptProduct` | ACCEPTPRODUCT | `{offerId, ifNotNewerThanTimestampUTC?, reshareChain?}` | `{}` |
| `rejectProduct` | ACCEPTPRODUCT | `{offerId, offeredByUrl}` | `{}` |
| `reserveProduct` | ACCEPTPRODUCT | `{offerId, requestedReservationSecs?, reshareChain?}` | `{reservationExpirationUTC}` |
| `acceptHistory` | PRODUCTHISTORY | `{historySinceUTC?, pageToken?, maxResultsPerPage?}` | `{offerHistories: OfferHistory[], nextPageToken?}` |
| `pushChanges` | PUSHCHANGES | **TBD** | **TBD** |

Two list formats: `SNAPSHOT` (full state) and `DIFF` (RFC 6902 JSON Patch from a watermark, with a special `"clear"` sentinel meaning "delete all"). Servers may downgrade `DIFF` → `SNAPSHOT` when the watermark is too old.

### 2.6 Trust / vetting

**Pure per-node ACL.** §4.3:

> "each organization automatically honors requests from a small number of other organizations. Each organization must store an access control list (ACL) of these trusted organizations."

There is no central registry of "good" orgs, no scoring, no web-of-trust. The reference impl `StaticServerAccessControlList` (`components/core/src/policy/staticserveraccesscontrollist.ts`, 48 lines) is literally a JSON list of org URLs you trust. Enrollment is out-of-band — the org description file has an `enrollmentURL` pointing to a human-readable web form.

Friend-of-a-friend is the **only** built-in trust-propagation mechanism: a chain of signed JWTs (`iss → sub` links carrying `entitlements` = either an offer id or the prior link's signature, plus a `scope` of `RESHARE`/`ACCEPT`) lets an unknown org accept an offer if it can prove an unbroken chain back to an ACL member of the offering org.

### 2.7 Idempotency & versioning

- **Offer-level timestamps:** every offer has `offerCreationUTC` (required) and `offerUpdateUTC` (required-after-update). `lastUpdateTimeUTC` is the optimistic-concurrency token used in `StructuredOfferId` to scope JSON Patches to a specific version.
- **Conditional accept:** `ifNotNewerThanTimestampUTC` on `acceptProduct` rejects the accept with a 409-like error containing the latest `currentOffer` if the offer mutated under you.
- **Server-driven watermarks:** §6.3.2.5 explicitly tells clients to use the server's last-returned `resultsTimestampUTC` as the next `diffStartTimestampUTC` to dodge clock skew.
- **Pagination:** opaque `pageToken`s; spec says "format is unspecified and may change at any time" — clients must treat as cursors.

No ETags, no `If-Match` headers, no sequence numbers, no CRDTs.

### 2.8 History / audit

**Yes, and it's a separate first-class endpoint with a 1-year retention SLA.** `acceptHistory` returns `OfferHistory` objects: `{offer, acceptingOrganization, reshareChain?, acceptedAtUTC}`. §6.3.7.5 explicitly recommends a **separate storage system** for history, indexed on `acceptingOrganization` and on every URL in every reshare chain — because the most important consumer is the **resharing middleman** who needs to know whose offers got picked up via their feed. Reshare middlemen **must not** publish history for offers they merely passed through (§6.3.7).

---

## 3. Authentication & Trust Model — summary

Three layers stacked:

1. **Transport**: HTTPS only, no exceptions (§4.1 + §5.3.1).
2. **Request auth**: JWT signed with org's private key, verified against JWKS fetched from org's description URL. Roughly **OIDC without an IdP** — every org is its own IdP, the org URL is the issuer.
3. **Request authz**: ACL lookup (`iss` ∈ ACL) **or** valid reshare chain. Optional fine-grained scope claim check.

Quote from `transfer_api.md` §8.1 ("Bad actors"):

> "The solution in OPR is the same as the solution in the real world — only trust trustworthy organizations, and stop working with organizations that abuse that trust."

OPR explicitly punts the trust problem to humans; the protocol just gives you the lever to revoke an org instantly.

---

## 4. Discovery & Federation Topology

OPR is a **pull-based bilateral mesh**:
- Each node statically configures a set of upstream org URLs to poll.
- Polling is per-recipient; offering org returns a filtered, possibly-resharer-customized view (§7.5).
- Topology is whatever you wire up. There is no auto-discovery, no DHT, no bootstrap registry.
- Resharing is the only mechanism for offer propagation beyond direct bilateral pairs, and it requires the resharer to extend the reshare-chain JWT chain per-recipient on every list call (§6.3.2.8) — **resharers do real cryptographic work on every poll**.

Push notifications (`pushChanges`) are reserved in the spec but TBD/unimplemented.

---

## 5. Implementation Surface (size & shape)

- **Language:** TypeScript/Node ≥18, Lerna monorepo, Express servers, `jose` for JWT.
- **Code size (LoC, hand-counted):**
  - `opr-core` server handlers: 7 handler files, ~430 lines total. The auth folder is ~800 lines. Model: ~1500 lines (dominated by `persistentoffermodel.ts` at 926 lines — the full state machine for offer lifecycle including reshare-chain extension and rejections).
  - `opr-models`: a folder of JSON Schemas (15 schemas) plus an auto-generated TS types file (`components/models/src/types-generated/types.ts`).
  - The minimal `examples/local-starter` runs in ~340 lines of TS (`src/index.ts` + `src/localintegrations.ts`).
- **TypeScript types:** yes, auto-generated from JSON Schema (`json-schema-to-typescript`) and published as `opr-models`.
- **OpenAPI:** no. JSON Schemas only.
- **Could you run this on Lambda + DynamoDB?** Yes, with caveats. The Express handlers are stateless modulo the `PersistentStorage`/`OfferModel` interface. The SQL integration (`integrations/sql-database`, ~20 files, uses TypeORM/Postgres) shows what the persistence contract looks like. DynamoDB would require: per-tenant ACL table, JWKS cache table, offer table with stream-friendly write patterns, history table indexed by acceptingOrg + each reshare-chain link. The Lambda cold-start cost on the JWKS fetch is bounded by the 48-hour cache TTL (§7.4). One Lambda per endpoint + EventBridge polling for `OfferProducer` upstream-pull is straightforward.

---

## 6. Failure Modes / Known Gaps

From reading issues + the spec's own §8 FAQ:

- **`pushChanges` is vaporware.** Spec §6.3.6 is literally "Additional details TBD." So OPR has no answer for low-latency push — fine for offers polled every 10 min, **terrible for a directory where a pantry closing today matters now**.
- **Deletion is awkward.** Offers expire (`offerExpirationUTC`). There is no soft-delete vs hard-delete distinction. Removal-from-listing is conflated with expiry. In `DIFF` format the only way to express "delete all" is the magic `"clear"` patch — there is no per-offer delete patch operation called out; you encode it as a JSON Patch `remove` op on the array, with all the brittleness §6.3.2.2.2 warns about.
- **Reshare-chain bloat.** Every list call to a resharer requires extending and signing every chain per-caller. Issue #75 / #102 acknowledge the IntegrationApi is overloaded; #103 admits the interfaces are under-documented.
- **No conflict resolution.** Two upstreams asserting different facts about the same logical entity = your problem. Offers are mostly owned by exactly one offering org, so OPR sidestepped the question entirely. **For directory federation this is the unavoidable problem.**
- **Scope checking is optional.** §6.2.1.3: "If an organization does not support scope checking, scopes must be ignored and all operations should proceed as if the required scopes are in the access token." Soft enforcement.
- **Trust is fully manual.** §8.1 quoted above. The protocol explicitly says "we don't solve this."
- **Project velocity.** Last spec touch ≈ Nov 2022. Open issues sit for 2+ years (#101 "self-documenting endpoints," #93 "break out event types," #102 "split IntegrationApi"). Google divested to CaravanStudios. **Treat OPR as a frozen design reference, not a living protocol.**

---

## 7. Mapping to PPR/Lighthouse/Beacon (directory federation)

| OPR primitive | Translates to PPR? | How |
|---|---|---|
| Org description file at canonical URL | **Direct.** | Each Lighthouse node hosts `https://{node}/.well-known/ppr-node.json` (or HSDS-style `/api/v1/about`) advertising its `organizationURL`, JWKS, endpoint URLs, supported HSDS version, supported data domains (e.g. "NJ", "FANO-affiliates"), trust profile. |
| `iss=org URL` JWT auth + JWKS at `jwksURL` | **Direct, steal verbatim.** | Use `jose`, same verifier recipe. Cache JWKS ≤48h per §7.4. |
| ACL per node | **Direct.** | Each Lighthouse declares trusted peers. PPR/FTGG could publish a *suggested* community ACL but every node decides who to honor. |
| `listProducts` (SNAPSHOT + DIFF + pageToken) | **Adapt.** Rename to `listLocations` / `listOrganizations` / `listServices`. Keep SNAPSHOT + DIFF + `diffStartTimestampUTC` + JSON Patch — these are the **most important ideas** to steal. HSDS has hundreds of slowly-changing resources; DIFF format with a watermark is the right wire shape. |
| `acceptProduct` / `reserveProduct` / `rejectProduct` | **Drop.** No transactional semantics; nobody "accepts" a pantry. Replace with `verifyLocation` / `claimLocation` (Plentiful's existing pantry-claim flow) and `disputeLocation`. |
| `acceptHistory` | **Adapt → `verificationHistory`.** Per-location audit log of who verified what when, with reshare-chain analog showing which middleman fed the verification. This is the **signal Plentiful and a Feeding America network would actually pay for**. |
| Reshare chain JWTs | **Adapt, scope down.** Use for *cross-network verification provenance*: "Plentiful verified this location on date X, which was reshared via TheFoodPantries.org from FANO". Chain length will typically be 1–2, much shorter than offer flows. |
| `offerCreationUTC` / `offerUpdateUTC` / `ifNotNewerThanTimestampUTC` | **Direct.** Every HSDS location/service already has `last_modified`. Use it as the optimistic-concurrency token. |
| `pushChanges` | **Critical to actually implement** (OPR didn't). Directory data changes are rare per-record but freshness matters — push via webhook + signed JWT body (the body itself is a JWT, replay-window via `iat`+`nbf`) is the natural design. |
| Friend-of-a-friend resharing | **Adapt with caution.** Useful for "Lighthouse A doesn't directly trust Lighthouse C but trusts Lighthouse B who vouches for C's data on FANO members." But every middleman has to re-sign per-recipient — at directory scale this could be cheap (resign once per day per peer, not per-list-call). |
| Trust = ACL + humans | **Steal philosophically.** Resist the urge to build a reputation system. Ship the ACL + revocation, let federation politics happen in Slack/email. |
| `enrollmentURL` for joining an ACL | **Direct.** Lighthouse `/admin/federation/enroll` form, manual approval. |

---

## 8. Top 5 Ideas Worth Stealing

1. **Org URL as canonical identity, JWKS-at-URL for keys.** No CA, no DID registry, no NPM-style hash, no UUID — the **URL is the ID** and DNS+HTTPS is the trust root. Self-signed JWT with `iss=URL`, verified by fetching `URL → jwksURL`. Devastatingly simple. Maps cleanly to a "Lighthouse" being identifiable by its hosted URL.
2. **SNAPSHOT + DIFF wire format with watermark-driven sync.** `listProducts` returning either a full snapshot or an RFC 6902 JSON Patch since a server-provided `diffStartTimestampUTC` is the right primitive for slowly-changing reference data. Combined with the `"clear"` sentinel and `StructuredOfferId.lastUpdateTimeUTC` scoping, this gives correct incremental sync without ETags/Merkle-trees/CRDTs. **This is the single most copy-able idea.**
3. **Per-tenant pluggable architecture in one process.** `oprtenantnode.ts` (540 lines) is "one server, many orgs". Lets a hosted Lighthouse service (e.g., a PPR-managed multi-tenant SaaS for FANO members who can't run their own infra) host dozens of orgs without forking the codebase.
4. **History as a separate first-class endpoint with retention SLA.** §6.3.7's "1 year minimum, indexed on accepting-org and every reshare-chain link" maps directly to a verification audit log that resharers can query: "show me every PPR location my reshares helped verify in the last 90 days." Killer feature for the "network of Lighthouses" pitch.
5. **JSON Schema as canonical spec, generated TS types as artifact.** `components/models/src/*.schema.json` + `Validator.validate(payload, 'list.payload.schema.json')` at the request-handler boundary. PPR already has Pydantic models — exposing them as JSON Schema, treating those as the federation wire contract, and code-generating client SDKs from them, is straightforward.

---

## 9. Top 3 Ideas to Deliberately NOT Steal

1. **Reshare-chain JWTs as the only trust-propagation mechanism.** They're cryptographically clever but operationally awful: every middleman re-signs every chain per-recipient on every list response. For OPR's tens-of-offers-per-day volume that's fine; for a directory with 50k+ locations resharing across 10+ peers it'd be a CPU sink. Use shorter, batch-signed verification attestations instead (one JWT per source per day per peer, not per-record-per-poll).
2. **Skipping `pushChanges` / forcing polling.** OPR's 10-minute polling default is wrong for both ends of the spectrum: too slow for "this pantry just closed permanently, stop sending people," and too aggressive when most data didn't change. Use webhooks-with-signed-bodies from day one (which OPR designed in the spec but never implemented — see §6.3.6 "TBD"). Make polling the fallback, not the default.
3. **Acceptance/reservation semantics.** OPR's whole `accept`/`reserve`/`reject` lifecycle assumes a transactional resource with a single owner who hands over responsibility. A pantry location has **no owner in that sense** — it has *claimants* (Plentiful's existing concept), *verifiers* (Lighthouse admins), and *aggregators* (PPR scrapers). Modeling these as accept/reserve will land you in a category error. Replace with explicit verification, dispute, and claim verbs whose semantics are "I assert this fact" not "I take this object."

---

## Appendix: Concrete file paths quoted

- `/tmp/federation-research/opr/standards/transfer_api.md` — full protocol spec, v0.5.2
- `/tmp/federation-research/opr/standards/description_format.md` — Offer/Product/ProductBundle data shape, v0.5.1
- `/tmp/federation-research/opr/components/models/src/offer.schema.json` — canonical Offer JSON Schema (props: id, description, contents, reshareChain, offeredBy, offerLocation, offerCreationUTC, offerUpdateUTC, offerExpirationUTC, maxReservationTimeSecs, ...)
- `/tmp/federation-research/opr/components/core/src/auth/standardverifier.ts` — JWT + reshare-chain verifier
- `/tmp/federation-research/opr/components/core/src/server/handlers/listrequesthandler.ts` — `listProducts` handler (41 lines; delegates to `OfferModel.list(issuerOrgUrl, payload)`)
- `/tmp/federation-research/opr/components/core/src/server/handlers/authenticatedrequesthandler.ts` — base class enforcing schema validation pre/post handler
- `/tmp/federation-research/opr/components/core/src/server/oprtenantnode.ts` — multi-tenant request routing
- `/tmp/federation-research/opr/components/core/src/offerproducer/oprfeedproducer.ts` — upstream-OPR-node polling adapter
- `/tmp/federation-research/opr/components/core/src/policy/universalacceptlistingpolicy.ts` — simplest possible ACL ("everyone on this list can accept")
- `/tmp/federation-research/opr/components/core/src/policy/staticserveraccesscontrollist.ts` — static ACL implementation (48 lines)
- `/tmp/federation-research/opr/examples/local-starter/src/index.ts` (210 lines) + `localintegrations.ts` (131 lines) — minimum viable server
