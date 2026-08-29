"""Job-related HTTP routes and boundary mapping."""

from fastapi import APIRouter

from job_hunter.api.contracts.common import ErrorResponse
from job_hunter.api.contracts.jobs import ImportJobRequest, ImportJobResponse
from job_hunter.api.dependencies import ImportJobDep

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
