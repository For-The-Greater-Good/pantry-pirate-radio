# HSDS Federation in PPR Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every PPR deployment a first-class federating node in an open HSDS food-resource network — publishing its canonical data, ingesting from peers, and notifying peers of changes — implemented in `app/` core, on by default, gated by nothing.

**Architecture (v3):** A new `app/federation/` core module plus a **verifiable, append-only `federation_log`** written at the canonical-commit points: every published activity is a JCS-canonical, content-addressed, **origin-signed object** in a Merkle-committed log with **signed checkpoints** (`state.txt` + `/federation/checkpoint`), inclusion/consistency proofs, and a witness-cosigning mesh as a committed later phase. Canonical Postgres remains the serving source of truth (the *app-view*); the log is the source of truth for federation. Read endpoints ride the existing read API (Uvicorn + slim Lambda); the write path (`/inbox`) and the pull consumer **verify proofs before enqueue** and funnel through a thin LLMJob enqueuer into the unchanged Content Store → LLM → Validator → Reconciler pipeline as `source_type='federated_node'`. Trust is an allow-list of peer DIDs; transport auth is **RFC 9421** HTTP Message Signatures (Ed25519); the whole surface sits behind a tested `FEDERATION_ENABLED` kill switch. The full design of record is [`../specs/2026-06-03-hsds-federation-core-design.md`](../specs/2026-06-03-hsds-federation-core-design.md) (read it first — §21 records the owner's v3 decisions).

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy (async) / PostgreSQL+Aurora / Pydantic v2 / `cryptography` (Ed25519) / httpx / structlog / RQ+Redis (local) / SQS+DynamoDB+Lambda+CDK (AWS) / pytest. All commands via `./bouy` (Principle I).

---

## Build status (updated 2026-06-05)

> Next-session entry point: [`../NEXT-SESSION.md`](../NEXT-SESSION.md). Issue map in [`../federation-github-epic.md`](../federation-github-epic.md).

- **P0 — Foundations: DONE, merged to `main`** (PR #545; phase #520 + tasks #529–#537 closed). Identity/discovery/WebFinger/actor in both envs, JCS canonicalization (fuzzed 1.52M values vs V8, 0 mismatches), RFC 9421/Ed25519 signing, SSRF-hardened fetch, multi-file HSDS Profile. Built via subagent-driven-development + the PR Gauntlet (all blocking findings fixed + re-verified, incl. a real SSRF IPv4-mapped-IPv6 bypass).
- **P0.5 — De-risking spike: DONE → GO accepted** (phase #521 closed). Memo: [`../research/2026-06-05-federation-p05-go-no-go.md`](../research/2026-06-05-federation-p05-go-no-go.md). The **in-place dense-sequence advisory-lock append is proven** (gapless/skip-free under real concurrency; M5 impossible; write-cost p99 ~0.2 ms). §6.2f relay/CDC fallback NOT taken. P1–P7 hard-gate **cleared**.
- **HSDS version decision:** pinned **3.1.1** (owner-confirmed on #522) — the models implement 3.1.1, not the submodule's 3.2.3; advertising 3.2 would violate Principle II. **This supersedes the design's "pin the 3.2 line" note** (design §7) — see #522. 3.2-model work is a separate follow-up.
- **P1 — Verifiable publish: IN PROGRESS (nearly closed).** 4-PR split. **PR-A (decomposition), PR-B (RED-tier substrate: `FederationLog` + dense-sequence append + RFC-6962 Merkle frontier + C2SP signed checkpoints + inclusion/consistency proofs + aggregate + JCS vectors), PR-C (hooks + kill-switch + `/api/v1/federation/{export,state.txt,checkpoint,history}`, #563) are MERGED to `main`.** PR-D is **mostly merged**: the **HSDS-FX conformance suite** shipped as 8 machine-reviewed PRs (#567 Slices 1–3 envelope/checkpoint/export+Level-2; #568 federation_id grammar; #569 JCS anchor + honesty hardening; #570 activity verbs/Tombstone; #571 RFC-3986 mechanic anchor; #572 RFC-6962 consistency-proof anchor) — 10 conformance areas, 19 externally-anchored vectors, every PR RED-tier-Gauntlet-gated (the Gauntlet caught real defects in the honesty machinery itself — a foolable substring trace, a non-idempotent normalizer, a fabricated RFC citation — all fixed pre-merge). **P1 PR-D REMAINING (P1 #522 stays open until these land):** (1) the **in-repo reference second node + golden P1 journey** — the *raw-sync* two-node loop: A publishes → B **discovers A's key from `/.well-known/did.json`** (needs a small `identity.public_key_from_multibase` decoder — the inverse of `public_key_multibase`; the one genuinely-new piece, scoped 2026-06-07) → B pulls `/export@N` → B verifies every envelope signature + RFC-6962 inclusion + consistency against A's signed checkpoint; (2) cold-start `_since=0` parity from raw tables; (3) archive tiering + retention-prune worker/Lambda + its Principle-XIV alarm. **Then** P2.

- **Scenario → phase map (owner ask 2026-06-07, "run through all the scenarios, swing big"):** the two-node ambition splits across two phases and must NOT be collapsed. **"Raw sync"** (publish→discover→pull→**verify** between two distinct instances, no writes) = **P1 PR-D** reference-second-node + golden journey (above). **"Different datasets federating, with everything that entails"** (pull **ingest** as `source_type='federated_node'`, the §117 verify-before-enqueue order, corroboration + §12.1 origin-dedup, Update/Announce/Delete authority via `activities.py:validate_activity`, `merge_location` + HUMAN_VERIFIED guard, Tombstone `redirectTo` re-point, **bidirectional**) = **P2 Pull ingest** (roadmapped below, tasks 0–15; acceptance = live Feeding America feed end-to-end). The activity-verb validator (P1 Slice 6) and the Level-2 runner (P1 Slice 3) are the load-bearing inputs P2 consumes. No P2 code ships before P1 #522 closes (living-plan contract).
- **Incidental (independent of federation):** the P0.5 spike surfaced two real Beacon data-loss bugs, fixed + merged (PR #546); deeper follow-ups filed (#547 CloudWatch alarm on `beacon_transform_failed`; #548 per-child isolation).

---

## How this living plan is structured (read before executing)

This feature spans phases P0–P7 plus the P0.5 hard-gate spike, across many sessions. Per the writing-plans Scope Check, it is **not** one bite-sized plan — it is a **living roadmap + per-phase plans**, each shipping working, tested software on its own:

- **§Roadmap** maps all phases (P0–P7) with deliverables, file-map, acceptance, and dependencies. It is the durable index.
- **P0 is fully task-decomposed below** (real code, TDD, no placeholders) — it is executable now and has zero external dependencies.
- **P1–P7 are roadmapped at task granularity** (title + files + key test assertions + acceptance + constitution touchpoints). Each phase is **expanded into its own bite-sized sibling plan at the start of its session** (e.g. `2026-..-hsds-federation-p1-publish.md`). This is deliberate: writing exact code for session-80 work now produces stale false-precision (the very thing "no placeholders" guards against in the other direction). The design doc + this roadmap carry the binding decisions; the bite-sized code is written just-in-time against live signatures.

**Per-task constitution gates (every task, every phase):**
- TDD red-first (Principle III). Per-task run: `./bouy exec app pytest <path>::<test> -v` (single-file selection; `./bouy test --pytest` does not select files well — owner practice). Pre-PR full gate: `./bouy test` (black + ruff + mypy + bandit + pytest, coverage ratchet — Principle X).
- Files ≤600 lines / cyclomatic ≤15 (Principle IX). Fictional test data only: `555-…`, `example.com` (Principle VII).
- Each phase's PR updates `CLAUDE.md` in the same PR (Principle XIII).
- AWS tasks add CloudWatch alarms + dashboard widgets + `infra/tests/` assertions routed to `pantry-pirate-radio-alerts-{env}` (Principle XIV).
- Both Docker and AWS realizations must work and not break each other (Principle XV).
- **Red-first on expansion:** when a P1–P7 roadmap section is expanded into bite-sized tasks, every implementation task MUST open with a concrete failing test + a `run; expect fail` step in P0's format — red-first is inherited verbatim, not implied. Principle III/X is satisfied by the mandatory pre-PR `./bouy test` even though single-file iteration uses `./bouy exec app pytest`.
- **AWS observability is not deferrable past introduction (Principle XIV, NON-NEGOTIABLE):** the phase that first creates a Lambda / SQS queue / DynamoDB table adds its alarms + dashboard widgets + `infra/tests/` assertions *in that same phase* — never a later one.

**Endpoint path convention (resolves a design-doc shorthand):** discovery docs are root-level (`/.well-known/hsds-federation`, `/.well-known/did.json`, `/.well-known/webfinger`, the actor doc) because `did:web` and WebFinger require it; the data endpoints the design wrote as `/federation/*` are mounted under the v1 router as **`/api/v1/federation/export|state.txt|history`** and their absolute URLs are advertised in the discovery doc (OPR-style: endpoints are advertised, not fixed by convention), so partners never hard-code the prefix.

---

## Roadmap

| Phase | Outcome | Primary files | Acceptance | Ext. dep |
|---|---|---|---|---|
| **P0 Foundations** | Identity (incl. recovery-key schema §6.1a), discovery, **JCS canonicalization + RFC 9421/Ed25519 signing**, SSRF-hardened fetch, HSDS Profile. PPR is *discoverable*. | `app/federation/{__init__,identity,discovery,canonical,signing,fetch}.py`, `app/federation/routes_public.py`, `app/core/config.py`, `app/main.py`, `app/api/lambda_app.py`, `profiles/`, `app/api/v1/router.py:362` (the `/api/v1/federation/*` router package is created in P1, not P0) | discovery + did.json + webfinger + actor resolve in both envs; JCS vectors pass; 9421 signing round-trips; fetch helper rejects internal IPs; Profile URI resolves | none |
| **P0.5 De-risking spike (HARD GATE)** | Throwaway branch (deleted; nothing merged) proving: (a) dense-sequence append under genuinely concurrent reconciler commits — no skipped rows, no global serialization; (b) cold-start aggregate parity from raw tables; (c) a two-node loop on disposable code; (d) JCS+sign+Merkle write-path cost in the reconciler hot path. Deliverable: a one-page go/no-go memo. Contention → escalate to the design §6.2f relay/CDC fallback **before** P1. | spike branch only | go/no-go memo accepted by owner | none |
| **P1 Verifiable publish** | The design-§6.2 substrate: signed content-addressed objects, Merkle log, **signed checkpoints**, inclusion/consistency proofs; `/export`+`state.txt`+`/checkpoint`+`history`; hooks (job_processor matched/new-Location, **dedup scripts** `Delete`+`redirectTo`, submarine); **kill switch**; cold-start **verifiable snapshot** (raw tables, parity test); **archive tiering** (never destroy); **HSDS-FX spec extraction + fixtures/conformance suite + Readiness Checker + static-feed generator + in-repo reference second node + golden journey test**; Task 0 = `job_processor.py` decomposition (Principle IX, resolved: decompose). PPR is *verifiably readable*. | `app/federation/log.py`, `app/database/models.py`, migration, `app/reconciler/job_processor.py` (decomposed), `scripts/dedupe_*.py`, `app/reconciler/submarine_location_handler.py`, `app/api/v1/federation/`, `fixtures/federation/`, spec repo/artifact, `infra/` (prune/archive Lambda + alarm) | golden P1 journey: concurrent-append→pull→proof-verify→parity→archive boundary; kill-switch byte-identical test; fixtures validate; checkpoint consistency detects a rewritten log | none |
| **P2 Pull ingest** | Thin consumable enqueuer; consumer (PPR peers **with proof-verify before enqueue**; plain-HSDS snapshot-diff §6.6a); the §12.3 corrections + **§12.1 origin-dedup + CvRDT order-shuffle property test**; un-corroborated gating + **§11.6a equity caveat**; per-peer budget; injection hardening; shared idempotency; VALIDATOR_ENABLED routing; Task 0 = IX gate for `merge_strategy.py`/`location_creator.py`; P2 observability (pull-consumer Lambda + ingest SQS + DLQ + budget alarm). **Closes the loop with a real node #2.** | `app/federation/{enqueue,ingest}.py`, `app/reconciler/{merge_strategy,location_creator,job_processor}.py`, `app/llm/...`, `app/database/models.py` (peer+cursor via `CursorStore` protocol), `infra/` | **acceptance: PPR ingests + corroborates the live Feeding America HSDS 3.0 feed end-to-end**; golden P2 journey (origin-dedup 100-announces→1; lone-peer gated; equity caveat served); enqueued job consumable by the aligner | none (FA feed is live) |
| **P3 Push** | RFC-9421 inbox (own Lambda; pinned-key + object-sig + checkpoint-consistency verify; zero hot-path fetches) + outbound signed sender (DLQ) + per-DID rate-limit + **mass-anomaly alarms** + **peer-remove recovery** (confidence recompute + field revert); full XIV enumeration per resource. | `app/federation/{outbound,ingest}.py`, `infra/stacks/federation_stack.py`, `infra/stacks/monitoring_stack.py`, `infra/tests/` | golden P3 journey: signed push + concurrent pull → one `location_source` touch; bad sig/attribution/replay/consistency rejected; peer-remove demonstrably reverts a poisoned field | a partner accepting webhooks (PPR-to-PPR via the reference node) |
| **P4 Trust UX, PII & review-at-scale** | `./bouy federation` peer-add/remove/list/status (both key fingerprints + sample records); PII heuristic (flag-not-suppress for informal pantries) + takedown; **minimal `Flag` verb**; **Lighthouse claim/verify as a corroboration tier**; **prioritized review queue + auto-expiry + time-to-correct SLA** (design §11.12). | `bouy`, `app/federation/{cli,pii}.py`, queue integration | peer onboarding documented; PII-flagged held; takedown emits redaction; a `Flag` un-serves a bad record within SLA; Lighthouse claim satisfies the gate | none |
| **P5 VC trust** *(deferred)* | `Verify` verb, VC verification at FANO gate, `verified_by='network'`; replaces `fano_allowlist.tsv`. | `app/federation/vc.py`, `app/api/v1/partners/ptf/` | a valid FA VC bumps `verified_by='network'` | an issuer (FA) |
| **P6 Witness mesh + Regions/relay** *(committed)* | **Witness cosigning** (C2SP tlog-witness; allow-list peers as witnesses; HAARRRvest recast as first witness); Region/Group actors; `Announce` relay (object sigs make origin survive hops); outbound `Announce` emission; §12.2 provenance/freshness weighting + the surfaced **"confirmed by N orgs, M days ago"** field. | `app/federation/{witness,regions}.py`, HAARRRvest | split-view equivocation detected mesh-wide; a peer `Follow`s a region; confirmation signal served | 2+ peers |
| **P7 Hardening** *(deferred)* | RBSR anti-entropy (Negentropy); optional public-log anchoring (Sigsum/Rekor); full version negotiation; `Move`; recovery-key ceremony; full GDPR redaction; a non-PPR reference impl validating HSDS-FX. | various | mixed-version peers interoperate; a TS/Worker node proves implementation-independence | partner-driven |
| **Adoption packaging** *(STRETCH — design §8.6; not phase-gating)* | Publish the canonical **HSDS-FX conformance suite** as (a) a **vectors** package, (b) a **conformance-runner/validator** (`hsdsfx verify <url>`), (c) a **reference client/SDK** (Ed25519+JCS+RFC-6962+C2SP, extracted from `app/federation/` pure modules), and (d) a **clone-able reference-node image** — PyPI + npm — so adoption is a one-line install or app-reuse, never a re-implementation. Each package dog-foods the suite it ships. Matures with HSDS-FX extraction (P1) + the P2 reference node, toward the RFC. | `fixtures/federation/` → standalone HSDS-FX artifact; the §15 reference node → image | a fresh checkout `pip install hsdsfx && hsdsfx verify <our /export>` passes; an SDK-built envelope passes the vector suite | adopters / RFC |

---

## P0 — Foundations (fully task-decomposed; execute now)

**Branch:** `docs/hsds-federation-core-design` already carries the design + this plan (docs PR). Implementation work starts on a fresh branch off `main`: `feat/federation-p0-foundations`.

### Task 0.1: Federation config + package skeleton

**Files:**
- Create: `app/federation/__init__.py`
- Modify: `app/core/config.py` (add a new Settings field block before the `build_database_url_from_components` model_validator ~line 250 — NOTE the Validator block does not end at ~line 137; Validation-Rules + Enrichment settings follow it)
- Test: `tests/test_federation/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_federation/test_config.py
from app.core.config import Settings


def test_federation_settings_have_safe_defaults():
    s = Settings()
    assert s.FEDERATION_ENABLED is True            # on by default (driver 3)
    assert s.FEDERATION_DATE_SKEW_SECONDS == 300   # §8.3 replay window
    assert s.FEDERATION_RETENTION_DAYS == 365       # OPR SLA
    assert s.FEDERATION_INGEST_MAX_RECORDS_PER_PEER_PER_DAY > 0  # §11.3 budget
    assert s.FEDERATION_DID is None or s.FEDERATION_DID.startswith(("did:web:", "https://"))
```

- [ ] **Step 2: Run it; expect fail**

Run: `./bouy exec app pytest tests/test_federation/test_config.py -v`
Expected: FAIL (`AttributeError: 'Settings' object has no attribute 'FEDERATION_ENABLED'`).

- [ ] **Step 3: Implement minimal config**

```python
# app/core/config.py — add as a new field block inside class Settings (before the build_database_url model_validator)
    # Federation Settings (HSDS federation core)
    FEDERATION_ENABLED: bool = True
    FEDERATION_DID: str | None = None            # did:web:<domain> for this node; None disables publish identity
    FEDERATION_SIGNING_KEY: str | None = None    # Ed25519 private key (PEM/base64); secret — never committed
    FEDERATION_RETENTION_DAYS: int = Field(default=365, ge=1)
    FEDERATION_DATE_SKEW_SECONDS: int = Field(default=300, ge=1)
    FEDERATION_INGEST_MAX_RECORDS_PER_PEER_PER_DAY: int = Field(default=50_000, ge=1)
    FEDERATION_INGEST_MAX_LLM_JOBS_PER_PEER_PER_DAY: int = Field(default=50_000, ge=1)
    FEDERATION_EXPORT_PAGE_SIZE: int = Field(default=1000, ge=1, le=10_000)
```

```python
# app/federation/__init__.py
"""HSDS federation core. See docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md."""
```

- [ ] **Step 4: Run; expect pass**

Run: `./bouy exec app pytest tests/test_federation/test_config.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add app/federation/__init__.py app/core/config.py tests/test_federation/
git commit -m "feat(federation): add federation config settings and package skeleton"
```

### Task 0.2: SSRF-hardened egress helper (§11.1 — blocker)

**Files:**
- Create: `app/federation/fetch.py`
- Test: `tests/test_federation/test_fetch.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_federation/test_fetch.py
import pytest
from app.federation.fetch import is_blocked_ip, FederationFetchError


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254",  # IMDS
    "100.64.0.1",        # CGNAT
    "::1", "fc00::1", "fe80::1",
])
def test_internal_ips_are_blocked(ip):
    assert is_blocked_ip(ip) is True


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "2606:4700::1111"])
def test_public_ips_are_allowed(ip):
    assert is_blocked_ip(ip) is False


async def test_fetch_rejects_non_https():  # asyncio auto-mode; no explicit marker (ruff PT)
    with pytest.raises(FederationFetchError):
        from app.federation.fetch import hardened_get
        await hardened_get("http://example.com/x")  # http -> reject
```

- [ ] **Step 2: Run; expect fail**

Run: `./bouy exec app pytest tests/test_federation/test_fetch.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# app/federation/fetch.py
"""Single hardened egress helper for ALL federation outbound HTTP (SSRF guard, §11.1)."""
import ipaddress
import socket

import httpx

_MAX_BYTES = 5 * 1024 * 1024
_MAX_REDIRECTS = 3
_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


class FederationFetchError(Exception):
    """Raised when a federation fetch is rejected or fails safety checks."""


def is_blocked_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        return True
    if addr.is_multicast or addr.is_unspecified:
        return True
    # CGNAT 100.64.0.0/10 (not flagged is_private)
    if addr.version == 4 and addr in ipaddress.ip_network("100.64.0.0/10"):
        return True
    return False


def _resolve_and_validate(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FederationFetchError(f"DNS resolution failed for {host}") from exc
    for info in infos:
        ip = info[4][0]
        if is_blocked_ip(ip):
            raise FederationFetchError(f"blocked internal IP {ip} for host {host}")


async def hardened_get(url: str) -> httpx.Response:
    """HTTPS-only GET with internal-IP blocking, redirect cap + per-hop revalidation, size cap."""
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        parsed = httpx.URL(current)
        if parsed.scheme != "https":
            raise FederationFetchError(f"non-https URL rejected: {current}")
        if parsed.host is None or _is_ip_literal(parsed.host):
            raise FederationFetchError("IP-literal or hostless URL rejected")
        _resolve_and_validate(parsed.host)
        async with httpx.AsyncClient(follow_redirects=False, timeout=_TIMEOUT) as client:
            resp = await client.get(current)
        if resp.is_redirect and resp.has_redirect_location:
            current = str(resp.next_request.url)  # revalidate next hop on loop
            continue
        if int(resp.headers.get("content-length", 0)) > _MAX_BYTES:
            raise FederationFetchError("response exceeds size cap")
        return resp
    raise FederationFetchError("too many redirects")


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False
```

> Note for the executing agent: the DNS-rebinding pin (connect to the *validated* IP while preserving SNI/Host) is a hardening refinement — implement via an httpx transport that connects to the resolved IP. The IP-range validation is the tested core here. The response **size cap** is likewise header-only/post-buffer in P0 (`content-length` is optional and the body is already buffered); replace it with `client.stream()` + an incremental byte counter that aborts past `_MAX_BYTES`. Add the connect-pin AND the streaming hard-cap (each with a test) when wiring real peer fetches in P2/P3 — both are deferred together, neither forgotten.

- [ ] **Step 4: Run; expect pass.** `./bouy exec app pytest tests/test_federation/test_fetch.py -v` → PASS.
- [ ] **Step 5: Commit.** `git commit -am "feat(federation): SSRF-hardened egress helper (§11.1)"`

### Task 0.3: JCS canonicalization (RFC 8785) + RFC 9421/Ed25519 HTTP Message Signatures (§8.3 — RESOLVED v3)

**Files:**
- Create: `app/federation/canonical.py`, `app/federation/signing.py`
- Test: `tests/test_federation/test_canonical.py`, `tests/test_federation/test_signing.py`

- [ ] **Step 1: Write the failing tests** (canonicalization first — every byte that is hashed or signed flows through it)

```python
# tests/test_federation/test_canonical.py
from app.federation.canonical import jcs_bytes


def test_jcs_orders_keys_and_strips_whitespace():
    # RFC 8785: lexicographic key order, no insignificant whitespace, UTF-8
    assert jcs_bytes({"b": 1, "a": "ü"}) == '{"a":"ü","b":1}'.encode()


def test_jcs_is_stable_across_dict_insertion_order():
    assert jcs_bytes({"x": [2, 1], "a": True}) == jcs_bytes(dict([("a", True), ("x", [2, 1])]))
```

```python
# tests/test_federation/test_signing.py
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app.federation.signing import build_signature_base, sign_request, verify_request, SignatureError
import pytest


def _keys():
    priv = Ed25519PrivateKey.generate()
    return priv, priv.public_key()


def test_signature_base_is_rfc9421_shaped():
    base = build_signature_base(
        method="POST", target_uri="https://h.example/federation/inbox",
        content_digest="sha-256=:abc=:", created=1780600000,
        keyid="did:web:h.example#main-key",
    )
    assert '"@method": POST' in base
    assert '"@target-uri": https://h.example/federation/inbox' in base
    assert base.rstrip().endswith(
        '"@signature-params": ("@method" "@target-uri" "content-digest")'
        ';created=1780600000;keyid="did:web:h.example#main-key";alg="ed25519"'
    )


def test_sign_then_verify_roundtrips_and_rejects_tamper():
    priv, pub = _keys()
    headers = sign_request(priv, "did:web:h.example#main-key", "POST",
                           "https://h.example/federation/inbox", body=b'{"x":1}', created=1780600000)
    assert {"Content-Digest", "Signature-Input", "Signature"} <= set(headers)
    verify_request(pub, "POST", "https://h.example/federation/inbox", headers,
                   body=b'{"x":1}', max_skew_seconds=300, now=1780600060)
    with pytest.raises(SignatureError):
        verify_request(pub, "POST", "https://h.example/federation/inbox", headers,
                       body=b'{"x":2}', max_skew_seconds=300, now=1780600060)
```

- [ ] **Step 2: Run; expect fail.** `./bouy exec app pytest tests/test_federation/test_canonical.py tests/test_federation/test_signing.py -v` → FAIL.
- [ ] **Step 3: Implement.** `canonical.py`: `jcs_bytes()` via the `rfc8785` PyPI library if it passes the Principle-VII supply-chain vet (bandit/safety/pip-audit), else a minimal RFC 8785 serializer (sorted keys, JSON number normalization, UTF-8, no whitespace). `signing.py`: `build_signature_base` per RFC 9421 §2.5 over covered components `("@method" "@target-uri" "content-digest")` with `created`/`keyid`/`alg` params; `sign_request` computes **RFC 9530 `Content-Digest`** (`sha-256=:base64(sha256(body)):` structured-field byte-sequence), builds the base, Ed25519-signs, returns `Content-Digest`/`Signature-Input`/`Signature` headers; `verify_request` recomputes the digest (reject mismatch), checks `created` within `±max_skew_seconds` of `now`, rebuilds the base, verifies (`InvalidSignature`→`SignatureError`). Consider the `http-message-signatures` PyPI package — vet it; else implement the minimal Ed25519 profile only. NOTE: the envelope **object** signature (`proof`, design §6.2a) reuses `canonical.py` + the same key in P1 — design both modules with that consumer in mind.
- [ ] **Step 4: Run; expect pass.**
- [ ] **Step 5: Commit.** `git commit -am "feat(federation): JCS canonicalization + RFC 9421 Ed25519 HTTP Message Signatures (§8.3)"`

### Task 0.4: Identity — did.json, actor doc, key loading

**Files:** Create `app/federation/identity.py`; Test `tests/test_federation/test_identity.py`.

- [ ] **Step 1: Failing test** — assert `build_did_document(did="did:web:h.example", public_key_multibase=...)` returns a dict with `id == "did:web:h.example"`, a `verificationMethod` entry whose `id` is `did:web:h.example#main-key` and `type` `Ed25519VerificationKey2020`, and `alsoKnownAs` containing the actor URL; assert `load_signing_key(None)` returns `None` and `load_signing_key(<pem>)` returns an `Ed25519PrivateKey`; assert `build_actor(did, domain)` returns `{id, type:"Service", inbox, outbox, publicKey}`.
- [ ] **Step 2: Run; fail.**
- [ ] **Step 3: Implement** `build_did_document`, `build_actor`, `load_signing_key`, `public_key_multibase` helpers. `verificationMethod` is an **ORDERED list with an explicit `priority` attribute** supporting N≥2 keys: the online signing key plus ≥1 higher-priority offline **recovery key** (design §6.1a — did:plc-inspired; the verify-side priority rule ships in P3, the schema is forward-compatible now). Include a recovery-key entry in the test fixture.
- [ ] **Step 4: Run; pass.**
- [ ] **Step 5: Commit.** `git commit -am "feat(federation): did:web document, actor, Ed25519 key loading"`

### Task 0.5: Discovery document (`.well-known/hsds-federation`)

**Files:** Create `app/federation/discovery.py`; Test `tests/test_federation/test_discovery.py`.

- [ ] **Step 1: Failing test** — `build_discovery_doc(settings)` returns a dict with keys `did`, `jwks_or_key_location`, `hsds_versions` (a LIST, per design §8.4 set-membership — asserted against a `FEDERATION_HSDS_VERSIONS` setting, NOT a hardcoded string; **baseline note (v3.1): the vendored spec submodule is HSDS v3.2.3 while `router.py:362` advertises 3.1.1 — this task includes verifying what the code actually implements and setting the advertised version(s) accordingly**), `profile_uri`, `endpoints.export`, `endpoints.inbox`, `endpoints.history`, `allow_list_policy in {"open","mutual","private"}`, `retention_days==settings.FEDERATION_RETENTION_DAYS`, `contact`.
- [ ] **Step 2: Run; fail.**
- [ ] **Step 3: Implement** `build_discovery_doc`; endpoint URLs are absolute, derived from the node domain (OPR-advertised, §endpoint-convention).
- [ ] **Step 4: Run; pass.**
- [ ] **Step 5: Commit.** `git commit -am "feat(federation): .well-known/hsds-federation discovery document"`

### Task 0.6: WebFinger

**Files:** Create `app/federation/identity.py` addition `build_webfinger(resource, actor_url)`; Test extends `test_identity.py`.

- [ ] **Step 1: Failing test** — `build_webfinger("acct:north-jersey-fb@h.example", "https://h.example/federation/actor")` returns a JRD with `subject` and a `links` entry `{rel:"self", type:"application/activity+json", href:<actor_url>}`.
- [ ] **Step 2–5:** implement, run, commit. `git commit -am "feat(federation): WebFinger JRD responder"`

### Task 0.7: Wire root-level public routes into both apps (m2 / Principle XV)

**Files:**
- Create: `app/federation/routes_public.py` (a `register_federation_public_routes(app)` helper)
- Modify: `app/main.py` (after line 78), `app/api/lambda_app.py` (after line 66)
- Test: `tests/test_federation/test_public_routes.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_federation/test_public_routes.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.federation.routes_public import register_federation_public_routes


def _client():
    app = FastAPI()
    register_federation_public_routes(app)
    return TestClient(app)


def test_well_known_discovery_served():
    r = _client().get("/.well-known/hsds-federation")
    assert r.status_code == 200
    assert isinstance(r.json()["hsds_versions"], list)  # §8.4 set-membership; pinned to the 3.2 line (see Task 0.5)


def test_did_json_served():
    r = _client().get("/.well-known/did.json")
    assert r.status_code in (200, 404)  # 404 only if FEDERATION_DID unset; 200 when configured


def test_webfinger_requires_resource():
    assert _client().get("/.well-known/webfinger").status_code == 422
```

- [ ] **Step 2: Run; fail.**
- [ ] **Step 3: Implement** `register_federation_public_routes(app)` registering root GETs for `/.well-known/hsds-federation`, `/.well-known/did.json` (404 when `FEDERATION_DID` unset), `/.well-known/webfinger` (`resource` query required → 422 if absent), and the actor doc; call it from `app/main.py` and `app/api/lambda_app.py`. Confirm `routes_public.py` imports only `app.federation.{identity,discovery}` (no Redis/LLM) so the slim Lambda stays slim.
- [ ] **Step 4: Run; pass.** Also run `./bouy exec app pytest tests/test_federation/ -v` (whole package green).
- [ ] **Step 5: Commit.** `git commit -am "feat(federation): serve .well-known discovery/did/webfinger/actor in both apps"`

### Task 0.8: HSDS Profile files + replace router profile URI (M12 / Principle II)

**Files:**
- Create: `profiles/hsds-ppr/location.json`, `profiles/hsds-ppr/service.json` (RFC-7386 merge patches adding optional `confidence_score`, `verified_by`, `sources`), `profiles/hsds-ppr/openapi.json` (patch adding `/api/v1/federation/*` paths), `profiles/hsds-ppr/README.md`
- Modify: `app/api/v1/router.py:362`
- Test: `tests/test_federation/test_profile.py`

- [ ] **Step 1: Failing test** — assert the API root (`GET /api/v1/`) `profile` field is no longer the generic `docs.openhumanservices.org/hsds/` and points at the PPR profile; assert each profile patch is valid JSON and `location.json` adds only optional properties (none in HSDS core `required`).
- [ ] **Step 2: Run; fail.**
- [ ] **Step 3: Implement** the merge-patch files (permitted modifications per `docs/HSDS/docs/hsds/profiles.md`: new optional props only), **based against the HSDS 3.2 line (vendored submodule is v3.2.3 — design §7 baseline note)**; set `router.py:362` profile to the canonical PPR profile URI (same host as `@context`).
- [ ] **Step 4: Run; pass.**
- [ ] **Step 5: Commit.** `git commit -am "feat(federation): publish multi-file HSDS Profile; resolve profile URI (§7,M12)"`

### Task 0.9: Docs + full gate (Principle XIII, X)

- [ ] **Step 1:** Update `CLAUDE.md`: add a "Federation (core)" subsection — the `.well-known` discovery surface, the (forthcoming) `./bouy federation` family, `source_type='federated_node'`, and a placeholder for the `federation_*` structlog grep targets (filled in P1+).
- [ ] **Step 2:** Run the full gate: `./bouy test` (black, ruff, mypy, bandit, pytest, coverage ratchet). Fix any failures.
- [ ] **Step 3: Commit + open PR.**

```bash
git add -A && git commit -m "docs(federation): document P0 federation surface in CLAUDE.md"
gh pr create --base main --title "feat(federation): P0 foundations — identity, discovery, signing, SSRF guard, HSDS Profile" --body "Implements P0 of docs/superpowers/plans/2026-06-03-hsds-federation-core.md"
```

**P0 acceptance:** discovery/did.json/webfinger/actor resolve in both Uvicorn and the slim Lambda (did.json carries the ordered recovery-key schema); JCS vectors pass; RFC 9421 signing round-trips and rejects tampering; the fetch helper blocks internal IPs and non-HTTPS; the PPR HSDS Profile URI resolves; `./bouy test` green.

---

## P0.5 — De-risking spike (HARD GATE; throwaway by design)

**Rule:** a disposable branch (`spike/federation-p05`); **nothing merges; the branch is deleted after.** Deliverable: a one-page **go/no-go memo** committed to `docs/superpowers/research/`, reviewed by the owner before P1 begins. Rationale: the plan otherwise first proves its riskiest assumptions inside the real P1/P2 build, entangled with a 1892-line file (steelman rank 1).

**Prove, together, on the thinnest vertical slice:**
1. **Sequencer under real concurrency** — two reconciler workers committing interleaved: a consumer at `_since=N` never skips a late-committing row AND the per-resource commit is not globally serialized; measure append-lock contention at realistic write rates.
2. **Cold-start aggregate parity** — rebuild one Location aggregate from the **raw normalized tables** in the HAARRRvest SQLite export; byte-compare to the live Beacon-shaped aggregate.
3. **Two-node loop** — process A appends to a `federation_log`; process B pulls `/export` by sequence and lands a `federated_node` `location_source` row.
4. **Verifiable-substrate write cost (v3)** — JCS-canonicalize + Ed25519-sign + Merkle-append in the reconciler hot path; measure added latency per commit (budget: low single-digit ms).

**Go/no-go:** contention or a missed-row edge → escalate to the design-§6.2f single-writer-relay / CDC(LSN) fallback **before** P1; write-cost overrun → coalesce checkpoint signing off the commit path and re-measure. The memo records the chosen path; P1's verifiable-log work depends on a green sequencer result.

---

## P1 — Publish (roadmap; expand to bite-sized at session start)

**Objective:** write the `federation_log` at the canonical-commit points and serve sequence-numbered deltas, so PPR is readable on the network. **Design refs:** §6.2, §6.3, §8, §9 Delete.

> **v3 DELTA (binding — the roadmap row + design §6.2/§17 are authoritative over the task list below, which predates the verifiable-substrate decision):** P1 now builds the **verifiable log**: every appended activity is a JCS-canonical, content-addressed (`id`), **origin-signed** (`proof`) object; sequence is **dense** (= Merkle leaf index) under the short append lock; a **signed checkpoint** (C2SP signed-note) is published in `state.txt` + `/federation/checkpoint`; `/export` rows carry **inclusion proofs** and consumers verify **consistency** across pulls. Task 9's "retention prune" becomes **archive tiering** (design §6.2g — never destroy; live Postgres window + S3 archive; tree state retained). New P1 deliverables: the **kill switch** (FEDERATION_ENABLED no-op at every hook site + the byte-identical-reconciler test, design §6.2d), **HSDS-FX spec extraction** + governance section, the **conformance suite / hosted Readiness Checker / static-feed generator** (DRY with `fixtures/`), the **in-repo reference second node**, the **golden P1 journey test** (concurrent-append→pull→proof-verify→parity→archive boundary, incl. a tampered-log case), and the **cold-start backfill** task ensuring `_since=0` covers ALL pre-existing canonical rows. **v3.1:** before the HSDS-FX extraction task, **crosswalk the envelope vocabulary** (`actor`/`attributedTo`/`origin`) to Open Referral's in-flight BODS-inspired publisher/steward/source model (spec issues #558/#553/#508) and carry `org-id.guide` identifiers alongside `did:web` (design §7/§8.5); pin `@context`/Profile/fixtures to the **3.2 line** (vendored baseline v3.2.3). The §8.5 engagement wedge (contribute to #558; propose the extend-`last_modified` and tombstone PRs upstream) can start during P1. Expand these into bite-sized tasks at session start per the living-plan contract.

**File-map:** `app/federation/log.py` (append + safe-high-water + retention + export/state/history queries); `app/database/models.py` (+`FederationLog`); a DB migration; `app/reconciler/job_processor.py` (call the log helper at the matched-Location and new-Location commit sites); `scripts/dedupe_near_duplicate_locations.py` + `scripts/dedupe_same_org_locations.py` (**the real soft-delete site** — append `Delete`+`redirectTo` at the `is_canonical=FALSE` UPDATE + `dedup_run_audit` insert; reuse Beacon `_resolve_terminal` survivor chain); `app/reconciler/submarine_location_handler.py` (enrichment → `Update`); `app/api/v1/federation/{__init__,router}.py` (`export`/`state.txt`/`history`, included in `app/api/v1/router.py`); `fixtures/federation/` (canonical activity examples + JSON Schema); `infra/stacks/federation_stack.py` + `infra/stacks/monitoring_stack.py` + `infra/tests/` (the retention-prune EventBridge Lambda + its alarm).

**Tasks (each → red-first failing test + impl + commit when expanded):**
0. **Principle-IX gate (binary, do FIRST).** The `Update` hooks land in `job_processor.py` (1892 lines, >600). Either (a) extract the matched/new-Location commit branch into a focused sub-module under 600 lines with tests green, OR (b) author `docs/superpowers/specs/federation-principle-ix-exception.md` with the written justification + simpler-alternatives-considered (Governance clause) and link it in the PR. Also fix the stale constitution §IX table entry (1568 → 1892). Recommended: (a).
1. `FederationLog` model + migration — columns per §6.2; index on `sequence`. Test: insert + query by `_since`.
2. Append helper. **Lock scoped to ONLY the sequence allocation + INSERT** (short critical section), NOT the reconciler resource commit, so the parallel write path is preserved; **safe-high-water** = top of the gap-free committed prefix. Tests: (i) simulate out-of-order commit → consumer at `_since=N` never skips the late row (the M5 hazard); (ii) assert the per-resource reconciler commit is NOT globally serialized (no whole-commit lock held). Note for expansion: if load testing shows contention, escalate to a single-writer relay assigning sequences off the hot path (design §6.2).
3. Build the **Location aggregate** serializer (§8.2) — Location + embedded schedules/phones/addresses/languages/accessibility/services-at-location — reusing Beacon/PTF shaping. Test: aggregate matches HSDS Pydantic models; `federation_id`/`attributedTo` are in the envelope, NOT the object (m1).
4. Hook the matched-Location + new-Location commit sites in `job_processor.py` to append an `Update`; **publish-side echo suppression** (commit driven solely by `federated_node` appends nothing — m7). Test: PPR-origin commit appends; pure-federated commit does not.
5. **Delete derivation (corrected — real site).** Hook the soft-delete in the **offline dedup backfill scripts** (`scripts/dedupe_*.py`) at the `is_canonical=FALSE` UPDATE + `dedup_run_audit` insert, appending a `federation_log` `Delete` with `redirectTo`=survivor `federation_id`. The reconciler's inline Tier-3 path is prevent-on-ingest (no soft-delete) — do NOT hook it. The append must run in the script context (no reconciler worker), so `log.py`'s append helper takes a plain DB session. Test: a script soft-delete emits a `Delete` whose `redirectTo` resolves through the `dedup_run_audit` survivor chain (Beacon `_resolve_terminal`).
6. Hook `submarine_location_handler.update_location` to append `Update`. Test: submarine enrichment emits a federation_log row.
7. `/api/v1/federation/export` (keyset pagination, `X-Federation-Next-Cursor`, `X-Federation-Sequence`=safe-high-water, `_since<horizon`→410), `state.txt`, `history`. Reuse Beacon `is_canonical`+confidence gate. Test: delta pull by sequence; 410 boundary.
8. **Cold-start `_since=0`** served from the HAARRRvest S3/SQLite snapshot (M8). **Rebuild the §8.2 aggregate from the RAW normalized tables in the export** (location+schedule+phone+address+language+accessibility+service_at_location+service) — NOT the lossy `location_master` materialized view (it collapses schedules via `DISTINCT ON` and string-aggregates phones/languages). Test: cold-start aggregate byte-equals the live `/export` aggregate for the same `federation_id` (round-trip parity, so a flattened-view shortcut fails CI).
9. **Retention prune (dual-env, Principle XV).** Prune `federation_log` older than the SLA; set `retention_horizon_sequence` = `min(sequence)` of survivors; expose in `state.txt`. AWS: an **EventBridge-scheduled Lambda** (HAARRRvest-publisher cadence); Docker: a **bouy-invoked worker/loop**. Test: prune + `410` boundary in both realizations.
10. **Observability for P1 AWS constructs (Principle XIV).** Add the retention-prune Lambda's Error alarm + a dashboard widget routed to `pantry-pirate-radio-alerts-{env}` on `PantryPirateRadio-{env}`, with an `infra/tests/` assertion. (The pull-consumer Lambda + ingest SQS alarms are P2's, added there.)
11. Normative **wire spec + JSON Schema + `fixtures/`** (§8); envelope key `type`; `@context` exact-match→422; the `Date` field is RFC-3339 per §8.3, pinned byte-exactly in a fixture. Tests validate fixtures against the schema.
12. Docs: CLAUDE.md export contract + the `federation_*` structlog grep targets; `./bouy test`.

**Constitution touchpoints:** IX (resolved by Task 0, not gestured), III (every task red-first), XII (structlog taxonomy), XIV (Task 10), XV (export on both Uvicorn + Lambda; cold-start via S3; dual-env prune).

**P1 acceptance:** a second process pulls `/export?_since=<cursor>` and receives exactly the activities committed since, in order, with no skips under concurrent reconciler writes; a dedup-script soft-delete and a Submarine enrichment both surface (the former as `Delete`+`redirectTo`); cold-start parity holds; fixtures validate; the retention-prune Lambda has its XIV alarm + infra test.

---

## P2 — Pull ingest + the reconciler corrections (roadmap)

**Objective:** ingest a peer (PPR or plain-HSDS) into the reconciler as `federated_node`, correctly and safely. **Closes the two-node loop — with a real node #2.** **Design refs:** §6.5a, §6.6, §6.6a, §11.2/3/5/6, §11.6a, §12.

> **v3 DELTA (binding):** (a) **acceptance is concrete** — PPR ingests + corroborates **the live Feeding America HSDS 3.0 feed** end-to-end via §6.6a (the adoption spearhead; no recruitment needed); (b) PPR-peer ingest **verifies object signature + inclusion + checkpoint consistency before enqueue**; (c) corroboration dedups by **ORIGIN** (§12.1) — see amended Task 4; (d) the **§11.6a equity caveat** is a new task: a plausibly-real single-source low-density Location is served *with a visible "unconfirmed" caveat* instead of gated invisible, with `federation_equity_caveat_served` instrumentation; (e) the **§12.1 CvRDT order-shuffle Hypothesis property test** is a new task (shuffled arrival order across N simulated peers → byte-identical canonical Location); (f) **field-change anomaly detection** (§11.11: coordinate jump >2 km / contact-hours flip against standing corroboration → demote-and-flag) lands here with its alarm.

**File-map:** `app/federation/enqueue.py` (thin LLMJob enqueuer — no `ScraperUtils`, Content-Store dedup, `QUEUE_BACKEND` redis/sqs); `app/federation/ingest.py` (pull consumer: PPR `/export` keyset + plain-HSDS snapshot-diff §6.6a; inbox activity router shared); `app/reconciler/merge_strategy.py` (corroboration widened to count distinct `federated_node` peer DIDs — §12/§11.2); `app/reconciler/location_creator.py` (new partial unique index + `ON CONFLICT` target for `federated_node`; exact-`federation_id` lookup before coordinate tiers — m9); `app/reconciler/job_processor.py` (federated `Update` cannot overwrite `verified_by∈{admin,source,claimed}` — M3); `app/llm/...` (delimit untrusted peer free-text — §11.5); `app/database/models.py` (`federation_peer`, `federation_peer_cursor`); `infra/stacks/federation_stack.py` + `infra/stacks/monitoring_stack.py` + `infra/tests/` (pull-consumer Lambda + ingest SQS + DLQ alarms).

**Tasks (each → red-first failing test + impl + commit):**
0. **Principle-IX gate (binary, do FIRST).** P2 edits `merge_strategy.py` (888 lines) and `location_creator.py` (968 lines), both >600. For each file being edited: either (a) extract the touched responsibility under 600 lines (tests green), OR (b) author/extend the `federation-principle-ix-exception.md` memo with the specific justification per Governance. Make the choice binding before adding the §12 corrections below.
1. `federation_peer` + `federation_peer_cursor` models + migration. **One shared inbound idempotency key `(actor, sequence)`** (used by both pull and the P3 inbox), per-peer budget counters, per-peer pull/push cursors. (NOTE: this is a new schema — `ptf_broker_sync_state` is keyed `PRIMARY KEY(location_id)` and is only a *pattern* reference, not the shape.)
2. **Thin, CONSUMABLE enqueuer.** Produce the same `LLMJob` envelope the scrapers produce — including a valid `format` (HSDS schema) and `prompt` (aligner) so the LLM worker can actually align it — by loading the schema CSV + aligner prompt **once at module import** (static files; no `ScraperUtils`, no Redis at import). For already-structured plain-HSDS peer records, take the cheaper alignment path (§6.6a/§11.5) instead of full free-form alignment; state which records take which path. Tests: (i) slim-import — `import app.federation.enqueue` pulls in no Redis/`ScraperUtils` at import time (Principle XV); (ii) consumable — an enqueued federation job carries non-empty `format`+`prompt` an aligner worker accepts (envelope ref: `app/llm/queue/job.py` `LLMJob`, worker read at `app/llm/queue/processor.py`). Content-Store SHA-256 dedup applied here (Principle VIII).
3. **VALIDATOR_ENABLED routing (M4).** Federated ingest routes through `should_use_validator()` exactly like scraped data; with `VALIDATOR_ENABLED` off, a `federated_node` record still gets confidence scoring + `VALIDATION_REJECTION_THRESHOLD` enforcement (NOT bypassed) — Principle VI. Test: a federated job with the validator off lands at the reconciler with a scored confidence and is subject to the rejection threshold (`should_use_validator` defaults False via `getattr` even though config defaults True — lock this in).
4. **Corroboration correction (§12.1/§11.2 — origin-deduped)** — widen `merge_location` to count distinct **ORIGINS** (the envelope's carried `origin` DID, not the announcing actor); pin `scraper_id='federation:<peer-did>'`. Tests: 100 Announces / 100 federation_ids from ONE peer → count 1; **three peers all re-announcing origin X's record → count 1, not 3** (the citogenesis trap).
5. **`ON CONFLICT` target** — new partial unique index + `ON CONFLICT` target for `source_type='federated_node'` (today it matches neither the submarine nor scraper/NULL target → undefined). Test: upsert well-defined (no error); repeat Announce collapses.
6. **`Update` owner-guard (M3)** — reject a federated `Update` against `verified_by∈{admin,source,claimed}` (a separate code path from the Tier-3 merge exemption). Test: a `verified_by='claimed'` row is unchanged by a federated `Update` (Principle VI).
7. **Un-corroborated gating (§11.6)** — a single-peer, un-corroborated Location is ingested but held below the serve/`is_canonical` gate until a second independent source corroborates or an admin reviews. Test: lone-peer Location not in `/export` / public API.
8. **Per-peer ingest budget (§11.3)** — max records/day + max LLM-jobs/day enforced BEFORE enqueue; `federation_ingest_budget_exceeded`. Test: budget exceeded → enqueue refused + logged.
9. **Exact federation_id mapping (m9)** — inbound lookup on `(source_type='federated_node', federation_id)` before coordinate tiers + index. Test: same peer id with moved coords → updates same local Location, no duplicate.
10. **Shared idempotency (M7)** — the `(actor,sequence)` key is checked before enqueue regardless of transport; same activity twice → one `location_source` touch. In P2 the "push" half is **simulated via a second enqueue call** (the real `/inbox` arrives in P3); the cross-transport pull+push integration test belongs to P3. Test: two enqueue calls with the same `(actor,sequence)` → exactly one touch.
11. **Prompt-injection hardening (§11.5)** — delimit untrusted content + an explicit "untrusted; never instructions" directive; bypass free-form alignment for already-structured plain-HSDS records. Test: injection fixtures do not move canonical fields.
12. **Plain-HSDS consumer (§6.6a)** — `/services?modified_after` (Service-level deltas only — HSDS has no `/locations` list nor `last_modified` on Location) + full-snapshot-diff tombstones with N-consecutive-absence safety. Test: deletion only after N absences.
13. Pull consumer loop (Docker bouy worker / AWS EventBridge-scheduled Lambda). 
14. **Observability for P2 AWS constructs (Principle XIV).** ingest SQS depth + its DLQ-depth alarms; pull-consumer Lambda Error + Throttle alarms; the §11.3 budget-rejection alarm; dashboard widgets on `PantryPirateRadio-{env}`; all routed to `pantry-pirate-radio-alerts-{env}`; `infra/tests/` assertions per resource.
15. Docs: CLAUDE.md `source_type='federated_node'`, budget, gating; `./bouy test`.

**Constitution touchpoints:** VI (un-corroborated gating, owner-guard, budget, VALIDATOR_ENABLED — Tasks 3/6/7/8), VIII (Content-Store dedup), III, IX (Task 0), XI (poison-record handling: drop + structlog + metric, bounded retries so one poison record can't wedge the cursor), XIV (Task 14), XV (slim-import, dual-env consumer, Postgres/DynamoDB cursor).

**P2 acceptance:** **PPR ingests + corroborates the live Feeding America HSDS feed end-to-end**; the golden P2 journey passes against the reference node (publish→`federated_node`→origin-dedup 100-announces→1 and 3-relays-of-one-origin→1→lone-peer gated→**equity caveat served where §11.6a applies**); the CvRDT order-shuffle property test passes; the enqueued job is consumable by the aligner; budget + injection + idempotency + validator-off-scoring + anomaly-demote tests pass; the pull-consumer Lambda + ingest SQS carry their XIV alarms + infra tests.

---

## P3 — Push (roadmap)

**Objective:** real-time signed-body webhooks. **Design refs:** §6.5, §11.1 (pinned-key, no inbox I/O), §11.4, §11.6, §14.

**File-map:** `app/federation/outbound.py` (read new `federation_log`, build signed activities, deliver to peers' inboxes, per-peer push high-water, retry/backoff, DLQ); `app/federation/ingest.py` (inbox router: verify against **pinned** `federation_peer.public_key` — zero network I/O; allow-list; `actor==attributedTo`; `(actor,sequence)` dedup + strictly-increasing; budget; rate-limit); `infra/stacks/federation_stack.py` (inbox Lambda — own non-slim image; outbound sender Lambda + DLQ; ingest SQS + DLQ; DynamoDB cursor); `infra/stacks/monitoring_stack.py` + `infra/tests/` (alarms + widgets — Principle XIV).

**Tasks:** inbox verify/guard chain (tests for each rejection reason → `federation_inbox_rejected_{signature,allowlist,attribution,replay,version}`); outbound sender + DLQ; **peer-remove recovery (§11.4)** — recompute confidence dropping the removed DID's votes + revert fields last-written by that DID (model on `scripts/undo_dedup_run.py`); **anomaly detector (§11.6)** — mass Delete/Update per peer → alarm; CDK stacks + monitoring (**copy design §14's enumeration item-by-item**: each new Lambda → Errors+Throttles alarms; each new SQS → DLQ-depth + queue-depth; the DynamoDB cursor → throttle + system-error; dashboard widgets; one `infra/tests/` assertion per resource class; all routed to `pantry-pirate-radio-alerts-{env}`); docs + `./bouy test`.

**P3 acceptance:** a signed push is verified with no outbound fetch, dedups idempotently with the pull path, rejects bad signature/attribution/replay; peer-remove demonstrably reverts a poisoned field; alarms exist in `infra/tests/`.

---

## P4 — Trust UX & PII (roadmap)

**Objective:** the operator surface + PII minimums + **review-at-scale** (v3). **Design refs:** §6.7, §11.8, §11.12.

> **v3 DELTA (binding):** P4 additionally ships: a **minimal `Flag`/dispute verb** (pulled forward from P6) so a refutation can un-serve a bad record as fast as corroboration serves one, with mesh-wide retraction propagation and a published, instrumented **time-to-correct SLA**; the **existing Lighthouse claim/verify flow wired in as a corroboration tier** (an owner-claim or source-confirm satisfies the §11.6 gate immediately — consume the existing flow, don't invent a parallel queue); and the **prioritized review queue** (served-population-impact × uncertainty × staleness, reusing `pick_next_scraper_task.py`'s population weighting; auto-expiry so nothing silently sticks). Peer-add shows **both** the signing and recovery key fingerprints (§6.1a).

**File-map:** `bouy` (+ `federation` command group) and `app/federation/cli.py`; `app/federation/pii.py`.

**Tasks:** `./bouy federation peer-add/remove/list/status` (peer-add fetches discovery via the hardened helper, shows fingerprint + retention + **sample records**, approves → allow-list row; peer-remove triggers P3 recovery); PII ingest heuristic (personal-email/non-business-phone → flag not auto-publish); takedown path (peer-remove + purge/redact exported + emit redaction `Delete`); docs + `./bouy test`.

**P4 acceptance:** peer onboarding is a documented `bouy` flow; a PII-flagged record is held, not published; a takedown emits a redaction and purges exports.

---

## P5–P7 (roadmap only — see design §17)

P5 VC trust *(deferred — needs an issuer)*: FA issues a FANO VC → `Verify` → `verified_by='network'`, replacing `fano_allowlist.tsv`. **P6 Witness mesh + Regions/relay *(committed, needs 2+ peers)***: witness cosigning (C2SP tlog-witness; allow-list peers as mutual witnesses; **HAARRRvest recast from privileged relay to the first, lowest-trust witness**) making split-view equivocation detectable mesh-wide; FEP-1b12 Region/Group actors; `Announce` relay (object signatures carry origin natively); outbound `Announce` emission; the §12.2 provenance-weighted, freshness-decayed corroboration + the served **"independently confirmed by N orgs in the last M days"** signal. P7 hardening *(partner-driven)*: RBSR anti-entropy (Negentropy), optional public-log anchoring (Sigsum/Rekor), full version negotiation, `Move`, the recovery-key ceremony, full GDPR redaction, and a non-PPR reference implementation validating HSDS-FX.

**Adoption packaging *(STRETCH — design §8.6; not phase-gating, owner-requested 2026-06-06)***: publish the canonical HSDS-FX conformance suite + tooling as installable packages (vectors, `hsdsfx verify` runner/validator, a reference client/SDK extracted from the `app/federation/` pure modules, and a clone-able reference-node image) on PyPI + npm, so a partner adopts with a one-line install — or by reusing our open-source app outright (the first real partner, a check-in tool, would reuse the OSS rather than re-implement). The §8.5 hosted Readiness Checker + static-feed generator are the zero-install rungs of the same adoption ladder. Each package must dog-food the conformance suite it ships. This is the distribution arm of the impl-first → donate-to-Open-Referral RFC strategy: a runnable, `pip install`-able reference makes the eventual RFC adoptable, not just readable. Matures alongside the HSDS-FX extraction (P1) and the P2 reference node.

---

## Self-review (plan vs. design coverage)

- **Every design §maps to a task:** identity/discovery/signing/fetch/Profile → P0; outbox+hooks+export+wire+Delete-derivation → P1; enqueuer+ingest+the §12 corrections+gating+budget+injection+idempotency+mapping+plain-HSDS → P2; push+recovery+anomaly+CDK/monitoring → P3; CLI+PII → P4; VC/Regions/version/GDPR → P5–P7. ✔
- **All §21 decisions are surfaced** and routed (signing profile → **RESOLVED v3: RFC 9421**, P0 Task 0.3; corroboration strength → P2 Task 4 with origin-dedup; Principle-IX → **RESOLVED: decompose**, P1/P2 Task 0; naming → neutral; substrate → **RESOLVED v3: full verifiable**, design §21). ✔
- **Every NON-NEGOTIABLE principle has explicit tasks:** II (Profile, aggregate validates against HSDS models), III (red-first per task), VI (un-corroborated gating, owner-guard, budget, validator routing), XIV (P3 alarms/widgets/infra-tests), XV (both-env tests, slim-import test). ✔
- **No placeholder code in P0** (the executable phase); P1–P7 are intentionally task-level per the Scope Check, each expanded before execution. ✔
- **Run-command consistency:** single-file via `./bouy exec app pytest …`; full gate via `./bouy test` (owner practice + Principle X). ✔
- **Plan-review (2026-06-04) folded in:** the `Delete` hook is re-pointed to the offline dedup scripts (the reconciler Tier-3 is prevent-on-ingest, not a soft-delete); the advisory lock is scoped to the sequence append only; cold-start rebuilds from raw tables not `location_master`; the signing `host` contract is fixed (P0.3); Principle-IX is now a binary gate task (P1.0/P2.0); VALIDATOR_ENABLED (P2.3) and in-phase XIV observability (P1.10/P2.14) are explicit tasks; the enqueuer is specified to be consumable; the P0 file-map and config insertion point are corrected. ✔
- **Steelman v3 (2026-06-04) folded in:** owner decisions integrated — **full verifiable substrate** (signed content-addressed objects, Merkle log, signed checkpoints, proofs; witness mesh committed at P6), **RFC 9421** signing (Task 0.3 rewritten; Cavage dropped), **§11.6a equity caveat** (P2), **HSDS-FX impl-first stewardship** (P1); plus the **P0.5 hard-gate spike**, the **kill switch**, **origin-deduped corroboration + CvRDT property test** (P2), the **live-FA-feed acceptance** (P2), the **reference second node + golden journey tests**, archive-not-prune retention, the recovery-key schema (P0.4), and `Flag`/Lighthouse-tier/prioritized-review pulled to P4. The roadmap table + v3 DELTA blocks are authoritative over any task text that predates them. ✔

---

## Execution handoff

This plan (design + roadmap + P0) is the durable artifact. When you start building:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per P0 task, review between tasks, fast iteration (REQUIRED SUB-SKILL: superpowers:subagent-driven-development).

**2. Inline Execution** — execute P0 tasks in-session with checkpoints (REQUIRED SUB-SKILL: superpowers:executing-plans).

Each subsequent phase (P1→P4) begins by expanding its roadmap section into a bite-sized sibling plan, then executing it the same way. No code ships ahead of its phase.
