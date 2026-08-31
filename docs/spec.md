# Job Hunter Product Specification

## 1. Document Authority

This file is the authoritative source for Job Hunter product requirements and MVP scope. It answers **what must be built**. See `architecture.md` for system design, `development.md` for the engineering process, and `acceptance.md` for measurable acceptance criteria. The convenience translation at `zh/spec.zh.md` is not authoritative for Codex or automation.

## 2. Product Definition

Job Hunter is a local-first AI Job Application Workspace for an individual's job search. It reduces the time from job discovery to application-ready materials through job collection or import, normalization, low-cost screening, human shortlisting, Career Evidence Retrieval, deep fit analysis, tailored material generation, factual validation, and application tracking while preserving truthfulness, user control, and end-to-end traceability.

It is neither a fully autonomous Auto Apply Agent nor merely a Resume Generator.

```text
AI responsibilities
discovery, normalization, screening recommendations, retrieval,
analysis, drafting, validation, and assistance

Human responsibilities
final job decisions, factual confirmation, material edits,
material approval, and authorization of external actions
```

## 3. Goals and Priority

### 3.1 Business Goals

- Reduce the effort required to find jobs, reread job descriptions, and perform initial screening.
- Help the user decide quickly whether a role deserves preparation time.
- Retrieve relevant, attributable evidence from Candidate Knowledge for each job requirement.
- Reduce repetitive resume and greeting customization.
- Maintain one system of record for jobs, material versions, approvals, and application progress.

### 3.2 Engineering and Portfolio Goals

Demonstrate LangGraph, Career RAG, Structured Output, controlled Tool Calling, Context Engineering, Human-in-the-loop, Validation/Repair, Traceability, Evaluation, Web/API Integration, and Backend Engineering through real product needs.

### 3.3 Conflict Resolution

Real business value has final veto power. Memory, Skills, MCP, Agentic RAG, and similar capabilities enter the primary workflow only when they solve a concrete, measurable problem. Otherwise they remain deferred capabilities or isolated experiments.

## 4. Target User and Role Scope

The MVP is a single-user, single-machine product for the developer's real job search.

- Region: Shenzhen.
- Primary role family: AI Agent / LLM Application Engineer.
- Adjacent role families: AI Backend Engineer and AI Full-stack Engineer.
- Target companies: 10–20 medium-to-large internet and AI companies, prioritizing official career channels; BOSS is the primary automated collection source for the first release.
- Formal evaluation: only the primary role family receives calibrated data and formal quality claims. Adjacent roles share the capability dimensions and use role-specific weights for preliminary scoring.

## 5. MVP Workflow

```text
Collect / Import
→ Normalize / Deduplicate
→ Parse Requirements
→ QuickScreen
→ Human Job Triage
→ Shortlisted
→ Evidence Retrieval
→ DeepFitAnalysis
→ Greeting / Resume Preparation
→ Validation / Bounded Repair
→ Human Material Review
→ Ready
```

### 5.1 QuickScreen

QuickScreen is a low-cost screening stage before human triage. It may use only:

- normalized job metadata;
- parsed job requirements;
- a limited set of stable, human-confirmed Candidate Profile facts;
- deterministic or bounded screening logic.

It returns `SCREEN_IN`, `SCREEN_OUT`, or `UNCERTAIN`. It does not run full Career RAG and does not claim to provide evidence-grounded fit. The system recommendation and the user's final decision must both be retained.

Each result retains the exact Candidate Profile snapshot used for screening. Creating a newer Profile does not invalidate or rewrite historical results; it makes results based on an older snapshot stale relative to the current Profile. The product must identify that state, recommend re-screening, and still allow the user to continue Human Triage with the historical result. Re-screening creates a new result and never overwrites history.

### 5.2 Human Job Triage

The user may accept or override the QuickScreen recommendation and marks the job `Shortlisted` or `Skipped`. Only Shortlisted jobs enter Evidence Retrieval, DeepFitAnalysis, and material generation.

When Triage uses a QuickScreen result based on a non-current Candidate Profile, the user interface must state that fact explicitly. Re-screening is recommended but is not a mandatory gate.

### 5.3 DeepFitAnalysis

For every atomic requirement, DeepFitAnalysis returns one of:

- `MATCHED`
- `PARTIAL`
- `MISSING`
- `UNKNOWN`

