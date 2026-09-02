# Job Hunter Development Guide

## 1. Document Authority

This file is the authoritative source for the engineering workflow, TDD strategy, code standards, and developer commands. It answers **how the system is built**. Architecture rules come from `architecture.md`; executable configuration is authoritative for formatting, linting, and type-check details. The convenience translation lives at `zh/development.zh.md`.

## 2. Development Principles

1. Build usable vertical slices rather than horizontal technology layers.
2. Run feasibility work before committing to uncertain dependencies.
3. Remain TDD-first while matching the test technique to the system layer.
4. Establish deterministic control before optimizing probabilistic quality.
5. Define datasets, rubrics, and baselines before prompt tuning.
6. Preserve traceability from requirement to test/evaluation evidence.
7. Prioritize core MVP; Collector and Executor must not block the material workspace.
8. Keep capabilities disabled until their admission or release gates pass.

## 3. Implementation Dependency Order

This is a dependency order, not a calendar or daily-hours schedule:

1. Repository scaffold, toolchain, CI, typed configuration, and core IDs.
2. Domain model, versioning, lineage, Repository/UoW, and Manual Job Sources.
3. Candidate Profile, EvidenceItem/Version, Requirement parsing, QuickScreen, and Workspace readback.
4. Evaluation datasets, fake model, baseline retrievers, and metric runners.
5. SQLAlchemy/SQLite persistence, Alembic migrations, restart durability, and concurrent-write admission.
6. Chroma feasibility, Hybrid Retriever, RetrievalPolicy, and ContextBuilder.
7. RuntimeContextManager, Capability Policy, and typed LangGraph workflow.
8. DeepFit, ResumeClaim, validation/repair, and MaterialApproval.
9. Structured Resume Editor, Template A, PDF/PNG, and critical E2E flows.
10. Boss Collector adapter and its independent Stretch Release Gate.
11. Browser Executor feasibility only after every core Hard Gate is stable.

## 4. Scope-cut Order and Stop Rules

When time or complexity pressure appears, cut scope in this order:

1. Do not implement Browser Executor, or keep it disabled.
2. Defer Template B and keep only Template A.
3. Defer OpenTelemetry instrumentation and additional metrics.
4. Keep BOSS live integration at adapter/fixture or disabled status while Manual Import remains functional.
5. Keep adjacent role families as uncalibrated generic support without formal quality claims.

Never cut:

- evidence-grounded claims and the zero-unsupported-claim gate;
- separation of QuickScreen and DeepFit;
- the two Human Gates;
- separation of MaterialApproval and ExecutionApproval;
- bounded repair, tools, retrieval, and context;
- domain lineage, versions, and hashes;
- privacy, fail-closed behavior, and external-side-effect boundaries;
- deterministic test Hard Gates.

When feasibility work cannot establish safety, contract stability, or basic usefulness, stop and record the result. Never compensate with anti-detection behavior, general permissions, or unbounded retry.

## 5. TDD Strategy

### 5.1 Domain, Policy, and Contract

Use strict Red → Green → Refactor:

- write the smallest failing test that expresses a state, invariant, or contract;
- implement the minimum behavior that passes;
- refactor only while the suite remains green;
- reproduce every bug with a regression test before fixing it.

This applies to state transitions, approval validity, versions/hashes, claim grounding, eligibility, deduplication, budgets, adapter normalization, and error mapping.

### 5.2 Persistence and Concurrent Writes

Do not infer concurrency guarantees from a Repository/UoW shape or from atomic behavior in a single test transaction. Before a persistent adapter or an overlapping-write runtime is admitted:

- freeze the expected-revision/active-version contract and its conflict mapping before implementation;
- write a deterministic test in which two UoWs start from the same version, the first commits, and the stale commit cannot silently overwrite it;
- verify that the successful state retains complete immutable history and authoritative lineage after the conflict;
- once an in-memory fake substitutes for the admitted adapter in concurrency-sensitive tests, run the same observable contract against both;
- test at the actual coordination boundary—database transactions or constraints for multi-process support—not only with a process-local lock.
- use two real connections to prove that a read UnitOfWork retains one snapshot after another connection commits; a framework Session flag alone is not evidence of SQLite transaction state;

