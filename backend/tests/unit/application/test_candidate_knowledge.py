from datetime import UTC, date, datetime
from typing import Never

import pytest

from job_hunter.application.candidate_knowledge import (
    CreateCandidateProfile,
    CreateCandidateProfileCommand,
    SaveEvidence,
    SaveEvidenceCommand,
)
from job_hunter.domain.ids import CorrelationId, RunId
from job_hunter.domain.knowledge import EvidenceSensitivity, EvidenceType, EvidenceValidity
from job_hunter.errors import DependencyUnavailableError, InputValidationError
from job_hunter.infrastructure.memory import InMemoryStore, InMemoryUnitOfWorkFactory
from tests.helpers import DeterministicIdGenerator, FixedClock

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)


class _FailingUnitOfWorkFactory:
    def __call__(self) -> Never:
        raise RuntimeError("secret persistence failure")


def _dependencies() -> tuple[
    InMemoryStore,
    InMemoryUnitOfWorkFactory,
    DeterministicIdGenerator,
]:
    store = InMemoryStore()
    return store, InMemoryUnitOfWorkFactory(store), DeterministicIdGenerator()


def test_create_profile_normalizes_and_persists_human_confirmed_projection() -> None:
    store, uow_factory, ids = _dependencies()
    result = CreateCandidateProfile(
        unit_of_work_factory=uow_factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        CreateCandidateProfileCommand(
            target_role_keywords=("  AI   Engineer ",),
            skill_keywords=(" Python ", "LangGraph"),
            preferred_cities=(" Shenzhen ",),
            correlation_id=CorrelationId("correlation-001"),
            run_id=RunId("run-001"),
        )
    )

    profile = store.get_active_profile()
    assert result.profile_id == profile.profile_id
    assert profile.target_role_keywords == ("AI Engineer",)
    assert profile.skill_keywords == ("Python", "LangGraph")
    assert profile.preferred_cities == ("Shenzhen",)
    assert profile.correlation_id == result.correlation_id
    assert profile.run_id == result.run_id


def test_new_profile_snapshot_becomes_active_without_losing_the_previous_input() -> None:
    store, uow_factory, ids = _dependencies()
    use_case = CreateCandidateProfile(
        unit_of_work_factory=uow_factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    )
    first = use_case.execute(
        CreateCandidateProfileCommand(
            target_role_keywords=("AI Engineer",),
            skill_keywords=("Python",),
            preferred_cities=("Shenzhen",),
            correlation_id=CorrelationId("correlation-001"),
            run_id=RunId("run-001"),
        )
    )
    second = use_case.execute(
        CreateCandidateProfileCommand(
            target_role_keywords=("AI Backend Engineer",),
            skill_keywords=("Python", "FastAPI"),
            preferred_cities=("Shenzhen",),
            correlation_id=CorrelationId("correlation-002"),
            run_id=RunId("run-002"),
        )
    )

    assert store.get_active_profile().profile_id == second.profile_id
    assert store.get_profile(first.profile_id).target_role_keywords == ("AI Engineer",)


def test_invalid_profile_does_not_enter_domain_state() -> None:
    store, uow_factory, ids = _dependencies()

    with pytest.raises(InputValidationError, match="skill keywords is required"):
        CreateCandidateProfile(
            unit_of_work_factory=uow_factory,
            clock=FixedClock(NOW),
            id_generator=ids,
        ).execute(
            CreateCandidateProfileCommand(
                target_role_keywords=("AI Engineer",),
                skill_keywords=(),
                preferred_cities=("Shenzhen",),
                correlation_id=CorrelationId("correlation-001"),
                run_id=RunId("run-001"),
            )
        )

    assert store.is_empty()


def test_evidence_create_and_update_preserve_authoritative_versions() -> None:
    store, uow_factory, ids = _dependencies()
    use_case = SaveEvidence(
        unit_of_work_factory=uow_factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    )
    first = use_case.execute(
        SaveEvidenceCommand(
            evidence_type=EvidenceType.PROJECT,
            canonical_content="Built an agent evaluation pipeline.",
            occurred_on=date(2026, 6, 1),
            source="manual",
            provenance="User-confirmed project record",
            sensitivity=EvidenceSensitivity.PRIVATE,
            validity=EvidenceValidity.VALID,
            correlation_id=CorrelationId("correlation-001"),
            run_id=RunId("run-001"),
        )
    )
    second = use_case.execute(
        SaveEvidenceCommand(
            evidence_type=EvidenceType.PROJECT,
            canonical_content="Built and benchmarked an agent evaluation pipeline.",
            occurred_on=date(2026, 7, 1),
            source="manual",
            provenance="User-confirmed project update",
            sensitivity=EvidenceSensitivity.PRIVATE,
            validity=EvidenceValidity.VALID,
            correlation_id=CorrelationId("correlation-002"),
            run_id=RunId("run-002"),
            existing_evidence_id=first.evidence_id,
        )
    )

    item = store.get_evidence(first.evidence_id)
    historical = store.get_evidence_version(first.evidence_version_id)
    active = store.get_evidence_version(second.evidence_version_id)
    assert item.active_version_id == second.evidence_version_id
    assert item.version_ids == (first.evidence_version_id, second.evidence_version_id)
    assert historical.canonical_content == "Built an agent evaluation pipeline."
    assert active.provenance == "User-confirmed project update"
    assert active.correlation_id == CorrelationId("correlation-002")
    assert active.run_id == RunId("run-002")


def test_save_evidence_translates_unit_of_work_factory_failure() -> None:
    use_case = SaveEvidence(
        unit_of_work_factory=_FailingUnitOfWorkFactory(),
        clock=FixedClock(NOW),
        id_generator=DeterministicIdGenerator(),
    )

    with pytest.raises(
        DependencyUnavailableError,
        match="evidence persistence is unavailable",
    ) as error:
        use_case.execute(
            SaveEvidenceCommand(
                evidence_type=EvidenceType.PROJECT,
                canonical_content="Built an evaluation pipeline.",
                occurred_on=date(2026, 6, 1),
                source="manual",
                provenance="User-confirmed project record",
                sensitivity=EvidenceSensitivity.PRIVATE,
                validity=EvidenceValidity.VALID,
                correlation_id=CorrelationId("correlation-001"),
                run_id=RunId("run-001"),
            )
        )

    assert "secret" not in str(error.value)
