"""FastAPI lifespan composition for application-scoped dependencies."""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from job_hunter.application.import_job import ImportJob
from job_hunter.infrastructure.memory import InMemoryJobStore, InMemoryUnitOfWorkFactory
from job_hunter.infrastructure.runtime import SystemClock, UuidIdGenerator
from job_hunter.ingestion.manual import JobSourceRegistry, ManualJDSource, ManualURLSource

type AppLifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def _build_default_import_job() -> ImportJob:
    # In-memory composition is deliberate for this slice; durable SQL persistence is
    # deferred and must not be pre-modeled with an empty adapter.
    store = InMemoryJobStore()
    return ImportJob(
        source_registry=JobSourceRegistry((ManualJDSource(), ManualURLSource())),
        unit_of_work_factory=InMemoryUnitOfWorkFactory(store),
        clock=SystemClock(),
        id_generator=UuidIdGenerator(),
    )


def create_lifespan(import_job_override: ImportJob | None) -> AppLifespan:
    """Create one application dependency graph per FastAPI lifespan."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        # Explicit test/application composition always wins; default construction is
        # deferred until startup and happens exactly once for this app lifespan.
        application.state.import_job = (
            import_job_override if import_job_override is not None else _build_default_import_job()
        )
        try:
            yield
        finally:
            # Current dependencies require no close operation. Removing the reference
            # makes the lifecycle boundary explicit and leaves a natural cleanup seam.
            del application.state.import_job

    return lifespan
