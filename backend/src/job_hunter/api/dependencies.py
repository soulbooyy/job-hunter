"""Request-time access to lifespan-managed application dependencies."""

from typing import Annotated, cast

from fastapi import Depends, Request

from job_hunter.application.import_job import ImportJob


def get_import_job(request: Request) -> ImportJob:
    """Return the ImportJob initialized once by the application lifespan."""
    try:
        candidate = cast(object, request.app.state.import_job)
    except AttributeError:
        raise RuntimeError("ImportJob is unavailable outside the application lifespan") from None
    if not isinstance(candidate, ImportJob):
        raise RuntimeError("Application state contains an invalid ImportJob dependency")
    return candidate


ImportJobDep = Annotated[ImportJob, Depends(get_import_job)]