`MATCHED` and `PARTIAL` must reference supporting EvidenceItemVersions. `MISSING` means authoritative Candidate Knowledge supports the conclusion that evidence does not exist. `UNKNOWN` means the available information is insufficient; a retrieval miss must not automatically become `MISSING`.

### 5.4 Material Preparation

Using JobVersion, DeepFitAnalysis, Candidate Evidence, and Resume IR, the system produces:

- a job-specific BOSS greeting;
- a tailored, one-page-first, ATS-friendly resume;
- PDF and PNG artifacts;
- evidence provenance, gaps, and risks;
- a field-level or content-block diff between the AI draft and the current version.

The user edits structured Resume IR while a curated template renders a real-time preview. Template A is required for MVP; Template B is time permitting; Template C is Post-MVP.

## 6. Job Sources

### REQ-JOB-001 — Manual JD Source

The system must permanently support manually supplied JD text.

### REQ-JOB-002 — Manual URL Source

The system must support a job URL plus user-provided content. Manual sources are first-class product capabilities, not temporary fallbacks.

### REQ-JOB-003 — Boss Source

The system provides BOSS collection through a controlled `eatmoreduck/boss-zhipin-scraper` dependency. The dependency is pinned to an immutable commit SHA and isolated behind a Job Hunter-owned adapter contract. It is disabled by default and may run only after passing its Stretch Release Gate and explicit user enablement.

### REQ-JOB-004 — List-first Collection

Initial BOSS collection should fetch list data first. Rule screening produces `PASS`, `REJECT`, or `UNCERTAIN`:

- `PASS` and `UNCERTAIN` proceed to detailed JD acquisition;
- only high-confidence hard rules may directly `REJECT`;
- all filtering records the reason and rule version and remains restorable and rerunnable.

### REQ-JOB-005 — Source Independence

Collector failure must not block existing jobs, Manual Import, DeepFit, Career RAG, material generation, or Tracking.

### REQ-JOB-006 — Freshness

Jobs must retain source, capture/collection time, last verification time, and freshness/stale status. Historical jobs must not be presented as currently active without revalidation.

### REQ-WORKSPACE-001 — Workspace Readback

The local workspace must reconstruct the current backend state after a browser reload without relying on browser persistence. Typed read models expose Jobs with active and historical versions, source/freshness lineage, ParsedRequirements, QuickScreen and Triage history, Candidate Profile snapshots with an active pointer, and EvidenceItems with immutable version history. Profile-relative screening freshness and Triage eligibility are derived projections and never replace authoritative IDs or history.

This requirement does not claim recovery after a backend process restart. Durable restart recovery requires the separately admitted SQLAlchemy/SQLite persistence slice and its concurrent-write gate.

### REQ-PERSIST-001 — Durable Local Persistence

The default local backend must store the complete currently authoritative Workspace graph in a migrated SQLite database so it can be reconstructed after process restart. Persistence must retain immutable histories, active pointers, exact cross-entity lineage, correlation/run IDs, and deterministic ordering. A persistent adapter cannot enter the default path until stale writers fail explicitly without overwriting a successful concurrent commit.

## 7. Candidate Knowledge and Career RAG

### REQ-KNOW-001 — Candidate Knowledge

The only authoritative MVP fact sources are:

- a structured Candidate Profile;
- EvidenceItems entered manually or curated from Markdown/plain text;
- explicit, user-confirmed Preferences.

Arbitrary PDF/DOCX bulk ingestion, automatic deduplication or fact merging, GitHub MCP ingestion, and model-written long-term memory are outside MVP scope.

### REQ-KNOW-002 — Evidence Provenance

Each EvidenceItem must have a stable ID, version, type, date, canonical content, and source/provenance. EvidenceChunks are rebuildable retrieval derivatives and cannot replace EvidenceItems as factual authority.

### REQ-RAG-001 — Retrieval Strategies

The shared `EvidenceRetriever` boundary must implement at least:

- eligible Full Context baseline;
- Lexical / Metadata baseline;
- Hybrid Retriever using metadata, lexical, semantic retrieval, and application-level fusion.

Hybrid RAG is required in MVP, but it becomes the default for a workload only after meeting its promotion threshold.

### REQ-RAG-002 — Retrieval Policy

RetrievalPolicy uses explicit, versioned, benchmarkable deterministic rules. The LLM does not route the first retrieval strategy.

### REQ-RAG-003 — Bounded Agentic Retrieval

