from dataclasses import replace
from datetime import UTC, datetime
from typing import Never

from fastapi.testclient import TestClient

from job_hunter.api.app import create_app
from job_hunter.application.workspace_queries import WorkspaceQueries
from tests.helpers import DeterministicIdGenerator, FixedClock, build_test_use_cases

NOW = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)


class _FailingUnitOfWorkFactory:
    def __call__(self) -> Never:
        raise RuntimeError("secret workspace read failure")


def _client() -> TestClient:
    use_cases = build_test_use_cases(
        clock=FixedClock(NOW),
        id_generator=DeterministicIdGenerator(),
    )
    return TestClient(create_app(use_cases=use_cases))


def _import_job(client: TestClient) -> dict[str, object]:
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
                "content": (
                    "- Must have Python experience\n"
                    "- Build production LLM agents\n"
                    "- Bachelor's degree preferred"
                ),
            },
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_profile(client: TestClient, *, target: str) -> dict[str, object]:
    id_suffix = target.replace(" ", "-")
    response = client.post(
        "/api/v1/knowledge/profile",
        json={
            "target_role_keywords": [target],
            "skill_keywords": ["Python", "LLM"],
            "preferred_cities": ["Shenzhen"],
            "correlation_id": f"correlation-profile-{id_suffix}",
            "run_id": f"run-profile-{id_suffix}",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_empty_workspace_readbacks_are_typed_and_not_cacheable() -> None:
    with _client() as client:
        jobs = client.get("/api/v1/jobs")
        profiles = client.get("/api/v1/knowledge/profiles")
        evidence = client.get("/api/v1/knowledge/evidence")

    assert jobs.status_code == 200
    assert jobs.json() == {"items": []}
    assert profiles.status_code == 200
    assert profiles.json() == {"active_profile_id": None, "items": []}
    assert evidence.status_code == 200
    assert evidence.json() == {"items": []}
    for response in (jobs, profiles, evidence):
        assert response.headers["cache-control"] == "no-store"


def test_job_readback_reconstructs_lineage_and_actionability() -> None:
    with _client() as client:
        imported = _import_job(client)
        first_profile = _create_profile(client, target="AI Engineer")
        job_id = imported["job_id"]
        screened = client.post(
            f"/api/v1/jobs/{job_id}/screen",
            json={"correlation_id": "correlation-screen", "run_id": "run-screen"},
        )
        assert screened.status_code == 201
        triaged = client.post(
            f"/api/v1/jobs/{job_id}/triage",
            json={
                "quick_screen_result_id": screened.json()["quick_screen_result_id"],
                "decision": "shortlisted",
                "correlation_id": "correlation-triage",
                "run_id": "run-triage",
            },
        )
        assert triaged.status_code == 201
        second_profile = _create_profile(client, target="Platform Engineer")
        first_evidence = client.post(
            "/api/v1/knowledge/evidence",
            json={
                "evidence_type": "project",
                "canonical_content": "Built an evaluation pipeline.",
                "occurred_on": "2026-06-01",
                "source": "manual",
                "provenance": "User-confirmed project",
                "sensitivity": "private",
                "validity": "valid",
                "correlation_id": "correlation-evidence-1",
                "run_id": "run-evidence-1",
            },
        )
        assert first_evidence.status_code == 201
        second_evidence = client.post(
            "/api/v1/knowledge/evidence",
            json={
                "existing_evidence_id": first_evidence.json()["evidence_id"],
                "evidence_type": "project",
                "canonical_content": "Built and benchmarked an evaluation pipeline.",
                "occurred_on": "2026-07-01",
                "source": "manual",
                "provenance": "User-confirmed project update",
                "sensitivity": "private",
                "validity": "valid",
                "correlation_id": "correlation-evidence-2",
                "run_id": "run-evidence-2",
            },
        )
        assert second_evidence.status_code == 201

        jobs = client.get("/api/v1/jobs")
        detail = client.get(f"/api/v1/jobs/{job_id}")
        profiles = client.get("/api/v1/knowledge/profiles")
        evidence = client.get("/api/v1/knowledge/evidence")

    assert jobs.status_code == 200
    assert jobs.headers["cache-control"] == "no-store"
    assert jobs.json()["items"][0]["current_screen_recommendation"] == "screen_in"
    assert jobs.json()["items"][0]["current_triage_decision"] == "shortlisted"
    assert detail.status_code == 200
    assert detail.headers["cache-control"] == "no-store"
    detail_body = detail.json()
    assert detail_body["active_version_id"] == imported["active_version_id"]
    assert detail_body["versions"][0]["source_snapshot_id"] == imported["source_snapshot_id"]
    assert detail_body["versions"][0]["source"]["kind"] == "manual_jd"
    assert len(detail_body["requirements"]) == 3
    assert detail_body["screening_results"] == [
        {
            **screened.json(),
            "profile_status": "stale",
            "job_version_status": "current",
            "is_latest_result": True,
            "triage_eligible": True,
        }
    ]
    assert detail_body["triage_history"] == [
        {
            **triaged.json(),
            "recommendation": "screen_in",
        }
    ]
    assert profiles.status_code == 200
    assert profiles.headers["cache-control"] == "no-store"
    assert profiles.json()["active_profile_id"] == second_profile["profile_id"]
    assert [item["profile_id"] for item in profiles.json()["items"]] == [
        first_profile["profile_id"],
        second_profile["profile_id"],
    ]
    assert evidence.status_code == 200
    assert evidence.headers["cache-control"] == "no-store"
    evidence_item = evidence.json()["items"][0]
    assert evidence_item["active_version_id"] == second_evidence.json()["active_version_id"]
    assert [item["version_number"] for item in evidence_item["versions"]] == [1, 2]


def test_unknown_job_readback_uses_stable_404_contract() -> None:
    with _client() as client:
        response = client.get("/api/v1/jobs/missing-job")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "job not found: missing-job"}
    }


def test_workspace_dependency_failure_uses_stable_503_contract() -> None:
    use_cases = build_test_use_cases(
        clock=FixedClock(NOW),
        id_generator=DeterministicIdGenerator(),
    )
    application = create_app(
        use_cases=replace(
            use_cases,
            workspace_queries=WorkspaceQueries(unit_of_work_factory=_FailingUnitOfWorkFactory()),
        )
    )

    with TestClient(application) as client:
        response = client.get("/api/v1/jobs")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "dependency_unavailable",
            "message": "workspace read dependency is unavailable",
        }
    }
    assert "secret" not in response.text
