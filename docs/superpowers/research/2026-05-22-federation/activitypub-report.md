# ActivityPub & the Fediverse — Technical Reference for a "Network of Lighthouses"

A hyper-deep distillation of ActivityPub (W3C Rec), Activity Streams 2.0, WebFinger, NodeInfo, HTTP Signatures, and the FEP series, with explicit mapping to a federation design for **charitable food directory reference data** (HSDS-shaped Locations, Services, Organizations).

Primary sources: W3C ActivityPub Rec, W3C ActivityStreams 2.0 Vocabulary, docs.joinmastodon.org (ActivityPub + Security + WebFinger + Moderation), RFC 7033 (WebFinger), nodeinfo.diaspora.software, FEP-1b12 / FEP-7628 (via SocialHub + NodeBB derivative docs), SWICG LOLA draft, plus engineering write-ups on fan-out scaling.

---

## 1. Identity model

### Actor object — required vs recommended fields

Per ActivityPub §4.1, an Actor is an `Object` with these **REQUIRED** properties:

- `id` — globally unique HTTPS URI; also the actor's canonical document URL
- `inbox` — `OrderedCollection` URL for incoming activities (S2S)
- `outbox` — `OrderedCollection` URL for outgoing activities (C2S + readable feed)

**SHOULD** properties:
- `followers`, `following` — Collections
- `preferredUsername` — short handle used by WebFinger

**Optional but ubiquitous in practice** (Mastodon-extension territory, ratified de-facto):
- `publicKey` — embedded object `{ id, owner, publicKeyPem }` used for HTTP Signature verification. *Not* required by the W3C Rec — it lives in the Security Considerations as "an open implementation choice" — but in practice every fediverse server expects it.
- `endpoints.sharedInbox` — one URL per server for fan-out optimization
- `featured`, `featuredTags`, `manuallyApprovesFollowers`, `suspended`, `discoverable`, `indexable`, `memorial` — Mastodon-introduced flags now widely honored
- `alsoKnownAs`, `movedTo` — for account migration (see §6)

Example shape (from W3C Rec §4.1, with Mastodon-style publicKey grafted on):

```json
{
  "@context": [
    "https://www.w3.org/ns/activitystreams",
    "https://w3id.org/security/v1"
  ],
  "type": "Person",
  "id": "https://kenzo.example/users/kenzo",
  "inbox": "https://kenzo.example/users/kenzo/inbox",
  "outbox": "https://kenzo.example/users/kenzo/outbox",
  "followers": "https://kenzo.example/users/kenzo/followers",
  "following": "https://kenzo.example/users/kenzo/following",
  "preferredUsername": "kenzo",
  "endpoints": { "sharedInbox": "https://kenzo.example/inbox" },
  "publicKey": {
    "id": "https://kenzo.example/users/kenzo#main-key",
    "owner": "https://kenzo.example/users/kenzo",
    "publicKeyPem": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkq...\n-----END PUBLIC KEY-----"
  }
}
```

### WebFinger lookup — `acct:` → actor URL

The bootstrap problem ("I typed `@alice@example.com`, what's the JSON URL?") is solved by **WebFinger (RFC 7033)**, not by ActivityPub itself.

1. Client constructs URI `acct:alice@example.com` (RFC 7565 acct scheme).
2. HTTPS GET to `https://example.com/.well-known/webfinger?resource=acct%3Aalice%40example.com`.
3. Server returns a **JRD** (JSON Resource Descriptor):

```json
{
  "subject": "acct:alice@example.com",
  "aliases": ["https://example.com/@alice", "https://example.com/users/alice"],
  "links": [
    { "rel": "self",
      "type": "application/activity+json",
      "href": "https://example.com/users/alice" },
    { "rel": "http://webfinger.net/rel/profile-page",
      "type": "text/html",
      "href": "https://example.com/@alice" }
  ]
}
```

4. Client follows `rel="self"` with `Accept: application/activity+json` to fetch the actor doc.

