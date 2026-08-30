# Job Hunter Acceptance Criteria

## 1. Document Authority

This file is the authoritative source for MVP acceptance, quality targets, and release gates. It answers **how completion is proven**. Datasets, rubrics, runners, and reports live under `evals/`. The Chinese translation at `zh/acceptance.zh.md` is provided for the developer's convenience and is not authoritative for Codex or automation.

## 2. Acceptance Model

### 2.1 Acceptance Severity

| Type | Meaning | Consequence when unmet |
|---|---|---|
| Hard Gate | Core business, safety, correctness, and reproducible verification | MVP is not complete |
| Quality Target | Measured quality of AI capabilities | Must be reported and must restrict default enablement, mark the capability experimental, narrow its supported scope, or record an explicit deviation |
| Stretch Release Gate | Optional external capabilities such as Collector and Executor | Capability remains disabled or unavailable; core MVP is not blocked |

### 2.2 Evaluation Environments

- **Synthetic:** edge cases, error behavior, and invariants.
- **Development/Replay:** repeatable iteration and regression testing.
- **Frozen Holdout:** independent evaluation not used for tuning.
- **Live/Real-world:** real providers, BOSS, or actual usage.

Report each environment separately. Do not compute a blended overall score. Hard Gates must not depend on the current availability of BOSS or the randomness of a live model.

## 3. Dataset Gates

### AC-DATA-001 — Minimum Dataset

Hard Gate:

```text
Development Set
- at least 20 realistic/replay Jobs
- at least 100 atomic Requirements

Frozen Holdout
- at least 10 Jobs
- at least 50 atomic Requirements
- 20%–30% of atomic Requirements are human-confirmed No-Evidence cases

Synthetic Edge Cases
- at least 20 independent cases
```

### AC-DATA-002 — Dataset Governance

- Every sample records source, generation method, human edits, split, annotation version, and dataset version.
- Requirement Ground Truth uses stable EvidenceItem IDs, supports multiple labels, and grades relevance as `DIRECT`, `PARTIAL`, or `BACKGROUND`.
- `no_relevant_evidence=true` requires explicit human confirmation and must not be inferred from an empty judgment list.
- A Holdout case used for targeted tuning is leaked. Move it to Development and replace it with a new Holdout case.
- Report Synthetic, Replay, Holdout, and Live results separately.
- Reports must disclose the limited sample size and must not claim representation of all AI roles.

### AC-EVAL-001 — Evaluation Foundation

- Invalid dataset structure, duplicate IDs, dangling judgments, judgments outside the eligible Evidence universe, and unconfirmed No-Evidence labels fail closed before evaluation begins.
- Full Context and Lexical/Metadata baselines apply the same eligibility input, preserve exact EvidenceItemVersion lineage, and are deterministic under repeated execution.
- Full Context either returns all eligible Evidence or `NOT_EXECUTABLE`; it never silently truncates.
- Completed retrieval runs keep selected-Evidence token estimates within `max_tokens` and report eligible-Evidence and selected-Evidence estimates separately.
- Retrieval and parser metrics match hand-calculated fixtures, include raw counts, priority per-class precision/recall/F1/support, and shared production/evaluation version metadata, and do not copy Candidate Evidence content into reports.
- `./scripts/eval-replay` runs without network, database, model, or browser dependencies and clearly reports that seed smoke fixtures do not satisfy AC-DATA-001.

## 4. Functional Hard Gates

### AC-JOB-001 — Source Independence

- ManualJDSource and ManualURLSource can independently complete the primary workflow.
- BossSource failure does not block saved jobs or downstream workflows.
- Source provenance, captured time, and freshness are complete.

### AC-PERSIST-001 — Concurrent Write Admission

This Hard Gate becomes applicable before a persistent Repository/UoW adapter or any runtime configuration that permits overlapping mutations enters the default path.

- In a deterministic scenario, two UoWs read the same entity version before either commits.
- The first valid commit succeeds; the stale commit cannot silently overwrite it and returns the stable conflict/stale-version error contract.
- The successful state, immutable version history, active-version pointer, and authoritative lineage remain mutually consistent after the rejected commit.
- The gate runs against the admitted persistence adapter at its real coordination boundary. A process-local-only lock is insufficient evidence for a multi-process claim.
- An adapter that does not pass this gate remains limited to an explicitly single-writer development or test configuration.

### AC-SCREEN-001 — Screening and Triage

- QuickScreen emits only `SCREEN_IN`, `SCREEN_OUT`, or `UNCERTAIN`.
- The QuickScreen recommendation and human decision are both retained.
- A Candidate Profile update does not rewrite or remove earlier QuickScreen results; each historical result retains traversable lineage to the exact Profile snapshot used.
- A user-facing screening read model labels a result based on a non-current Profile as stale and recommends re-screening, while still allowing Human Triage to proceed with that result.
- Re-screening creates a new QuickScreen result without overwriting history.
- The user can restore or override filtered jobs.
- Only Shortlisted jobs enter DeepFit and material preparation.

