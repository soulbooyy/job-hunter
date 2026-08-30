from datetime import UTC, date, datetime
from typing import Never

import pytest

from job_hunter.application.candidate_knowledge import (
    CreateCandidateProfile,
    CreateCandidateProfileCommand,
    SaveEvidence,
    SaveEvidenceCommand,
)
from job_hunter.application.import_job import ImportJob, ImportJobCommand
from job_hunter.application.screening import (
    RecordJobTriage,
    RecordJobTriageCommand,
    RunQuickScreen,
    RunQuickScreenCommand,
)
from job_hunter.application.workspace_queries import (
    JobVersionReadStatus,
    ProfileReadStatus,
    WorkspaceQueries,
)
from job_hunter.domain.ids import CorrelationId, JobId, RunId
from job_hunter.domain.knowledge import EvidenceSensitivity, EvidenceType, EvidenceValidity
from job_hunter.domain.screening import QuickScreenRecommendation, TriageDecision
from job_hunter.errors import DependencyUnavailableError, EntityNotFoundError
from job_hunter.infrastructure.memory import InMemoryStore, InMemoryUnitOfWorkFactory
from job_hunter.ingestion.manual import JobSourceRegistry, ManualJDInput, ManualJDSource
from tests.helpers import DeterministicIdGenerator, FixedClock

NOW = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)


class _FailingUnitOfWorkFactory:
    def __call__(self) -> Never:
        raise RuntimeError("secret read failure")


def _dependencies() -> tuple[
    InMemoryStore,
    InMemoryUnitOfWorkFactory,
    DeterministicIdGenerator,
]:
    store = InMemoryStore()
    return store, InMemoryUnitOfWorkFactory(store), DeterministicIdGenerator()


def _import_job(
    factory: InMemoryUnitOfWorkFactory,
    ids: DeterministicIdGenerator,
    *,
    title: str = "Senior AI Engineer",
    existing_job_id: JobId | None = None,
) -> JobId:
    result = ImportJob(
        source_registry=JobSourceRegistry((ManualJDSource(),)),
        unit_of_work_factory=factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        ImportJobCommand(
            source_input=ManualJDInput(
                title=title,
                company="Example AI",
                city="Shenzhen",
                content=(
                    "- Must have Python experience\n"
                    "- Build production LLM agents\n"
                    "- Bachelor's degree preferred"
                ),
            ),
            correlation_id=CorrelationId("correlation-import"),
            run_id=RunId("run-import"),
            existing_job_id=existing_job_id,
        )
    )
    return result.job_id


def _create_profile(
    factory: InMemoryUnitOfWorkFactory,
    ids: DeterministicIdGenerator,
    *,
    target: str = "AI Engineer",
) -> None:
    id_suffix = target.replace(" ", "-")
    CreateCandidateProfile(
        unit_of_work_factory=factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        CreateCandidateProfileCommand(
            target_role_keywords=(target,),
            skill_keywords=("Python", "LLM"),
            preferred_cities=("Shenzhen",),
            correlation_id=CorrelationId(f"correlation-profile-{id_suffix}"),
            run_id=RunId(f"run-profile-{id_suffix}"),
        )
    )


def _screen(
    factory: InMemoryUnitOfWorkFactory,
    ids: DeterministicIdGenerator,
    job_id: JobId,
):
    return RunQuickScreen(
        unit_of_work_factory=factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        RunQuickScreenCommand(
            job_id=job_id,
            correlation_id=CorrelationId("correlation-screen"),
            run_id=RunId("run-screen"),
        )
    )


def test_empty_workspace_queries_return_typed_empty_collections() -> None:
    _store, factory, _ids = _dependencies()
    queries = WorkspaceQueries(unit_of_work_factory=factory)

    assert queries.list_jobs().items == ()
    assert queries.list_profiles().active_profile_id is None
    assert queries.list_profiles().items == ()
    assert queries.list_evidence().items == ()


