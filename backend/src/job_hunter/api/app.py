"""FastAPI application composition root."""

from fastapi import FastAPI

from job_hunter.api.errors import register_exception_handlers
from job_hunter.api.lifespan import ApplicationUseCases, create_lifespan
from job_hunter.api.routers import health, jobs, knowledge
from job_hunter.config import RuntimeSettings


def create_app(
    *,
    use_cases: ApplicationUseCases | None = None,
    settings: RuntimeSettings | None = None,
) -> FastAPI:
    """Create the local Job Hunter API application."""
    application = FastAPI(
        title="Job Hunter API",
        version="0.1.0",
        lifespan=create_lifespan(use_cases, settings=settings),
    )

    register_exception_handlers(application)
    application.include_router(health.router)
    application.include_router(jobs.router)
    application.include_router(knowledge.router)
    return application


app = create_app()
