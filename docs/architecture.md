# Job Hunter System Architecture

## 1. Document Authority

This file is the authoritative source for the current system architecture and technology boundaries. It answers **how the system is designed** and describes the effective target state rather than preserving the Q1–Q82 discussion history. See `spec.md` for product requirements, `development.md` for engineering rules, and `acceptance.md` for release criteria. The convenience translation lives at `zh/architecture.zh.md`.

## 2. Architecture Principles

1. **Business First:** business value may veto technology demonstrations.
2. **Local First:** MVP data, identity state, browser state, and artifacts remain local by default.
3. **Read/Write Separation:** read-only collection and external writes are separated by process, authority, and state.
4. **Human Authority:** job selection, factual confirmation, material approval, and external-action authorization belong to the user.
5. **Evidence Grounding:** factual output must bind to Candidate Evidence.
6. **Fail Closed:** stop when authority, schema, page outcome, or provenance cannot be established.
7. **Deterministic Control Plane:** state, budgets, approvals, idempotency, and safety are enforced by code, not prompts.
8. **Bounded Agency:** retrieval, tool loops, context compaction, and repair have explicit limits.
9. **Traceability by Design:** lineage is domain data, not a by-product of logging.
10. **Design for Change, Implement for Today:** preserve correct seams without pre-implementing future adapters.

## 3. System Context

```text
User
  │
  ▼
React + TypeScript + Vite SPA
  │ HTTP; SSE/WebSocket only when a use case requires streaming
  ▼
FastAPI Application
  ├── Job Acquisition and Screening
  ├── Candidate Knowledge and Retrieval
  ├── LangGraph Material Workflow
  ├── Resume Rendering
  ├── Approval and Tracking
  └── Domain Lineage
  │
  ├── SQLite authoritative data
  ├── Chroma rebuildable vector index
  ├── Local artifact store
  ├── LLM provider through the LangChain model interface
  └── Optional local processes
      ├── Boss Collector
      └── Local Browser Executor (Stretch, disabled by default)
```

MVP is a localhost, single-machine application. It exposes neither LAN nor public access and provides no multi-device synchronization. Typed Runtime Configuration owns environment-specific values; business logic must not depend on repository cwd, hard-coded ports, or machine-specific paths.

FastAPI and independent local processes bind to `127.0.0.1` by default. CORS allows only configured Job Hunter frontend origins, and mutation endpoints use explicit origin/request protection. Even on loopback, Browser Executor requires a random, narrowly scoped local authentication token and must expose no cookie, Shell, JavaScript, or general browser-RPC interfaces. MVP has no product account system, but local access is not treated as unlimited trust.

## 4. Repository Topology

```text
job-hunter/
├── backend/
│   ├── src/job_hunter/
│   │   ├── domain/
│   │   ├── application/
│   │   ├── api/
│   │   ├── ingestion/
│   │   ├── knowledge/
│   │   ├── retrieval/
│   │   ├── context/
│   │   ├── workflows/
│   │   ├── rendering/
│   │   ├── execution/
│   │   ├── observability/
│   │   └── infrastructure/
│   ├── tests/{unit,integration,contract}/
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/
│   ├── src/
│   ├── tests/
│   └── package.json
├── evals/{datasets,rubrics,runners,reports}/
├── docs/
├── scripts/
├── third-party/
├── .github/
├── AGENTS.md
└── README.md
```

The repository root is the product workspace. `backend/` and `frontend/` are real toolchain/runtime boundaries, but MVP remains a modular monolith and does not introduce generic `apps/packages/services/platform/shared` hierarchies.

## 5. Layers and Dependency Direction

```text
API / UI / CLI
      ↓
Application Use Cases
      ↓
Domain Policies / Entities
      ↓
Ports
      ↑
Infrastructure Adapters
```

### 5.1 API

FastAPI routes handle request validation, local request context, use-case invocation, response mapping, and error mapping. They do not write SQL or call Chroma, LLMs, scrapers, or browsers directly.

### 5.2 Application

Use Cases represent complete business intents such as `ImportJob`, `RunQuickScreen`, `ShortlistJob`, `PrepareMaterials`, `ApproveMaterials`, and `AuthorizeExecution`. Application code manages transaction boundaries and port collaboration without owning external SDK details.

