"""Candidate Knowledge HTTP routes."""

from typing import Any

from fastapi import APIRouter

from job_hunter.api.contracts.common import ErrorResponse
from job_hunter.api.contracts.knowledge import (
    CandidateProfileRequest,
    CandidateProfileResponse,
    EvidenceRequest,
    EvidenceResponse,
)
from job_hunter.api.dependencies import CreateCandidateProfileDep, SaveEvidenceDep

router = APIRouter(prefix="/api/v1/knowledge", tags=["candidate-knowledge"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


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
