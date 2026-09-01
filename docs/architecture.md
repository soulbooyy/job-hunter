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

Routes that invoke the synchronous SQLAlchemy application graph are synchronous FastAPI handlers so framework-managed worker threads, not the event loop, perform blocking database I/O. Async handlers remain reserved for genuinely async boundaries.

Workspace readback uses resource-oriented GET contracts for the Job collection, one complete Job read model, Candidate Profile snapshots, and Evidence histories. The Job read model contains its version/source/Requirement lineage plus QuickScreen and Triage history; the API does not expose Domain objects or introduce a catch-all `/workspace` dump. Responses containing Candidate Knowledge or Job content use `Cache-Control: no-store`.

### 5.2 Application

Use Cases represent complete business intents such as `ImportJob`, `RunQuickScreen`, `ShortlistJob`, `PrepareMaterials`, `ApproveMaterials`, and `AuthorizeExecution`. Application code manages transaction boundaries and port collaboration without owning external SDK details.

Acquiring a UnitOfWork is part of the Application failure boundary. Unknown factory or port exceptions are translated into stable Job Hunter errors, and rollback is attempted only after a UnitOfWork was successfully acquired.

`WorkspaceQueries` constructs each read model from one UnitOfWork snapshot. The SQLite adapter explicitly begins a database transaction before the first SELECT so every repository read in that UnitOfWork observes one committed snapshot. It deterministically orders immutable histories and derives `current/stale` and Triage-eligibility fields from authoritative active pointers. These fields are projections only and are never written back into Domain State.

### 5.3 Domain

Domain owns stable entities, value objects, and policies: Job/JobVersion, Requirement, Evidence, ResumeClaim, Approval, lifecycle transitions, evidence eligibility, deduplication, claim grounding, and approval validity.

### 5.4 Infrastructure

SQLAlchemy, SQLite, Chroma, LangChain providers, scrapers, renderers, artifact storage, and browsers are adapters. Third-party exceptions are translated into the Job Hunter error taxonomy at adapter boundaries.

### 5.5 Port Rule

Define Ports only for real replacement or test seams, including Repository, UnitOfWork, ModelGateway, EvidenceRetriever, Clock, IDGenerator, ArtifactStore, Collector, Renderer, and Executor. Do not create ceremonial interfaces for ordinary helpers, policies, or value objects.

API composition may depend directly on a concrete Application Use Case while there is one production implementation and inheritance-based test substitutes satisfy the real seam. Introduce an application-level Protocol only when a second non-subclass implementation or substitute must honor the same contract. When lifespan-managed dependencies are read from dynamic framework state, the API boundary must validate them at runtime; an unchecked `cast()` is not validation. If a Protocol later becomes that runtime boundary, make its runtime-checking semantics explicit rather than weakening or deleting the guard.

Application-scoped use cases that must share one transaction or repository graph are composed and overridden as one complete typed bundle. Per-use-case partial overrides are not supported unless the use cases are explicitly independent; composition must not silently combine dependencies backed by different stores.

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

Manual URL provenance accepts only HTTP(S) locators without userinfo. Before Domain State is created, the source adapter must reject URLs whose query or fragment contains an explicitly recognized, case-insensitive secret-bearing parameter name, including token, secret, password, credential, authorization, API-key, and signature families. Ordinary query and fragment data may be retained because they can carry job identity. Rejection is fail-closed, error messages never include parameter values, and the user must provide a clean canonical URL rather than having Job Hunter silently persist or rewrite embedded credentials.

### 6.3 Requirement

ParsedRequirement is a stable, atomic requirement under a JobVersion. It stores requirement ID, text, type, priority (`REQUIRED/PREFERRED/UNSPECIFIED`), and parser provenance. Compound requirements should be decomposed while preserving their mapping to the original JD text.

The initial deterministic baseline preserves normalized JD line boundaries and treats each non-empty bullet/line as one source unit. It removes only recognized bullet prefixes, deduplicates exact normalized lines, applies explicit keyword rules for type/priority, and records parser name/version. Requirement IDs are allocated once per immutable JobVersion and reused by later QuickScreen runs. This baseline enables deterministic workflow tests but makes no parser-quality claim before the dataset and evaluation slice; model parsing and bounded repair remain out of scope here.

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

The current CandidateProfile input is an immutable, human-confirmed screening snapshot containing only target-role keywords, skill keywords, and preferred cities. Creating a newer snapshot changes the active profile projection without deleting older snapshots; every QuickScreenResult references the exact profile ID it used. Evidence remains separate and is not promoted into Profile facts or consumed by QuickScreen automatically.

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