The Hybrid workflow permits at most one query reformulation and one supplemental retrieval. If evidence remains insufficient, it must return `NO_RELEVANT_EVIDENCE` or `INSUFFICIENT_EVIDENCE`.

### REQ-RAG-004 — Eligibility Boundary

All Retrievers share candidate scope, task type, sensitivity, permission, validity, and redaction filtering. Full Context means all eligible Evidence. When it exceeds the retrieval budget it must be recorded as not executable; implicit truncation must never be reported as Full Context. Retrieval records both the eligible-Evidence and selected-Evidence token estimates, and any completed selection must respect its retrieval budget. ContextBuilder separately enforces the final ContextPackage budget, including Requirements, instructions, and packaging overhead.

### REQ-EVAL-001 — Reproducible Evaluation Foundations

Evaluation datasets, annotations, replay inputs, metric parameters, and reports must be runtime-validated and versioned. Retrieval ground truth references stable EvidenceItem IDs with explicit relevance grades, and every relevance judgment must belong to that case's complete eligible Evidence universe. A No-Evidence label requires human confirmation and is never inferred from an empty judgment list. Synthetic smoke fixtures may prove runner behavior but cannot be presented as satisfying the minimum Development or Frozen Holdout dataset gates.

## 8. Context Engineering

### REQ-CTX-001 — Context Package

ContextBuilder must construct a versioned ContextPackage from Job Requirements, selected Evidence, user-confirmed facts, Preferences, task instructions, and a minimal workflow projection. It records provenance, inclusion/exclusion reasons, redaction, token accounting, and version.

### REQ-CTX-002 — Runtime Context Manager

MVP must implement a bounded, typed, deterministic RuntimeContextManager supporting:

- typed ContextEntries with priority;
- duplicate and obsolete entry elimination;
- large-result externalization;
- local Artifacts and typed ContextReferences;
- explicit rehydration;
- versioned priority-based compaction;
- explicit failure when protected context still exceeds the budget.

General unlimited conversation compression, recursive LLM summarization, autonomous memory rewriting, and arbitrary cross-workflow history reconstruction are excluded.

## 9. LangGraph and Tool Calling

### REQ-AGENT-001 — Stateful Material Workflow

LangGraph orchestrates only:

```text
Parsed Shortlisted Job
→ Retrieve
→ Deep Fit
→ Draft
→ Validate
→ Repair?
→ Human Review interrupt
→ Approved / Revision Requested
```

Requirement Parsing, QuickScreen, Job Triage, Job Discovery, CRUD, Tracking, renderer implementation, and Browser Execution are outside the Graph. Material Review uses a LangGraph interrupt; Job Triage uses a durable Application/Domain HITL checkpoint.

### REQ-AGENT-002 — Bounded Repair

At most two targeted repair attempts are allowed. Each repair may modify only authorized Resume IR fields and must be followed by full revalidation. Unbounded loops are forbidden.

### REQ-AGENT-003 — Capability Policy

Every node declares a static NodeToolPolicy containing allowed tools, resource scope, call/iteration limits, timeout, token/result-size budget, and side-effect class. Code enforces the policy; prompts do not.

### REQ-AGENT-004 — External Side Effects

Normal Agent tool loops must not receive Browser Executor, external messaging, resume upload, Shell, arbitrary code execution, arbitrary SQL, or general filesystem permissions.

## 10. Grounded Resume

### REQ-RESUME-001 — Resume Claim

AI-generated or AI-rewritten factual content must first exist as a ResumeClaim with text, claim type, EvidenceItemVersion references, transformation type, and validation status.

### REQ-RESUME-002 — Unsupported Claims

A factual claim without Evidence, or one validated as unsupported, must not enter the final resume. Inference, new quantitative results, expanded responsibility, or inferred skill proficiency are high-risk transformations requiring explicit validation or human confirmation.

### REQ-RESUME-003 — Structured Editor

The frontend must provide a Structured Resume Editor, real-time preview, finite curated templates, field/content-block diff, version saving, and PDF/PNG export. Free dragging, arbitrary rich text, arbitrary CSS, and Canva-style design are excluded.

## 11. Human-in-the-loop and Approvals

### REQ-HITL-001 — Job Triage Gate

After QuickScreen, the user must decide Shortlisted or Skipped. The system recommendation and human final decision are both retained.

### REQ-HITL-002 — Material Review Gate

