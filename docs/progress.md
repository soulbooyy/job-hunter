# Job Hunter Implementation Progress

This document is the concise, rolling implementation status shared by developers, Codex, and automation. It reports implementation state only; `spec.md`, `architecture.md`, `development.md`, and `acceptance.md` remain authoritative for requirements, design, workflow, and completion criteria.

## Current Baseline

- Branch: `main`
- Latest stable implementation commit: `e9e2630` (`feat: add durable SQLite workspace persistence`)
- Last verified: 2026-08-31 11:48 HKT
- `./scripts/check`: passing

## Completed Slices

| Slice | Key deliverables | Commit |
|---|---|---|
| Reproducible development environment | Python 3.12 and uv lock, React/TypeScript/Vite toolchain, setup/check wrappers | `3a47be7` |
| CI and core identifiers | Locked GitHub Actions verification, fixed Node version, typed immutable `RunId` and `CorrelationId` | `76237cf` |
| Domain versioning, lineage, and Manual Job Sources | Immutable self-validating aggregates/versions, active-version history, credential-safe manual JD/URL adapters, import use case, in-memory UoW, stable errors and HTTP contract | `a6e9fc8` |
| FastAPI API organization and lifecycle | Composition root, lifespan-managed `ImportJob`, typed `app.state` provider, module-level Depends-based routers, centralized errors, and split contracts | `a6e9fc8` |
| Candidate Knowledge, deterministic screening, and minimal Job Triage | Human-confirmed Profile snapshots, immutable Evidence versions, stable requirement lineage, versioned three-state QuickScreen, append-only reversible human decisions, and callable HTTP contracts | `a3286fb` |
| Local frontend intake, screening, triage, and Evidence workspace | Runtime-validated mutation clients, session-only workflow state, Profile-relative stale warnings, append-only screening/Triage views, Manual Evidence versioning, Simplified Chinese user copy, accessible request states, and deterministic component tests | `1fbb860` |
| Workspace read models and browser-reload readback | Resource-oriented Job, Profile, and Evidence GET contracts; immutable lineage histories; deterministic current/stale and Triage-eligibility projections; no-store responses; shared lifespan composition | `6340e36` |
| Frontend Workspace readback adoption | Strict GET runtime contracts, browser-reload hydration, multi-Job selection, complete lineage views, backend-derived screening actionability, mutation resynchronization, and accessible retry/error states | `83c1e67` |
| Deterministic Workspace Playwright coverage | Mock-backed Chromium coverage for reload reconstruction, Job selection, stale-Profile Triage eligibility, historical JobVersion ineligibility, and Triage request targeting; unified local and CI check integration | `83c1e67` |
| Web Workspace path 1 completion | Stateful mock-backed Candidate Profile → Manual JD → QuickScreen → Human Triage browser flow, mutation/readback resynchronization, reload reconstruction, and backend-unavailable retry recovery | `11fa7ea` |
| Evaluation foundations and deterministic retrieval baselines | Runtime-validated smoke dataset and rubric, shared Evidence eligibility, Full Context/Lexical-Metadata retrievers, immutable RetrievalRun lineage, exact retrieval/parser/QuickScreen metrics, structured replay validation, and offline replay entry point | `e78ebea` |
| Frontend persistence-boundary synchronization | SQLite restart-recovery copy, explicit local-only/no-backup boundary, and stable `stale_write` conflict mapping with runtime-contract tests | `45a76e1` |
| Durable SQLite Workspace persistence | Alembic-managed SQLAlchemy/SQLite graph, restart durability, consistent UoW snapshots, optimistic concurrency, authoritative latest-screen coordination, normalized lineage ownership, metadata-drift verification, and persistent default lifespan composition | `e9e2630` |

## Active Slice

**Goal:** close the documentation for the committed SQLAlchemy/SQLite persistence baseline; no additional implementation slice is active.

