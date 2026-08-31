import json
import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from job_hunter.api.app import create_app
from job_hunter.application.retrieval import RetrieveEvidence, RetrieveEvidenceCommand
from job_hunter.config import RuntimeSettings
from job_hunter.domain.ids import (
    CandidateProfileId,
    CorrelationId,
    EvidenceItemId,
    EvidenceVersionId,
    JobId,
    JobVersionId,
    QuickScreenResultId,
    RequirementId,
    RetrievalRunId,
    RunId,
    SourceSnapshotId,
    TriageDecisionId,
)
from job_hunter.domain.jobs import (
    Freshness,
    FreshnessStatus,
    JobLifecycleStatus,
    SourceKind,
    SourceSnapshot,
)
from job_hunter.domain.knowledge import (
    CandidateProfile,
    EvidenceItem,
    EvidenceItemVersion,
    EvidenceSensitivity,
    EvidenceType,
    EvidenceValidity,
)
from job_hunter.domain.retrieval import (
    EvidenceExclusion,
    EvidenceExclusionReason,
    RetrievalHit,
    RetrievalMatchReason,
    RetrievalRun,
    RetrievalStatus,
    RetrievalStrategy,
)
from job_hunter.domain.screening import JobTriageRecord, TriageDecision
from job_hunter.errors import (
    ConflictError,
    DependencyUnavailableError,
    EntityNotFoundError,
    StaleWriteError,
)
from job_hunter.infrastructure.persistence.database import (
    DatabaseRuntime,
    create_database_runtime,
    get_database_revision,
    get_migration_head,
    upgrade_database,
)
from job_hunter.infrastructure.persistence.uow import SqlAlchemyUnitOfWorkFactory
from job_hunter.infrastructure.retrieval import FullContextRetriever
from tests.helpers import DeterministicIdGenerator, FixedClock, build_test_use_cases

NOW = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)


class _ReverseScreenIdGenerator(DeterministicIdGenerator):
    def __init__(self) -> None:
        super().__init__()
        self._screen_ids = iter(("quick-screen-z", "quick-screen-a"))

    def new_quick_screen_result_id(self) -> QuickScreenResultId:
        return QuickScreenResultId(next(self._screen_ids))


def _settings(database_path: Path) -> RuntimeSettings:
    return RuntimeSettings(database_path=database_path)


def _evidence_version(
    version_id: str,
    evidence_id: EvidenceItemId,
    version_number: int,
    content: str,
) -> EvidenceItemVersion:
    return EvidenceItemVersion(
        version_id=EvidenceVersionId(version_id),
        evidence_id=evidence_id,
        version_number=version_number,
        evidence_type=EvidenceType.PROJECT,
        canonical_content=content,
        occurred_on=date(2026, 6, 1),
        source="manual",
        provenance="Human-confirmed fixture",
        sensitivity=EvidenceSensitivity.PRIVATE,
        validity=EvidenceValidity.VALID,
        created_at=NOW,
        correlation_id=CorrelationId(f"correlation-{version_id}"),
        run_id=RunId(f"run-{version_id}"),
    )


