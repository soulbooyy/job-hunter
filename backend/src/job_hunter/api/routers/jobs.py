"""Job-related HTTP routes and boundary mapping."""

from typing import Annotated

from fastapi import APIRouter, Path

from job_hunter.api.contracts.common import ErrorResponse
from job_hunter.api.contracts.jobs import ImportJobRequest, ImportJobResponse
from job_hunter.api.contracts.screening import (
    QuickScreenRequest,
    QuickScreenResponse,
    TriageRequest,
    TriageResponse,
)
from job_hunter.api.dependencies import ImportJobDep, RecordJobTriageDep, RunQuickScreenDep

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.post(
    "/import",
    response_model=ImportJobResponse,
    status_code=201,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def import_manual_job(
    request: ImportJobRequest,
    import_job: ImportJobDep,
) -> ImportJobResponse:
    result = import_job.execute(request.to_command())
    return ImportJobResponse.from_result(result)


@router.post(
    "/{job_id}/screen",
    response_model=QuickScreenResponse,
    status_code=201,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def run_quick_screen(
    job_id: Annotated[str, Path(min_length=1, pattern=r"^\S+$")],
    request: QuickScreenRequest,
    use_case: RunQuickScreenDep,
) -> QuickScreenResponse:
    return QuickScreenResponse.from_result(use_case.execute(request.to_command(job_id)))


@router.post(
    "/{job_id}/triage",
    response_model=TriageResponse,
    status_code=201,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def record_job_triage(
    job_id: Annotated[str, Path(min_length=1, pattern=r"^\S+$")],
    request: TriageRequest,
    use_case: RecordJobTriageDep,
) -> TriageResponse:
    return TriageResponse.from_result(use_case.execute(request.to_command(job_id)))