def test_workspace_queries_reconstruct_lineage_and_derived_screening_state() -> None:
    _store, factory, ids = _dependencies()
    job_id = _import_job(factory, ids)
    _create_profile(factory, ids)
    screen = _screen(factory, ids, job_id)
    RecordJobTriage(
        unit_of_work_factory=factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        RecordJobTriageCommand(
            job_id=job_id,
            quick_screen_result_id=screen.quick_screen_result_id,
            decision=TriageDecision.SHORTLISTED,
            correlation_id=CorrelationId("correlation-triage"),
            run_id=RunId("run-triage"),
        )
    )
    _create_profile(factory, ids, target="Platform Engineer")
    evidence = SaveEvidence(
        unit_of_work_factory=factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    )
    first_evidence = evidence.execute(
        SaveEvidenceCommand(
            evidence_type=EvidenceType.PROJECT,
            canonical_content="Built an evaluation pipeline.",
            occurred_on=date(2026, 6, 1),
            source="manual",
            provenance="User-confirmed project",
            sensitivity=EvidenceSensitivity.PRIVATE,
            validity=EvidenceValidity.VALID,
            correlation_id=CorrelationId("correlation-evidence-1"),
            run_id=RunId("run-evidence-1"),
        )
    )
    evidence.execute(
        SaveEvidenceCommand(
            evidence_type=EvidenceType.PROJECT,
            canonical_content="Built and benchmarked an evaluation pipeline.",
            occurred_on=date(2026, 7, 1),
            source="manual",
            provenance="User-confirmed project update",
            sensitivity=EvidenceSensitivity.PRIVATE,
            validity=EvidenceValidity.VALID,
            correlation_id=CorrelationId("correlation-evidence-2"),
            run_id=RunId("run-evidence-2"),
            existing_evidence_id=first_evidence.evidence_id,
        )
    )

    queries = WorkspaceQueries(unit_of_work_factory=factory)
    summaries = queries.list_jobs()
    profiles = queries.list_profiles()
    evidence_history = queries.list_evidence()
    detail = queries.get_job(job_id)

    assert len(summaries.items) == 1
    assert summaries.items[0].job_id == job_id
    assert summaries.items[0].current_screen_recommendation is (QuickScreenRecommendation.SCREEN_IN)
    assert summaries.items[0].current_triage_decision is TriageDecision.SHORTLISTED
    assert profiles.active_profile_id == profiles.items[-1].profile_id
    assert len(profiles.items) == 2
    assert len(evidence_history.items) == 1
    assert (
        evidence_history.items[0].active_version_id
        == evidence_history.items[0].versions[-1].version_id
    )
    assert tuple(version.version_number for version in evidence_history.items[0].versions) == (1, 2)
    assert detail.job_id == job_id
    assert len(detail.versions) == 1
    assert detail.versions[0].is_active
    assert detail.versions[0].source.snapshot_id == detail.versions[0].source_snapshot_id
    assert len(detail.requirements) == 3
    assert len(detail.screening_results) == 1
    read_screen = detail.screening_results[0]
    assert read_screen.profile_status is ProfileReadStatus.STALE
    assert read_screen.job_version_status is JobVersionReadStatus.CURRENT
    assert read_screen.is_latest_result
    assert read_screen.triage_eligible
    assert len(detail.triage_history) == 1
    assert detail.triage_history[0].recommendation is QuickScreenRecommendation.SCREEN_IN


def test_new_screen_and_job_version_keep_history_but_change_actionability() -> None:
    _store, factory, ids = _dependencies()
    job_id = _import_job(factory, ids)
    _create_profile(factory, ids)
    first = _screen(factory, ids, job_id)
    _create_profile(factory, ids, target="Platform Engineer")
    second = _screen(factory, ids, job_id)

    before_new_version = WorkspaceQueries(unit_of_work_factory=factory).get_job(job_id)
    first_read, second_read = before_new_version.screening_results
    assert first_read.result_id == first.quick_screen_result_id
    assert not first_read.is_latest_result
    assert not first_read.triage_eligible
    assert second_read.result_id == second.quick_screen_result_id
    assert second_read.is_latest_result
    assert second_read.triage_eligible

    _import_job(factory, ids, title="Principal AI Engineer", existing_job_id=job_id)
    after_new_version = WorkspaceQueries(unit_of_work_factory=factory).get_job(job_id)

    assert len(after_new_version.versions) == 2
    assert after_new_version.versions[-1].is_active
    assert after_new_version.screening_results[-1].is_latest_result
    assert after_new_version.screening_results[-1].job_version_status is (
        JobVersionReadStatus.HISTORICAL
    )
    assert not after_new_version.screening_results[-1].triage_eligible


def test_job_listing_has_deterministic_tie_break_order() -> None:
    _store, factory, ids = _dependencies()
    first = _import_job(factory, ids, title="AI Engineer One")
    second = _import_job(factory, ids, title="AI Engineer Two")

    result = WorkspaceQueries(unit_of_work_factory=factory).list_jobs()

    assert tuple(item.job_id for item in result.items) == (first, second)


def test_workspace_query_unknown_job_uses_stable_not_found_error() -> None:
    _store, factory, _ids = _dependencies()

    with pytest.raises(EntityNotFoundError, match="job not found: missing-job"):
        WorkspaceQueries(unit_of_work_factory=factory).get_job(JobId("missing-job"))


def test_workspace_query_translates_unit_of_work_factory_failure() -> None:
    queries = WorkspaceQueries(unit_of_work_factory=_FailingUnitOfWorkFactory())

    with pytest.raises(
        DependencyUnavailableError,
        match="workspace read dependency is unavailable",
    ) as error:
        queries.list_jobs()

    assert "secret" not in str(error.value)
