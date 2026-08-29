from datetime import UTC, datetime
from typing import Never

import pytest

from job_hunter.application.candidate_knowledge import (
    CreateCandidateProfile,
    CreateCandidateProfileCommand,
)
from job_hunter.application.import_job import ImportJob, ImportJobCommand
from job_hunter.application.screening import (
    RecordJobTriage,
    RecordJobTriageCommand,
    RunQuickScreen,
    RunQuickScreenCommand,
)
from job_hunter.domain.ids import CorrelationId, JobId, QuickScreenResultId, RunId
from job_hunter.domain.jobs import JobLifecycleStatus
from job_hunter.domain.screening import (
    QuickScreenRecommendation,
    RequirementPriority,
    RequirementType,
    ScreenReasonCode,
    TriageDecision,
)
from job_hunter.errors import DependencyUnavailableError
from job_hunter.infrastructure.memory import InMemoryStore, InMemoryUnitOfWorkFactory
from job_hunter.ingestion.manual import JobSourceRegistry, ManualJDInput, ManualJDSource
from tests.helpers import DeterministicIdGenerator, FixedClock

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)


class _FailingUnitOfWorkFactory:
    def __call__(self) -> Never:
        raise RuntimeError("secret persistence failure")


def _prepared() -> tuple[
    InMemoryStore,
    InMemoryUnitOfWorkFactory,
    DeterministicIdGenerator,
    JobId,
]:
    store = InMemoryStore()
    uow_factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    job = ImportJob(
        source_registry=JobSourceRegistry((ManualJDSource(),)),
        unit_of_work_factory=uow_factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        ImportJobCommand(
            source_input=ManualJDInput(
                title="Senior AI Engineer",
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
        )
    )
    CreateCandidateProfile(
        unit_of_work_factory=uow_factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        CreateCandidateProfileCommand(
            target_role_keywords=("AI Engineer",),
            skill_keywords=("Python", "LLM"),
            preferred_cities=("Shenzhen",),
            correlation_id=CorrelationId("correlation-profile"),
            run_id=RunId("run-profile"),
        )
    )
    return store, uow_factory, ids, job.job_id


def test_quick_screen_parses_stable_requirements_and_emits_screen_in() -> None:
    store, uow_factory, ids, job_id = _prepared()
    use_case = RunQuickScreen(
        unit_of_work_factory=uow_factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    )
    result = use_case.execute(
        RunQuickScreenCommand(
            job_id=job_id,
            correlation_id=CorrelationId("correlation-screen-1"),
            run_id=RunId("run-screen-1"),
        )
    )
    rerun = use_case.execute(
        RunQuickScreenCommand(
            job_id=job_id,
            correlation_id=CorrelationId("correlation-screen-2"),
            run_id=RunId("run-screen-2"),
        )
    )

    requirements = store.list_requirements(result.job_version_id)
    stored_result = store.get_quick_screen_result(result.quick_screen_result_id)
    assert result.recommendation is QuickScreenRecommendation.SCREEN_IN
    assert result.reason_codes == (
        ScreenReasonCode.TARGET_ROLE_MATCH,
        ScreenReasonCode.SKILL_OVERLAP,
    )
    assert result.requirement_ids == rerun.requirement_ids
    assert (
        store.get_profile(stored_result.candidate_profile_id).profile_id
        == result.candidate_profile_id
    )
    assert (
        tuple(store.get_requirement(item_id) for item_id in stored_result.requirement_ids)
        == requirements
    )
    assert len(requirements) == 3
    assert requirements[0].priority is RequirementPriority.REQUIRED
    assert requirements[0].requirement_type is RequirementType.SKILL
    assert requirements[2].priority is RequirementPriority.PREFERRED
    assert store.get_job(result.job_id).lifecycle_status is JobLifecycleStatus.SCREENED
    assert result.correlation_id == CorrelationId("correlation-screen-1")
    assert result.run_id == RunId("run-screen-1")


def test_quick_screen_uses_explicit_city_preference_for_screen_out() -> None:
    _store, uow_factory, ids, job_id = _prepared()
    CreateCandidateProfile(
        unit_of_work_factory=uow_factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        CreateCandidateProfileCommand(
            target_role_keywords=("AI Engineer",),
            skill_keywords=("Python",),
            preferred_cities=("Guangzhou",),
            correlation_id=CorrelationId("correlation-profile-2"),
            run_id=RunId("run-profile-2"),
        )
    )

    result = RunQuickScreen(
        unit_of_work_factory=uow_factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        RunQuickScreenCommand(
            job_id=job_id,
            correlation_id=CorrelationId("correlation-screen"),
            run_id=RunId("run-screen"),
        )
    )

    assert result.recommendation is QuickScreenRecommendation.SCREEN_OUT
    assert result.reason_codes == (ScreenReasonCode.CITY_OUTSIDE_PREFERENCE,)


def test_quick_screen_returns_uncertain_without_enough_confirmed_signal() -> None:
    _store, uow_factory, ids, job_id = _prepared()
    CreateCandidateProfile(
        unit_of_work_factory=uow_factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        CreateCandidateProfileCommand(
            target_role_keywords=("Data Scientist",),
            skill_keywords=("Rust",),
            preferred_cities=("Shenzhen",),
            correlation_id=CorrelationId("correlation-profile-2"),
            run_id=RunId("run-profile-2"),
        )
    )

    result = RunQuickScreen(
        unit_of_work_factory=uow_factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        RunQuickScreenCommand(
            job_id=job_id,
            correlation_id=CorrelationId("correlation-screen"),
            run_id=RunId("run-screen"),
        )
    )

    assert result.recommendation is QuickScreenRecommendation.UNCERTAIN
    assert result.reason_codes == (ScreenReasonCode.INSUFFICIENT_SIGNAL,)


def test_triage_retains_recommendation_and_allows_human_override() -> None:
    store, uow_factory, ids, job_id = _prepared()
    screen = RunQuickScreen(
        unit_of_work_factory=uow_factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        RunQuickScreenCommand(
            job_id=job_id,
            correlation_id=CorrelationId("correlation-screen"),
            run_id=RunId("run-screen"),
        )
    )
    triage = RecordJobTriage(
        unit_of_work_factory=uow_factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    )
    skipped = triage.execute(
        RecordJobTriageCommand(
            job_id=job_id,
            quick_screen_result_id=screen.quick_screen_result_id,
            decision=TriageDecision.SKIPPED,
            correlation_id=CorrelationId("correlation-triage-1"),
            run_id=RunId("run-triage-1"),
        )
    )
    restored = triage.execute(
        RecordJobTriageCommand(
            job_id=job_id,
            quick_screen_result_id=screen.quick_screen_result_id,
            decision=TriageDecision.SHORTLISTED,
            correlation_id=CorrelationId("correlation-triage-2"),
            run_id=RunId("run-triage-2"),
        )
    )

    records = store.list_triage_records(skipped.job_id)
    assert screen.recommendation is QuickScreenRecommendation.SCREEN_IN
    assert skipped.lifecycle_status is JobLifecycleStatus.SKIPPED
    assert restored.lifecycle_status is JobLifecycleStatus.SHORTLISTED
    assert tuple(record.decision for record in records) == (
        TriageDecision.SKIPPED,
        TriageDecision.SHORTLISTED,
    )
    assert records[1].correlation_id == CorrelationId("correlation-triage-2")
    assert records[1].run_id == RunId("run-triage-2")


def test_profile_update_preserves_historical_screen_and_does_not_block_triage() -> None:
    store, uow_factory, ids, job_id = _prepared()
    screen = RunQuickScreen(
        unit_of_work_factory=uow_factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        RunQuickScreenCommand(
            job_id=job_id,
            correlation_id=CorrelationId("correlation-screen"),
            run_id=RunId("run-screen"),
        )
    )
    newer_profile = CreateCandidateProfile(
        unit_of_work_factory=uow_factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        CreateCandidateProfileCommand(
            target_role_keywords=("Platform Engineer",),
            skill_keywords=("Rust",),
            preferred_cities=("Guangzhou",),
            correlation_id=CorrelationId("correlation-profile-new"),
            run_id=RunId("run-profile-new"),
        )
    )

    triage = RecordJobTriage(
        unit_of_work_factory=uow_factory,
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

    historical = store.get_quick_screen_result(screen.quick_screen_result_id)
    assert historical.candidate_profile_id == screen.candidate_profile_id
    assert store.get_active_profile().profile_id == newer_profile.profile_id
    assert historical.candidate_profile_id != newer_profile.profile_id
    assert triage.lifecycle_status is JobLifecycleStatus.SHORTLISTED


def test_quick_screen_translates_unit_of_work_factory_failure() -> None:
    use_case = RunQuickScreen(
        unit_of_work_factory=_FailingUnitOfWorkFactory(),
        clock=FixedClock(NOW),
        id_generator=DeterministicIdGenerator(),
    )

    with pytest.raises(
        DependencyUnavailableError,
        match="quick screen dependency is unavailable",
    ) as error:
        use_case.execute(
            RunQuickScreenCommand(
                job_id=JobId("job-001"),
                correlation_id=CorrelationId("correlation-001"),
                run_id=RunId("run-001"),
            )
        )

    assert "secret" not in str(error.value)


def test_job_triage_translates_unit_of_work_factory_failure() -> None:
    use_case = RecordJobTriage(
        unit_of_work_factory=_FailingUnitOfWorkFactory(),
        clock=FixedClock(NOW),
        id_generator=DeterministicIdGenerator(),
    )

    with pytest.raises(
        DependencyUnavailableError,
        match="job triage dependency is unavailable",
    ) as error:
        use_case.execute(
            RecordJobTriageCommand(
                job_id=JobId("job-001"),
                quick_screen_result_id=QuickScreenResultId("quick-screen-001"),
                decision=TriageDecision.SHORTLISTED,
                correlation_id=CorrelationId("correlation-001"),
                run_id=RunId("run-001"),
            )
        )

    assert "secret" not in str(error.value)