### AC-WORKSPACE-001 — Workspace Readback

- Empty Job, Profile, and Evidence collections return typed `200` responses rather than fabricated entities.
- After deterministic mutation fixtures, GET read models reproduce active pointers, immutable versions, source/freshness lineage, ParsedRequirements, QuickScreen results, and Triage decisions without loss or reordering.
- A QuickScreen result is `stale` only relative to a newer active Candidate Profile; Profile staleness does not by itself make Triage ineligible.
- A result for a historical JobVersion or a result that is no longer latest remains readable but is not Triage-eligible.
- Unknown Job detail returns the stable `404` ErrorResponse, dependency failures return the stable `503` contract, and sensitive read responses include `Cache-Control: no-store`.
- Readback tests may prove browser-reload recovery while the in-memory backend remains alive, but must not claim backend-restart durability.

### AC-FIT-001 — Deep Fit Structure

- Every successfully parsed atomic Requirement has a stable requirement ID.
- Each DeepFit Requirement is classified as `MATCHED`, `PARTIAL`, `MISSING`, or `UNKNOWN`.
- Every `MATCHED` or `PARTIAL` result references supporting EvidenceItemVersions.
- `MISSING` and `UNKNOWN` never fabricate Evidence; a retrieval miss does not automatically mean `MISSING`.
- Structured Output that remains invalid after bounded repair fails explicitly and does not enter Domain State.

### AC-HITL-001 — Human Gates

- Job Triage interrupt/resume scenarios pass 100%.
- Material Review interrupt/resume scenarios pass 100%.
- Fact conflicts, sensitive or unknown information, and low-confidence decisions can trigger a conditional interrupt.

Job Triage verifies an Application/Domain checkpoint. Material Review verifies a LangGraph interrupt/checkpoint. They do not need to share one state machine.

## 5. Retrieval Quality

### AC-RAG-001 — Hybrid Promotion Targets

Initial Frozen Holdout Quality Targets:

| Metric | Target |
|---|---:|
| EvidenceItem Recall@5 | at least 0.85 |
| Direct-Evidence MRR | at least 0.70 |
| No-Evidence Accuracy | at least 0.90 |

No-Evidence results must also report raw correct/total counts. When Hybrid misses a threshold, it remains an implemented experimental capability, but RetrievalPolicy must not select it by default.

### AC-RAG-002 — Context Efficiency

For samples with large eligible contexts:

| Metric | Target |
|---|---:|
| Context token reduction | at least 30% |
| Recall@5 degradation | no more than 5 percentage points |
| No-Evidence degradation | no more than 2 percentage points |

Compare directly against eligible Full Context when it is runtime feasible. Otherwise use an offline eligible full-evidence reference. The eligibility scope must remain identical.

### AC-RAG-003 — Retrieval Correctness Hard Gates

- Factual Claim provenance coverage equals 100%.
- Metric runners, datasets, retriever/policy versions, and parameters are reproducible.
- The fallback path is verified when Hybrid misses promotion targets.
- Bounded Agentic RAG performs at most one query reformulation and returns an explicit no/insufficient-evidence result when evidence remains inadequate.

## 6. Parser and Fit Quality Targets

| Metric | Initial target |
|---|---:|
| Atomic Requirement Recall | at least 0.90 |
| Atomic Requirement Precision | at least 0.85 |
| Requirement Priority Macro-F1 | at least 0.85 |

Priority classes are `REQUIRED`, `PREFERRED`, and `UNSPECIFIED`. Reports must include raw counts and per-class metrics. Human Acceptance Rate and Override Rate are observed and reported but are not MVP Hard Gates.

QuickScreen has a separate lightweight evaluation and must not be evaluated as DeepFit.

## 7. Resume Grounding Hard Gates

### AC-RESUME-001 — Provenance and Support

| Invariant | Gate |
|---|---:|
| Factual Claim provenance coverage | 100% |
| Validator-known unsupported claims | 0 |
| Unapproved high-risk inferences | 0 |
| Failed or unresolved validation entering Ready | 0 |
| Approval to ResumeVersion/artifact-hash match | 100% |

### AC-RESUME-002 — Manual Holdout Review

Perform human claim-level grounding review on every factual Claim in the Frozen Holdout. The unsupported factual Claim rate must equal 0%. Finding one unsupported Claim fails this gate. Move the case into Development during remediation and replace it with a new Frozen Holdout case.

A report may state only that no unsupported factual claims were observed in dataset/version X. It must not claim that the system can never hallucinate.

## 8. Context Management

### AC-CTX-001 — Hard Gates

