from ipaddress import IPv4Address

import pytest
from fastapi.routing import APIRoute
from pydantic import AnyHttpUrl, ValidationError

import job_hunter
from job_hunter.api.app import app
from job_hunter.config import RuntimeSettings


def test_package_is_importable() -> None:
    assert job_hunter.__version__ == "0.1.0"


def test_fastapi_scaffold_exposes_liveness() -> None:
    assert app.title == "Job Hunter API"
    assert "/health" in {route.path for route in app.routes if isinstance(route, APIRoute)}


def test_runtime_settings_have_loopback_defaults() -> None:
    settings = RuntimeSettings()

    assert settings.api_host == IPv4Address("127.0.0.1")
    assert settings.api_port == 8000
    assert settings.frontend_origin == AnyHttpUrl("http://127.0.0.1:5173")


def test_runtime_settings_validate_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_HUNTER_API_PORT", "70000")

    with pytest.raises(ValidationError):
        RuntimeSettings()
