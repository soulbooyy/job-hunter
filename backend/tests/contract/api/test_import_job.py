from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from job_hunter.api.app import create_app
from job_hunter.api.contracts.common import ErrorResponse
from job_hunter.api.contracts.jobs import ImportJobResponse
from job_hunter.application.import_job import ImportJob, ImportJobCommand, ImportJobResult
from job_hunter.domain.jobs import SourceKind
from job_hunter.errors import ConflictError
from job_hunter.ingestion.manual import (
    JobSource,
    ManualSourceInput,
    ValidatedSourceData,
)
from tests.helpers import DeterministicIdGenerator, FixedClock, build_test_use_cases

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def _app(*, sources: tuple[JobSource, ...] | None = None) -> tuple[FastAPI, ImportJob]:
    use_cases = build_test_use_cases(
        clock=FixedClock(NOW),
        id_generator=DeterministicIdGenerator(),
        sources=sources,
    )
    return create_app(use_cases=use_cases), use_cases.import_job


def test_manual_jd_api_returns_stable_structured_contract() -> None:
    application, importer = _app()
    with TestClient(application) as client:
        assert application.state.import_job is importer
        response = client.post(
            "/api/v1/jobs/import",
            json={
                "correlation_id": "correlation-001",
                "run_id": "run-001",
                "source": {
                    "source_type": "manual_jd",
                    "title": "AI Engineer",
                    "company": "Example AI",
                    "city": "Shenzhen",
                    "content": "Build grounded agents.",
                },
            },
        )

    assert response.status_code == 201
    body = ImportJobResponse.model_validate_json(response.content)
    assert body.model_dump(mode="json") == {
        "job_id": "job-001",
        "job_version_id": "job-version-001",
        "active_version_id": "job-version-001",
        "source_snapshot_id": "source-snapshot-001",
        "version_number": 1,
        "lifecycle_status": "imported",
        "source": {
            "kind": "manual_jd",
            "locator": None,
            "captured_at": "2026-08-27T12:00:00Z",
            "last_verified_at": "2026-08-27T12:00:00Z",
            "freshness": "fresh",
        },
        "correlation_id": "correlation-001",
        "run_id": "run-001",
    }


def test_manual_url_api_accepts_user_provided_content() -> None:
    application, _ = _app()
    with TestClient(application) as client:
        response = client.post(
            "/api/v1/jobs/import",
            json={
                "correlation_id": "correlation-001",
                "run_id": "run-001",
                "source": {
                    "source_type": "manual_url",
                    "url": "https://jobs.example/roles/1",
                    "title": "AI Engineer",
                    "company": "Example AI",
                    "city": "Shenzhen",
                    "content": "User-provided job content.",
                },
            },
        )

    assert response.status_code == 201
    body = ImportJobResponse.model_validate_json(response.content)
    assert body.source.model_dump(mode="json") == {
        "kind": "manual_url",
        "locator": "https://jobs.example/roles/1",
        "captured_at": "2026-08-27T12:00:00Z",
        "last_verified_at": "2026-08-27T12:00:00Z",
        "freshness": "fresh",
    }


def test_import_job_dependency_is_reused_within_one_lifespan() -> None:
    application, importer = _app()
    payload = {
        "correlation_id": "correlation-001",
        "run_id": "run-001",
        "source": {
            "source_type": "manual_jd",
            "title": "AI Engineer",
            "company": "Example AI",
            "city": "Shenzhen",
            "content": "Build grounded agents.",
        },
    }

    with TestClient(application) as client:
        first = client.post("/api/v1/jobs/import", json=payload)
        second = client.post("/api/v1/jobs/import", json=payload)

        assert application.state.import_job is importer

    first_body = ImportJobResponse.model_validate_json(first.content)
    second_body = ImportJobResponse.model_validate_json(second.content)
    assert first_body.job_id == "job-001"
    assert second_body.job_id == "job-002"


