"""Process liveness HTTP route."""

from fastapi import APIRouter

from job_hunter.api.contracts.common import HealthStatus

router = APIRouter()


@router.get("/health", response_model=HealthStatus)
async def health() -> HealthStatus:
    return HealthStatus()
