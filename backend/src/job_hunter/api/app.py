"""FastAPI application composition root."""

from fastapi import FastAPI

from job_hunter.api.errors import register_exception_handlers
from job_hunter.api.lifespan import create_lifespan
from job_hunter.api.routers import health, jobs
from job_hunter.application.import_job import ImportJob


def create_app(*, import_job: ImportJob | None = None) -> FastAPI:
    """Create the local Job Hunter API application."""
    application = FastAPI(
        title="Job Hunter API",
        version="0.1.0",
        lifespan=create_lifespan(import_job),
    )

    register_exception_handlers(application)
    application.include_router(health.router)
    application.include_router(jobs.router)
    return application


app = create_app()
