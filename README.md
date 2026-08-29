# Job Hunter

Job Hunter is a local-first AI Job Application Workspace for an individual's job search. It organizes job acquisition, low-cost screening, human decision-making, Career Evidence Retrieval, deep job-fit analysis, tailored material generation, factual validation, and application tracking into one traceable, semi-automated workflow.

The core boundary is simple: AI may discover, analyze, retrieve, draft, and validate; the user retains final control over job decisions, factual confirmation, material approval, and every external action.

## MVP Workflow

```text
Collect / Import
→ Normalize / Deduplicate
→ Parse Requirements
→ QuickScreen
→ Human Job Triage
→ Shortlisted
→ Evidence Retrieval
→ DeepFitAnalysis
→ Material Preparation
→ Validation / Bounded Repair
→ Human Material Review
→ Ready
```

Single-job BOSS outreach and result read-back are a Stretch Goal. Even when implemented, the executor must remain disabled until it passes separate safety, idempotency, and read-back verification gates.

## Positioning

- The first release targets AI Agent / LLM Application Engineer roles in Shenzhen.
- AI Backend Engineer and AI Full-stack Engineer roles may use the shared capability model and preliminary role weights, but are outside the MVP's formal quality claims.
- Career RAG, LangGraph, Context Engineering, and Human-in-the-loop must solve concrete problems and be evaluated.
- Unattended batch applications, CAPTCHA bypass, active anti-detection work, general code execution, and multi-tenant SaaS are explicit non-goals.

## Authoritative Documentation

- [Product specification](docs/spec.md)
- [System architecture](docs/architecture.md)
- [Development guide](docs/development.md)
- [Acceptance criteria](docs/acceptance.md)
- [Current implementation progress](docs/progress.md)

The English documents are authoritative for Codex, automation, implementation, and acceptance. Chinese translations are provided for the developer:

- [Chinese README](docs/zh/README.zh.md)
- [Chinese product specification](docs/zh/spec.zh.md)
- [Chinese system architecture](docs/zh/architecture.zh.md)
- [Chinese development guide](docs/zh/development.zh.md)
- [Chinese acceptance criteria](docs/zh/acceptance.zh.md)

`spec.md` defines what to build, `architecture.md` defines how it is designed, `development.md` defines how it is built, and `acceptance.md` defines how completion is proven. `progress.md` reports the current implementation state without redefining those authorities and intentionally has no Chinese copy.

## Status

The reproducible development environment, deterministic CI workflow, and core run/correlation identifiers are established. The domain versioning and lineage foundation with first-class Manual Job Sources is implemented and verified in the current uncommitted working tree. See [Current implementation progress](docs/progress.md) for the rolling baseline, verification state, risks, and next slice.