| Invariant | Gate |
|---|---:|
| Protected-entry loss | 0 |
| ContextReference rehydration correctness | 100% |
| Provenance continuity | 100% |
| Unsupported factual claims introduced by compaction | 0 |
| Silent truncation | 0 |

When protected context still exceeds the budget, the workflow must return `CONTEXT_BUDGET_EXCEEDED`.

### AC-CTX-002 — Stress Benchmark Quality Targets

| Metric | Target |
|---|---:|
| Active-context token reduction | at least 25% |
| Effective Evidence Recall degradation | no more than 5 percentage points |
| Workflow completion degradation | no more than 5 percentage points |

Reports should expose the token-saving versus quality-loss trade-off across workloads.

## 9. Workflow and Capability Policy Hard Gates

All defined deterministic scenarios must pass 100%:

- every legal conditional route;
- rejection of every defined illegal state transition;
- Job Triage and Material Review interrupt/checkpoint/resume;
- no more than 2 repair attempts;
- checkpoint recovery does not regenerate or persist already-frozen versions;
- unauthorized NodeToolPolicy calls are rejected;
- tool-call, iteration, timeout, token/cost, and result-size budgets are enforced;
- Graph-triggered browser external side effects equal 0;
- valid run ID and correlation ID coverage equals 100%.

Timeout and budget tests use deterministic or fake timing to avoid flaky CI.

## 10. Traceability Hard Gates

### AC-TRACE-001 — Traversable Lineage

For every final factual ResumeClaim:

- a semantically valid path to EvidenceItemVersion exists in 100% of cases;
- a path to ParsedRequirement/JobVersion exists in 100% of cases;
- a path to ValidationResult/ResumeVersion exists in 100% of cases.

AI-generated or AI-rewritten factual Claims must also traverse to ContextPackage/ModelInvocation in 100% of cases. Human-authored or human-edited Claims record human provenance and must not fabricate a ModelInvocation.

Every ResumeVersion entering Ready must traverse to a valid MaterialApproval in 100% of cases.

### AC-TRACE-002 — Corruption Rejection

The following negative scenarios must fail closed:

- missing parent or reference;
- wrong artifact hash;
- cross-job Evidence binding;
- broken version reference;
- stale or invalid MaterialApproval;
- use of MaterialApproval as ExecutionApproval;
- ExecutionApproval referencing an invalid MaterialApproval.

Tests verify reference existence, target/version/hash match, semantic validity, and complete traversal—not merely non-null IDs.

## 11. Approval Hard Gates

- MaterialApproval and ExecutionApproval use different types and validation logic.
- Ready never means execution permission.
- Executor cannot consume MaterialApproval.
- ExecutionApproval references a valid MaterialApproval with matching versions and hashes.
- Material mutation invalidates MaterialApproval and all unconsumed ExecutionApprovals that reference it.
- ExecutionApproval remains single-use, scope-bound, and time-bound.
- Consumed Approvals preserve history; every later action requires a new Approval.

## 12. Rendering Hard Gates

The same Resume IR, template version, and renderer version must produce consistent semantic content and layout. Template A includes at least 5 golden fixtures with different content densities and satisfies:

- no missing required fields;
- no overlapping, clipped, or invisible required text;
- every designated fixture remains one page;
- extracted PDF text matches ResumeClaim content;
- visual regression stays within the defined tolerance;
- both PDF and PNG export succeed.

Byte-identical PDFs are not required. MaterialApproval binds to the actual displayed artifact hash.

## 13. Web Workspace Hard Gates

Playwright deterministic CI uses fake/replay services to cover:

1. ManualJDSource fixture → normalize → inspect → triage;
2. BossSource normalized fixture → the same downstream workflow;
3. Shortlist → Evidence Retrieval/DeepFit → material generation;
4. Resume IR edit → preview/diff → validation → MaterialApproval;
5. PDF/PNG export → Ready.

Failure coverage includes no Evidence, structured-output failure, stale or invalid Approval, and backend unavailable. CI accesses neither live BOSS nor a live LLM.

## 14. Runtime Budgets

### AC-BUDGET-001 — Mechanism Hard Gate

Fit and Material Workflows must have configurable, versioned, observable, runtime-enforced latency, model-call, and token/cost budgets. When a budget is exceeded, the workflow stops or pauses with an explicit status. It must not retry without bounds, silently exceed the budget, or switch automatically to an unvalidated model.

Every run records actual latency, calls, tokens, and cost.

### AC-BUDGET-002 — BudgetPolicy v1

Freeze specific thresholds after the primary-model feasibility benchmark. The hypotheses of 90 seconds/5 calls, 3 minutes/10 calls, and US$0.50 are starting references, not current Hard Gates. Before the corresponding capability is enabled by default, BudgetPolicy v1 must exist in versioned configuration and its evaluation report.