**In Scope:** record the verified `e9e2630` baseline, its persistence and concurrency decisions, and the recommended next slice.

**Out of Scope:** further code changes, frontend features, new HTTP resources, PostgreSQL or speculative remote adapters, FTS5 search, Chroma/embedding/Hybrid retrieval, automatic RetrievalPolicy routing, ContextBuilder, DeepFit, LangGraph, database encryption/backup/sync, auth, live LLM/BOSS/browser dependencies, and material generation.

**Traceability:** REQ-PERSIST-001, REQ-WORKSPACE-001, AC-PERSIST-001/002, and the transaction, lineage, runtime-validation, strict-typing, error-boundary, and privacy Hard Gates.

## Verification

- Final `./scripts/check`: passed with Ruff format/check, Pyright strict (0 errors), 136 backend tests, frontend format/lint/typecheck, 36 Vitest API/component test cases, 4 Playwright Chromium E2E cases, and Vite build.
- Backend unit, API contract, and persistence integration tests: 136 passed, including 22 API contract/composition tests, 15 real-SQLite integration tests, and 34 retrieval/evaluation tests.
- SQLite verification covers idempotent Alembic upgrade, Alembic-derived head and metadata-drift checks, startup schema-head refusal, complete Workspace and RetrievalRun restart recovery, a real two-connection read snapshot, independent-Session stale writes for Job/Profile/Evidence roots, both concurrent re-screen/Triage commit orders, normalized lineage ownership and corruption rejection, losing-lineage rollback, transaction atomicity, write-order preservation, and invalid-payload error redaction.
- `./scripts/eval-replay`: passed offline against `smoke-v1`; the report records all dataset/parser/retriever/policy versions, contains no Evidence content, and explicitly reports that AC-DATA-001 is not satisfied.
- `git diff --check`: passed.
- The prior localhost browser smoke covered Profile and Manual JD browser reload. A new manual browser smoke was not required because HTTP contracts are unchanged; persistent restart behavior is exercised against the real SQLite adapter in backend integration tests.
- Playwright Workspace suite: 4 passed against deterministic browser-level HTTP mocks, covering full Manual JD path 1, post-mutation readback and reload, Job switching, stale/current/historical projections, enabled/disabled Triage controls, selected QuickScreenResult targeting, and safe network-unavailable retry recovery.
- Live/remote checks not run: GitHub Actions requires a later authorized push; live BOSS and LLM checks were not run. Web Workspace paths 2–5 remain unavailable because their product slices do not yet exist.

## Decisions and Deviations