def test_api_rejects_empty_jd_illegal_url_and_missing_fields() -> None:
    application, _ = _app()
    invalid_sources = (
        {
            "source_type": "manual_jd",
            "title": "AI Engineer",
            "company": "Example AI",
            "city": "Shenzhen",
            "content": " ",
        },
        {
            "source_type": "manual_url",
            "url": "javascript:alert(1)",
            "title": "AI Engineer",
            "company": "Example AI",
            "city": "Shenzhen",
            "content": "Build agents.",
        },
        {
            "source_type": "manual_jd",
            "title": "AI Engineer",
            "city": "Shenzhen",
            "content": "Build agents.",
        },
    )

    with TestClient(application) as client:
        for source in invalid_sources:
            response = client.post(
                "/api/v1/jobs/import",
                json={
                    "correlation_id": "correlation-001",
                    "run_id": "run-001",
                    "source": source,
                },
            )

            assert response.status_code == 422
            body = ErrorResponse.model_validate_json(response.content)
            assert body.model_dump() == {
                "error": {
                    "code": "input_validation",
                    "message": "Request validation failed",
                }
            }


class _UnavailableSource:
    @property
    def kind(self) -> SourceKind:
        return SourceKind.MANUAL_JD

    def capture(self, source_input: ManualSourceInput) -> ValidatedSourceData:
        del source_input
        raise RuntimeError("raw third-party failure detail")


def test_api_maps_boundary_failure_without_exposing_raw_exception() -> None:
    application, _ = _app(sources=(_UnavailableSource(),))
    with TestClient(application) as client:
        response = client.post(
            "/api/v1/jobs/import",
            json={
                "correlation_id": "correlation-001",
                "run_id": "run-001",
                "source": {
                    "source_type": "manual_jd",
                    "title": "AI Engineer",
                    "company": "Example AI",
                    "city": "Shenzhen",
                    "content": "Build grounded agents.",
                },
            },
        )

    assert response.status_code == 503
    body = ErrorResponse.model_validate_json(response.content)
    assert body.model_dump() == {
        "error": {
            "code": "dependency_unavailable",
            "message": "job source is unavailable",
        }
    }


def test_api_maps_unknown_existing_job_to_not_found_contract() -> None:
    application, _ = _app()
    with TestClient(application) as client:
        response = client.post(
            "/api/v1/jobs/import",
            json={
                "correlation_id": "correlation-001",
                "run_id": "run-001",
                "existing_job_id": "missing-job",
                "source": {
                    "source_type": "manual_jd",
                    "title": "AI Engineer",
                    "company": "Example AI",
                    "city": "Shenzhen",
                    "content": "Build grounded agents.",
                },
            },
        )

    assert response.status_code == 404
    body = ErrorResponse.model_validate_json(response.content)
    assert body.model_dump() == {
        "error": {
            "code": "not_found",
            "message": "job not found: missing-job",
        }
    }


class _ConflictingImportJob(ImportJob):
    def __init__(self) -> None:
        pass

    def execute(self, command: ImportJobCommand) -> ImportJobResult:
        del command
        raise ConflictError("controlled job conflict")


def test_api_maps_application_conflict_to_conflict_contract() -> None:
    conflicting_importer = _ConflictingImportJob()
    use_cases = build_test_use_cases(
        clock=FixedClock(NOW),
        id_generator=DeterministicIdGenerator(),
        import_job=conflicting_importer,
    )
    application = create_app(use_cases=use_cases)
    with TestClient(application) as client:
        assert application.state.import_job is conflicting_importer
        response = client.post(
            "/api/v1/jobs/import",
            json={
                "correlation_id": "correlation-001",
                "run_id": "run-001",
                "source": {
                    "source_type": "manual_jd",
                    "title": "AI Engineer",
                    "company": "Example AI",
                    "city": "Shenzhen",
                    "content": "Build grounded agents.",
                },
            },
        )

    assert response.status_code == 409
    body = ErrorResponse.model_validate_json(response.content)
    assert body.model_dump() == {
        "error": {
            "code": "conflict",
            "message": "controlled job conflict",
        }
    }
