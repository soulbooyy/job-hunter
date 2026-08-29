# Job Hunter Implementation Progress

This document is the concise, rolling implementation status shared by developers, Codex, and automation. It reports implementation state only; `spec.md`, `architecture.md`, `development.md`, and `acceptance.md` remain authoritative for requirements, design, workflow, and completion criteria.

## Current Baseline

- Branch: `main`
- Latest stable implementation commit: `a6e9fc8` (`feat: implement versioned manual job imports`)
- Last verified: 2026-08-29 17:59 HKT
- `./scripts/check`: passing

## Completed Slices

| Slice | Key deliverables | Commit |
|---|---|---|
| Reproducible development environment | Python 3.12 and uv lock, React/TypeScript/Vite toolchain, setup/check wrappers | `3a47be7` |
| CI and core identifiers | Locked GitHub Actions verification, fixed Node version, typed immutable `RunId` and `CorrelationId` | `76237cf` |
| Domain versioning, lineage, and Manual Job Sources | Immutable self-validating aggregates/versions, active-version history, credential-safe manual JD/URL adapters, import use case, in-memory UoW, stable errors and HTTP contract | `a6e9fc8` |
| FastAPI API organization and lifecycle | Composition root, lifespan-managed `ImportJob`, typed `app.state` provider, module-level Depends-based routers, centralized errors, and split contracts | `a6e9fc8` |

## Active Slice

**Goal:** no implementation slice is active; the completed Job Import baseline and its review decisions are documented for the next authorized slice.

**In Scope:** documentation alignment for the committed Job Import baseline, including future concurrent-write and application-Protocol admission conditions.

**Out of Scope:** private constructors, persistence hydration design, an application use-case protocol, HTTP schema/status changes, new endpoints, generic DI, SQLite, Fit Analysis, Evidence, Resume, or RAG.

**Traceability:** the implementation work preserves REQ-JOB-001, REQ-JOB-002, REQ-JOB-005, REQ-JOB-006, AC-JOB-001, and existing API contract evidence. Future persistent or overlapping-write runtimes are now governed by AC-PERSIST-001.

## Verification

- Final `./scripts/check`: passed with Ruff format/check, Pyright strict (0 errors), 45 backend tests, frontend format/lint/typecheck, and Vite build.
- Backend unit and API contract tests: 45 passed, including 10 API contract/composition tests.
- `git diff --check`: passed.
- Live/remote checks not run: GitHub Actions requires a later authorized push; no live network, BOSS, LLM, or database check belongs to this slice.

## Decisions and Deviations

- Review-critical domain invariants, boundary translations, transaction/failure semantics, and deliberate scope limits now carry concise intent comments. This is a reviewability standard, not an architecture deviation.
- Concurrent-write admission is now frozen in Architecture, Development, and Acceptance: it becomes mandatory before persistent storage or overlapping mutation enters the default runtime, and requires deterministic stale-writer rejection without lineage loss.
- FastAPI lifespan builds or accepts one application-scoped `ImportJob`, stores only that use case in `app.state`, and removes the reference on shutdown. A typed `Depends` provider reuses it for every Job request.
- Standard lifespan-aware tests use Starlette's current `httpx2` TestClient backend; no manual startup hooks or global mutable overrides are used.
- Direct `Job` construction now enforces aggregate-local history, active-version, and source-reference consistency; factories retain cross-object validation responsibilities.
- Manual URL import preserves ordinary job-identity query/fragment data but rejects recognized secret-bearing parameter families before Domain State. Error messages never include parameter values.
- HTTP tests now exercise actual 404 and 409 responses in addition to their OpenAPI declarations. `ImportJob` remains the concrete injection contract because there is still one production implementation and subclass-based test substitutes; Architecture and Development now require a narrow Protocol only when a real non-subclass implementation appears, without weakening runtime `app.state` validation.
- No implementation-stage architecture deviation is currently recorded.

## Risks and Blockers

- Remote GitHub Actions cannot be observed until the committed baseline is pushed; pushing is intentionally not authorized in this slice.
- Runtime persistence is intentionally in-memory; process restart loses imported jobs, and overlapping UoWs may silently overwrite one another. The current adapter is supported only as a single-writer development baseline until the persistence/concurrency admission gate is implemented.
- No current local blocker.

## Next Slice

After review and explicit commit authorization, proceed to Candidate Profile, EvidenceItem/Version, Requirement Parsing, and QuickScreen. Its prerequisites—a stable manual import contract, traversable Job lineage, and green repository verification—are satisfied. Do not begin persistence or retrieval infrastructure ahead of that dependency order.