### 5.3 Domain

Domain owns stable entities, value objects, and policies: Job/JobVersion, Requirement, Evidence, ResumeClaim, Approval, lifecycle transitions, evidence eligibility, deduplication, claim grounding, and approval validity.

### 5.4 Infrastructure

SQLAlchemy, SQLite, Chroma, LangChain providers, scrapers, renderers, artifact storage, and browsers are adapters. Third-party exceptions are translated into the Job Hunter error taxonomy at adapter boundaries.

### 5.5 Port Rule

Define Ports only for real replacement or test seams, including Repository, UnitOfWork, ModelGateway, EvidenceRetriever, Clock, IDGenerator, ArtifactStore, Collector, Renderer, and Executor. Do not create ceremonial interfaces for ordinary helpers, policies, or value objects.

## 6. Core Domain Model

### 6.1 Job and Versions

```text
Job
├── job_id                     logical identity
├── active_version_id
├── source references[]
└── lifecycle status

JobVersion
├── immutable normalized facts
├── normalized company/title/city
├── JD content
├── freshness
└── source snapshot references
```

Source-local identity:

```text
source_identity = platform + source_job_id
```

Cross-posting duplicate candidate:

```text
dedup_fingerprint = normalized_company
                  + normalized_title
                  + city
                  + description_signature
```

High-confidence duplicates may be linked or merged automatically. Fuzzy results are only marked `possible_duplicate` and require user confirmation.

### 6.2 SourceSnapshot and Ephemeral Fields

Raw collection output first becomes an isolated SourceSnapshot. Only adapter validation and normalization may produce a JobVersion. BOSS `security_id`, `lid`, and similar ephemeral fields exist only in a SourceSnapshot or ExecutionContext with `captured_at`, TTL, and source. They do not participate in canonical identity and must be reacquired or revalidated before execution.

### 6.3 Requirement

ParsedRequirement is a stable, atomic requirement under a JobVersion. It stores requirement ID, text, type, priority (`REQUIRED/PREFERRED/UNSPECIFIED`), and parser provenance. Compound requirements should be decomposed while preserving their mapping to the original JD text.

### 6.4 Candidate Knowledge

```text
CandidateProfile
EvidenceItem
├── evidence_id
├── active_version_id
└── versions[]

EvidenceItemVersion
├── canonical content
├── type/date/source/provenance
├── sensitivity/validity
└── metadata

EvidenceChunk
├── chunk_id
├── parent evidence_version_id
├── chunk_policy_version
└── retrieval text/index metadata
```

EvidenceItemVersion is factual authority. EvidenceChunk is a rebuildable indexing derivative. Final ResumeClaims bind to EvidenceItemVersions, not mutable chunk IDs.

### 6.5 Resume and Claims

Resume IR is canonical resume content. Templates change presentation only.

```text
ResumeClaim
├── claim_id
├── text
├── claim_type
├── evidence_version_ids[]
├── matched_requirement_ids[]
├── transformation_type
├── author_type
└── validation_status
```

`author_type` distinguishes AI-generated, AI-rewritten, human-authored, and human-edited. Human content must not invent a ModelInvocation but remains subject to evidence grounding and validation.

### 6.6 Approvals

```text
MaterialApproval
├── material bundle versions/hashes
├── user decision
└── validity

ExecutionApproval
├── material_approval_id
├── account_id
├── canonical_job_id
├── action_set
├── artifact versions/hashes
├── expires_at
├── single_use
└── consumed_at
```

Ready means materials are approved; it does not authorize execution. Material mutation creates a new version and invalidates the related MaterialApproval and all unconsumed ExecutionApprovals.

## 7. Job Acquisition Architecture

### 7.1 Static Adapter Registry

```text
JobSource protocol
└── JobSourceRegistry
    ├── ManualJDSource
    ├── ManualURLSource
    └── BossSource
```

Here, plugin means a configurable adapter, not a dynamic installation system, Codex Skill, or MCP Server.

### 7.2 BOSS Third-party Dependency

