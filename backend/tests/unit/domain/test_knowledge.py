from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime

import pytest

from job_hunter.domain.ids import (
    CandidateProfileId,
    CorrelationId,
    EvidenceItemId,
    EvidenceVersionId,
    RunId,
)
from job_hunter.domain.knowledge import (
    CandidateProfile,
    EvidenceItem,
    EvidenceItemVersion,
    EvidenceSensitivity,
    EvidenceType,
    EvidenceValidity,
)
from job_hunter.errors import ConflictError, InputValidationError

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)


def _evidence_version(*, number: int = 1, item_id: str = "evidence-001") -> EvidenceItemVersion:
    return EvidenceItemVersion(
        version_id=EvidenceVersionId(f"evidence-version-{number:03d}"),
        evidence_id=EvidenceItemId(item_id),
        version_number=number,
        evidence_type=EvidenceType.PROJECT,
        canonical_content="Built a grounded agent evaluation pipeline.",
        occurred_on=date(2026, 6, 1),
        source="manual",
        provenance="User-confirmed project record",
        sensitivity=EvidenceSensitivity.PRIVATE,
        validity=EvidenceValidity.VALID,
        created_at=NOW,
        correlation_id=CorrelationId("correlation-001"),
        run_id=RunId("run-001"),
    )


def test_candidate_profile_requires_unique_human_confirmed_facts() -> None:
    with pytest.raises(InputValidationError, match="target role keywords must be unique"):
        CandidateProfile(
            profile_id=CandidateProfileId("profile-001"),
            target_role_keywords=("AI Engineer", "ai engineer"),
            skill_keywords=("Python",),
            preferred_cities=("Shenzhen",),
            created_at=NOW,
            correlation_id=CorrelationId("correlation-001"),
            run_id=RunId("run-001"),
        )


def test_evidence_versions_are_immutable_and_history_is_append_only() -> None:
    first = _evidence_version()
    item = EvidenceItem.create(first)
    second = _evidence_version(number=2)

    updated = item.with_version(second)

    with pytest.raises(FrozenInstanceError):
        first.__setattr__("canonical_content", "Changed in place")
    assert item.active_version_id == first.version_id
    assert updated.active_version_id == second.version_id
    assert updated.version_ids == (first.version_id, second.version_id)


def test_evidence_rejects_cross_item_or_non_sequential_versions() -> None:
    item = EvidenceItem.create(_evidence_version())

    with pytest.raises(ConflictError, match="another evidence item"):
        item.with_version(_evidence_version(number=2, item_id="evidence-002"))

    with pytest.raises(ConflictError, match="number must be sequential"):
        item.with_version(_evidence_version(number=3))


def test_evidence_constructor_rejects_active_version_outside_history() -> None:
    with pytest.raises(InputValidationError, match="active version must belong to history"):
        EvidenceItem(
            evidence_id=EvidenceItemId("evidence-001"),
            active_version_id=EvidenceVersionId("evidence-version-002"),
            version_ids=(EvidenceVersionId("evidence-version-001"),),
        )
