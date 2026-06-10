# HSDS Federation — Next Session Opening Prompt

> **Paste this as the opening message of the next federation build session** (fresh machine OK).
> It is self-sufficient: bootstrap, current state, locked decisions, and the concrete next move.
> Public repo — keep everything you commit free of PII (no personal names, emails, or local paths).

---

## 0. Operating model (read first, then act)

You are continuing an autonomous, multi-session build of **HSDS Federation in PPR core** (epic #519). The owner is a solo operator who **cannot deep-review crypto/concurrency** — so **the machine is the reviewer**: build via `superpowers:subagent-driven-development` (a fresh subagent per task, TDD red-first, review between tasks), and gate every PR with the **PR Gauntlet** (static gates → multi-lens review → adversarial refute-skeptics → property/conformance tests → synthesis), iterating until clean. The owner does **product sign-off only** and answers go/no-go gates. **ultracode is encouraged** for the substantive phases (use the `Workflow` tool for the Gauntlet and for fan-out work). RED-tier work (Merkle log / proofs / CvRDT / concurrency) gets mandatory Phase-4 executable-truth + adversarial verification — never let AI grade its own crypto.

**Read, in order** (all on `main`):
1. `constitution.md` — 15 principles; NON-NEGOTIABLE: I (Docker-first via `./bouy`), II (HSDS), III (TDD red-first), VI (data quality), X (quality gates), XIV (AWS observability), XV (dual-env).
2. `CLAUDE.md` — repo commands + the "Federation (HSDS federation core)" subsection.
3. `docs/superpowers/plans/2026-06-09-hsds-federation-p2-pull-ingest.md` — **the ACTIVE P2 plan (REVISION 2)**; its "▶ RESUME POINTER" is the concrete next move. Start here for build work.
4. `docs/superpowers/research/2026-06-10-federation-design-and-spec-review.md` — the deep design+spec review whose findings REVISION 2 folds in (verdicts: design = right-with-corrections; spec = document-shaped gap).
5. `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md` — **design of record (v3.1)**; §21 = owner's binding decisions. Authoritative over plan/code text — EXCEPT where the review found design-doc defects (§6.2a Merkle-leaf misstatement, §8.1 example, void FA-feed refs) — those are tracked as P2 Slice 19 scrub work; the plan's REVISION 2 text wins there.
6. `docs/superpowers/plans/2026-06-03-hsds-federation-core.md` — living plan + roadmap (build-status section). `docs/superpowers/federation-github-epic.md` — issue map; `docs/superpowers/federation-ai-build-playbook.md` — the build playbook.

---

## 1. Fresh-machine bootstrap (only Docker is required locally — Principle I)

```bash
# 1. Docker + Docker Compose (the ONLY local prereq). On Ubuntu: install docker.io + the compose plugin, add your user to the docker group.
# 2. Clone + submodules
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio
git submodule update --init --recursive   # docs/HSDS (public), docs/GeoJson/States (public),
                                           # app/scraper/scrapers (PRIVATE — needs For-The-Greater-Good access)
# 3. (All federation docs + code are on main — no extra branches to fetch.)
git fetch origin
# 4. Configure + start
./bouy setup            # interactive; creates .env from .env.example
./bouy up --with-init   # start services + init DB
./bouy build            # build images (first run pulls the toolchain)
./bouy test             # confirm a green baseline
```

- `plugins/ppr-*` are **separate repos, NOT submodules** — P2 doesn't need them until late (Slice 17's `plugins/ppr-federation-demo/` overlay is created in-repo, not a separate ppr-* repo). Skip cloning ppr-* unless a task names one.
- GitHub writes use the **For-The-Greater-Good** account (the org account); confirm with `gh auth status` before any push/issue write.
- **Testing:** single file `./bouy test --pytest <path>` or `./bouy exec app pytest <path>`; full gate `./bouy test`. (The multi-clone caveat from the prior machine does **not** apply on a single-clone machine.)
- **Known fresh-build snag (apply if it bites):** a full `./bouy test --mypy` may hit a mypy `INTERNAL ERROR` inside `openai/_client.py` (the unpinned `crawl4ai` install can pull a newer `openai` than the lock; CI is green on the lock-pinned version). It is **not** federation code. If local mypy crashes there, add to `pyproject.toml` `[tool.mypy]`, mirroring the existing `rich`/`structlog` skips:
  ```toml
  [[tool.mypy.overrides]]
  module = "openai.*"
  follow_imports = "skip"
  ```
  Verify CI stays green after. Until then, check your own code with `mypy <path>` scoped to the changed files.