The current in-memory adapter may remain single-writer and simpler than the future persistent adapter while that limitation is explicit and unsupported concurrent configurations are not enabled.

Every UnitOfWork is one-shot and must be explicitly closed in a `finally` path after commit, rollback, or a successful read. Persistence tests use temporary database files and real independent connections; they never reuse or delete the developer's configured database.

Synchronous SQLAlchemy use cases must be invoked by synchronous FastAPI handlers or an explicit worker-thread boundary. Do not execute blocking database work directly in an async route.

Read-model tests must cover deterministic ordering, active pointers, immutable history, cross-entity lineage, empty collections, stable not-found behavior, and derived actionability. A browser-reload claim requires contract evidence that mutation results can be reconstructed from backend GET responses; it does not imply backend-restart durability.

### 5.3 LangGraph

Test typed state, legal and illegal routes, conditional repair, interrupt/checkpoint/resume, and budgets before implementation. Use FakeModel, FakeTool, FixedClock, and DeterministicIdGenerator. Unit and integration tests must not depend on a live provider.

For synchronous persistent capabilities, enforce deadlines and result-size limits cooperatively before commit. A post-commit deadline observation must preserve the committed resource identity and record attempted/completed/committed usage; it cannot be reported as a rollback. Translate graph-library construction and invocation exceptions at the workflow boundary without retaining raw exception text.

### 5.4 RAG, Prompts, and LLMs

Use evaluation-driven development:

```text
Dataset
→ Annotation / Rubric
→ Baseline
→ Candidate Implementation
→ Error Analysis
→ Frozen Holdout Evaluation
```

The Development Set may evolve. A Holdout case used for targeted tuning is leaked and must move to Development while a new Holdout case replaces it. Never tune against a Holdout example and continue describing it as unseen.

Evaluation-foundation tests must freeze dataset validation, reference integrity, active-version ownership, eligibility exclusions and judgment eligibility, deterministic ranking/tie-breaking, Full Context completeness, retrieval-budget accounting without silent truncation, exact metric arithmetic including parser per-class metrics, and shared report/production version metadata before implementation. Seed synthetic fixtures remain intentionally small and must be labeled as runner smoke data rather than Dataset Gate evidence. Replay/fake model adapters are permitted only when an evaluation runner or contract test executes them; they never justify an unused production abstraction or a live dependency in deterministic CI.

### 5.5 Rendering

Use typed Resume IR fixtures, structural assertions, PDF text extraction, and visual golden regression. Do not use PDF binary hashes as the sole determinism measure.

### 5.6 Frontend

Write component/E2E tests for critical interactions: job ingestion/triage, Evidence/DeepFit, Resume edit/preview/diff, validation/approval/export, and required failures. Do not force every CSS detail into unit-test-first development.

### 5.7 Third-party Spikes

Scraper, Chroma packaging, and Browser Executor may begin as bounded spikes. Every spike must:

- state the question, scope/time bound, and exit criteria;
- remain outside the production path;
- avoid real external side effects unless the user approves each one;
- record observed facts and risks;
- freeze a Job Hunter-owned contract and characterization tests before production adoption;
- be removed, isolated, or left disabled if its admission gate fails.

## 6. Test Tracks

### Fast Deterministic CI

Fake models, domain, contracts, workflow, repositories, rendering invariants, frontend unit/component tests, and mock-backed E2E. This is the standard change Hard Gate.

### Replay Evaluation

Fixed or recorded structured model output, golden datasets, prompt contracts, retriever comparisons, and workflow-quality regression. Reproducible checks may enter CI and release gates.

### Live Evaluation

Real providers/models, explicitly triggered BOSS smoke tests, and user-approved executor validation. Run manually, periodically, or before release and report each environment separately. Live evaluation does not block every change unless a metric later proves stable enough to be promoted.

## 7. Python Engineering Standards