`quick-screen-v1` is deterministic and intentionally conservative: a job outside a non-empty preferred-city set yields `SCREEN_OUT`; an acceptable-city job with both a target-title match and at least one confirmed skill keyword in its ParsedRequirements yields `SCREEN_IN`; all other cases yield `UNCERTAIN`. The result records the active JobVersion, exact CandidateProfile snapshot, Requirement IDs, reason codes, policy version, run ID, and correlation ID.

Running QuickScreen creates a new append-only recommendation and moves the Job to `Screened`. Human Triage records a separate append-only `Shortlisted` or `Skipped` decision referencing the latest recommendation. Users may override either decision later. A new active JobVersion returns the Job to `Imported`, and Triage rejects recommendations for an older JobVersion or any recommendation that is no longer latest.

Candidate Profile freshness is a derived read concern, not mutable state on `QuickScreenResult`: compare the result's exact `profile_id` with the active Candidate Profile ID and report `current` or `stale`. Activating a newer Profile never deletes, rewrites, or invalidates historical screening lineage. A stale-profile result may still support Human Triage when it remains the latest result for the active JobVersion, but user-facing read models must label it and recommend re-screening. Re-screening appends a new result rather than replacing the old one.

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

Spike 5.5 admitted Chroma 1.5.9 with constraints. Production semantic retrieval therefore remains an explicitly installed, default-disabled capability. `semantic-onnx-minilm-v1` wraps Chroma's local `all-MiniLM-L6-v2` ONNX artifact, records its 384 dimensions and archive SHA-256 `913d7300ceae3b2dbc2c50d1de4baacab4be7b9380491c27fab7418616a16ec3`, and passes explicit embeddings to collections configured with no embedding function. Model acquisition is an explicit setup action; request handling never downloads a model. A missing or unusable runtime/model makes semantic retrieval unavailable without blocking authoritative SQLite use. Invalid collection manifests, record metadata, source accounting, or chunk lineage are integrity failures and must fail closed rather than activate fallback.

`evidence-chunk-v1` deterministically splits normalized Evidence content into chunks of at most 192 estimated tokens with a 32-token overlap. A stable EvidenceChunk ID derives from the parent EvidenceVersion ID, chunk-policy version, ordinal, and normalized-content hash. Chunks and embeddings are derivative values: Chroma stores vectors and non-content identity/filter metadata, while RetrievalRun and ContextPackage retain authoritative EvidenceVersion lineage. Chroma never stores Candidate content in its `documents` field.

The first retrieval baseline operates on active EvidenceItemVersions obtained from the authoritative repository. The Application boundary verifies that every returned version matches both the owning EvidenceItem ID and its active-version pointer before eligibility or retrieval. A shared eligibility policy admits only `VALID` Evidence whose sensitivity is explicitly allowed by the caller; excluded IDs and reasons remain in RetrievalRun lineage. Retriever outputs and evaluation reports contain stable IDs, ranks, scores, reasons, and version metadata rather than copying Candidate Evidence content.

`FullContextRetriever` returns every eligible Evidence item in deterministic order or an explicit `NOT_EXECUTABLE` outcome when the versioned deterministic token estimate exceeds its budget. Application and Domain validation independently reject a completed Full Context result that does not cover the exact eligible set. `LexicalMetadataRetriever` uses versioned exact-phrase, normalized-token, and metadata matching with stable ID tie-breaking. It selects a ranked prefix constrained by both `top_k` and the retrieval `max_tokens`; it never skips an oversized higher-ranked item to admit weaker Evidence. A zero-signal result is explicit `NO_RELEVANT_EVIDENCE`, while a signaled top item that cannot fit is `NOT_EXECUTABLE`.

Each RetrievalRun separately records token estimates for the complete eligible Evidence set and for the selected Evidence. The Application boundary recomputes both values from authoritative EvidenceVersion content, requires exact agreement with the adapter result, and rejects a completed selection whose authoritative estimate exceeds `max_tokens`. This is the retrieval-selection budget only; ContextBuilder separately owns the final ContextPackage hard budget after adding Requirements, instructions, and packaging overhead.

`hybrid-rrf-v1` performs application-level reciprocal-rank fusion over independently ranked Lexical/Metadata and Semantic results. Both sources have weight 1.0, the RRF constant is 60, chunk results aggregate to their authoritative EvidenceVersion, and stable EvidenceItem/EvidenceVersion IDs break final ties. Raw lexical and semantic scores are retained as source observations but are never added as though they shared one scale. Final selection remains a deterministic `top_k` and token-budget ranked prefix.