- Review-critical domain invariants, boundary translations, transaction/failure semantics, and deliberate scope limits now carry concise intent comments. This is a reviewability standard, not an architecture deviation.
- Concurrent-write admission is now frozen in Architecture, Development, and Acceptance: it becomes mandatory before persistent storage or overlapping mutation enters the default runtime, and requires deterministic stale-writer rejection without lineage loss.
- The default lifespan now validates the configured Alembic head, owns one synchronous SQLAlchemy engine/session factory, and builds the complete application graph on short-lived SQL UnitOfWork instances. Setup and `./scripts/db-upgrade` apply migrations explicitly; application startup never creates or migrates schema.
- SQLite transaction control now emits an explicit `BEGIN` before read and write operations so a UnitOfWork observes one committed snapshot. FastAPI routes that invoke the synchronous application graph are synchronous handlers and therefore run blocking SQLAlchemy work in framework-managed worker threads.
- Job, EvidenceItem, and Candidate Profile active-pointer state use infrastructure-only optimistic revisions. Independent stale writers return `stale_write`; the losing transaction cannot retain immutable child rows or alter the winning active pointer and lineage.
- Job owns the authoritative latest-QuickScreen pointer. Re-screen advances it under the same optimistic revision as Triage, a new JobVersion clears it, and read projections no longer infer actionability from append order.
- Persisted immutable values use runtime-validated JSON payloads paired with normalized identity, ownership, lineage, active-pointer, revision, and write-order columns. Hydration cross-validates both representations and reports invalid state only through a redacted dependency-unavailable error.
- QuickScreen requirements and RetrievalRun hit/exclusion Evidence lineage use ordered relational association rows with composite ownership constraints. Repository hydration also cross-checks the complete Job/JobVersion/Requirement, Triage/QuickScreen/Job, RetrievalRun/Requirement/JobVersion, and EvidenceItem/EvidenceVersion chains.
- `./scripts/db-check` upgrades a temporary database to the unique head derived from the Alembic migration graph and runs `alembic check`; it never reads or modifies the configured developer database.
- FastAPI lifespan builds one internally shared default `ApplicationUseCases` graph or accepts one complete explicit bundle. Per-use-case partial overrides are intentionally unsupported because mixing an override with defaults could split related use cases across different stores. The bundle members are exposed individually through typed `app.state` providers and removed on shutdown.
- Standard lifespan-aware tests use Starlette's current `httpx2` TestClient backend; no manual startup hooks or global mutable overrides are used.
- Direct `Job` construction now enforces aggregate-local history, active-version, and source-reference consistency; factories retain cross-object validation responsibilities.
- Manual URL import preserves ordinary job-identity query/fragment data but rejects recognized secret-bearing parameter families before Domain State. Error messages never include parameter values.
- HTTP tests now exercise actual 404 and 409 responses in addition to their OpenAPI declarations. `ImportJob` remains the concrete injection contract because there is still one production implementation and subclass-based test substitutes; Architecture and Development now require a narrow Protocol only when a real non-subclass implementation appears, without weakening runtime `app.state` validation.
- CandidateProfile values are immutable human-confirmed snapshots; a newer snapshot becomes active without deleting older inputs, and QuickScreenResult references the exact snapshot used. Profile-relative `current`/`stale` status is derived without invalidating history; stale-profile results remain eligible for Human Triage, while a future user-facing read model must label them and recommend re-screening.
- UnitOfWorkFactory failures in Evidence, QuickScreen, and Job Triage are converted before any transaction exists; rollback is attempted only after a UoW was successfully constructed, and raw dependency details do not cross the Application boundary.
- `deterministic-line-parser` v1 preserves normalized JD lines, allocates Requirement IDs once per immutable JobVersion, and makes no quality claim before the dataset/evaluation slice.
- `quick-screen-v1` uses only preferred city, target-role, and confirmed-skill signals. Recommendations and human Triage decisions are separate append-only records; reruns and new JobVersions fail stale decisions closed.
- `evidence-eligibility-v1` receives only repository values that match both the owning EvidenceItem and its active-version pointer, then admits `VALID` Evidence whose sensitivity is explicitly allowed. Retrieval adapters cannot create factual lineage: mismatched active versions or unknown returned IDs fail closed before retrieval or commit, and evaluation judgments outside the same eligible universe are invalid.
- `full-context-v1` returns the exact eligible set or `NOT_EXECUTABLE` without truncation; Application and Domain both enforce its strategy semantics. `lexical-metadata-v1` uses exact phrase, normalized tokens, metadata signals, top-k, stable ID tie-breaking, and a deterministic ranked-prefix token budget. RetrievalRun records eligible and selected token estimates separately; ContextBuilder retains responsibility for the later final-package budget.
- Parser reports expose per-priority precision, recall, F1, support, raw confusion counts, and Macro-F1. Production QuickScreen and evaluation reports use one shared policy-version constant.
- `smoke-v1` is a hand-authored synthetic mechanics fixture, not a quality dataset. Its perfect parser/QuickScreen numbers and baseline retrieval differences support no product-quality claim; the AC-DATA-001 curated corpus remains outstanding.
- InMemoryStore remains a deterministic single-writer test adapter with no concurrency-isolation claim; it is no longer the default application runtime.
- Frontend JSON remains `unknown` until a strict endpoint-specific Zod schema accepts it; malformed success/error bodies and network exceptions become stable `ApiError` values without exposing raw data.
- The SPA stores only validated mutation responses in React memory. It writes no Profile, JD, Evidence, or URL data to browser storage, logs, or navigation state; one Job workflow keeps a stable correlation ID and every mutation receives a fresh injected run ID.
- Profile-relative stale status and current JobVersion/actionability are derived read projections. A stale-Profile result remains triageable, while a result for a historical JobVersion remains visible but cannot be used as the current action target.
- Workspace readback uses four resource-oriented GET contracts rather than a catch-all dump. Each query reads one UoW snapshot, preserves authoritative IDs and histories, deterministically orders collections, and emits `Cache-Control: no-store`; derived status fields are never persisted.
- The frontend requests all Workspace resources with `no-store`, validates each response before atomically replacing its readback view, and uses backend-projected Profile/JobVersion/result status and Triage eligibility rather than recreating those rules in React.
- Successful mutations trigger Workspace resynchronization. A failed, malformed, or superseded read request cannot replace the last validated view; users can retry without exposing raw dependency errors.
- Frontend persistence copy now reflects restart recovery from the default local SQLite database while explicitly avoiding cross-device-sync or automatic-backup claims. The stable `stale_write` 409 code is runtime-validated and directs users to resynchronize before retrying.
- Playwright is pinned in the frontend lockfile and uses its matching Chromium revision. E2E routes mock only Job Hunter HTTP contracts, use synthetic fixtures and accessible locators, run with one worker and no retry, trace, screenshot, or video retention, and are isolated from Vitest discovery.
- Web Workspace path 1 uses a stateful fake API installed before navigation, so browser actions exercise real request mapping, runtime validation, React transitions, readback resynchronization, and reload behavior without contacting a live backend or depending on random IDs.
- The unified repository check runs the selected Playwright suite; GitHub CI installs the locked Chromium runtime and its system dependencies before invoking the same check entry point.
- Vite proxies `/api` and `/health` to the loopback backend by default; `VITE_API_BASE_URL` remains an explicit deployment override.
- Frontend labels, controls, request feedback, accessibility names, and explanatory copy default to Simplified Chinese. Established product/domain names and serialized API enum values, versions, and IDs remain unchanged so localization cannot create an alternate contract truth.
- No implementation-stage architecture deviation is currently recorded.

