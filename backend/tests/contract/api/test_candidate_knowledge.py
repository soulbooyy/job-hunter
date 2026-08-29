from datetime import UTC, datetime

from fastapi.testclient import TestClient

from job_hunter.api.app import create_app
from job_hunter.api.contracts.knowledge import (
    CandidateProfileResponse,
    EvidenceResponse,
)
from tests.helpers import DeterministicIdGenerator, FixedClock, build_test_use_cases

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)


def _app():
    return create_app(
        use_cases=build_test_use_cases(
            clock=FixedClock(NOW),
            id_generator=DeterministicIdGenerator(),
        )
    )


def test_candidate_profile_api_returns_normalized_stable_contract() -> None:
    with TestClient(_app()) as client:
        response = client.post(
            "/api/v1/knowledge/profile",
            json={
                "target_role_keywords": ["  AI   Engineer "],
                "skill_keywords": [" Python ", "LangGraph"],
                "preferred_cities": [" Shenzhen "],
                "correlation_id": "correlation-001",
                "run_id": "run-001",
            },
        )

    assert response.status_code == 201
    body = CandidateProfileResponse.model_validate_json(response.content)
    assert body.model_dump(mode="json") == {
        "profile_id": "candidate-profile-001",
        "target_role_keywords": ["AI Engineer"],
        "skill_keywords": ["Python", "LangGraph"],
        "preferred_cities": ["Shenzhen"],
        "created_at": "2026-08-29T09:00:00Z",
        "correlation_id": "correlation-001",
        "run_id": "run-001",
    }


def test_evidence_api_creates_and_versions_authoritative_content() -> None:
    application = _app()
    first_payload = {
        "evidence_type": "project",
        "canonical_content": "Built an agent evaluation pipeline.",
        "occurred_on": "2026-06-01",
        "source": "manual",
        "provenance": "User-confirmed project record",
        "sensitivity": "private",
        "validity": "valid",
        "correlation_id": "correlation-001",
        "run_id": "run-001",
    }
    with TestClient(application) as client:
        first = client.post("/api/v1/knowledge/evidence", json=first_payload)
        second = client.post(
            "/api/v1/knowledge/evidence",
            json={
                **first_payload,
                "existing_evidence_id": "evidence-001",
                "canonical_content": "Built and benchmarked an agent evaluation pipeline.",
                "correlation_id": "correlation-002",
                "run_id": "run-002",
            },
        )

    assert first.status_code == 201
    assert second.status_code == 201
    first_body = EvidenceResponse.model_validate_json(first.content)
    second_body = EvidenceResponse.model_validate_json(second.content)
    assert first_body.version_number == 1
    assert second_body.model_dump(mode="json") == {
        "evidence_id": "evidence-001",
        "evidence_version_id": "evidence-version-002",
        "active_version_id": "evidence-version-002",
        "version_number": 2,
        "evidence_type": "project",
        "canonical_content": "Built and benchmarked an agent evaluation pipeline.",
        "occurred_on": "2026-06-01",
        "source": "manual",
        "provenance": "User-confirmed project record",
        "sensitivity": "private",
        "validity": "valid",
        "created_at": "2026-08-29T09:00:00Z",
        "correlation_id": "correlation-002",
        "run_id": "run-002",
    }


def test_candidate_knowledge_api_rejects_missing_or_empty_required_facts() -> None:
    with TestClient(_app()) as client:
        profile = client.post(
            "/api/v1/knowledge/profile",
            json={
                "target_role_keywords": ["AI Engineer"],
                "skill_keywords": [],
                "correlation_id": "correlation-001",
                "run_id": "run-001",
            },
        )
        evidence = client.post(
            "/api/v1/knowledge/evidence",
            json={
                "evidence_type": "project",
                "canonical_content": " ",
                "source": "manual",
                "provenance": "confirmed",
                "sensitivity": "private",
                "validity": "valid",
                "correlation_id": "correlation-001",
                "run_id": "run-001",
            },
        )

    assert profile.status_code == 422
    assert evidence.status_code == 422
