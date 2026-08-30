"""FastAPI lifespan composition for application-scoped dependencies."""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI

from job_hunter.application.candidate_knowledge import CreateCandidateProfile, SaveEvidence
from job_hunter.application.import_job import ImportJob
from job_hunter.application.screening import RecordJobTriage, RunQuickScreen
from job_hunter.application.workspace_queries import WorkspaceQueries
from job_hunter.infrastructure.memory import InMemoryStore, InMemoryUnitOfWorkFactory
from job_hunter.infrastructure.runtime import SystemClock, UuidIdGenerator
from job_hunter.ingestion.manual import JobSourceRegistry, ManualJDSource, ManualURLSource

type AppLifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


@dataclass(frozen=True, slots=True)
class ApplicationUseCases:
    """Complete application graph owned by one FastAPI lifespan."""

    import_job: ImportJob
    create_candidate_profile: CreateCandidateProfile
    save_evidence: SaveEvidence
    run_quick_screen: RunQuickScreen
    record_job_triage: RecordJobTriage
    workspace_queries: WorkspaceQueries


def _build_default_use_cases() -> ApplicationUseCases:
    # One store/UoW graph makes Job checkpoints and their Candidate Knowledge,
    # requirement, screening, and triage lineage visible in the same transaction.
    store = InMemoryStore()
    unit_of_work_factory = InMemoryUnitOfWorkFactory(store)
    clock = SystemClock()
    id_generator = UuidIdGenerator()
    return ApplicationUseCases(
        import_job=ImportJob(
            source_registry=JobSourceRegistry((ManualJDSource(), ManualURLSource())),
            unit_of_work_factory=unit_of_work_factory,
            clock=clock,
            id_generator=id_generator,
        ),
        create_candidate_profile=CreateCandidateProfile(
            unit_of_work_factory=unit_of_work_factory,
            clock=clock,
            id_generator=id_generator,
        ),
        save_evidence=SaveEvidence(
            unit_of_work_factory=unit_of_work_factory,
            clock=clock,
            id_generator=id_generator,
        ),
        run_quick_screen=RunQuickScreen(
            unit_of_work_factory=unit_of_work_factory,
            clock=clock,
            id_generator=id_generator,
        ),
        record_job_triage=RecordJobTriage(
            unit_of_work_factory=unit_of_work_factory,
            clock=clock,
            id_generator=id_generator,
        ),
        workspace_queries=WorkspaceQueries(unit_of_work_factory=unit_of_work_factory),
    )


def create_lifespan(use_cases_override: ApplicationUseCases | None = None) -> AppLifespan:
    """Create one application dependency graph per FastAPI lifespan."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        # Overrides own the complete graph. Mixing individual replacements with
        # defaults could silently split related use cases across different stores.
        use_cases = (
            use_cases_override if use_cases_override is not None else _build_default_use_cases()
        )
        application.state.import_job = use_cases.import_job
        application.state.create_candidate_profile = use_cases.create_candidate_profile
        application.state.save_evidence = use_cases.save_evidence
        application.state.run_quick_screen = use_cases.run_quick_screen
        application.state.record_job_triage = use_cases.record_job_triage
        application.state.workspace_queries = use_cases.workspace_queries
        try:
            yield
        finally:
            # Current in-memory dependencies require no close operation. Removing all
            # references keeps the lifecycle boundary explicit for future resources.
            del application.state.import_job
            del application.state.create_candidate_profile
            del application.state.save_evidence
            del application.state.run_quick_screen
            del application.state.record_job_triage
            del application.state.workspace_queries

    return lifespan
