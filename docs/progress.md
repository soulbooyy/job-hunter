# Job Hunter Implementation Progress

This document is the concise, rolling implementation status shared by developers, Codex, and automation. It reports implementation state only; `spec.md`, `architecture.md`, `development.md`, and `acceptance.md` remain authoritative for requirements, design, workflow, and completion criteria.

## Current Baseline

- Branch: `main`
- Latest stable implementation commit: `a3286fb` (`feat: add candidate knowledge and screening workflow`)
- Last verified: 2026-08-29 23:39 HKT
- `./scripts/check`: passing

## Completed Slices

| Slice | Key deliverables | Commit |
|---|---|---|
| Reproducible development environment | Python 3.12 and uv lock, React/TypeScript/Vite toolchain, setup/check wrappers | `3a47be7` |
| CI and core identifiers | Locked GitHub Actions verification, fixed Node version, typed immutable `RunId` and `CorrelationId` | `76237cf` |
| Domain versioning, lineage, and Manual Job Sources | Immutable self-validating aggregates/versions, active-version history, credential-safe manual JD/URL adapters, import use case, in-memory UoW, stable errors and HTTP contract | `a6e9fc8` |
| FastAPI API organization and lifecycle | Composition root, lifespan-managed `ImportJob`, typed `app.state` provider, module-level Depends-based routers, centralized errors, and split contracts | `a6e9fc8` |
| Candidate Knowledge, deterministic screening, and minimal Job Triage | Human-confirmed Profile snapshots, immutable Evidence versions, stable requirement lineage, versioned three-state QuickScreen, append-only reversible human decisions, and callable HTTP contracts | `a3286fb` |
| Local frontend intake, screening, triage, and Evidence workspace | Runtime-validated mutation clients, session-only workflow state, Profile-relative stale warnings, append-only screening/Triage views, Manual Evidence versioning, Simplified Chinese user copy, accessible request states, and deterministic component tests | Uncommitted working tree |

## Active Slice

**Goal:** the mutation-only frontend workspace and its Simplified Chinese user-copy policy are implemented and verified; the uncommitted slice is awaiting review and explicit commit authorization.

**In Scope:** App shell and feature-panel prose, labels, controls, loading/success/error feedback, accessibility names, deterministic component assertions, and aligned English-authoritative/Chinese-convenience frontend development rules.

**Out of Scope:** HTTP schema or backend behavior changes, translating serialized API values or established technical/product identifiers, i18n infrastructure, persistent frontend cache, and all previously deferred product capabilities.

**Traceability:** REQ-JOB-001, REQ-JOB-002, REQ-JOB-006, REQ-KNOW-001, REQ-KNOW-002, REQ-HITL-001, AC-JOB-001, and AC-SCREEN-001. The frontend can retain only the current browser session's validated mutation responses because read/query contracts do not yet exist.

## Verification

- Final `./scripts/check`: passed with Ruff format/check, Pyright strict (0 errors), 74 backend tests, frontend format/lint/typecheck, 26 Vitest API/component test cases, and Vite build.
- Backend unit and API contract tests: 74 passed, including 17 API contract/composition tests.
- `git diff --check`: passed.
- Manual localhost browser smoke: passed Profile → Manual JD Import → QuickScreen (`screen_in`) → Shortlisted against the real in-memory API, with accessible DOM state and no browser console errors.
- Live/remote checks not run: GitHub Actions requires a later authorized push; the Playwright Web Workspace CI Hard Gate, live BOSS, LLM, and database checks were not run.

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
- Frontend JSON remains `unknown` until a strict endpoint-specific Zod schema accepts it; malformed success/error bodies and network exceptions become stable `ApiError` values without exposing raw data.
- The SPA stores only validated mutation responses in React memory. It writes no Profile, JD, Evidence, or URL data to browser storage, logs, or navigation state; one Job workflow keeps a stable correlation ID and every mutation receives a fresh injected run ID.
- Profile-relative stale status and current JobVersion/actionability are derived read projections. A stale-Profile result remains triageable, while a result for a historical JobVersion remains visible but cannot be used as the current action target.
- Vite proxies `/api` and `/health` to the loopback backend by default; `VITE_API_BASE_URL` remains an explicit deployment override.
- Frontend labels, controls, request feedback, accessibility names, and explanatory copy default to Simplified Chinese. Established product/domain names and serialized API enum values, versions, and IDs remain unchanged so localization cannot create an alternate contract truth.
- No implementation-stage architecture deviation is currently recorded.

## Risks and Blockers

- Remote GitHub Actions cannot be observed until the committed baseline is pushed; pushing is intentionally not authorized in this slice.
- Runtime persistence is intentionally in-memory; process restart loses imported jobs, and overlapping UoWs may silently overwrite one another. The current adapter is supported only as a single-writer development baseline until the persistence/concurrency admission gate is implemented.
- Parser and QuickScreen behavior is a deterministic baseline only; accuracy and promotion decisions remain unmeasured until versioned datasets and metric runners exist.
- The user-facing stale-Profile warning and re-screen recommendation are implemented for mutation responses obtained in the current browser session. No GET/read endpoint exists for jobs, Profiles, Evidence, screening, or Triage, so reload/readback and cross-session stale projections remain unavailable.
- The Playwright Web Workspace Hard Gate has not run; the deterministic Vitest component suite and manual localhost browser smoke do not replace it.
- No current local blocker.

## Next Slice

After review and explicit commit authorization, the next frontend acceptance slice should add locked, mock-backed Playwright coverage for the current mutation-only Manual Import → QuickScreen → Triage path and backend-unavailable behavior, without claiming the broader Web Workspace Hard Gate. The backend evaluation-foundations slice remains a separate next track: versioned datasets, ground truth, fake model contracts, baseline retrieval fixtures, and reproducible parser/QuickScreen metric runners.