RFC 7033 mandates HTTPS-only and `Access-Control-Allow-Origin: *`. It warns about **enumeration abuse** (harvesting valid handles) and recommends rate limits — directly relevant to the Lighthouse threat model since org names are arguably less sensitive than personal emails but spammer-actionable nonetheless.

### Server identity — NodeInfo

WebFinger answers "who is this actor?"; **NodeInfo** answers "what software is this server, and what does it federate?". Discovery via `/.well-known/nodeinfo` returns a JRD pointing at a versioned schema URL:

```json
{ "links": [
  { "rel": "http://nodeinfo.diaspora.software/ns/schema/2.1",
    "href": "https://example.com/nodeinfo/2.1" }
]}
```

The 2.1 document exposes: `software.{name,version,repository}`, `protocols[]` (e.g. `["activitypub"]`), `services.{inbound,outbound}`, `openRegistrations` bool, `usage.{users.total/activeMonth/activeHalfyear, localPosts, localComments}`, and a freeform `metadata` object. It is **server-level** (one per host) while WebFinger is **actor-level** (potentially many per host).

### Key rotation / multi-key actors

The Rec is silent. Pragmatic state of the art: actors expose **one** `publicKey` whose `id` is a fragment URI (`#main-key`). Rotation = publish the actor with a new `publicKeyPem` and update the `id` fragment; old `keyId` URLs go 404 and remote servers re-fetch the actor on verification failure. **FEP-521a** (multikey) proposes formalizing an `assertionMethod` array of keys per actor; uptake is partial.

---

## 2. The 2-actor message-passing model

### The collections

| Collection  | Purpose                                          | HTTP semantics          |
|-------------|--------------------------------------------------|-------------------------|
| `inbox`     | Things addressed to this actor (S2S incoming)    | POST = deliver; GET = read (auth) |
| `outbox`    | Things this actor authored (C2S out; S2S feed)   | POST = publish (C2S); GET = public timeline |
| `followers` | Actors subscribed to this actor                  | GET (sometimes private) |
| `following` | Actors this actor subscribes to                  | GET                     |

§5.1 and §5.2 require `inbox` and `outbox` to be `OrderedCollection` in reverse-chronological order. `followers`/`following` MAY be either ordered or unordered.

### The 7 activity verbs that actually matter on the wire

From AS2 §3 and ActivityPub §6:

1. **`Create`** (§6.2) — wraps a newly-published object. Side effect on receivers: store the wrapped object, link via `attributedTo`.
2. **`Update`** (§6.3 / §7.3) — modifies an existing object. **S2S = complete replacement**; C2S = partial. Authorization required (see authoritative-source rule below).
3. **`Delete`** (§6.4 / §7.4) — removes an object. Receiver SHOULD replace with a `Tombstone` (HTTP 410 thereafter) instead of 404, so collection references don't dangle.
4. **`Follow`** (§6.5) — subscription request. Side effect after `Accept`: target's `followers` gets the requester; requester's `following` gets the target.
5. **`Accept`** / **`Reject`** (§6.6, §6.7) — response to a `Follow`, `Invite`, or `Offer`. The `Accept(Follow)` pattern is the cornerstone handshake.
6. **`Announce`** (§7.11) — share/boost/repost. Wraps another activity or object; receivers fan it out to the announcer's followers.
7. **`Undo`** (§6.10) — reverses a prior activity. Used for unfollow (`Undo(Follow)`), unboost (`Undo(Announce)`), unlike. Constraint: the `Undo.actor` MUST match the original activity's actor.

Honourable mentions used in directory contexts: **`Move`** (§6.12 — account portability), **`Flag`** (§6.13 — report; only delivered to moderators, no public side-effect), **`Add`/`Remove`** (collection management).

### GET vs POST semantics, dereferenceable objects

