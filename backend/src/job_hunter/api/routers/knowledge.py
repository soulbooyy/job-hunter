"""Candidate Knowledge HTTP routes."""

from typing import Any

from fastapi import APIRouter, Response

from job_hunter.api.contracts.common import ErrorResponse
from job_hunter.api.contracts.knowledge import (
    CandidateProfileRequest,
    CandidateProfileResponse,
    EvidenceRequest,
    EvidenceResponse,
)
from job_hunter.api.contracts.workspace import (
    CandidateProfileHistoryResponse,
    EvidenceHistoryResponse,
)
from job_hunter.api.dependencies import (
    CreateCandidateProfileDep,
    SaveEvidenceDep,
    WorkspaceQueriesDep,
)

router = APIRouter(prefix="/api/v1/knowledge", tags=["candidate-knowledge"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


@router.get(
    "/profiles",
    response_model=CandidateProfileHistoryResponse,
    responses={503: {"model": ErrorResponse}},
)
async def list_candidate_profiles(
    response: Response,
    queries: WorkspaceQueriesDep,
) -> CandidateProfileHistoryResponse:
    result = queries.list_profiles()
    response.headers["Cache-Control"] = "no-store"
    return CandidateProfileHistoryResponse.from_result(result)


@router.get(
    "/evidence",
    response_model=EvidenceHistoryResponse,
    responses={503: {"model": ErrorResponse}},
)
async def list_evidence(
    response: Response,
    queries: WorkspaceQueriesDep,
) -> EvidenceHistoryResponse:
    result = queries.list_evidence()
    response.headers["Cache-Control"] = "no-store"
    return EvidenceHistoryResponse.from_result(result)


@router.post(
    "/profile",
    response_model=CandidateProfileResponse,
    status_code=201,
    responses={code: value for code, value in _ERROR_RESPONSES.items() if code != 404},
)
async def create_candidate_profile(
    request: CandidateProfileRequest,
    use_case: CreateCandidateProfileDep,
) -> CandidateProfileResponse:
    return CandidateProfileResponse.from_result(use_case.execute(request.to_command()))


@router.post(
    "/evidence",
    response_model=EvidenceResponse,
    status_code=201,
    responses=_ERROR_RESPONSES,
)
async def save_evidence(
    request: EvidenceRequest,
    use_case: SaveEvidenceDep,
) -> EvidenceResponse:
    return EvidenceResponse.from_result(use_case.execute(request.to_command()))