## 15. Privacy and Security Hard Gates

- API keys, cookies, tokens, passwords, session secrets, and unrelated page content never enter logs, traces, or metrics.
- External LangSmith traces do not upload complete Candidate Profiles, resumes, Evidence, or PII by default.
- Sensitive invocations can disable input/output tracing.
- Raw prompts/responses and diagnostic artifacts follow local retention and redaction policies.
- Privacy deletion can physically remove sensitive content while retaining only a minimal tombstone.
- Collector and Executor are disabled by default and contain no CAPTCHA/risk bypass or active anti-detection behavior.
- Normal Agent tool loops receive no external-side-effect, Shell, or general code-execution permissions.

Use canary secret and PII fixtures to verify redaction and forbidden-log behavior.

## 16. BossSource Stretch Release Gate

Every condition must pass before enablement:

- immutable SHA, lock, and license/admission record are complete;
- adapter contract fixtures pass 100%;
- malformed or schema-drift output is rejected before domain writes;
- CAPTCHA, risk codes, login anomalies, and unknown results fail closed;
- the source is disabled by default and live smoke runs only under explicit user invocation;
- source, `captured_at`, freshness, and adapter version are traceable;
- live failure is explicit and offers Manual Import fallback.

MVP makes no guarantee of BOSS coverage, long-term success rate, anti-bot resilience, or always-on availability.

## 17. Browser Executor Stretch Release Gate

Every condition must pass before the UI may label the capability `experimental enabled`:

- disabled by default, one task, visible browser, explicit user start;
- Approval scope/hash/expiry checks pass 100%;
- idempotency tests pass 100%;
- partial-success failure-injection tests pass 100%;
- automatic retry is disabled;
- CAPTCHA, rate limit, or unknown page state trips the circuit breaker immediately;
- dry-run/simulation passes 100%;
- at least one explicitly user-approved real single-job execution has read-back evidence of the expected external effect.

When any condition is unmet, code or a feasibility report may remain, but the UI must not expose the execution entry point.

## 18. MVP Completion

Core MVP is complete only when:

1. every Hard Gate passes;
2. every Quality Target is measured, versioned, and reported;
3. each unmet Quality Target applies an explicit capability consequence;
4. `./scripts/check` and reproducible replay evaluation pass;
5. README, Spec, Architecture, Development, and Acceptance documents match implementation;
6. every Stretch capability that misses its gate remains disabled;
7. synthetic/replay metrics are not presented as real Time-to-Application improvement.

Collect a real manual Time-to-Application baseline only after entering real usage. Record screening, analysis, tailoring, preparation, and form-filling time separately. Business-efficiency claims require real comparative usage rather than synthetic benchmarks.

## 19. Requirement Traceability Matrix

| Spec Requirement | Primary acceptance evidence |
|---|---|
| REQ-JOB-001 / REQ-JOB-002 / REQ-JOB-005 / REQ-JOB-006 | AC-JOB-001, Web Workspace path 1, source/freshness contract tests |
| REQ-JOB-003 / REQ-JOB-004 | BossSource Stretch Release Gate, adapter and three-way screening tests |
| REQ-WORKSPACE-001 | AC-WORKSPACE-001, backend read-model contracts, browser-reload tests |
| REQ-EVAL-001 | AC-DATA-001/002, AC-EVAL-001, reproducible replay reports |
| REQ-KNOW-001 / REQ-KNOW-002 | Dataset Gates, AC-RAG-003, AC-TRACE-001/002 |
| REQ-RAG-001 / REQ-RAG-002 | AC-RAG-001/002, fallback and policy-version tests |
| REQ-RAG-003 / REQ-RAG-004 | AC-RAG-003, budget/eligibility/no-evidence tests |
| REQ-CTX-001 | AC-TRACE-001, ContextPackage schema/redaction/token tests |
| REQ-CTX-002 | AC-CTX-001/002 |
| REQ-AGENT-001 | AC-HITL-001, Workflow and Capability Policy Hard Gates |
| REQ-AGENT-002 / REQ-AGENT-003 / REQ-AGENT-004 | Workflow and Capability Policy Hard Gates, Privacy and Security Hard Gates |
| REQ-RESUME-001 / REQ-RESUME-002 | AC-RESUME-001/002, AC-TRACE-001/002 |
| REQ-RESUME-003 | Rendering Hard Gates, Web Workspace paths 3–5 |
| REQ-HITL-001 / REQ-HITL-002 | AC-SCREEN-001, AC-HITL-001, Web Workspace paths 1–4 |
| REQ-APPROVAL-001 / REQ-APPROVAL-002 / REQ-APPROVAL-003 | Approval Hard Gates, AC-TRACE-002, Browser Executor Stretch Release Gate |

When a stable Requirement ID is added or changed, update this matrix or provide an equivalent machine-traceable mapping.
