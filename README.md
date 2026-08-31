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

The local Manual Job → QuickScreen → Human Triage workspace and backend readback path are established. The default backend now uses an explicitly migrated SQLAlchemy/SQLite store for restart-durable Workspace state and stale-writer rejection. It also includes versioned evaluation contracts, deterministic Evidence retrieval baselines, authoritative RetrievalRun lineage, and offline replay metrics. See [Current implementation progress](docs/progress.md) for the rolling baseline, verification state, risks, and next slice.

`./scripts/setup` installs locked dependencies and upgrades the local database; `./scripts/db-upgrade` applies only the database migration. Application startup validates the current Alembic head and intentionally does not auto-migrate. Repository verification uses `./scripts/check`; deterministic seed evaluation uses `./scripts/eval-replay`. The seed evaluation is a mechanics smoke test and does not claim that the minimum curated Dataset Gate has passed.
