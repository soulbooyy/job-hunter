import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from job_hunter.api.app import create_app
from job_hunter.application.import_job import ImportJob, ImportJobCommand, ImportJobResult


class _OpenApiOperation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    responses: dict[str, object]


class _OpenApiPath(BaseModel):
    model_config = ConfigDict(extra="ignore")

    get: _OpenApiOperation | None = None
    post: _OpenApiOperation | None = None


class _OpenApiDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paths: dict[str, _OpenApiPath]


class _UnusedImportJob(ImportJob):
    def __init__(self) -> None:
        pass

    def execute(self, command: ImportJobCommand) -> ImportJobResult:
        del command
        raise AssertionError("health route must not execute ImportJob")


def test_create_app_composes_working_health_route() -> None:
    application = create_app()

    assert not hasattr(application.state, "import_job")
    with TestClient(application) as client:
        assert isinstance(application.state.import_job, ImportJob)
        response = client.get("/health")

    assert response.status_code == 200
    assert response.content == b'{"status":"ok"}'
    assert not hasattr(application.state, "import_job")


def test_lifespan_preserves_explicit_import_job_override() -> None:
    override = _UnusedImportJob()
    application = create_app(import_job=override)

    with TestClient(application) as client:
        assert application.state.import_job is override
        assert client.get("/health").status_code == 200

    with pytest.raises(AttributeError):
        _ = application.state.import_job


def test_openapi_keeps_existing_paths_and_response_statuses() -> None:
    document = _OpenApiDocument.model_validate(create_app().openapi())
    health = document.paths["/health"].get
    import_job = document.paths["/api/v1/jobs/import"].post

    assert health is not None
    assert set(health.responses) == {"200"}
    assert import_job is not None
    assert set(import_job.responses) == {"201", "404", "409", "422", "503"}
