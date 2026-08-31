import inspect
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from job_hunter.api.app import create_app
from job_hunter.api.routers import jobs, knowledge
from job_hunter.application.candidate_knowledge import CreateCandidateProfile, SaveEvidence
from job_hunter.application.import_job import ImportJob, ImportJobCommand, ImportJobResult
from job_hunter.application.screening import RecordJobTriage, RunQuickScreen
from job_hunter.application.workspace_queries import WorkspaceQueries
from job_hunter.config import RuntimeSettings
from job_hunter.infrastructure.persistence.database import upgrade_database
from tests.helpers import DeterministicIdGenerator, FixedClock, build_test_use_cases

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)


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


def _migrated_settings(tmp_path: Path) -> RuntimeSettings:
    database_path = tmp_path / "job-hunter.db"
    upgrade_database(database_path)
    return RuntimeSettings(database_path=database_path)


def test_create_app_composes_working_health_route(tmp_path: Path) -> None:
    application = create_app(settings=_migrated_settings(tmp_path))

    assert not hasattr(application.state, "import_job")
    with TestClient(application) as client:
        assert hasattr(application.state, "database_runtime")
        assert isinstance(application.state.import_job, ImportJob)
        assert isinstance(application.state.create_candidate_profile, CreateCandidateProfile)
        assert isinstance(application.state.save_evidence, SaveEvidence)
        assert isinstance(application.state.run_quick_screen, RunQuickScreen)
        assert isinstance(application.state.record_job_triage, RecordJobTriage)
        assert isinstance(application.state.workspace_queries, WorkspaceQueries)
        response = client.get("/health")

    assert response.status_code == 200
    assert response.content == b'{"status":"ok"}'
    assert not hasattr(application.state, "import_job")
    assert not hasattr(application.state, "create_candidate_profile")
    assert not hasattr(application.state, "save_evidence")
    assert not hasattr(application.state, "run_quick_screen")
    assert not hasattr(application.state, "record_job_triage")
    assert not hasattr(application.state, "workspace_queries")
    assert not hasattr(application.state, "database_runtime")


def test_lifespan_preserves_complete_explicit_use_case_bundle() -> None:
    use_cases = build_test_use_cases(
        clock=FixedClock(NOW),
        id_generator=DeterministicIdGenerator(),
        import_job=_UnusedImportJob(),
    )
    application = create_app(use_cases=use_cases)

    with TestClient(application) as client:
        assert not hasattr(application.state, "database_runtime")
        assert application.state.import_job is use_cases.import_job
        assert application.state.create_candidate_profile is use_cases.create_candidate_profile
        assert application.state.save_evidence is use_cases.save_evidence
        assert application.state.run_quick_screen is use_cases.run_quick_screen
        assert application.state.record_job_triage is use_cases.record_job_triage
        assert application.state.workspace_queries is use_cases.workspace_queries
        assert client.get("/health").status_code == 200

    with pytest.raises(AttributeError):
        _ = application.state.import_job


def test_default_composition_shares_state_across_the_vertical_path(tmp_path: Path) -> None:
    application = create_app(settings=_migrated_settings(tmp_path))
    with TestClient(application) as client:
        imported = client.post(
            "/api/v1/jobs/import",
            json={
                "correlation_id": "correlation-import",
                "run_id": "run-import",
                "source": {
                    "source_type": "manual_jd",
                    "title": "AI Engineer",
                    "company": "Example AI",
                    "city": "Shenzhen",
                    "content": "- Must have Python experience",
                },
            },
        )
        profile = client.post(
            "/api/v1/knowledge/profile",
            json={
                "target_role_keywords": ["AI Engineer"],
                "skill_keywords": ["Python"],
                "preferred_cities": ["Shenzhen"],
                "correlation_id": "correlation-profile",
                "run_id": "run-profile",
            },
        )
        job_id = imported.json()["job_id"]
        screened = client.post(
            f"/api/v1/jobs/{job_id}/screen",
            json={"correlation_id": "correlation-screen", "run_id": "run-screen"},
        )

    assert imported.status_code == 201
    assert profile.status_code == 201
    assert screened.status_code == 201


def test_openapi_keeps_existing_paths_and_response_statuses() -> None:
    document = _OpenApiDocument.model_validate(create_app().openapi())
    health = document.paths["/health"].get
    import_job = document.paths["/api/v1/jobs/import"].post

    assert health is not None
    assert set(health.responses) == {"200"}
    assert import_job is not None
    assert set(import_job.responses) == {"201", "404", "409", "422", "503"}
    profile = document.paths["/api/v1/knowledge/profile"].post
    evidence = document.paths["/api/v1/knowledge/evidence"].post
    screen = document.paths["/api/v1/jobs/{job_id}/screen"].post
    triage = document.paths["/api/v1/jobs/{job_id}/triage"].post
    jobs = document.paths["/api/v1/jobs"].get
    job_detail = document.paths["/api/v1/jobs/{job_id}"].get
    profiles = document.paths["/api/v1/knowledge/profiles"].get
    evidence_history = document.paths["/api/v1/knowledge/evidence"].get
    assert profile is not None
    assert evidence is not None
    assert screen is not None
    assert triage is not None
    assert jobs is not None
    assert job_detail is not None
    assert profiles is not None
    assert evidence_history is not None
    assert set(profile.responses) == {
        "201",
        "409",
        "422",
        "503",
    }
    assert set(evidence.responses) == {
        "201",
        "404",
        "409",
        "422",
        "503",
    }
    assert set(screen.responses) == {
        "201",
        "404",
        "409",
        "422",
        "503",
    }
    assert set(triage.responses) == {
        "201",
        "404",
        "409",
        "422",
        "503",
    }
    assert set(jobs.responses) == {"200", "503"}
    assert set(job_detail.responses) == {"200", "404", "422", "503"}
    assert set(profiles.responses) == {"200", "503"}
    assert set(evidence_history.responses) == {"200", "503"}


def test_routes_that_call_synchronous_use_cases_run_in_fastapi_threadpool() -> None:
    for route_handler in (
        jobs.list_jobs,
        jobs.get_job,
        jobs.import_manual_job,
        jobs.run_quick_screen,
        jobs.record_job_triage,
        knowledge.list_candidate_profiles,
        knowledge.list_evidence,
        knowledge.create_candidate_profile,
        knowledge.save_evidence,
    ):
        assert not inspect.iscoroutinefunction(route_handler)