Every activity and object has an `id` that is an HTTPS URI that **MUST be dereferenceable** (§3) and return JSON content negotiated via `Accept: application/activity+json` or `application/ld+json; profile="https://www.w3.org/ns/activitystreams"`. This is the property that makes the network self-describing: any actor or activity you receive can be re-fetched from its authoritative source.

POST is reserved for delivery (to `inbox`) or publication (to `outbox`). GET is for reading. There is no PUT/DELETE on the wire — mutation happens by POSTing an `Update` or `Delete` activity that *describes* the mutation. This is the core architectural choice that makes the protocol an **event log over a document store**, not a REST CRUD API.

### The authoritative-source rule (the single most important federation rule)

From §7.3 (Update, S2S): *"The receiving server **MUST** take care to be sure that the `Update` is authorized to modify its `object`. At minimum, this may be done by ensuring that the `Update` and its `object` are of same origin."*

From §7.4 (Delete, S2S): *"assuming the `object` is owned by the sending actor / server… the server receiving the delete activity **SHOULD** remove its representation of the `object`."*

Combined with §3.2: *"Servers **SHOULD** validate the content they receive to avoid content spoofing attacks."*

**Enforcement in practice** is layered:
1. The HTTP Signature on the inbox POST (§3) proves the POST came from a key controlled by some actor.
2. The receiver checks that the **origin of the signing actor** matches the **origin of the object** (`new URL(activity.object.id).host === new URL(activity.actor.id).host`).
3. For high-trust ops (Update/Delete), some implementations additionally **re-fetch the object from its origin** ("authorized fetch" / "secure mode") to confirm the canonical state.

This is the rule that prevents `evil.example` from POSTing `Delete { object: "https://good.example/notes/123" }` and having `good.example`'s posts wiped from the network.

---

## 3. Wire-level security

### HTTP Signatures — Cavage flavour (the deployed reality)

Mastodon (and ~everyone) ships **draft-cavage-http-signatures-12** (now superseded by **RFC 9421**, but RFC 9421 has near-zero deployment in the fediverse). The signature header:

```
Signature: keyId="https://kenzo.example/users/kenzo#main-key",
           algorithm="rsa-sha256",
           headers="(request-target) host date digest",
           signature="Y2FiYW...IxNGRiZDk4ZA=="
```

What's covered:
- `(request-target)` — pseudo-header `lowercase(method) + " " + path` (e.g. `post /users/alice/inbox`)
- `host` — receiver's hostname
- `date` — must be within ±12h of receiver clock (replay window)
- `digest` — for POST only: `SHA-256=base64(sha256(body))`. Receiver recomputes and rejects on mismatch.

Verification: receiver parses `keyId`, GETs the actor doc (Accept-content-negotiated), extracts `publicKey.publicKeyPem`, reconstructs the signing string, verifies RSA-SHA256.

GETs are signed in **"secure mode" / "authorized fetch"** (default ON in Mastodon 3.0+): every cross-server GET — even for public objects — must carry a Signature. This blocks scraping by unauthenticated crawlers but means defederation can be enforced at fetch time, not just delivery time.

### Linked Data Signatures — and why both

Mastodon also signs activities with **`RsaSignature2017`** (an LD-Sigs proof) when it expects the activity to be **forwarded**. Why both?

- HTTP Signatures cover the **transport** — they prove "this HTTP request came from key X right now." They do **not** survive being relayed by a third party.
- LD Signatures cover the **document** — they prove "this JSON-LD activity was signed by key X at any time in the past." Survives proxying, mailbox aggregation, relay re-announce.

Forwarding rule (§7.1.2): when a server receives a reply addressed to a Collection it owns, it MUST forward the original to that Collection's members. The forwarded copy still has the **original signer's** LD signature; the new HTTP Signature is the forwarder's. Two signatures, two trust questions: "did this actually originate at the claimed source?" (LD) vs "did I just receive it from a legitimate peer?" (HTTP).

LD Sigs / `RsaSignature2017` is considered obsolete; **FEP-8b32** (Object Integrity Proofs, using `DataIntegrityProof` from the W3C VC Data Integrity spec) is the modern proposal. Adoption is partial.

