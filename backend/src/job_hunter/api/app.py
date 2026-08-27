"""FastAPI application composition."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel


class HealthStatus(BaseModel):
    """Liveness response contract."""

    status: Literal["ok"] = "ok"


def create_app() -> FastAPI:
    """Create the local Job Hunter API application."""
    application = FastAPI(title="Job Hunter API", version="0.1.0")

    async def health() -> HealthStatus:
        return HealthStatus()

    application.add_api_route(
        "/health",
        health,
        methods=["GET"],
        response_model=HealthStatus,
    )
    return application


app = create_app()