- Runtime: Python 3.12; use uv and commit `backend/uv.lock`.
- Layout: `backend/src/job_hunter`; pytest uses importlib import mode.
- Formatting, linting, and import sorting: Ruff stable mode. Do not add Black, isort, or Flake8.
- Typing: Pyright strict is the only Python static-type authority.
- External input may briefly be `Any` at an adapter/IO boundary but must immediately pass through Pydantic or an explicit parser into a typed contract.
- `Any` must not propagate into Domain, Application, LangGraph State, Retrieval, Context, or persistence core logic.
- `# type: ignore` must be local and include a specific error code and reason. Do not use file/global ignores to hide business-code errors.
- LangGraph State uses TypedDict, Pydantic, or another explicit contract, never `dict[str, Any]`.
- Migrations, generated code, and controlled third-party code may use separate exclusions.
- Use constructor injection. Use FastAPI `Depends` only at API composition boundaries.
- Inject application-scoped use cases that share repositories or transactions as one complete typed composition bundle; do not offer per-use-case partial overrides that can silently split the dependency graph.
- Inject time, IDs, models, repositories, artifacts, collectors, and executors. Tests must not rely on wall-clock time or random IDs.
- Include UnitOfWorkFactory acquisition inside the Application error boundary. Translate unknown acquisition failures without raw details, and call rollback only when a UnitOfWork was actually created.
- Runtime-validate dependencies retrieved from dynamic framework state at the API boundary; `cast()` may inform static typing but cannot establish runtime correctness.
- Keep a concrete Application Use Case injection type until a real non-subclass implementation or test substitute requires a shared Protocol. When that trigger occurs, define and contract-test the narrow Protocol, update composition typing coherently, and preserve an explicit runtime guard.
- Add concise comments or docstrings where reviewers need intent that types and names cannot express directly: domain invariants, authoritative lineage, boundary validation and translation, transaction/failure semantics, safety controls, and deliberate scope limitations.
- Comments explain **why** a constraint or ordering exists, not what an obvious statement does. Keep them synchronized with behavior; remove stale plans and do not use comments to justify dead code or speculative abstractions.

## 8. Frontend Engineering Standards

- React + TypeScript + Vite. MVP includes neither Next.js nor Electron.
- Enable TypeScript `strict`, `noUncheckedIndexedAccess`, and `exactOptionalPropertyTypes`.
- Runtime-validate external JSON/API responses; type assertions are not validation.
- Use ESLint flat config with typescript-eslint. Prettier owns formatting and must not duplicate lint rules.
- The UI depends only on versioned HTTP contracts, never backend Python implementation details.
- Keep API clients, domain view models, and component state separate. Do not duplicate backend business rules inside components.
- User-facing copy defaults to Simplified Chinese, including labels, controls, status and error feedback, accessibility names, and explanatory text. Preserve established product/domain/technology names such as `Job Hunter`, `Candidate Profile`, `QuickScreen`, `DeepFit`, `Evidence`, and `RAG`, plus serialized API enum values, versions, and IDs; do not translate machine contract values into alternate frontend truth.
- Playwright tests user-visible behavior with accessible locators and mocked third-party services.

## 9. Architecture Coding Rules

- Routes/controllers contain no business rules, SQL, LLM, Chroma, or browser code.
- Application Use Cases own one business operation and its transaction boundary.
- Domain imports none of FastAPI, SQLAlchemy, LangGraph, Chroma, LangChain, or Playwright.
- SQLAlchemy models are not cross-layer domain APIs.
- Separate Pydantic DTOs, Domain Models, and Persistence Models only where boundaries require it; do not clone structures ceremonially.
- LangGraph Nodes orchestrate typed state and invoke application capabilities; they do not manipulate infrastructure directly.
- Third-party exceptions cannot cross adapter boundaries.
- Never expose general Shell, JavaScript, selector, SQL, or filesystem tools to a model.
- No unvalidated model or third-party output may enter Domain State.

## 10. Error and Failure Semantics

The error taxonomy must at least distinguish validation, policy denial, budget exceeded, not found, conflict, stale version, invalid approval, dependency unavailable, login/auth anomaly, schema drift, timeout, rate/risk signal, partial external success, and unknown external result.

