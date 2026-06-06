# HSDS Federation — Next Session Opening Prompt

> **Paste this as the opening message of the next federation build session** (fresh machine OK).
> It is self-sufficient: bootstrap, current state, locked decisions, and the concrete next move.
> Public repo — keep everything you commit free of PII (no personal names, emails, or local paths).

---

## 0. Operating model (read first, then act)

You are continuing an autonomous, multi-session build of **HSDS Federation in PPR core** (epic #519). The owner is a solo operator who **cannot deep-review crypto/concurrency** — so **the machine is the reviewer**: build via `superpowers:subagent-driven-development` (a fresh subagent per task, TDD red-first, review between tasks), and gate every PR with the **PR Gauntlet** (static gates → multi-lens review → adversarial refute-skeptics → property/conformance tests → synthesis), iterating until clean. The owner does **product sign-off only** and answers go/no-go gates. **ultracode is encouraged** for the substantive phases (use the `Workflow` tool for the Gauntlet and for fan-out work). RED-tier work (Merkle log / proofs / CvRDT / concurrency) gets mandatory Phase-4 executable-truth + adversarial verification — never let AI grade its own crypto.

**Read, in order** (all in this repo once branches are fetched — see §1):
1. `constitution.md` — 15 principles; NON-NEGOTIABLE: I (Docker-first via `./bouy`), II (HSDS), III (TDD red-first), VI (data quality), X (quality gates), XIV (AWS observability), XV (dual-env).
2. `CLAUDE.md` — repo commands + the "Federation (HSDS federation core)" subsection.
3. `docs/superpowers/specs/2026-06-03-hsds-federation-core-design.md` — **design of record (v3.1)**; §21 = owner's binding decisions. Authoritative over plan/code text.
4. `docs/superpowers/plans/2026-06-03-hsds-federation-core.md` — living plan + roadmap (see its **Build status** section for what's done).
5. `docs/superpowers/plans/2026-06-05-hsds-federation-p1-publish.md` — **the P1 bite-sized plan** (15 tasks, 4-PR split). *(On branch `docs/federation-p1-plan` until merged.)*
6. `docs/superpowers/federation-github-epic.md` — issue map; and `docs/superpowers/federation-ai-build-playbook.md` — the build playbook.

---

## 1. Fresh-machine bootstrap (only Docker is required locally — Principle I)

```bash
# 1. Docker + Docker Compose (the ONLY local prereq). On Ubuntu: install docker.io + the compose plugin, add your user to the docker group.
# 2. Clone + submodules
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio
git submodule update --init --recursive   # docs/HSDS (public), docs/GeoJson/States (public),
                                           # app/scraper/scrapers (PRIVATE — needs For-The-Greater-Good access)
# 3. Fetch the not-yet-merged federation doc/work branches (see §2 for the list)
git fetch origin
# 4. Configure + start
./bouy setup            # interactive; creates .env from .env.example
./bouy up --with-init   # start services + init DB
./bouy build            # build images (first run pulls the toolchain)
./bouy test             # confirm a green baseline
```

- `plugins/ppr-*` are **separate repos, NOT submodules** — **P1 does not need them** (P1 is core `app/`). Skip unless a later phase needs a plugin.
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

- **Epic:** #519. Phases: P0 #520 (closed), **P0.5 #521 (closed — GO accepted)**, **P1 #522 (open, IN PROGRESS)**, P2 #523, P3 #524, P4 #525, P5 #526, P6 #527, P7 #528. STD/WATCH #538–#542. (P1–P7 hard-gate **cleared**.)
- **`main`** has: P0 foundations (merged #545) + the Beacon data-loss fixes (merged #546).
- **`docs/hsds-federation-core-design`** (PR **#518**, draft) — design + living plan + playbook + epic + this file. *(Owner to merge to main when ready.)*
- **`docs/federation-p1-plan`** — the P1 bite-sized plan. **`docs/federation-p05-memo`** — the P0.5 go/no-go memo (`docs/superpowers/research/2026-06-05-federation-p05-go-no-go.md`).
- **`feat/federation-p1a-decomposition`** (PR **#549**, DRAFT) — **P1 PR-A WIP**: `job_processor.py` decomposed (1892→1328; commit branches extracted to `app/reconciler/location_commit.py` 531 + `location_match.py` 193). Suite green, no behavior change.
- Beacon follow-ups (independent of federation): #547 (CloudWatch alarm on `beacon_transform_failed`), #548 (per-child isolation).

---

## 3. Locked decisions (do NOT relitigate — rationale in design §21 / the memo)

- Federation is **core `app/`, on by default**. The verifiable substrate is **FULL** (JCS/RFC-8785 content-addressed, Ed25519-signed objects → Merkle log → C2SP signed checkpoints → inclusion/consistency proofs; witness mesh at P6). Signing = **RFC 9421 + RFC 9530**.
- **P0.5 spike = GO:** the **in-place dense-sequence advisory-lock append** is proven sound (gapless/skip-free under real concurrency; M5 hazard impossible; write-cost p99 ~0.2 ms). **Do NOT** take the §6.2f single-writer-relay / CDC-LSN fallback. (Re-confirm append throughput on Aurora during P1; the local number was a single-lock ceiling on Docker.)
- **HSDS version = 3.1.1** (owner-confirmed on #522). The Pydantic models implement 3.1.1, not the submodule's 3.2.3 — advertising 3.2 would violate Principle II. Pin `@context`/Profile/fixtures/`FEDERATION_HSDS_VERSIONS` to 3.1.1; 3.2-model work is a separate follow-up. Keep a CI guard that forbids advertising 3.2 over a 3.1.1-shaped object.
- Other v3 owner calls: equity floor (serve single-source low-density Locations with an "unconfirmed" caveat); HSDS-FX spec extracted impl-first, donated toward Open Referral; corroboration **origin-deduped** (citogenesis fix); Principle IX = decompose; neutral naming. Recovery-key verify-side enforcement is P3 (schema only shipped in P0).

---

## 4. The concrete next move — finish P1 PR-A, then PR-B…D

Per the 4-PR split in the P1 plan:
- **PR-A (in progress, #549):** decomposition is DONE. **Remaining:** add **Task -1** — the HSDS-3.1.1 CI guard test (assert the advertised version matches the 3.1.1-shaped models). Then run the **PR Gauntlet** on PR-A, fix anything, mark it **ready**, and present to the owner for merge.
- **PR-B (RED tier — the substrate):** `FederationLog` model + migration; the **in-place dense-sequence advisory-lock append** + RFC-6962 Merkle frontier + C2SP signed checkpoints + inclusion/consistency proofs; the §8.2 Location aggregate serializer; normative wire spec + JSON Schema + `fixtures/federation/` (JCS vectors + worked proof). **No hooks fire yet** — hammer the crypto/concurrency in isolation. Mandatory Phase-4 property tests + adversarial verification; **strongly consider an external security/distributed-systems spot-audit here** (playbook).
- **PR-C:** the hooks (job_processor matched/new-Location `Update` at the extracted `location_commit.py` site; dedup-script `Delete`+`redirectTo`; submarine `Update`) + the `FEDERATION_ENABLED` kill switch (byte-identical-reconciler test) + `/api/v1/federation/{export,state.txt,checkpoint,history}` (dual-env).
- **PR-D:** cold-start `_since=0` from raw tables (parity vs the **real** `/export` aggregate) + archive tiering (never destroy) + Principle-XIV alarms + HSDS-FX extraction + Readiness Checker + static-feed generator + in-repo reference second node + golden journey test + docs.

**Per-task gates (every task):** TDD red-first; files ≤600 / cyclomatic ≤15; fictional test data only; same-PR `CLAUDE.md` update; pre-PR `./bouy test` green; AWS tasks add CloudWatch alarms + `infra/tests/` (Principle XIV); both Docker + AWS work (Principle XV).

**Open owner decisions to surface (don't block PR-A on them):** archive live-window length + S3 layout (design §21); whether to commission the external audit of PR-B.

---

## 5. Autonomy boundaries

- **MAY:** dispatch subagents/workflows freely; commit freely on working branches; open PRs; run the Gauntlet; close sub-issues as tasks land; file follow-up issues; make sensible mechanical defaults.
- **SURFACE to the owner (batched, don't interrupt the build):** genuine product/judgment forks; merge of any PR (the owner merges — present gauntlet verdict + recommendation); the open decisions above.
- **Durability:** if approaching context/time limits, leave committed WIP on branches, issues updated, and a short "resume here" in the active PR description.
- If the plan ever conflicts with the design doc, **the design wins** (cite the §); note it and continue.