### C2S vs S2S — and Mastodon's reject of C2S

ActivityPub defines **two protocols sharing one document**:
- **S2S (server-server)** — federation via inbox/outbox POSTs, signed with HTTP Signatures. Universally implemented.
- **C2S (client-server)** — clients POST activities directly to a user's outbox using OAuth 2.0 bearer tokens. Mastodon **does not implement C2S at all**. Mastodon clients use a parallel proprietary REST API (`/api/v1/statuses` etc.).

Why the C2S failure?
- The base spec is minimal; clients also need search, media upload, pagination, notifications, follow-request management, blocks — none of which AP C2S defines.
- JSON-LD parsing is hostile to mobile/web clients ("steep learning curve and overhead… can slow development").
- Mastodon shipped its REST API first and never had incentive to retrofit.
- Classic chicken-and-egg: no clients → no servers → no clients.

The 2024 SocialHub discourse has explicitly floated an "ActivityPub 2.0" that separates the two layers and de-emphasizes JSON-LD.

---

## 4. Discovery and topology

### How does instance A find instance B?

**It doesn't bootstrap.** There is no central registry, no DNS-SD, no DHT. Discovery is *parasitic on user action*:

1. A user on instance A types `@bob@b.example` (out-of-band knowledge).
2. A's server does WebFinger on `b.example` → gets Bob's actor URL.
3. A's user clicks Follow → A POSTs `Follow{actor: alice, object: bob}` to Bob's inbox.
4. Now A knows B exists, and on `Accept`, B knows A exists too.
5. Future activities from Bob flow to Alice (and any other A-resident follower) via A's shared inbox.

This is **the** structural difference between fediverse federation and, say, email: email has MX records pointing at well-known mail servers; AP has *no* server-level discovery. Everything is actor-mediated.

### Shared inbox optimization

§7.1.3: "When an object is being delivered to the originating actor's followers, a server MAY reduce the number of receiving actors delivered to by identifying all followers which share the same sharedInbox."

So instead of POSTing the same `Create(Note)` 800 times to 800 individual inboxes on `mastodon.social`, the sender POSTs **once** to `https://mastodon.social/inbox` and tags the addressing (`to`, `cc`) so the receiver can fan out internally. Without this optimization, the protocol would have melted under Twitter-migration traffic in 2022.

### Relays — FEP-1b12 group actors

A **relay** is an actor (type `Application` or `Group`) that:
- Accepts `Follow` activities from server admins (one follow per follower-server, not per user).
- Re-announces every public `Create` it sees, by sending `Announce(Activity)` to all its followers.

FEP-1b12 ("Group federation", used by Lemmy, Kbin, Friendica) formalizes the pattern: *"In case the incoming activity is deemed valid, the group MUST wrap it in an `Announce` activity, with the original activity as object."* The wrapped activity retains its original LD signature → receivers can verify origin even though the relay is the immediate sender.

Why relays exist: a brand-new instance with zero follows sees nothing. Following one relay = firehose of everything that relay's members publish. Trade-off: noise + DoS amplification surface.

Common implementations: `activityrelay`, `pub.relay.net`, `litepub-relay`.

### `.well-known` summary

| Path                                | Purpose                       | Spec      |
|-------------------------------------|-------------------------------|-----------|
| `/.well-known/webfinger?resource=…` | Actor lookup by `acct:` URI   | RFC 7033  |
| `/.well-known/nodeinfo`             | Server software/protocol info | nodeinfo.diaspora.software |
| `/.well-known/host-meta`            | Legacy XRD; sometimes still used | RFC 6415 |

---

## 5. Trust, moderation, defederation

There is no central registry. Health is maintained by **per-instance policy**, transmitted through **out-of-band social channels** (Matrix, Mastodon itself, blog posts). The mechanisms:

### Domain blocks (Mastodon)