def _import_job(client: TestClient) -> dict[str, object]:
    response = client.post(
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
    assert response.status_code == 201
    return response.json()


def test_empty_database_upgrades_to_current_head_idempotently(tmp_path: Path) -> None:
    database_path = tmp_path / "job-hunter.db"

    upgrade_database(database_path)
    upgrade_database(database_path)

    assert get_database_revision(database_path) == get_migration_head()
    runtime = create_database_runtime(database_path)
    try:
        assert runtime.table_names() >= {
            "jobs",
            "job_versions",
            "source_snapshots",
            "source_references",
            "candidate_profiles",
            "candidate_profile_state",
            "evidence_items",
            "evidence_versions",
            "parsed_requirements",
            "quick_screen_results",
            "job_triage_records",
            "retrieval_runs",
            "quick_screen_requirements",
            "retrieval_run_hits",
            "retrieval_run_exclusions",
        }
    finally:
        runtime.dispose()


def test_application_refuses_to_start_before_explicit_migration(tmp_path: Path) -> None:
    application = create_app(settings=_settings(tmp_path / "unmigrated.db"))

    with (
        pytest.raises(DependencyUnavailableError, match="schema upgrade is required"),
        TestClient(application),
    ):
        pass


def test_workspace_survives_application_lifespan_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "job-hunter.db"
    upgrade_database(database_path)
    settings = _settings(database_path)

    first_application = create_app(settings=settings)
    with TestClient(first_application) as first:
        imported = _import_job(first)
        profile = first.post(
            "/api/v1/knowledge/profile",
            json={
                "target_role_keywords": ["AI Engineer"],
                "skill_keywords": ["Python"],
                "preferred_cities": ["Shenzhen"],
                "correlation_id": "correlation-profile",
                "run_id": "run-profile",
            },
        )
        assert profile.status_code == 201
        job_id = imported["job_id"]
        screened = first.post(
            f"/api/v1/jobs/{job_id}/screen",
            json={"correlation_id": "correlation-screen", "run_id": "run-screen"},
        )
        assert screened.status_code == 201
        triaged = first.post(
            f"/api/v1/jobs/{job_id}/triage",
            json={
                "quick_screen_result_id": screened.json()["quick_screen_result_id"],
                "decision": "shortlisted",
                "correlation_id": "correlation-triage",
                "run_id": "run-triage",
            },
        )
        assert triaged.status_code == 201
        evidence = first.post(
            "/api/v1/knowledge/evidence",
            json={
                "evidence_type": "project",
                "canonical_content": "Built a Python evaluation pipeline",
                "occurred_on": "2026-06-01",
                "source": "manual",
                "provenance": "Human-confirmed fixture",
                "sensitivity": "private",
                "validity": "valid",
                "correlation_id": "correlation-evidence",
                "run_id": "run-evidence",
            },
        )
        assert evidence.status_code == 201
        database = first_application.state.database_runtime
        assert isinstance(database, DatabaseRuntime)
        retrieval = RetrieveEvidence(
            unit_of_work_factory=SqlAlchemyUnitOfWorkFactory(database.session_factory),
            retriever=FullContextRetriever(),
            clock=FixedClock(NOW),
            id_generator=DeterministicIdGenerator(),
        ).execute(
            RetrieveEvidenceCommand(
                requirement_id=RequirementId(screened.json()["requirement_ids"][0]),
                allowed_sensitivities=(EvidenceSensitivity.PRIVATE,),
                max_tokens=100,
                top_k=5,
                correlation_id=CorrelationId("correlation-retrieval"),
                run_id=RunId("run-retrieval"),
            )
        )

    with TestClient(create_app(settings=settings)) as second:
        jobs = second.get("/api/v1/jobs")
        detail = second.get(f"/api/v1/jobs/{job_id}")
        profiles = second.get("/api/v1/knowledge/profiles")
        evidence_history = second.get("/api/v1/knowledge/evidence")

    assert jobs.status_code == 200
    assert jobs.json()["items"][0]["job_id"] == job_id
    assert detail.status_code == 200
    assert detail.json()["active_version_id"] == imported["active_version_id"]
    assert (
        detail.json()["screening_results"][0]["quick_screen_result_id"]
        == screened.json()["quick_screen_result_id"]
    )
    assert (
        detail.json()["triage_history"][0]["triage_decision_id"]
        == triaged.json()["triage_decision_id"]
    )
    assert profiles.json()["active_profile_id"] == profile.json()["profile_id"]
    assert (
        evidence_history.json()["items"][0]["active_version_id"]
        == evidence.json()["active_version_id"]
    )
    reopened = create_database_runtime(database_path)
    verification = SqlAlchemyUnitOfWorkFactory(reopened.session_factory)()
    try:
        stored_run = verification.retrieval.get_run(retrieval.retrieval_run_id)
        assert stored_run.requirement_id == retrieval.requirement_id
        assert str(stored_run.hits[0].evidence_version_id) == evidence.json()["active_version_id"]
        assert stored_run.correlation_id == CorrelationId("correlation-retrieval")
        assert stored_run.run_id == RunId("run-retrieval")
    finally:
        verification.close()
        reopened.dispose()


def test_read_uow_keeps_one_snapshot_after_another_connection_commits(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job-hunter.db"
    upgrade_database(database_path)
    settings = _settings(database_path)
    application = create_app(settings=settings)

    with TestClient(application) as client:
        database = application.state.database_runtime
        assert isinstance(database, DatabaseRuntime)
        factory = SqlAlchemyUnitOfWorkFactory(database.session_factory)
        reader = factory()
        try:
            assert reader.jobs.list_jobs() == ()
            imported = _import_job(client)
            # The writer committed through a separate Session/connection, but the
            # already-reading UoW must keep its original SQLite snapshot.
            assert reader.jobs.list_jobs() == ()
        finally:
            reader.close()

        fresh = factory()
        try:
            assert tuple(str(job.job_id) for job in fresh.jobs.list_jobs()) == (imported["job_id"],)
        finally:
            fresh.close()


def test_stale_sqlite_uow_cannot_overwrite_successful_commit(tmp_path: Path) -> None:
    database_path = tmp_path / "job-hunter.db"
    upgrade_database(database_path)
    settings = _settings(database_path)
    with TestClient(create_app(settings=settings)) as client:
        imported = _import_job(client)
        assert (
            client.post(
                "/api/v1/knowledge/profile",
                json={
                    "target_role_keywords": ["AI Engineer"],
                    "skill_keywords": ["Python"],
                    "preferred_cities": ["Shenzhen"],
                    "correlation_id": "correlation-profile",
                    "run_id": "run-profile",
                },
            ).status_code
            == 201
        )
        screened = client.post(
            f"/api/v1/jobs/{imported['job_id']}/screen",
            json={"correlation_id": "correlation-screen", "run_id": "run-screen"},
        )
        assert screened.status_code == 201

    runtime = create_database_runtime(database_path)
    factory = SqlAlchemyUnitOfWorkFactory(runtime.session_factory)
    job_id = JobId(str(imported["job_id"]))
    first = factory()
    stale = factory()
    try:
        first_job = first.jobs.get_job(job_id)
        stale_job = stale.jobs.get_job(job_id)
        first.jobs.save_job(first_job.with_triage_decision(TriageDecision.SHORTLISTED))
        stale.jobs.save_job(stale_job.with_triage_decision(TriageDecision.SKIPPED))

        first.commit()
        with pytest.raises(StaleWriteError, match="state changed"):
            stale.commit()
    finally:
        first.close()
        stale.close()
        runtime.dispose()

    reopened = create_database_runtime(database_path)
    verification = SqlAlchemyUnitOfWorkFactory(reopened.session_factory)()
    try:
        stored = verification.jobs.get_job(job_id)
        assert stored.lifecycle_status is JobLifecycleStatus.SHORTLISTED
        assert stored.latest_quick_screen_result_id == QuickScreenResultId(
            screened.json()["quick_screen_result_id"]
        )
        assert tuple(str(item) for item in stored.version_ids) == (imported["job_version_id"],)
        version = verification.jobs.get_version(stored.active_version_id)
        snapshot = verification.jobs.get_snapshot(version.source_snapshot_id)
        assert version.version_id == stored.active_version_id
        assert stored.source_references[0].snapshot_id == snapshot.snapshot_id
        assert snapshot.correlation_id == CorrelationId("correlation-import")
        assert snapshot.run_id == RunId("run-import")
    finally:
        verification.close()
        reopened.dispose()


@pytest.mark.parametrize("winning_operation", ["triage", "rescreen"])
def test_concurrent_triage_and_rescreen_share_the_job_revision(
    tmp_path: Path,
    winning_operation: str,
) -> None:
    database_path = tmp_path / "job-hunter.db"
    upgrade_database(database_path)
    settings = _settings(database_path)
    with TestClient(create_app(settings=settings)) as client:
        imported = _import_job(client)
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
        assert profile.status_code == 201
        screened = client.post(
            f"/api/v1/jobs/{imported['job_id']}/screen",
            json={"correlation_id": "correlation-screen-a", "run_id": "run-screen-a"},
        )
        assert screened.status_code == 201

    runtime = create_database_runtime(database_path)
    factory = SqlAlchemyUnitOfWorkFactory(runtime.session_factory)
    triage = factory()
    rescreen = factory()
    job_id = JobId(str(imported["job_id"]))
    screen_a_id = QuickScreenResultId(screened.json()["quick_screen_result_id"])
    screen_b_id = QuickScreenResultId("quick-screen-concurrent-b")
    try:
        triage_job = triage.jobs.get_job(job_id)
        rescreen_job = rescreen.jobs.get_job(job_id)
        screen_a = triage.screening.get_quick_screen_result(screen_a_id)
        screen_b = replace(
            screen_a,
            result_id=screen_b_id,
            correlation_id=CorrelationId("correlation-screen-b"),
            run_id=RunId("run-screen-b"),
        )
        triage_record = JobTriageRecord(
            decision_id=TriageDecisionId("triage-concurrent-a"),
            job_id=job_id,
            quick_screen_result_id=screen_a_id,
            decision=TriageDecision.SHORTLISTED,
            decided_at=NOW,
            correlation_id=CorrelationId("correlation-triage"),
            run_id=RunId("run-triage"),
        )
        triage.jobs.save_job(triage_job.with_triage_decision(TriageDecision.SHORTLISTED))
        triage.screening.add_triage_record(triage_record)
        rescreen.jobs.save_job(rescreen_job.with_screening(screen_b_id))
        rescreen.screening.add_quick_screen_result(screen_b)

        winner, loser = (triage, rescreen) if winning_operation == "triage" else (rescreen, triage)
        winner.commit()
        with pytest.raises(StaleWriteError, match="state changed"):
            loser.commit()
    finally:
        triage.close()
        rescreen.close()

    verification = factory()
    try:
        stored_job = verification.jobs.get_job(job_id)
        screens = verification.screening.list_quick_screen_results(job_id)
        triage_records = verification.screening.list_triage_records(job_id)
        if winning_operation == "triage":
            assert stored_job.lifecycle_status is JobLifecycleStatus.SHORTLISTED
            assert stored_job.latest_quick_screen_result_id == screen_a_id
            assert tuple(item.result_id for item in screens) == (screen_a_id,)
            assert tuple(item.decision_id for item in triage_records) == (
                triage_record.decision_id,
            )
        else:
            assert stored_job.lifecycle_status is JobLifecycleStatus.SCREENED
            assert stored_job.latest_quick_screen_result_id == screen_b_id
            assert tuple(item.result_id for item in screens) == (screen_a_id, screen_b_id)
            assert triage_records == ()
    finally:
        verification.close()
        runtime.dispose()


def test_stale_active_profile_pointer_rolls_back_losing_snapshot(tmp_path: Path) -> None:
    database_path = tmp_path / "job-hunter.db"
    upgrade_database(database_path)
    runtime = create_database_runtime(database_path)
    factory = SqlAlchemyUnitOfWorkFactory(runtime.session_factory)
    first = factory()
    stale = factory()
    winning = CandidateProfile(
        profile_id=CandidateProfileId("profile-winning"),
        target_role_keywords=("AI Engineer",),
        skill_keywords=("Python",),
        preferred_cities=("Shenzhen",),
        created_at=NOW,
        correlation_id=CorrelationId("correlation-profile-winning"),
        run_id=RunId("run-profile-winning"),
    )
    losing = CandidateProfile(
        profile_id=CandidateProfileId("profile-losing"),
        target_role_keywords=("Data Engineer",),
        skill_keywords=("SQL",),
        preferred_cities=("Guangzhou",),
        created_at=NOW,
        correlation_id=CorrelationId("correlation-profile-losing"),
        run_id=RunId("run-profile-losing"),
    )
    try:
        assert first.knowledge.get_active_profile_id() is None
        assert stale.knowledge.get_active_profile_id() is None
        first.knowledge.add_profile(winning)
        stale.knowledge.add_profile(losing)

        first.commit()
        with pytest.raises(StaleWriteError, match="state changed"):
            stale.commit()
    finally:
        first.close()
        stale.close()

    verification = factory()
    try:
        assert verification.knowledge.get_active_profile_id() == winning.profile_id
        assert verification.knowledge.list_profiles() == (winning,)
        with pytest.raises(EntityNotFoundError, match="candidate profile not found"):
            verification.knowledge.get_profile(losing.profile_id)
    finally:
        verification.close()
        runtime.dispose()


def test_stale_evidence_pointer_cannot_commit_losing_version(tmp_path: Path) -> None:
    database_path = tmp_path / "job-hunter.db"
    upgrade_database(database_path)
    runtime = create_database_runtime(database_path)
    factory = SqlAlchemyUnitOfWorkFactory(runtime.session_factory)
    evidence_id = EvidenceItemId("evidence-concurrent")
    original = _evidence_version("evidence-version-1", evidence_id, 1, "Original")
    setup = factory()
    try:
        setup.knowledge.add_evidence(EvidenceItem.create(original))
        setup.knowledge.add_evidence_version(original)
        setup.commit()
    finally:
        setup.close()

    first = factory()
    stale = factory()
    winning_version = _evidence_version("evidence-version-winning", evidence_id, 2, "Winning")
    losing_version = _evidence_version("evidence-version-losing", evidence_id, 2, "Losing")
    try:
        winning_item = first.knowledge.get_evidence(evidence_id).with_version(winning_version)
        losing_item = stale.knowledge.get_evidence(evidence_id).with_version(losing_version)
        first.knowledge.save_evidence(winning_item)
        first.knowledge.add_evidence_version(winning_version)
        stale.knowledge.save_evidence(losing_item)
        stale.knowledge.add_evidence_version(losing_version)

        first.commit()
        with pytest.raises(StaleWriteError, match="state changed"):
            stale.commit()
    finally:
        first.close()
        stale.close()

    verification = factory()
    try:
        stored = verification.knowledge.get_evidence(evidence_id)
        assert stored.active_version_id == winning_version.version_id
        assert stored.version_ids == (original.version_id, winning_version.version_id)
        with pytest.raises(EntityNotFoundError, match="evidence version not found"):
            verification.knowledge.get_evidence_version(losing_version.version_id)
    finally:
        verification.close()
        runtime.dispose()


def test_failed_sqlite_commit_rolls_back_every_staged_row(tmp_path: Path) -> None:
    database_path = tmp_path / "job-hunter.db"
    upgrade_database(database_path)
    runtime = create_database_runtime(database_path)
    factory = SqlAlchemyUnitOfWorkFactory(runtime.session_factory)
    snapshot = SourceSnapshot(
        snapshot_id=SourceSnapshotId("source-snapshot-atomic"),
        source_kind=SourceKind.MANUAL_JD,
        source_locator=None,
        raw_title="AI Engineer",
        raw_company="Example AI",
        raw_city="Shenzhen",
        raw_description="Python",
        captured_at=NOW,
        freshness=Freshness(FreshnessStatus.FRESH, checked_at=NOW),
        correlation_id=CorrelationId("correlation-atomic"),
        run_id=RunId("run-atomic"),
    )
    failed = factory()
    try:
        failed.jobs.add_snapshot(snapshot)
        failed.jobs.add_snapshot(snapshot)
        with pytest.raises(ConflictError, match="database state conflicts"):
            failed.commit()
    finally:
        failed.close()

    verification = factory()
    try:
        with pytest.raises(EntityNotFoundError, match="source snapshot not found"):
            verification.jobs.get_snapshot(snapshot.snapshot_id)
    finally:
        verification.close()
        runtime.dispose()


def test_same_timestamp_screen_history_uses_commit_order_not_id_order(tmp_path: Path) -> None:
    database_path = tmp_path / "job-hunter.db"
    upgrade_database(database_path)
    runtime = create_database_runtime(database_path)
    factory = SqlAlchemyUnitOfWorkFactory(runtime.session_factory)
    use_cases = build_test_use_cases(
        clock=FixedClock(NOW),
        id_generator=_ReverseScreenIdGenerator(),
        unit_of_work_factory=factory,
    )
    try:
        with TestClient(create_app(use_cases=use_cases)) as client:
            imported = _import_job(client)
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
            assert profile.status_code == 201
            job_id = imported["job_id"]
            first = client.post(
                f"/api/v1/jobs/{job_id}/screen",
                json={"correlation_id": "correlation-screen-1", "run_id": "run-screen-1"},
            )
            second = client.post(
                f"/api/v1/jobs/{job_id}/screen",
                json={"correlation_id": "correlation-screen-2", "run_id": "run-screen-2"},
            )
            detail = client.get(f"/api/v1/jobs/{job_id}")

        assert first.status_code == 201
        assert second.status_code == 201
        assert [item["quick_screen_result_id"] for item in detail.json()["screening_results"]] == [
            "quick-screen-z",
            "quick-screen-a",
        ]
        direct = factory()
        try:
            assert direct.screening.get_latest_quick_screen_result(
                JobId(str(job_id))
            ).result_id == QuickScreenResultId("quick-screen-a")
        finally:
            direct.close()
    finally:
        runtime.dispose()


def test_relational_ownership_rejects_cross_job_screen_triage_and_retrieval(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job-hunter.db"
    upgrade_database(database_path)
    settings = _settings(database_path)
    with TestClient(create_app(settings=settings)) as client:
        job_a = _import_job(client)
        job_b = _import_job(client)
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
        assert profile.status_code == 201
        screened_a = client.post(
            f"/api/v1/jobs/{job_a['job_id']}/screen",
            json={"correlation_id": "correlation-screen-a", "run_id": "run-screen-a"},
        )
        assert screened_a.status_code == 201
        screened_b = client.post(
            f"/api/v1/jobs/{job_b['job_id']}/screen",
            json={"correlation_id": "correlation-screen-b", "run_id": "run-screen-b"},
        )
        assert screened_b.status_code == 201

    runtime = create_database_runtime(database_path)
    factory = SqlAlchemyUnitOfWorkFactory(runtime.session_factory)
    screen_b_id = QuickScreenResultId(screened_b.json()["quick_screen_result_id"])
    malformed_screen_uow = factory()
    try:
        screen_b = malformed_screen_uow.screening.get_quick_screen_result(screen_b_id)
        malformed_screen_uow.screening.add_quick_screen_result(
            replace(
                screen_b,
                result_id=QuickScreenResultId("quick-screen-wrong-owner"),
                job_id=JobId(str(job_a["job_id"])),
            )
        )
        with pytest.raises(ConflictError, match="database state conflicts"):
            malformed_screen_uow.commit()
    finally:
        malformed_screen_uow.close()

    malformed_triage_uow = factory()
    try:
        malformed_triage_uow.screening.add_triage_record(
            JobTriageRecord(
                decision_id=TriageDecisionId("triage-wrong-owner"),
                job_id=JobId(str(job_a["job_id"])),
                quick_screen_result_id=screen_b_id,
                decision=TriageDecision.SHORTLISTED,
                decided_at=NOW,
                correlation_id=CorrelationId("correlation-triage-wrong-owner"),
                run_id=RunId("run-triage-wrong-owner"),
            )
        )
        with pytest.raises(ConflictError, match="database state conflicts"):
            malformed_triage_uow.commit()
    finally:
        malformed_triage_uow.close()

    malformed_run_uow = factory()
    try:
        malformed_run_uow.retrieval.add_run(
            RetrievalRun(
                retrieval_run_id=RetrievalRunId("retrieval-wrong-owner"),
                requirement_id=RequirementId(screened_b.json()["requirement_ids"][0]),
                job_version_id=JobVersionId(str(job_a["job_version_id"])),
                strategy=RetrievalStrategy.LEXICAL_METADATA,
                retriever_version="test-retriever-v1",
                eligibility_policy_version="test-eligibility-v1",
                token_estimator_version="test-token-v1",
                status=RetrievalStatus.NO_RELEVANT_EVIDENCE,
                hits=(),
                exclusions=(),
                eligible_count=0,
                eligible_estimated_tokens=0,
                selected_estimated_tokens=0,
                max_tokens=100,
                top_k=5,
                created_at=NOW,
                correlation_id=CorrelationId("correlation-retrieval-wrong-owner"),
                run_id=RunId("run-retrieval-wrong-owner"),
            )
        )
        with pytest.raises(ConflictError, match="database state conflicts"):
            malformed_run_uow.commit()
    finally:
        malformed_run_uow.close()
        runtime.dispose()

    # Simulate storage corruption with FK enforcement disabled: both serialized
    # requirement IDs and their association rows are changed. Hydration must still
    # reject the cross-JobVersion chain rather than trusting either representation.
    connection = sqlite3.connect(database_path)
    try:
        screen_payload = connection.execute(
            "SELECT payload FROM quick_screen_results WHERE result_id = ?",
            (str(screen_b_id),),
        ).fetchone()
        assert screen_payload is not None
        payload = cast(dict[str, object], json.loads(cast(str, screen_payload[0])))
        payload["requirement_ids"] = [{"value": screened_a.json()["requirement_ids"][0]}]
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            """
            UPDATE quick_screen_requirements
            SET requirement_id = ?, job_version_id = ?
            WHERE quick_screen_result_id = ?
            """,
            (
                screened_a.json()["requirement_ids"][0],
                job_a["job_version_id"],
                str(screen_b_id),
            ),
        )
        connection.execute(
            "UPDATE quick_screen_results SET payload = ? WHERE result_id = ?",
            (json.dumps(payload), str(screen_b_id)),
        )
        connection.commit()
    finally:
        connection.close()

    reopened = create_database_runtime(database_path)
    verification = SqlAlchemyUnitOfWorkFactory(reopened.session_factory)()
    try:
        with pytest.raises(DependencyUnavailableError, match="persisted state is invalid"):
            verification.screening.get_quick_screen_result(screen_b_id)
    finally:
        verification.close()
        reopened.dispose()


@pytest.mark.parametrize("association_kind", ["hit", "exclusion"])
def test_retrieval_lineage_rejects_mismatched_evidence_ownership(
    tmp_path: Path,
    association_kind: str,
) -> None:
    database_path = tmp_path / "job-hunter.db"
    upgrade_database(database_path)
    settings = _settings(database_path)
    with TestClient(create_app(settings=settings)) as client:
        imported = _import_job(client)
        assert (
            client.post(
                "/api/v1/knowledge/profile",
                json={
                    "target_role_keywords": ["AI Engineer"],
                    "skill_keywords": ["Python"],
                    "preferred_cities": ["Shenzhen"],
                    "correlation_id": "correlation-profile",
                    "run_id": "run-profile",
                },
            ).status_code
            == 201
        )
        screened = client.post(
            f"/api/v1/jobs/{imported['job_id']}/screen",
            json={"correlation_id": "correlation-screen", "run_id": "run-screen"},
        )
        assert screened.status_code == 201

    runtime = create_database_runtime(database_path)
    factory = SqlAlchemyUnitOfWorkFactory(runtime.session_factory)
    evidence_a_id = EvidenceItemId("evidence-owner-a")
    evidence_b_id = EvidenceItemId("evidence-owner-b")
    version_a = _evidence_version("evidence-version-owner-a", evidence_a_id, 1, "A")
    version_b = _evidence_version("evidence-version-owner-b", evidence_b_id, 1, "B")
    setup = factory()
    try:
        setup.knowledge.add_evidence(EvidenceItem.create(version_a))
        setup.knowledge.add_evidence_version(version_a)
        setup.knowledge.add_evidence(EvidenceItem.create(version_b))
        setup.knowledge.add_evidence_version(version_b)
        setup.commit()
    finally:
        setup.close()

    malformed = factory()
    try:
        hit = RetrievalHit(
            evidence_id=evidence_a_id,
            evidence_version_id=version_b.version_id,
            rank=1,
            score=1.0,
            reasons=(RetrievalMatchReason.TOKEN_OVERLAP,),
        )
        exclusion = EvidenceExclusion(
            evidence_id=evidence_a_id,
            evidence_version_id=version_b.version_id,
            reason=EvidenceExclusionReason.INVALID,
        )
        malformed.retrieval.add_run(
            RetrievalRun(
                retrieval_run_id=RetrievalRunId(f"retrieval-mismatched-{association_kind}"),
                requirement_id=RequirementId(screened.json()["requirement_ids"][0]),
                job_version_id=JobVersionId(str(imported["job_version_id"])),
                strategy=RetrievalStrategy.LEXICAL_METADATA,
                retriever_version="test-retriever-v1",
                eligibility_policy_version="test-eligibility-v1",
                token_estimator_version="test-token-v1",
                status=(
                    RetrievalStatus.COMPLETED
                    if association_kind == "hit"
                    else RetrievalStatus.NO_RELEVANT_EVIDENCE
                ),
                hits=(hit,) if association_kind == "hit" else (),
                exclusions=(exclusion,) if association_kind == "exclusion" else (),
                eligible_count=1 if association_kind == "hit" else 0,
                eligible_estimated_tokens=1 if association_kind == "hit" else 0,
                selected_estimated_tokens=1 if association_kind == "hit" else 0,
                max_tokens=100,
                top_k=5,
                created_at=NOW,
                correlation_id=CorrelationId("correlation-retrieval-mismatch"),
                run_id=RunId("run-retrieval-mismatch"),
            )
        )
        with pytest.raises(ConflictError, match="database state conflicts"):
            malformed.commit()
    finally:
        malformed.close()
        runtime.dispose()


def test_invalid_persisted_payload_fails_closed_without_database_details(tmp_path: Path) -> None:
    database_path = tmp_path / "private-workspace.db"
    upgrade_database(database_path)
    application = create_app(settings=_settings(database_path))

    with TestClient(application) as client:
        imported = _import_job(client)
        with application.state.database_runtime.engine.begin() as connection:
            payload = connection.execute(
                text("SELECT payload FROM jobs WHERE job_id = :job_id"),
                {"job_id": imported["job_id"]},
            ).scalar_one()
            assert isinstance(payload, str)
            invalid_job = cast(dict[str, object], json.loads(payload))
            invalid_job["active_version_id"] = {"value": "job-version-missing"}
            connection.execute(
                text("UPDATE jobs SET payload = :payload WHERE job_id = :job_id"),
                {
                    "payload": json.dumps(invalid_job),
                    "job_id": imported["job_id"],
                },
            )
        response = client.get(f"/api/v1/jobs/{imported['job_id']}")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "dependency_unavailable",
            "message": "persisted state is invalid",
        }
    }
    assert "job-version-missing" not in response.text
    assert str(database_path) not in response.text
    assert "UPDATE jobs" not in response.text
