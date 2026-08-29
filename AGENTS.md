# AGENTS.md

This is the short operational entry point for coding agents. English documentation is authoritative. Chinese translations under `docs/zh/`, including `docs/zh/AGENTS.zh.md`, are provided only for the developer's convenience.

## Authoritative Documents

- Product scope and requirements: `docs/spec.md`
- Architecture, invariants, and technology boundaries: `docs/architecture.md`
- TDD, code standards, and development workflow: `docs/development.md`
- Hard Gates, Quality Targets, and Release Gates: `docs/acceptance.md`
- Current implementation status: `docs/progress.md`

If these documents conflict, stop implementation and reconcile them first. Never resolve ambiguity by choosing broader permissions, a wider product scope, or weaker safety behavior.

`docs/progress.md` reports the current implementation state only. It must stay concise, must be updated with each development slice, and must not redefine requirements, architecture, engineering rules, or acceptance criteria. It is the only project document without a Chinese translation.

## Mandatory Invariants

- Business value takes priority; technology does not enter the main path solely for demonstration.
- AI must not create or alter career facts that lack support in authoritative Candidate Knowledge.
- Keep `QuickScreen` separate from evidence-grounded `DeepFitAnalysis`.
- Keep `MaterialApproval` separate from `ExecutionApproval`; `Ready` never means external execution is authorized.
- LangGraph must never execute or automatically replay browser side effects.
- Collector and Executor are disabled by default. Never implement CAPTCHA bypass, risk-code bypass, or active anti-detection behavior.
- Validate external data at the adapter boundary. Unvalidated data must not enter domain state.
- Keep core Python and TypeScript business code strictly typed. Do not allow `Any`, `unknown`, or third-party exceptions to propagate across boundaries.
- Add concise comments at review-critical boundaries and invariants to explain intent, ownership, transaction or failure semantics, and non-obvious constraints. Do not narrate syntax or preserve stale implementation plans in comments.
- Write a failing test or evaluation contract before implementing deterministic behavior. A feasibility spike must not enter the production path without frozen contracts and tests.
- Do not read, log, commit, or upload cookies, tokens, passwords, browser sessions, or unrelated personal data.

## Completion Check

Before declaring implementation complete, run the repository verification entry point:

```text
./scripts/check
```

Until that script exists, run the equivalent commands documented in `docs/development.md`. Never claim completion while a relevant Hard Gate is failing.