Three severities:
- **Reject media** — drop attachments, avatars, headers, emoji from `evil.example` but keep the text.
- **Limit / silence** — content from `evil.example` is hidden from public timelines; follows become follow-requests.
- **Suspend** — total cutoff. *"Equivalent to suspending all past and future accounts from the server. No content from the server will be stored locally except for usernames."* Existing follow relationships are **destroyed** and do **not** auto-restore on unsuspend.

### Allow-list vs block-list mode

Default Mastodon is **block-list / open federation**: federate with anyone, block bad actors retroactively. **Allow-list mode** ("limited federation") inverts the default: federate with no-one unless explicitly approved. Operationally rare for general-purpose servers; common for corporate/institutional deployments. The Mastodon admin docs cover blocklist *import* but explicitly omit allow-list mode from operational guidance.

### Fediblock — informal shared blocklists

A hashtag-driven, social process: admins publish lists of suspended domains (sometimes as CSV/JSON), other admins import them at their discretion. **No protocol-level shared blocklist exists.** Attempts (FEP-D767, FEP-fb2a, various drafts) have not converged.

### Flag activity

`Flag { actor: alice, object: <bad-thing>, content: "spam" }` — sent to the offending server's moderators (and sometimes to other moderators in the audience). Crucially: **no public side-effect** and no Accept/Reject required. Receiver acts at their discretion. This is the only AP primitive for cross-instance reporting.

---

## 6. Conflict resolution & object lifecycle

### Authoritative source recap

For any object `O` with `id: https://example.com/things/123` and `attributedTo: https://example.com/users/alice`:
- **Only** `example.com` can Update or Delete `O`.
- Other servers' copies are *replicas*. They MUST re-fetch on signature failure, MUST apply Update activities only if origin-matched, MUST honour Delete by inserting a Tombstone.
- There is no merge logic. There are no conflicts to resolve — the origin is god.

This is **deliberately CRDT-free**: the social-web use case has a single writer per object. Directory data with multiple verifying parties violates this assumption — see §8.

### Delete + Tombstone

```json
{
  "@context": "https://www.w3.org/ns/activitystreams",
  "type": "Tombstone",
  "id": "https://example.com/things/123",
  "formerType": "Note",
  "deleted": "2026-05-22T12:00:00Z"
}
```

Returned with HTTP 410 Gone. Lets replies and quote-chains render gracefully ("this post was deleted") instead of dangling on 404.

### Move activity (FEP-7628) — account portability

The deployed solution. Two-sided handshake using actor properties:
- Old actor declares `movedTo: <new-actor-url>`.
- New actor declares `alsoKnownAs: [<old-actor-url>]` (mutual recognition; prevents hijack).
- Old actor sends `Move { actor: old, object: old, target: new }` to its followers' inboxes.
- Each follower verifies the `alsoKnownAs` ↔ `movedTo` pair, then sends `Follow(new)` and `Undo(Follow(old))`.

**What persists:** the social graph (followers/following), gradually, via follower-server action.
**What is lost:** posts, bookmarks, likes, lists, DMs, follower-counts-on-old-posts. Everything content-shaped stays at the old origin and stops being updated.

### LOLA — Location-Of-Last-Activity (SWICG, draft v0.2)

The proposed evolution. Server-to-server, OAuth-authorized **bulk data transfer** of:
- Outbox activities (Notes, Articles, attachments)
- Following list
- Block list
- Likes / favorites

**Notably excluded:** inbox contents, follower collection (rebuilds via Move-style notifications), Create/Update/Delete activity records (the receiving server *re-emits* its own).

Status: draft, several open issues, no deployed implementation as of writing. The article *"The Sisyphean Effort of ActivityPub Migration"* (voidfox.com) is a fair survey of why this is still unsolved 8 years post-Rec.

---

## 7. What ActivityPub does badly — known criticisms

1. **C2S adoption failure.** Mastodon never shipped it; the spec is incomplete (no search, no media, no notifications, no follow-request mgmt); JSON-LD is hostile to mobile clients. The 2024 SocialHub consensus is that C2S needs to be unbundled from the Rec.