## Risks and Blockers

- Remote GitHub Actions cannot be observed until the committed baseline is pushed; pushing is intentionally not authorized in this slice.
- The local SQLite database contains private Candidate and Job content and currently has no application-level encryption, backup, recovery, or sync workflow. It remains a local file excluded by Git patterns and must not be copied or committed casually.
- Startup intentionally fails when the configured database is not at the current Alembic head; developers must run `./scripts/setup` or `./scripts/db-upgrade` after pulling schema changes.
- Parser, QuickScreen, and baseline retrieval now have reproducible metric runners, but only synthetic smoke cases exist. Quality and promotion decisions remain unmeasured until the curated Development and Frozen Holdout minimums are independently annotated.
- Browser reload and backend restart now restore the currently implemented Workspace graph from SQLite; cross-device sync and disaster recovery remain out of scope.
- Web Workspace path 1 and backend-unavailable recovery now pass locally. The complete Web Workspace Hard Gate remains open until paths 2–5 and their required failure cases exist; remote GitHub CI execution is not observable before an authorized commit and push.
- No current local blocker.

## Next Slice

The recommended next backend slice is a bounded Chroma feasibility spike followed—only if admitted and explicitly authorized—by Hybrid Retrieval, RetrievalPolicy, and ContextBuilder. The spike must prove local persistence, metadata filtering, update/delete, rebuild, packaging, and benchmark behavior before Chroma enters the production path.