`eatmoreduck/boss-zhipin-scraper` runs in an independent Python environment and is governed by an immutable commit SHA, dependency/hash lock, allowlisted CLI invocation, and Job Hunter-owned contract.

Never follow `master` or treat an upstream self-reported version as a stable API. Do not depend on internal Python module APIs by default. A traceable patch/fork is allowed only when the CLI cannot satisfy integration needs and the user explicitly approves it. Record the upstream SHA, reason, impact, approval, and contract-test results.

### 7.3 Collector Contract

```json
{
  "contract_version": "1",
  "run_id": "...",
  "status": "succeeded|partial|failed",
  "jobs": [],
  "warnings": [],
  "error": null,
  "source_metadata": {}
}
```

BossCollectorAdapter manages subprocess lifecycle, temporary output, timeout, exit-code mapping, raw JSON/CSV, normalization, schema validation, stderr redaction, and error classification. Abnormal raw results may become diagnostic artifacts only; they must never write directly to the domain database.

### 7.4 Safety Policy

Collector is disabled by default. Users may configure search conditions, maximum jobs, and intervals bounded by safety floors. CAPTCHA, risk codes, login anomalies, account verification, major schema drift, repeated abnormal responses, or unknown results stop collection immediately. Automatic cookie copying, CAPTCHA bypass, risk-code bypass, and anti-detection enhancements are forbidden.

## 8. Screening and Fit

### 8.1 QuickScreen

QuickScreen runs before Human Triage and reduces downstream cost. It uses Job metadata, ParsedRequirements, a limited Candidate Profile projection, and bounded rules/model logic. It emits `SCREEN_IN/SCREEN_OUT/UNCERTAIN` with reasons. It is not Career RAG and does not emit formal requirement-level fit.

### 8.2 DeepFitAnalysis

Only Shortlisted jobs enter DeepFit. Evidence is retrieved first, then each Requirement receives `MATCHED/PARTIAL/MISSING/UNKNOWN`, supporting Evidence, and risks. DeepFit is the only formal Fit artifact evaluated by the DeepFit quality and grounding gates.

## 9. Retrieval Architecture

### 9.1 Eligibility First

```text
Candidate Knowledge
→ candidate/task scope
→ permission/sensitivity/validity
→ redaction
→ eligible Evidence set
→ RetrievalPolicy
```

No Retriever may bypass this boundary.

### 9.2 Strategies

```text
EvidenceRetriever
├── FullContextRetriever
├── LexicalMetadataRetriever
└── HybridRetriever
    ├── SQLite metadata / FTS5
    ├── Chroma semantic index
    └── application-level fusion
```

SQLite stores authoritative Evidence and metadata. Chroma stores only a rebuildable vector index and records embedding model/provider, dimension, chunk-policy version, and index version. A bounded local feasibility spike must validate persistence, metadata filtering, update/delete, rebuild, packaging, and benchmark performance before Chroma is frozen.

### 9.3 Deterministic Retrieval Policy

- eligible tokens within a calibrated threshold: Full Context;
- identifier/certificate/named project/skill lookup: Lexical + Metadata;
- semantic requirement-to-experience matching: Hybrid;
- overlapping conditions use fixed precedence.

Every run records policy version, input statistics, selected strategy, and reason. Hybrid remains experimental and falls back to Full Context or Lexical until it passes promotion thresholds.

### 9.4 Bounded Agentic RAG

```text
Initial Retrieval
→ Structured Sufficiency Assessment
→ At most one Query Reformulation
→ Supplemental Retrieval
→ Final Sufficiency Decision
```

When budgets expire or evidence remains inadequate, return a normal no/insufficient-evidence state. Do not lower relevance thresholds or continue searching until something appears supportive.

## 10. Context Engineering

### 10.1 Context Construction

ContextBuilder produces an immutable, versioned ContextPackage:

```text
Job Requirements
+ selected Evidence and provenance
+ approved Candidate facts/preferences
+ task instructions
+ minimal workflow projection
+ redaction and token budget
→ ContextPackage
```

It records input versions, inclusion/exclusion reasons, token estimates, redaction, and policy/prompt versions. It must not inject other jobs, full conversation history, or the whole Career Vault.