2. **JSON-LD complexity, mostly unused.** Almost no implementation performs actual LD context expansion. Everyone treats the documents as plain JSON with a `@context` field they cargo-cult. This creates a **security hole**: remote `@context` URLs can be used to redefine vocabulary and bypass validators that *do* expand. Periodic vulnerabilities (e.g. the "remote JSON-LD context bypass" thread on SocialHub).

3. **No discovery primitive.** No search, no directory, no "list servers near me." Mastodon's `https://api.joinmastodon.org/servers` is a separate, centralized, opt-in registry — *not* part of the protocol.

4. **Portability unfinished after 8 years.** Move moves the graph, not the content. LOLA is still draft. Practical effect: leaving an instance is expensive, which gives admins power.

5. **Spam, scraping, GDPR.** Public objects are by definition globally fetchable. "Right to be forgotten" is structurally impossible — Delete is best-effort across N independent servers with no enforcement. Authorized-fetch helps with scraping but doesn't fix it.

6. **Fan-out is O(followers).** Each `Create` from an actor with N followers spans up to N HTTP POSTs (reduced by sharedInbox to ~N_servers). Stephen-Fry-class accounts (56k+ followers) generated tens of thousands of Sidekiq jobs per post on `mastodon.social`; mega-posts have caused incidental DDoS on linked sites via OpenGraph fetch storms. There is no pull-model alternative in the protocol.

7. **Defederation is political, not technical.** Trust is per-instance, social, and brittle. A popular admin's block cascades; a quiet admin's block is invisible.

8. **No transactions, no acknowledgments beyond HTTP 202.** Receivers process asynchronously; you cannot know your Create was actually stored without separately GETting the object back.

---

## 8. Mapping to PPR / Lighthouse / Beacon — directory federation

Classification key: **(D)** translates directly · **(A)** adapt · **(R)** replace/skip.

| AP primitive          | Lighthouse equivalent                                  | Class |
|-----------------------|--------------------------------------------------------|-------|
| Actor (Person)        | **Organization** actor (food bank, 211 node, county GIS) | **A** |
| Actor (Group)         | **Region** actor (NJ region, ZIP cluster, Feeding America network) | **A** |
| Object (Note)         | **HSDS `Location`** (with embedded Services, Schedules) — Place-shaped | **A** |
| `attributedTo`        | `source_type` + `verified_by` from the confidence model | **D** |
| inbox                 | `POST /federation/inbox` accepting `Update(Location)`  | **D** |
| outbox                | `GET /federation/outbox` of recent activities          | **D** |
| Create(Location)      | New location ingestion from origin org                 | **D** |
| Update(Location)      | Hours/phone/service change, signed by origin           | **D** |
| Delete(Location)      | Permanent closure → Tombstone (HSDS `is_active=false`) | **D** |
| Follow(Region)        | "Subscribe me to all locations in NJ ZIP 070xx"        | **A** |
| Announce(Location)    | Corroboration / re-publication signal ("I verified this independently") | **A** |
| Flag(Location)        | "This entry is wrong/closed/spam" report to origin     | **D** |
| Move(Actor)           | Org changes domain / merges (Vivery → Plentiful)       | **D** |
| HTTP Signatures       | **Mandatory.** Per-org Ed25519 (skip RSA legacy)       | **A** |
| LD Signatures / FEP-8b32 | Object integrity proofs for relayed updates         | **A** |
| WebFinger             | `acct:north-jersey-fb@plentiful.org` → org actor URL   | **D** |
| NodeInfo              | `/.well-known/nodeinfo` advertising HSDS version, scrapers offered | **D** |
| Shared inbox          | One `/federation/inbox` per Lighthouse node            | **D** |
| C2S protocol          | **SKIP.** Use existing PPR REST + Write API            | **R** |
| JSON-LD `@context`    | Use plain JSON with versioned `@context: https://hsds.openreferral.org/3.1.1`, **don't actually do LD expansion** | **A** |
| OrderedCollection     | Activity log per org, exposed as paginated feed         | **D** |
| Relay (FEP-1b12)      | **HAARRRvest-as-firehose** — a Group actor that re-Announces every `Create`/`Update` from member orgs | **A** |
| Allow-list mode       | Default for Lighthouse — orgs explicitly federate, not open-by-default | **A** |
| Block-list / Fediblock | Out-of-band shared list of known-bad scrapers/spammers | **A** |
| `manuallyApprovesFollowers` | Region subscriptions require admin approval (rate-limit + abuse) | **D** |
| GDPR Delete           | Same problem we already have — Tombstone + best-effort propagation | **A** |
| O(followers) fan-out  | Most orgs have ~10–100 followers; not a problem at our scale | **D** |

