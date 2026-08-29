# Job Hunter Implementation Progress

This document is the concise, rolling implementation status shared by developers, Codex, and automation. It reports implementation state only; `spec.md`, `architecture.md`, `development.md`, and `acceptance.md` remain authoritative for requirements, design, workflow, and completion criteria.

## Current Baseline

- Branch: `main`
- Latest stable implementation commit: `a3286fb` (`feat: add candidate knowledge and screening workflow`)
- Last verified: 2026-08-29 21:55 HKT
- `./scripts/check`: passing

## Completed Slices

| Slice | Key deliverables | Commit |
|---|---|---|
| Reproducible development environment | Python 3.12 and uv lock, React/TypeScript/Vite toolchain, setup/check wrappers | `3a47be7` |
| CI and core identifiers | Locked GitHub Actions verification, fixed Node version, typed immutable `RunId` and `CorrelationId` | `76237cf` |
| Domain versioning, lineage, and Manual Job Sources | Immutable self-validating aggregates/versions, active-version history, credential-safe manual JD/URL adapters, import use case, in-memory UoW, stable errors and HTTP contract | `a6e9fc8` |
| FastAPI API organization and lifecycle | Composition root, lifespan-managed `ImportJob`, typed `app.state` provider, module-level Depends-based routers, centralized errors, and split contracts | `a6e9fc8` |
| Candidate Knowledge, deterministic screening, and minimal Job Triage | Human-confirmed Profile snapshots, immutable Evidence versions, stable requirement lineage, versioned three-state QuickScreen, append-only reversible human decisions, and callable HTTP contracts | `a3286fb` |

## Active Slice

**Goal:** no backend implementation slice is active; the Candidate Knowledge → Requirement Parsing → QuickScreen → Minimal Job Triage slice is committed and ready for the next authorized backend slice.

**In Scope:** documentation alignment for the committed backend baseline and its review decisions.

**Out of Scope:** the parallel uncommitted frontend workspace, evaluation datasets, persistence, retrieval, DeepFit, resume/material workflows, and external execution.

**Traceability:** REQ-KNOW-001, REQ-KNOW-002, REQ-HITL-001, AC-SCREEN-001, and the lineage, runtime-validation, strict-typing, run-ID, and correlation-ID Hard Gates. Parser quality targets remain unevaluated until the following dataset/evaluation slice.

## Verification

- Final `./scripts/check`: passed with Ruff format/check, Pyright strict (0 errors), 74 backend tests, frontend format/lint/typecheck, and Vite build.
- Backend unit and API contract tests: 74 passed, including 17 API contract/composition tests.
- `git diff --check`: passed.
- Live/remote checks not run: GitHub Actions requires a later authorized push; no live network, BOSS, LLM, or database check belongs to this slice.

## Decisions and Deviations

- Review-critical domain invariants, boundary translations, transaction/failure semantics, and deliberate scope limits now carry concise intent comments. This is a reviewability standard, not an architecture deviation.
- Concurrent-write admission is now frozen in Architecture, Development, and Acceptance: it becomes mandatory before persistent storage or overlapping mutation enters the default runtime, and requires deterministic stale-writer rejection without lineage loss.
- FastAPI lifespan builds one internally shared default `ApplicationUseCases` graph or accepts one complete explicit bundle. Per-use-case partial overrides are intentionally unsupported because mixing an override with defaults could split related use cases across different stores. The bundle members are exposed individually through typed `app.state` providers and removed on shutdown.
- Standard lifespan-aware tests use Starlette's current `httpx2` TestClient backend; no manual startup hooks or global mutable overrides are used.
- Direct `Job` construction now enforces aggregate-local history, active-version, and source-reference consistency; factories retain cross-object validation responsibilities.
- Manual URL import preserves ordinary job-identity query/fragment data but rejects recognized secret-bearing parameter families before Domain State. Error messages never include parameter values.
- HTTP tests now exercise actual 404 and 409 responses in addition to their OpenAPI declarations. `ImportJob` remains the concrete injection contract because there is still one production implementation and subclass-based test substitutes; Architecture and Development now require a narrow Protocol only when a real non-subclass implementation appears, without weakening runtime `app.state` validation.
- CandidateProfile values are immutable human-confirmed snapshots; a newer snapshot becomes active without deleting older inputs, and QuickScreenResult references the exact snapshot used. Profile-relative `current`/`stale` status is derived without invalidating history; stale-profile results remain eligible for Human Triage, while a future user-facing read model must label them and recommend re-screening.
- UnitOfWorkFactory failures in Evidence, QuickScreen, and Job Triage are converted before any transaction exists; rollback is attempted only after a UoW was successfully constructed, and raw dependency details do not cross the Application boundary.
- `deterministic-line-parser` v1 preserves normalized JD lines, allocates Requirement IDs once per immutable JobVersion, and makes no quality claim before the dataset/evaluation slice.
- `quick-screen-v1` uses only preferred city, target-role, and confirmed-skill signals. Recommendations and human Triage decisions are separate append-only records; reruns and new JobVersions fail stale decisions closed.
- The expanded InMemoryStore commits Job, Candidate Knowledge, Requirement, screening, and Triage indexes together but remains explicitly single-writer with no concurrency-isolation claim.
- No implementation-stage architecture deviation is currently recorded.

## Risks and Blockers

- Remote GitHub Actions cannot be observed until the committed baseline is pushed; pushing is intentionally not authorized in this slice.
- Runtime persistence is intentionally in-memory; process restart loses imported jobs, and overlapping UoWs may silently overwrite one another. The current adapter is supported only as a single-writer development baseline until the persistence/concurrency admission gate is implemented.
- Parser and QuickScreen behavior is a deterministic baseline only; accuracy and promotion decisions remain unmeasured until versioned datasets and metric runners exist.
- The backend preserves and can identify Profile snapshot lineage, but the user-facing stale-result warning and re-screen recommendation remain pending because screening read APIs and frontend feature work are outside this slice.
- No current local blocker.

## Next Slice

After review and explicit commit authorization, proceed to evaluation foundations: versioned Development/Holdout/Synthetic datasets, requirement ground truth, a fake model contract, baseline retrieval fixtures, and reproducible parser/QuickScreen metric runners. Chroma feasibility and Hybrid Retrieval remain the following slice and must not enter the default path before those baselines exist.