Unknown external results fail closed. Do not use broad exception handling to present failure as success, and do not propagate third-party exception strings as business state.

## 11. Dependency Management

- Python and frontend dependencies use committed lockfiles; every upgrade is explicit.
- Do not enable Ruff preview or unstable tool behavior without separate approval.
- Keep one formatter and one primary type authority per language.
- Before runtime admission, inspect third-party license, maintenance, immutable versioning, interface, security permissions, and replaceability.
- `third-party/` stores dependency identity, immutable SHA, license/admission notes, patch metadata, and contract version. It stores no credentials or copied browser profiles.
- Vendor patches/forks require explicit user approval and preserve upstream SHA, patch, reason, and revalidation evidence.

## 12. Git and Change Workflow

- Keep each change focused; do not mix unrelated refactors.
- Commit messages describe business behavior or architecture-boundary changes.
- Update authoritative documents before implementing changes to requirements, architecture, Hard Gates, or safety boundaries.
- New requirements receive stable IDs; related tests/evaluations must cite the ID or appear in the acceptance traceability mapping.
- Never commit secrets, real cookies, browser profiles, unredacted personal data, temporary diagnostic artifacts, or retention-bound screenshots.

## 13. Unified Developer Commands

The repository root must provide stable wrapper commands. Their underlying implementation may change during scaffolding, but their meaning remains stable:

```text
./scripts/setup          install locked backend/frontend dependencies
./scripts/db-upgrade     upgrade the configured local SQLite schema
./scripts/db-check       verify Alembic head and metadata against a temporary database
./scripts/dev            start local FastAPI and Vite
./scripts/check          run all deterministic checks
./scripts/eval-replay    run reproducible replay evaluation
./scripts/semantic-check verify the optional adapter in an isolated locked environment
./scripts/semantic-setup explicitly acquire and verify the pinned local ONNX model
./scripts/hybrid-eval    run explicit local-model synthetic Hybrid evaluation
./scripts/context-eval   run deterministic synthetic RuntimeContext mechanics evaluation
```

A live-evaluation entry point is not currently implemented. Add it only after a primary provider/model is admitted; it must remain explicit and outside the default setup and check workflows.

`./scripts/check` must eventually include:

```text
Backend format check
Backend lint
Pyright strict
Backend deterministic tests
Isolated optional Chroma adapter format/type/persistence tests
Frontend format/lint/typecheck
Frontend deterministic tests/build
Selected mock-backed Playwright E2E
```

Pre-commit runs only low-latency formatter/linter feedback. CI runs locked verification equivalent to `./scripts/check`; it does not maintain a separate command universe.

`semantic-setup` is never part of default setup or request handling. `semantic-check` skips the real embedding-runtime assertion when the explicitly installed model is absent, while still verifying locked Chroma packaging and persistent index behavior. A local Hybrid quality report requires `semantic-setup` first and remains non-promotional unless the exact eligible human-reviewed Frozen Holdout satisfies the Acceptance thresholds.

## 14. Completion Checklist

Before declaring a feature complete, confirm:

- a corresponding Spec requirement and Acceptance criterion exist;
- a failing test/evaluation contract preceded implementation;
- every new external input has runtime validation;
- type, lint, format, and deterministic tests pass;
- lineage, versions, hashes, and privacy behavior are covered;
- review-critical invariants and boundary/failure semantics have concise, current comments where the code alone is insufficient;
- errors, budget exhaustion, and boundary failures are explicit states;
- documentation and behavior agree;
- a capability missing a Quality Target has the specified consequence;
- a Stretch capability missing its Release Gate remains disabled.

## 15. Rolling Implementation Status

`progress.md` is the concise, authoritative record of current implementation status for developers, Codex, and automation. It reports the baseline, completed and active slices, verification, implementation decisions or deviations, current risks, and the recommended next slice. It does not redefine Product, Architecture, Development, or Acceptance authority and is the only project document without a Chinese translation.

Update it at the start and completion of every development slice. Keep it with the corresponding code change and replace stale status instead of appending command transcripts, chat history, temporary debugging notes, calendar schedules, or daily effort plans. Architecture changes still require `architecture.md` to be updated first.