### Key adaptation calls

**Actor = Org, not Location.** A `Location` is a *Place* (AS2 Place type fits — `latitude`, `longitude`, `address`, `radius`) and the *object* of activities; the Org that maintains it is the actor. This preserves the authoritative-source rule: only `north-jersey-fb` can Update locations it `attributedTo`s itself.

**Authoritative source ⇄ verified_by.** Our confidence model already encodes "who said this": `source_type ∈ {scraper, submarine, admin, claimed, ...}`. In federation terms, an `Update(Location)` from `attributedTo: north-jersey-fb` arrives, and the receiver:
1. Verifies the HTTP Signature against `north-jersey-fb`'s public key.
2. Checks origin-match: `north-jersey-fb`'s host == the Location's `attributedTo` host.
3. Maps to `verified_by="source"` if it's the canonical owner, else **stores it as a corroboration `Announce`** rather than overwriting the local copy.

This is the **critical departure from social AP**: in social, only the origin can Update, period. In directory data, *multiple parties want to verify the same Place*, and that's a feature, not a bug. We need both:
- An `Update` channel (origin-only) for facts about a Location the origin owns.
- An `Announce` channel (any verified party) for "I corroborate this is correct as of $date" — feeds the multi-source bonus in our scoring.

**Follow targets Regions, not Orgs.** Following `north-jersey-fb` makes sense if you want their announcements. But a 211 node wants "everything in my county," not "everything one specific food bank does." Use FEP-1b12-style **Group actors** keyed on geography (ZIP, county, H3 cell). A subscriber `Follow`s `acct:zip-07030@plentiful.org`; the Group `Announce`s any `Update(Location)` where the Location's `address.postalCode == 07030`.

**WebFinger as the only directory of orgs.** `acct:<slug>@<lighthouse-domain>` resolves to an Org actor. No central registry; orgs are discovered by being mentioned, embedded in HSDS payloads as `attributedTo`, or listed in a Region's collection.

**HTTP Signatures + per-org keys.** Skip RSA-2048 (legacy); ship Ed25519 from day one (FEP-521a multikey advertises it). Every Org actor has `publicKey` with a fragment id, rotation works the same as Mastodon.

---

## 9. Top 5 ideas worth stealing

1. **The authoritative-source rule + Tombstones.** §7.3, §7.4 of the Rec. Adopt verbatim: each Location has exactly one `attributedTo` Org, and only that Org can issue `Update`/`Delete`. Deletes leave Tombstones so subscriber caches degrade gracefully (this maps perfectly to our `is_active=false` + `change_audit` model). *Why steal*: solves "who's allowed to change this Location?" without a central authority.

2. **HTTP Signatures (Cavage) + `Digest` header on POST.** docs.joinmastodon.org/spec/security — proven, simple, no JWT/PASETO/OAuth machinery. Every federation POST signs `(request-target) host date digest`; receivers fetch the Org's public key from the Org's actor doc. *Why steal*: zero shared-secret distribution. Pairs cleanly with our existing per-source-system tracking (replace API keys with public keys in `source_type` records).