### 10.2 Runtime Context Manager

Each ContextEntry stores type, source, token estimate, priority, provenance, retention class, protected flag, and rehydratable flag.

A versioned CompactionPolicy controls deterministic deduplication, obsolete-entry removal, low-priority trimming, and large-result externalization. ArtifactReferences are typed and explicitly rehydratable. Protected entries cannot be dropped silently; return `CONTEXT_BUDGET_EXCEEDED` when safe compaction is insufficient.

Compaction changes only the representation visible to the model. It never changes Candidate Knowledge, User Preferences, or domain authority.

## 11. Memory and Capability Plane

Keep these concepts distinct:

- Agent Context: current messages, necessary history, Job, retrieved Evidence, and Tool Results;
- Candidate Knowledge: Profile and Evidence;
- User Memory: explicit user-confirmed Preferences only;
- Workflow/Domain State: Job, Resume, Approval, checkpoints, and execution records;
- Capability Plane: Tools, future Skills, and future MCP.

Models cannot freely write Candidate Knowledge or long-term User Memory. Checkpoints, cookies, tokens, browser sessions, and infrastructure state are invisible by default; only a minimal semantic projection may enter ContextPackage.

MVP implements neither Skill Runtime nor MCP. A future Skill system uses a versioned registry and progressive disclosure. The first MCP candidate is an allowlisted, read-only GitHub Client whose output becomes a human-reviewed Evidence Draft only.

## 12. LangGraph Runtime

### 12.1 Graph Boundary

```text
Parsed Shortlisted Job
→ Retrieve
→ Deep Fit
→ Draft
→ Validate
→ Repair? (max 2)
→ Material Review interrupt
→ Approved / Revision Requested
```

Requirement Parsing and QuickScreen run before Human Job Triage as ordinary Application Services. Only Shortlisted jobs enter the Graph. Nodes are coarse-grained typed state transitions. They do not write SQL, manipulate browsers, or run external processes directly; they invoke application services/ports.

The two Human Gates use different durable mechanisms. Job Triage is an Application/Domain checkpoint for `Screened → Shortlisted/Skipped`. Material Review is a LangGraph interrupt/checkpoint for validated materials. Both support durable resume and audit, but Job Triage is not forced into LangGraph for cosmetic uniformity.

### 12.2 Structured Output

Job Hunter uses the existing LangChain model interface rather than rewrapping provider SDKs. ModelProfile/Factory declares provider, model, credential reference, base URL, timeout, and necessary parameters. MVP formally tests one primary provider/model and permits explicit configuration-driven switching to supported providers. Automatic fallback and dynamic routing are excluded.

Every model output entering domain state passes a Pydantic structured-output contract. Raw text cannot directly become Job, FitAnalysis, ResumeClaim, or ValidationResult state.

### 12.3 Capability Policy

Every node declares a NodeToolPolicy: allowed tools, resource scope, maximum calls/iterations, timeout, token/cost/result-size budget, and side-effect class.

Tools are classified as `READ_ONLY`, `LOCAL_REVERSIBLE_WRITE`, `LOCAL_PERSISTENT_WRITE`, or `EXTERNAL_SIDE_EFFECT`. Normal tool loops receive only pre-authorized read/local capabilities. External side effects never enter the Graph.

### 12.4 Validation and Repair

Deterministic checks enforce schema, field constraints, provenance, approval, and rendering invariants. Bounded semantic checks evaluate claim-evidence support. Repair receives only explicit errors, target fields, and related Evidence and produces a structured patch. Every patch is fully revalidated. After at most two attempts, the workflow moves to human handling or failure.

## 13. Resume Rendering

The template renderer converts Resume IR into HTML/CSS, PDF, and PNG. Template A is required for MVP. Template switching changes presentation only.

Determinism means that the same IR/template/renderer yields consistent semantic content and layout, not byte-identical PDFs. Every actual artifact still receives an immutable hash, and MaterialApproval binds to the artifact the user reviewed.

## 14. Browser Execution Boundary