A Validated Draft must pass human review before entering Ready. The page exposes DeepFit, Evidence provenance, unsupported/unknown items, diffs, greeting, and final resume preview.

### REQ-APPROVAL-001 — MaterialApproval

MaterialApproval binds ResumeVersion, optional GreetingVersion, and the actual artifact/hash. It means the user accepts the materials and permits Ready. It grants no external execution authority.

### REQ-APPROVAL-002 — ExecutionApproval

ExecutionApproval references a valid MaterialApproval and binds account, canonical job, action set, artifact versions/hashes, and expiry. It is single-use, scope-bound, time-bound, and consumable only by the deterministic Browser Executor.

### REQ-APPROVAL-003 — Invalidation

A change to material content, version, or hash invalidates the associated MaterialApproval and every unconsumed ExecutionApproval. An Executor must never accept MaterialApproval as execution authority.

## 12. Application Tracking

The MVP business lifecycle is:

```text
Imported
→ Screened
→ Shortlisted / Skipped
→ Preparing
→ Ready
```

Channels may produce non-linear business milestones:

- BOSS: `Contacted`, `MaterialsSent`;
- company ATS: `Applied`;
- Email: `MaterialsSent`.

`Rejected` and `Withdrawn` are terminal states. `Ready` does not mean an external action was authorized or performed. Browser clicks, input, uploads, CAPTCHA, rate limits, and failures belong to ExecutionEvent/execution state and do not expand ApplicationStatus.

## 13. Stretch Goal — Browser Executor

Core MVP completion does not depend on real application execution. If implemented, the Stretch Executor supports only:

- one approved task;
- explicit user start;
- a visible browser;
- one job per execution;
- allowlisted business actions;
- read-back after every action;
- immediate stop for unknown or abnormal states;
- no automatic retry;
- after `PARTIAL`, continuation only under a new, narrower ExecutionApproval for missing steps.

CAPTCHA, rate limits, authentication anomalies, unrecognized page structure, repeated verification failure, or account-security prompts must trip the circuit breaker. CAPTCHA bypass, platform-limit bypass, account switching, and active anti-detection are forbidden.

## 14. Data, Security, and Privacy

- MVP is a localhost single-machine application: React SPA, FastAPI, SQLite, Chroma, and local artifact storage.
- Complete career data, contact information, credentials, cookies, tokens, Chrome Profile, and browser sessions remain local by default.
- Third-party models receive only the minimal redacted ContextPackage needed for the task.
- External traces contain IDs, versions, structure, token/latency data, and error classifications by default. Sensitive invocations may hide inputs/outputs or disable external tracing.
- Raw prompts/responses, diagnostic artifacts, and cropped screenshots use short local retention. Executor screenshots default to seven days.
- Users may delete sensitive source content; the system retains only a non-sensitive tombstone and deletion audit.

## 15. Traceability

The system must maintain traversable authoritative lineage:

```text
SourceSnapshot
→ JobVersion
→ ParsedRequirement
→ RetrievalRun
→ EvidenceChunk / EvidenceItemVersion
→ ContextPackage
→ ModelInvocation
→ ResumeClaim
→ ValidationResult
→ ResumeVersion
→ MaterialApproval
→ ExecutionApproval / ExecutionEvent
```

Domain Lineage is authoritative. LangSmith and system observability do not replace it.

## 16. Explicit Non-goals

- unattended or long-running batch Auto Apply;
- automatic final submission or automatic external communication;
- CAPTCHA bypass, risk-code bypass, or active anti-detection;
- crawling the entire internet for jobs;
- arbitrary document bulk ingestion and automatic fact merging;
- model-written Candidate Facts or general long-term memory;
- dynamic Skill Runtime, plugin marketplace, or general MCP platform;
- Shell, general code execution, or an OS/container sandbox;
- SaaS, multi-tenancy, Redis, Celery, microservices, or Kubernetes;
- external vector services, a full observability platform, Electron, or Cloud Control Plane;
- a free-form resume design tool.

## 17. Deferred Capabilities

- read-only GitHub MCP Client producing human-reviewed Evidence Drafts;
- versioned Skill Registry with progressive disclosure;
- Interview Preparation, Application Questions, and Company Research;
- additional curated templates and optional Electron packaging;
- company career/ATS connectors;
- small-batch Executor;
- Experience Memory;
- Cloud Control Plane plus Local Execution Agent;
- PostgreSQL, remote executors, and production-grade observability.