3. **WebFinger + NodeInfo for the directory-of-directories.** RFC 7033 + nodeinfo.diaspora.software. `acct:org-slug@lighthouse.example` for org lookup; `/.well-known/nodeinfo` for "what HSDS version, what scrapers, what regions does this Lighthouse cover." *Why steal*: gives us a discovery story without standing up a registry, and a federation-onboarding URL we can publish in docs.

4. **Group actors + `Announce(Activity)` (FEP-1b12).** Region/ZIP/county Group actors that subscribers Follow once, and that re-Announce every Update from member orgs. *Why steal*: directly serves the "211 node wants all updates in their county" use case. HAARRRvest becomes a Group actor that Announces the firehose; small Lighthouses Follow it.

5. **`Flag` for cross-instance reporting (no side-effect contract).** AS2 vocabulary `Flag`. Moderation channel that doesn't require receiver action; preserves origin authority. *Why steal*: "this Location looks wrong" reports from a 211 node about a food-bank's data, without giving the 211 node write access. Maps to our existing claim/correction flow but federated.

---

## 10. Top 3 ideas to deliberately NOT steal

1. **JSON-LD context expansion.** Use the `@context` field as a *version tag* (`https://hsds.openreferral.org/3.1.1`), treat documents as plain JSON, never call a JSON-LD processor. *Rationale*: the wider fediverse has spent 8 years not doing real LD processing and discovered remote-context security holes (SocialHub thread). Our payloads are structured HSDS — we have Pydantic models — we don't need RDF.

2. **C2S protocol.** Don't ship an AP-shaped client→server API. Keep PPR's existing REST + Write API + Lighthouse UI. *Rationale*: Mastodon's track record + JSON-LD complexity + chicken-and-egg = guaranteed failure. Federation is server↔server; humans use our existing UIs.

3. **Open-federation-by-default + retroactive defederation.** Mastodon's default is "federate with anyone, block bad actors later." For *vulnerable-population reference data*, the cost of a single bad-actor write is catastrophic (fake addresses, scam phone numbers). Default to **allow-list mode**: a Lighthouse only accepts Updates from explicitly-trusted peer orgs. Use Mastodon's `manuallyApprovesFollowers` pattern for region subscriptions too. *Rationale*: Constitution principle VI ("data quality for vulnerable populations") trumps network effects. We can build the social graph slowly with trust intact.

---

### Sources cited

- W3C ActivityPub Recommendation — https://www.w3.org/TR/activitypub/
- W3C Activity Streams 2.0 Vocabulary — https://www.w3.org/TR/activitystreams-vocabulary/
- Mastodon ActivityPub implementation — https://docs.joinmastodon.org/spec/activitypub/
- Mastodon Security (HTTP Signatures, LD Sigs) — https://docs.joinmastodon.org/spec/security/
- Mastodon WebFinger — https://docs.joinmastodon.org/spec/webfinger/
- Mastodon Moderation / defederation — https://docs.joinmastodon.org/admin/moderation/
- RFC 7033 WebFinger — https://datatracker.ietf.org/doc/html/rfc7033
- NodeInfo — https://nodeinfo.diaspora.software/protocol.html, /schema.html
- FEP-1b12 Group federation — https://socialhub.activitypub.rocks/t/fep-1b12-group-federation/2724, https://docs.nodebb.org/activitypub/fep/1b12/
- FEP-7628 Move actor — https://socialhub.activitypub.rocks/t/fep-7628-move-actor/3583
- LOLA portability draft — https://swicg.github.io/activitypub-data-portability/lola.html
- Steve Bate, "ActivityPub Client API: A Way Forward" — https://www.stevebate.net/activitypub-client-api-a-way-forward/
- "The Sisyphean Effort of ActivityPub Migration" — https://voidfox.com/blog/the_sisyphean_effort_of_activitypub_migration/
- ActivityPub on Wikipedia — https://en.wikipedia.org/wiki/ActivityPub