Browser Executor is a separate deterministic service, not part of LangGraph. It exposes narrow business commands such as `OpenJob`, `SendApprovedGreeting`, `SendApprovedResume`, and `VerifyOutreachResult`. It exposes no arbitrary selector click, JavaScript, Shell, cookie export, MITM, or general private-protocol interface.

```text
ExecutionApproval verification
→ Idempotency check
→ Precondition/read-current-state
→ One allowlisted browser action
→ Read-back verification
→ Append-only ExecutionEvent
```

The idempotency key is `platform + account_id + canonical_job_id`. `PARTIAL` stores `last_verified_step`; verified actions must not replay. Continuing missing steps requires a new, narrower ExecutionApproval.

MVP implements only LocalBrowserExecutor and creates no RemoteExecutor or OfficialAPIExecutor shells. A third-party executor may replace the minimal Job Hunter-owned Playwright/CDP adapter only after passing license, maintenance, immutable versioning, interface, security, and narrow-command admission gates.

## 15. Persistence, Versioning, and Deletion

Persistence flows through Repository + Unit of Work into SQLAlchemy/SQLite. The architecture does not promise a zero-cost SQLite-to-PostgreSQL switch and does not pre-implement PostgreSQL adapters.

Entities that affect generation, approval, or execution are versioned. Snapshot records are immutable after creation. Logical entities hold only an active-version pointer. Privacy deletion may physically remove sensitive content while retaining only non-sensitive entity/version IDs, deletion time, reason, and necessary hash tombstones.

## 16. Traceability and Observability

### 16.1 Domain Lineage

Authoritative lineage is stored in the Job Hunter database:

```text
SourceSnapshot → JobVersion → ParsedRequirement
→ RetrievalRun → EvidenceChunk/EvidenceItemVersion
→ ContextPackage → ModelInvocation
→ ResumeClaim → ValidationResult → ResumeVersion
→ MaterialApproval → ExecutionApproval/ExecutionEvent
```

Every layer uses stable IDs, parent references, versions/hashes, policy/prompt/model versions, timestamps, run IDs, and correlation IDs.

### 16.2 Agent / LLM Trace

LangSmith observes LangGraph nodes, model invocations, tool calls, token use, latency, and errors. Metadata links traces to domain IDs, but LangSmith is not authoritative provenance. Masking is the default; sensitive invocations hide inputs/outputs or disable external tracing.

### 16.3 System Observability

MVP Hard Requirements are structured local logs, correlation/run IDs, liveness/readiness, and privacy-safe LangSmith tracing. OpenTelemetry remains an architecture seam. Basic FastAPI/SQLAlchemy spans and a small metric set are time permitting. External backends, dashboards, and alerting are excluded.

### 16.4 Retention

Minimal lineage metadata is retained long-term. Raw prompts/responses, ContextPackage diagnostic snapshots, and cropped page screenshots use short local retention; Executor screenshots default to seven days. Cookies, tokens, passwords, session secrets, and unrelated page content are forbidden in logs, traces, and metrics.

## 17. Technology Choices

| Technology | Responsibility and boundary |
|---|---|
| Python 3.12 | Backend runtime |
| FastAPI | HTTP/API boundary, not domain logic |
| Pydantic | Runtime validation for external and structured-output boundaries |
| SQLAlchemy + SQLite | Authoritative relational persistence |
| Alembic | Schema migration |
| LangGraph | Bounded stateful material workflow |
| LangChain model interface | Provider/model integration without automatic routing |
| Chroma local persistent | Rebuildable semantic vector index, never source of truth |
| LangSmith | Agent/LLM tracing, never domain lineage |
| React + TypeScript + Vite | Local SPA |
| Playwright | Web E2E/visual tests and candidate Stretch browser adapter |
| uv / Ruff / Pyright / pytest | Python reproducibility, style, typing, and testing |
| ESLint / typescript-eslint / Prettier | Frontend linting, type-aware rules, and formatting |

## 18. Evolution Boundary

The system may evolve into a packaged local application and later a Cloud Control Plane plus Local Execution Agent. A cloud component would send only narrow business intents; cookies, sessions, and local files would remain local. The current repository creates no speculative future classes or services. Evolution relies on typed configuration, ports, versioned contracts, an authoritative domain model, and migratable data.