`semantic-chroma-v1` reconstructs the complete allowed EvidenceChunk identity set from the authoritative EvidenceVersion inputs and validates every source match before applying relevance or `top_k` cutoffs. Unknown, stale, cross-scope, or fabricated Evidence/Version/Chunk lineage invalidates the entire retrieval. Cosine distance greater than `0.75` is insufficient under its versioned experimental relevance rule; those valid but irrelevant neighbors do not become retrieval hits. This fixed cutoff enables explicit No-Evidence/Insufficient-Evidence behavior but is not a quality claim and may be recalibrated only through a new retriever version and an eligible evaluation dataset.

### 9.3 Deterministic Retrieval Policy

- eligible tokens within a calibrated threshold: Full Context;
- identifier/certificate/named project/skill lookup: Lexical + Metadata;
- semantic requirement-to-experience matching: Hybrid;
- overlapping conditions use fixed precedence.

Every run records policy version, input statistics, selected strategy, and reason. Hybrid remains experimental and falls back to Full Context or Lexical until it passes promotion thresholds.

`retrieval-policy-v1` uses fixed precedence: executable eligible context at or below 1,200 estimated tokens selects Full Context; identifier, certification, named-project, and explicit-skill lookup selects Lexical/Metadata; semantic requirement-to-experience matching selects Hybrid only when the exact evaluation version is promoted and the semantic runtime is ready. Otherwise it records and executes a Full Context fallback when executable, or Lexical/Metadata when it is not. Policy selection and fallback are never silent.

The Application use case enforces Shortlisted/current-JobVersion eligibility and persists an immutable RetrievalRun linking the Requirement to the exact EvidenceItemVersions and derivative chunks returned. Each run records policy version, input statistics, promotion evidence, semantic readiness, initial and selected strategy, decision/fallback reasons, index/embedding/chunk versions, and zero or one supplemental retrieval. A deterministic sufficiency check may reformulate the atomic Requirement once using its typed metadata; after one supplemental retrieval the result becomes explicit no/insufficient evidence instead of continuing to search.

Only a typed, redacted semantic-runtime-unavailable failure may activate the recorded policy fallback. Invalid source lineage, accounting, or other adapter contract violations fail closed and cannot be reclassified as ordinary semantic unavailability.

### 9.3.1 Evaluation Boundary

Versioned JSON under `evals/datasets/` is untrusted IO and must pass Pydantic validation before a runner constructs typed evaluation cases. Dataset loaders reject duplicate case IDs, dangling or duplicate judgments, relevance judgments outside the case's eligible Evidence universe, and unconfirmed No-Evidence labels. Retrieval Recall@5 is macro-averaged across cases with relevant judgments, Direct-Evidence MRR across cases with at least one `DIRECT` judgment, and No-Evidence Accuracy across explicitly human-confirmed No-Evidence cases. AC-RAG-002 promotion is evaluated only on cases whose eligible context exceeds the fixed policy large-context threshold. It compares Hybrid with a paired Full Context reference over the exact same eligibility universe; when Full Context is not runtime-executable, the runner builds an offline all-eligible reference. Reports retain retrieval-selection token reduction as a diagnostic, while promotion uses only final ContextPackage token reduction after the shared ContextBuilder projection adds protected entries, redaction, chunk overlap, and packaging overhead. Recall and No-Evidence degradation are measured against the paired Full Context results, never against an assumed perfect score; missing large relevant or large No-Evidence samples makes promotion ineligible. Parser atomic precision/recall uses exact normalized-text matching; priority per-class precision, recall, F1, support, and Macro-F1 are calculated only over matched atomic requirements. QuickScreen reports a separate exact-label accuracy and raw confusion counts, using the same policy-version constant as production execution. Every metric includes its numerator/denominator or confusion counts. Replay model outputs remain evaluation-only and cannot enter Domain State or make live-provider calls.

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

`context-builder-v1` records input versions, inclusion/exclusion reasons, redaction, per-entry and total token estimates, packaging overhead, and policy/prompt versions. Requirements, task instructions, minimal workflow identity, and provenance are protected. Evidence is admitted only as a stable ranked prefix after deterministic contact-data redaction and exact ownership validation. When protected entries and overhead exceed the final budget it returns `CONTEXT_BUDGET_EXCEEDED`; it never silently truncates or injects another Job, full conversation history, or the whole Career Vault.