---

## 2. Where everything is (branch / PR / issue map)

- **Epic:** #519. Phases: P0 #520 (closed), P0.5 #521 (closed — GO), **P1 #522 (CLOSED 2026-06-08 — verifiable publish COMPLETE)**, **P2 #523 (open, IN PROGRESS — pull ingest + LIVE two-node demo)**, P3 #524, P4 #525, P5 #526, P6 #527, P7 #528. STD/WATCH #538–#542.
- **Everything is on `main`** — design/plans/playbook/epic docs, P0 foundations, all P1 slices (HSDS-FX conformance #567–#572, two-node golden journey #573, cold-start parity #574, archive tiering #575), the P1→reality docs reconcile (#576), and P2 Slice 1 (#578, corroboration extraction + org/service mixin).
- **Active P2 plan:** `docs/superpowers/plans/2026-06-09-hsds-federation-p2-pull-ingest.md` (REVISION 2, 2026-06-10) — wire-freeze decisions D1–D7 + five new review-driven slices (W, 5.5, 5.6, 6.5, NR). Slice 1 ✅ done; **next = Slice W (adopt W3C `eddsa-jcs-2022`)**.
- Beacon follow-ups (independent of federation): #547 (CloudWatch alarm on `beacon_transform_failed`), #548 (per-child isolation).

---

## 3. Locked decisions (do NOT relitigate — rationale in design §21 / the memo)

- Federation is **core `app/`, on by default**. The verifiable substrate is **FULL** (JCS/RFC-8785 content-addressed, Ed25519-signed objects → Merkle log → C2SP signed checkpoints → inclusion/consistency proofs; witness mesh at P6). Signing = **RFC 9421 + RFC 9530**.
- **P0.5 spike = GO:** the **in-place dense-sequence advisory-lock append** is proven sound (gapless/skip-free under real concurrency; M5 hazard impossible; write-cost p99 ~0.2 ms). **Do NOT** take the §6.2f single-writer-relay / CDC-LSN fallback. (Re-confirm append throughput on Aurora during P1; the local number was a single-lock ceiling on Docker.)
- **HSDS version = 3.1.1** (owner-confirmed on #522). The Pydantic models implement 3.1.1, not the submodule's 3.2.3 — advertising 3.2 would violate Principle II. Pin `@context`/Profile/fixtures/`FEDERATION_HSDS_VERSIONS` to 3.1.1; 3.2-model work is a separate follow-up. Keep a CI guard that forbids advertising 3.2 over a 3.1.1-shaped object.
- Other v3 owner calls: equity floor (serve single-source low-density Locations with an "unconfirmed" caveat); HSDS-FX spec extracted impl-first, donated toward Open Referral; corroboration **origin-deduped** (citogenesis fix); Principle IX = decompose; neutral naming. Recovery-key verify-side enforcement is P3 (schema only shipped in P0).
- **Wire-freeze decisions D1–D7 (owner, 2026-06-10 — see the P2 plan §"Wire-freeze decisions"):** headline = **D1: ADOPT W3C `eddsa-jcs-2022`** (DataIntegrityProof + multibase proofValue, replacing the bespoke `ed25519-jcs-2026`; envelope `proof` object only — Merkle leaves/checkpoints/content-addresses are proof-independent, so the leaf/inclusion/consistency/checkpoint vectors do NOT change). Also locked: neutral @context domain, keep AS vocabulary + crosswalk, license = SPDX/URI (strip the bespoke string from vectors), conformance split (Core = proof-OPTIONAL), Announce embeds the origin's signed envelope/id, PII redaction = leaf-payload-destroy + leaf-hash-retention.
- **P2 owner calls (2026-06-09):** `verified_by='network'` tier built NOW (`auto < network < {claimed,source,admin}`, conferred only on allow-listed authoritative peers); §6.6a plain-HSDS consumer built NOW as a general capability (no live target).

---

## 4. The concrete next move — execute the P2 plan, starting at Slice W

**Updated 2026-06-10.** P1 (#522) is complete + closed. P2 is **in progress**: Slice 1 (corroboration-counter extraction + org/service mixin, `merge_strategy` 879→437) merged as **#578**. A deep design+implementation review and an HSDS-FX spec RFC-readiness review (both adversarial multi-lens workflows) landed 2026-06-10; their findings are folded into the P2 plan as **REVISION 2** — read `docs/superpowers/research/2026-06-10-federation-design-and-spec-review.md` before building.

**Open the P2 plan (`docs/superpowers/plans/2026-06-09-hsds-federation-p2-pull-ingest.md`) and follow its "▶ RESUME POINTER".** In short:

- **Next slice = W (issue #579): adopt W3C `eddsa-jcs-2022`** (wire-freeze D1). RED-tier. It changes the P1-shipped `envelope.py` proof object + re-bakes the `envelope_proof` AND `envelope_assembly` conformance vectors (both embed the proof object; leaf/inclusion/consistency/checkpoint vectors UNCHANGED — proof-independent), vendors the W3C cryptosuite KAT, and applies the auto wire-freeze items (header rename, verb registry, I-JSON note, `verify_note` accept-set). It MUST land before the two-node demo or any partner pins bytes.
- Then Slices 2 (location_creator §IX extraction), 3 (models/migration), 15 (router DI seam) — dependency-free, can interleave.
- All **10** review critical/high corrections are baked into specific slices (see the plan's ⚠️R# flags) — do NOT build the old shapes. The five most build-shaping: Slice 5 is **INVERTED** (verified peer records take a deterministic no-LLM validator-stage path — precedent `app/replay/replay.py:enqueue_to_validator`); 5.5 = scale/#562 Tier A (blocking before the demo); 5.6 = prune-safety archive-format fix; 6.5 = wire-shape hardening (addresses/phones/services into the signed aggregate); 8 = the `network` tier as a REAL merge-algorithm change (field-level tier precedence), not a mere owner-guard. The rest ride W, 3, 4, 6, 7a, 7b, 12, NR.
- 🎯 **Headline acceptance (the partner-integration gate): two SEPARATELY-RUNNING PPR nodes** — own deployment/DB-or-schema/`did:web` DID/dataset — pull → verify → ingest as `federated_node` → corroborate, over real HTTP, bidirectionally (Slices 16/17). ⚠️ NO Feeding America feed exists; the old FA-feed acceptance is VOID. A foreign/non-PPR node is P7.

**Per-slice gates (every slice):** TDD red-first; files ≤600 / cyclomatic ≤15; fictional test data only; same-PR `CLAUDE.md` update; pre-PR `./bouy test` green; RED-tier slices get the full PR Gauntlet (iterate until clean); AWS tasks add CloudWatch alarms + `infra/tests/` (Principle XIV); both Docker + AWS work (Principle XV).

**Spec track (parallel, after the wire freeze lands):** the review's Stage 0 scrub (design-doc §6.2a Merkle-leaf fix, §8.1 example, FA-feed refs, public issue #541) is P2 Slice 19; the standalone HSDS-FX spec document (#540, 22-section outline in the review doc) comes after the wire freeze + Stage 1 Open-Referral contributor engagement. Don't write the spec document before Slice W lands — it would document the wrong proof format.

**Open owner decisions (surfaced at their slice, not now):** Slice 8 network-confidence band; Slice 12 equity-caveat params; Slice 13 anomaly params; Slice 17 `FEDERATION_FETCH_ALLOW_HOSTS` scope; NR volatile-field set + heartbeat cadence.

---

## 5. Autonomy boundaries

- **MAY:** dispatch subagents/workflows freely; commit freely on working branches; open PRs; run the Gauntlet; close sub-issues as tasks land; file follow-up issues; make sensible mechanical defaults.
- **SURFACE to the owner (batched, don't interrupt the build):** genuine product/judgment forks; merge of any PR (the owner merges — present gauntlet verdict + recommendation); the open decisions above.
- **Durability:** if approaching context/time limits, leave committed WIP on branches, issues updated, and a short "resume here" in the active PR description.
- If the plan ever conflicts with the design doc, **the design wins** (cite the §); note it and continue.
