import hashlib
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from job_hunter.domain.context import (
    ContextEntry,
    ContextEntryKind,
    ContextInclusionReason,
    ContextPackage,
    ContextRedaction,
)
from job_hunter.domain.ids import (
    CandidateProfileId,
    ContextPackageId,
    CorrelationId,
    EvidenceChunkId,
    EvidenceItemId,
    EvidenceVersionId,
    JobVersionId,
    RequirementId,
    RetrievalRunId,
    RunId,
)
from job_hunter.errors import InputValidationError

NOW = datetime(2026, 8, 31, 18, 0, tzinfo=UTC)


def _entry() -> ContextEntry:
    return ContextEntry(
        kind=ContextEntryKind.EVIDENCE,
        content="Delivered a synthetic migration without contact data.",
        estimated_tokens=8,
        protected=False,
        requirement_id=RequirementId("requirement-1"),
        evidence_id=EvidenceItemId("evidence-1"),
        evidence_version_id=EvidenceVersionId("evidence-version-1"),
        evidence_chunk_id=EvidenceChunkId("evidence-chunk-1"),
        redaction=ContextRedaction.NONE,
        content_hash=hashlib.sha256(
            b"Delivered a synthetic migration without contact data."
        ).hexdigest(),
        inclusion_reason=ContextInclusionReason.RETRIEVAL_HIT,
    )


def _protected_entry(kind: ContextEntryKind) -> ContextEntry:
    content = f"synthetic {kind.value}"
    return ContextEntry(
        kind=kind,
        content=content,
        estimated_tokens=2,
        protected=True,
        requirement_id=(
            RequirementId("requirement-1") if kind is ContextEntryKind.REQUIREMENT else None
        ),
        evidence_id=None,
        evidence_version_id=None,
        evidence_chunk_id=None,
        redaction=ContextRedaction.NONE,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        inclusion_reason=ContextInclusionReason.REQUIRED_PROTECTED,
    )


def _entries() -> tuple[ContextEntry, ...]:
    return (
        _protected_entry(ContextEntryKind.REQUIREMENT),
        _protected_entry(ContextEntryKind.INSTRUCTION),
        _protected_entry(ContextEntryKind.WORKFLOW),
        _protected_entry(ContextEntryKind.PROFILE),
        _entry(),
    )


def test_context_package_is_immutable_versioned_and_budget_accounted() -> None:
    package = ContextPackage(
        context_package_id=ContextPackageId("context-package-1"),
        job_version_id=JobVersionId("job-version-1"),
        requirement_ids=(RequirementId("requirement-1"),),
        retrieval_run_id=RetrievalRunId("retrieval-run-1"),
        candidate_profile_id=CandidateProfileId("profile-1"),
        entries=_entries(),
        builder_version="context-builder-v1",
        redaction_policy_version="context-redaction-v1",
        token_estimator_version="deterministic-token-estimator-v1",
        packaging_overhead_tokens=3,
        total_estimated_tokens=19,
        max_tokens=30,
        created_at=NOW,
        correlation_id=CorrelationId("correlation-context"),
        run_id=RunId("run-context"),
    )

    assert package.total_estimated_tokens == 19

    with pytest.raises(InputValidationError, match="token accounting"):
        ContextPackage(
            context_package_id=package.context_package_id,
            job_version_id=package.job_version_id,
            requirement_ids=package.requirement_ids,
            retrieval_run_id=package.retrieval_run_id,
            candidate_profile_id=package.candidate_profile_id,
            entries=package.entries,
            builder_version=package.builder_version,
            redaction_policy_version=package.redaction_policy_version,
            token_estimator_version=package.token_estimator_version,
            packaging_overhead_tokens=3,
            total_estimated_tokens=18,
            max_tokens=30,
            created_at=package.created_at,
            correlation_id=package.correlation_id,
            run_id=package.run_id,
        )


def test_context_entry_recomputes_token_accounting_from_content() -> None:
    with pytest.raises(InputValidationError, match="token accounting"):
        replace(_entry(), estimated_tokens=1)


@pytest.mark.parametrize(
    "entries",
    (
        _entries()[1:],
        tuple(entry for entry in _entries() if entry.kind is not ContextEntryKind.PROFILE),
        (
            _protected_entry(ContextEntryKind.INSTRUCTION),
            _protected_entry(ContextEntryKind.REQUIREMENT),
            *_entries()[2:],
        ),
    ),
)
def test_context_package_requires_complete_ordered_protected_entries(
    entries: tuple[ContextEntry, ...],
) -> None:
    total = 3 + sum(entry.estimated_tokens for entry in entries)

    with pytest.raises(InputValidationError, match="protected entries"):
        ContextPackage(
            context_package_id=ContextPackageId("context-package-invalid"),
            job_version_id=JobVersionId("job-version-1"),
            requirement_ids=(RequirementId("requirement-1"),),
            retrieval_run_id=RetrievalRunId("retrieval-run-1"),
            candidate_profile_id=CandidateProfileId("profile-1"),
            entries=entries,
            builder_version="context-builder-v1",
            redaction_policy_version="context-redaction-v1",
            token_estimator_version="deterministic-token-estimator-v1",
            packaging_overhead_tokens=3,
            total_estimated_tokens=total,
            max_tokens=100,
            created_at=NOW,
            correlation_id=CorrelationId("correlation-context"),
            run_id=RunId("run-context"),
        )
