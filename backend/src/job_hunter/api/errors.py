"""FastAPI-specific Job Hunter error mapping and registration."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from job_hunter.api.contracts.common import ErrorDetail, ErrorResponse
from job_hunter.errors import (
    ConflictError,
    DependencyUnavailableError,
    EntityNotFoundError,
    InputValidationError,
    JobHunterError,
)


def _error_response(code: str, message: str, status_code: int) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


async def _request_validation_error(request: Request, error: Exception) -> JSONResponse:
    del request, error
    return _error_response("input_validation", "Request validation failed", 422)


async def _job_hunter_error(request: Request, error: Exception) -> JSONResponse:
    del request
    if not isinstance(error, JobHunterError):
        return _error_response("job_hunter_error", "Internal application error", 500)
    if isinstance(error, InputValidationError):
        status_code = 422
    elif isinstance(error, EntityNotFoundError):
        status_code = 404
    elif isinstance(error, ConflictError):
        status_code = 409
    elif isinstance(error, DependencyUnavailableError):
        status_code = 503
    else:
        status_code = 500
    return _error_response(error.code, str(error), status_code)


def register_exception_handlers(application: FastAPI) -> None:
    """Register stable API mappings without leaking FastAPI into application code."""
    application.add_exception_handler(RequestValidationError, _request_validation_error)
    application.add_exception_handler(JobHunterError, _job_hunter_error)
