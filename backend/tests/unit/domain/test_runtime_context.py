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
    ArtifactId,
    CandidateProfileId,
    ContextPackageId,
    ContextReferenceId,
    CorrelationId,
    EvidenceChunkId,
    EvidenceItemId,
    EvidenceVersionId,
    JobVersionId,
    RequirementId,
    RetrievalRunId,
    RunId,
    RuntimeContextId,
)
from job_hunter.domain.retrieval import TOKEN_ESTIMATOR_VERSION, estimate_tokens
from job_hunter.domain.runtime_context import (
    RUNTIME_CONTEXT_POLICY_VERSION,
    ContextSupersession,
    RuntimeContextPolicy,
)
from job_hunter.errors import ContextBudgetExceededError, InputValidationError

NOW = datetime(2026, 9, 1, 16, 0, tzinfo=UTC)


def _entry(
    kind: ContextEntryKind,
    content: str,
    *,
    ordinal: int = 1,
    protected: bool = True,
) -> ContextEntry:
    requirement_id = (
        RequirementId("requirement-1")
        if kind in {ContextEntryKind.REQUIREMENT, ContextEntryKind.EVIDENCE}
        else None
    )
    return ContextEntry(
        kind=kind,
        content=content,
        estimated_tokens=estimate_tokens(content),
        protected=protected,
        requirement_id=requirement_id,
        evidence_id=(EvidenceItemId(f"evidence-{ordinal}") if not protected else None),
        evidence_version_id=(
            EvidenceVersionId(f"evidence-version-{ordinal}") if not protected else None
        ),
        evidence_chunk_id=(EvidenceChunkId(f"evidence-chunk-{ordinal}") if not protected else None),
        redaction=ContextRedaction.NONE,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        inclusion_reason=(
            ContextInclusionReason.REQUIRED_PROTECTED
            if protected
            else ContextInclusionReason.RETRIEVAL_HIT
        ),
    )


def _package(entries: tuple[ContextEntry, ...]) -> ContextPackage:
    return ContextPackage(
        context_package_id=ContextPackageId("context-package-1"),
        job_version_id=JobVersionId("job-version-1"),
        requirement_ids=(RequirementId("requirement-1"),),
        retrieval_run_id=RetrievalRunId("retrieval-run-1"),
        candidate_profile_id=CandidateProfileId("profile-1"),
        entries=entries,
        builder_version="context-builder-v1",
        redaction_policy_version="context-redaction-v1",
        token_estimator_version=TOKEN_ESTIMATOR_VERSION,
        packaging_overhead_tokens=3,
        total_estimated_tokens=3 + sum(item.estimated_tokens for item in entries),
        max_tokens=10_000,
        created_at=NOW,
        correlation_id=CorrelationId("correlation-context"),
        run_id=RunId("run-context"),
    )


def _protected() -> tuple[ContextEntry, ...]:
    return (
        _entry(ContextEntryKind.REQUIREMENT, "synthetic requirement"),
        _entry(ContextEntryKind.INSTRUCTION, "grounded assessment only"),
        _entry(ContextEntryKind.WORKFLOW, "context preparation"),
        _entry(ContextEntryKind.PROFILE, "synthetic profile"),
    )


def test_runtime_context_compaction_preserves_protected_and_exact_provenance() -> None:
    repeated = " ".join(f"synthetic{index}" for index in range(90))
    package = _package(
        (
            *_protected(),
            _entry(ContextEntryKind.EVIDENCE, repeated, ordinal=1, protected=False),
            _entry(ContextEntryKind.EVIDENCE, repeated, ordinal=2, protected=False),
        )
    )

    plan = RuntimeContextPolicy().compact(
        package,
        runtime_context_id=RuntimeContextId("runtime-context-1"),
        max_tokens=55,
        created_at=NOW,
        correlation_id=CorrelationId("correlation-runtime"),
        run_id=RunId("run-runtime"),
    )

    assert plan.snapshot.policy_version == RUNTIME_CONTEXT_POLICY_VERSION
    assert tuple(entry.source_ordinals for entry in plan.snapshot.entries[:4]) == (
        (1,),
        (2,),
        (3,),
        (4,),
    )
    assert plan.snapshot.entries[4].source_ordinals == (5, 6)
    assert plan.snapshot.entries[4].reference_id is not None
    assert len(plan.artifacts) == 1
    assert plan.snapshot.total_estimated_tokens <= plan.snapshot.max_tokens
    assert plan.snapshot.covered_source_ordinals == (1, 2, 3, 4, 5, 6)


def test_runtime_context_never_drops_protected_content_to_meet_budget() -> None:
    package = _package(_protected())

    with pytest.raises(ContextBudgetExceededError):
        RuntimeContextPolicy().compact(
            package,
            runtime_context_id=RuntimeContextId("runtime-context-1"),
            max_tokens=1,
            created_at=NOW,
            correlation_id=CorrelationId("correlation-runtime"),
            run_id=RunId("run-runtime"),
        )


def test_runtime_context_supersession_must_be_explicit_same_scope_and_unprotected() -> None:
    package = _package(
        (
            *_protected(),
            _entry(ContextEntryKind.EVIDENCE, "old synthetic fact", ordinal=1, protected=False),
            _entry(ContextEntryKind.EVIDENCE, "new synthetic fact", ordinal=2, protected=False),
        )
    )

    with pytest.raises(InputValidationError, match="same logical source"):
        RuntimeContextPolicy().compact(
            package,
            runtime_context_id=RuntimeContextId("runtime-context-1"),
            max_tokens=100,
            created_at=NOW,
            correlation_id=CorrelationId("correlation-runtime"),
            run_id=RunId("run-runtime"),
            supersessions=(ContextSupersession(obsolete_ordinal=5, replacement_ordinal=6),),
        )


def test_runtime_context_explicit_same_evidence_supersession_preserves_both_ordinals() -> None:
    old = _entry(ContextEntryKind.EVIDENCE, "old synthetic fact", ordinal=1, protected=False)
    replacement = replace(
        _entry(ContextEntryKind.EVIDENCE, "new synthetic fact", ordinal=2, protected=False),
        evidence_id=old.evidence_id,
    )
    package = _package((*_protected(), old, replacement))

    plan = RuntimeContextPolicy().compact(
        package,
        runtime_context_id=RuntimeContextId("runtime-context-1"),
        max_tokens=100,
        created_at=NOW,
        correlation_id=CorrelationId("correlation-runtime"),
        run_id=RunId("run-runtime"),
        supersessions=(ContextSupersession(obsolete_ordinal=5, replacement_ordinal=6),),
    )

    assert plan.snapshot.entries[-1].source_ordinals == (5, 6)
    assert plan.snapshot.entries[-1].inline_content == "new synthetic fact"
    assert plan.snapshot.covered_source_ordinals == (1, 2, 3, 4, 5, 6)


def test_content_addressed_artifact_and_reference_identities_are_stable() -> None:
    content_hash = hashlib.sha256(b"redacted synthetic content").hexdigest()

    assert ArtifactId.from_content_hash(content_hash) == ArtifactId.from_content_hash(content_hash)
    assert ContextReferenceId.from_source(
        ContextPackageId("context-package-1"), (5, 6), content_hash
    ) == ContextReferenceId.from_source(ContextPackageId("context-package-1"), (5, 6), content_hash)