ContextPackage is an immutable SQLite-persisted lineage artifact containing only the exact redacted representation prepared for a later model boundary plus stable source IDs, hashes, and versions. Its complete ordered entry structure and normalized Requirement, RetrievalRun, EvidenceVersion, and EvidenceChunk associations are cross-validated against its runtime-validated payload. Hydration reconstructs Requirement and Profile projections and Evidence chunks from authoritative source rows, reapplies redaction, and verifies exact content, hash, and token accounting; a missing protected entry or any coherent payload/normalized-row fabrication still fails closed. Raw prompts, model responses, unredacted diagnostic snapshots, and Chroma vectors are not ContextPackage state. RuntimeContextManager compaction, externalization, and rehydration remain a later slice.

`context-redaction-v1` removes recognized email addresses and phone numbers from every ContextPackage entry, including protected Requirement/Profile/instruction/workflow projections as well as Evidence chunks, before token accounting and content hashing.

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

The default local adapter uses one lifespan-owned synchronous SQLAlchemy engine/session factory and one short-lived Session per UnitOfWork. SQLite driver transaction control is disabled and SQLAlchemy emits an explicit deferred `BEGIN` for both reads and writes; this preserves concurrent readers while making the first SELECT establish the UnitOfWork snapshot. Application use cases continue to own transaction boundaries and must explicitly close every UnitOfWork, including successful read-only operations. Alembic is the only schema-creation path: setup or an explicit database-upgrade command applies migrations, while application startup validates the schema head and never silently calls `create_all()` or auto-migrates.

Mutable logical roots (`Job`, `EvidenceItem`, and the Candidate Profile active-pointer state) carry infrastructure-owned optimistic revisions. `Job` also owns the authoritative latest-QuickScreen pointer: every re-screen changes that pointer, while a new JobVersion clears it and Triage preserves it. The SQL Repository captures the expected revision when hydrating or reading the root and uses a database compare-and-swap update at flush/commit. Concurrent re-screen and Triage operations therefore cannot both commit from the same Job revision. Revision metadata does not enter Domain models or HTTP contracts. Immutable version and lineage rows remain append-only and are rolled back with the losing transaction.

The initial adapter stores runtime-validated immutable value payloads as JSON text alongside normalized relational columns for identity, ownership, lineage, deterministic write order, active pointers, and revisions. Hydration cross-validates every duplicated identity/ownership field and fails closed on mismatch or invalid payloads. These payloads are an internal persistence representation, not an alternate Domain or API contract; a Domain shape change requires an Alembic data migration as well as schema changes.

QuickScreen-to-Requirement and RetrievalRun-to-Evidence lineage is stored in normalized ordered association rows, not only inside serialized payloads. Composite ownership constraints and hydration checks enforce Job → JobVersion → Requirement, Triage → QuickScreen → Job, RetrievalRun → Requirement → JobVersion, and EvidenceItem → EvidenceItemVersion relationships. Payload and association rows must describe the same lineage; a mismatch fails closed.

Entities that affect generation, approval, or execution are versioned. Snapshot records are immutable after creation. Logical entities hold only an active-version pointer. Privacy deletion may physically remove sensitive content while retaining only non-sensitive entity/version IDs, deletion time, reason, and necessary hash tombstones.

### 15.1 Concurrent Write Boundary

The current in-memory Repository/UoW is a deterministic single-writer development adapter. One UoW commits its Job, JobVersion, and SourceSnapshot state atomically, but overlapping UoWs may overwrite changes because the adapter provides neither transaction isolation nor lost-update prevention. It must not be presented as a production transaction implementation or used in a runtime configuration that permits overlapping mutations.

Concurrent-write design becomes mandatory before any of the following enters the default runtime path:

- SQLAlchemy/SQLite or another persistent Repository/UoW adapter;
- parallel mutation use cases, background writers, or independent local processes sharing authoritative state;
- multiple API workers or any other configuration in which writes can overlap.

The admitted design must prevent silent lost updates. A mutation based on versioned state carries an explicit expected revision or expected active-version identifier; a stale writer fails with the stable conflict/stale-version taxonomy, while committed version history and authoritative lineage remain intact. The persistence slice may choose database constraints, optimistic revision checks, compare-and-swap, or serialization appropriate to SQLite, but must freeze observable transaction and conflict semantics before choosing the mechanism. Process-local locking alone cannot establish a multi-process guarantee.

The admitted SQLite adapter uses foreign-key enforcement, WAL mode, a bounded busy timeout, and SQLAlchemy optimistic version checks. A failed compare-and-swap or stale SQLite snapshot becomes the stable `stale_write` conflict; unrelated database availability failures remain dependency-unavailable errors. SQL statements, parameters, Candidate content, and local database paths are never included in boundary errors or enabled SQL logs.

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
