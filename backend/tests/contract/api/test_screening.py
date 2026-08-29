from datetime import UTC, datetime

from fastapi.testclient import TestClient

from job_hunter.api.app import create_app
from job_hunter.api.contracts.common import ErrorResponse
from job_hunter.api.contracts.screening import QuickScreenResponse, TriageResponse
from tests.helpers import DeterministicIdGenerator, FixedClock, build_test_use_cases

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)


def _app():
    return create_app(
        use_cases=build_test_use_cases(
            clock=FixedClock(NOW),
            id_generator=DeterministicIdGenerator(),
        )
    )


def _import(client: TestClient) -> None:
    response = client.post(
        "/api/v1/jobs/import",
        json={
            "correlation_id": "correlation-import",
            "run_id": "run-import",
            "source": {
                "source_type": "manual_jd",
                "title": "Senior AI Engineer",
                "company": "Example AI",
                "city": "Shenzhen",
                "content": "- Must have Python experience\n- Build production LLM agents",
            },
        },
    )
    assert response.status_code == 201


def _profile(client: TestClient) -> None:
    response = client.post(
        "/api/v1/knowledge/profile",
        json={
            "target_role_keywords": ["AI Engineer"],
            "skill_keywords": ["Python", "LLM"],
            "preferred_cities": ["Shenzhen"],
            "correlation_id": "correlation-profile",
            "run_id": "run-profile",
        },
    )
    assert response.status_code == 201


def test_screen_and_triage_api_complete_user_decision_path() -> None:
    with TestClient(_app()) as client:
        _import(client)
        _profile(client)
        screen = client.post(
            "/api/v1/jobs/job-001/screen",
            json={"correlation_id": "correlation-screen", "run_id": "run-screen"},
        )
        triage = client.post(
            "/api/v1/jobs/job-001/triage",
            json={
                "quick_screen_result_id": "quick-screen-001",
                "decision": "shortlisted",
                "correlation_id": "correlation-triage",
                "run_id": "run-triage",
            },
        )

    assert screen.status_code == 201
    assert triage.status_code == 201
    screen_body = QuickScreenResponse.model_validate_json(screen.content)
    triage_body = TriageResponse.model_validate_json(triage.content)
    assert screen_body.model_dump(mode="json") == {
        "quick_screen_result_id": "quick-screen-001",
        "job_id": "job-001",
        "job_version_id": "job-version-001",
        "candidate_profile_id": "candidate-profile-001",
        "requirement_ids": ["requirement-001", "requirement-002"],
        "recommendation": "screen_in",
        "reason_codes": ["target_role_match", "skill_overlap"],
        "policy_version": "quick-screen-v1",
        "lifecycle_status": "screened",
        "created_at": "2026-08-29T09:00:00Z",
        "correlation_id": "correlation-screen",
        "run_id": "run-screen",
    }
    assert triage_body.model_dump(mode="json") == {
        "triage_decision_id": "triage-001",
        "job_id": "job-001",
        "quick_screen_result_id": "quick-screen-001",
        "recommendation": "screen_in",
        "decision": "shortlisted",
        "lifecycle_status": "shortlisted",
        "decided_at": "2026-08-29T09:00:00Z",
        "correlation_id": "correlation-triage",
        "run_id": "run-triage",
    }


def test_screen_api_requires_candidate_profile() -> None:
    with TestClient(_app()) as client:
        _import(client)
        response = client.post(
            "/api/v1/jobs/job-001/screen",
            json={"correlation_id": "correlation-screen", "run_id": "run-screen"},
        )

    assert response.status_code == 404
    body = ErrorResponse.model_validate_json(response.content)
    assert body.model_dump() == {
        "error": {"code": "not_found", "message": "candidate profile not found"}
    }


def test_triage_api_rejects_a_stale_quick_screen_result() -> None:
    with TestClient(_app()) as client:
        _import(client)
        _profile(client)
        for suffix in ("one", "two"):
            response = client.post(
                "/api/v1/jobs/job-001/screen",
                json={"correlation_id": f"correlation-{suffix}", "run_id": f"run-{suffix}"},
            )
            assert response.status_code == 201
        stale = client.post(
            "/api/v1/jobs/job-001/triage",
            json={
                "quick_screen_result_id": "quick-screen-001",
                "decision": "skipped",
                "correlation_id": "correlation-triage",
                "run_id": "run-triage",
            },
        )

    assert stale.status_code == 409
    body = ErrorResponse.model_validate_json(stale.content)
    assert body.model_dump() == {
        "error": {"code": "conflict", "message": "quick screen result is stale"}
    }
