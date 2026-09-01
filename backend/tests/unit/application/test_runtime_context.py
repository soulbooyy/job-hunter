import hashlib
import inspect
from datetime import UTC, datetime

import pytest

from job_hunter.application.runtime_context import (
    PrepareRuntimeContext,
    PrepareRuntimeContextCommand,
    RehydrateContextReference,
    RehydrateContextReferenceCommand,
)
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
from job_hunter.domain.retrieval import TOKEN_ESTIMATOR_VERSION, estimate_tokens
from job_hunter.errors import BudgetExceededError, DependencyUnavailableError
from job_hunter.infrastructure.artifacts import InMemoryArtifactStore
from job_hunter.infrastructure.memory import InMemoryStore, InMemoryUnitOfWorkFactory
from tests.helpers import DeterministicIdGenerator, FixedClock

NOW = datetime(2026, 9, 1, 17, 0, tzinfo=UTC)


class _RejectCommitGuard:
    def check(self) -> None:
        pass

    def check_before_commit(self, *, result_bytes: int) -> None:
        assert result_bytes > 0
        raise BudgetExceededError("workflow timeout budget exceeded")


def _entry(kind: ContextEntryKind, content: str, *, protected: bool) -> ContextEntry:
    evidence = not protected
    return ContextEntry(
        kind=kind,
        content=content,
        estimated_tokens=estimate_tokens(content),
        protected=protected,
        requirement_id=(
            RequirementId("requirement-1")
            if kind in {ContextEntryKind.REQUIREMENT, ContextEntryKind.EVIDENCE}
            else None
        ),
        evidence_id=EvidenceItemId("evidence-1") if evidence else None,
        evidence_version_id=EvidenceVersionId("evidence-version-1") if evidence else None,
        evidence_chunk_id=EvidenceChunkId("evidence-chunk-1") if evidence else None,
        redaction=ContextRedaction.NONE,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        inclusion_reason=(
            ContextInclusionReason.REQUIRED_PROTECTED
            if protected
            else ContextInclusionReason.RETRIEVAL_HIT
        ),
    )


def _package() -> ContextPackage:
    entries = (
        _entry(ContextEntryKind.REQUIREMENT, "synthetic requirement", protected=True),
        _entry(ContextEntryKind.INSTRUCTION, "use grounded facts", protected=True),
        _entry(ContextEntryKind.WORKFLOW, "context preparation", protected=True),
        _entry(ContextEntryKind.PROFILE, "synthetic profile", protected=True),
        _entry(
            ContextEntryKind.EVIDENCE,
            " ".join(f"synthetic{index}" for index in range(90)),
            protected=False,
        ),
    )
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
        total_estimated_tokens=3 + sum(entry.estimated_tokens for entry in entries),
        max_tokens=10_000,
        created_at=NOW,
        correlation_id=CorrelationId("correlation-context"),
        run_id=RunId("run-context"),
    )


def test_prepare_and_rehydrate_context_reference_preserves_exact_redacted_content() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    artifacts = InMemoryArtifactStore()
    unit_of_work = factory()
    package = _package()
    unit_of_work.context.add_package(package)
    unit_of_work.commit()
    unit_of_work.close()

    prepared = PrepareRuntimeContext(
        unit_of_work_factory=factory,
        artifact_store=artifacts,
        clock=FixedClock(NOW),
        id_generator=DeterministicIdGenerator(),
    ).execute(
        PrepareRuntimeContextCommand(
            context_package_id=package.context_package_id,
            max_tokens=45,
            correlation_id=CorrelationId("correlation-runtime"),
            run_id=RunId("run-runtime"),
        )
    )

    assert prepared.artifact_count == 1
    verification = factory()
    snapshot = verification.runtime_context.get_snapshot(prepared.runtime_context_id)
    reference_id = snapshot.entries[-1].reference_id
    verification.close()
    assert reference_id is not None
    rehydrated = RehydrateContextReference(
        unit_of_work_factory=factory,
        artifact_store=artifacts,
    ).execute(
        RehydrateContextReferenceCommand(
            runtime_context_id=prepared.runtime_context_id,
            reference_id=reference_id,
        )
    )

    assert rehydrated.content == package.entries[-1].content
    assert rehydrated.source_ordinals == (5,)


def test_rehydrate_rejects_missing_artifact_without_disclosing_content() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    original_artifacts = InMemoryArtifactStore()
    unit_of_work = factory()
    package = _package()
    unit_of_work.context.add_package(package)
    unit_of_work.commit()
    unit_of_work.close()
    prepared = PrepareRuntimeContext(
        unit_of_work_factory=factory,
        artifact_store=original_artifacts,
        clock=FixedClock(NOW),
        id_generator=DeterministicIdGenerator(),
    ).execute(
        PrepareRuntimeContextCommand(
            context_package_id=package.context_package_id,
            max_tokens=45,
            correlation_id=CorrelationId("correlation-runtime"),
            run_id=RunId("run-runtime"),
        )
    )
    verification = factory()
    reference_id = (
        verification.runtime_context.get_snapshot(prepared.runtime_context_id)
        .entries[-1]
        .reference_id
    )
    verification.close()
    assert reference_id is not None

    with pytest.raises(DependencyUnavailableError, match="runtime artifact is unavailable"):
        RehydrateContextReference(
            unit_of_work_factory=factory,
            artifact_store=InMemoryArtifactStore(),
        ).execute(
            RehydrateContextReferenceCommand(
                runtime_context_id=prepared.runtime_context_id,
                reference_id=reference_id,
            )
        )


def test_prepare_command_does_not_expose_unauthorized_supersession_input() -> None:
    assert "supersessions" not in inspect.signature(PrepareRuntimeContextCommand).parameters


def test_prepare_guard_rejects_before_runtime_context_commit() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    package = _package()
    unit_of_work = factory()
    unit_of_work.context.add_package(package)
    unit_of_work.commit()
    unit_of_work.close()

    with pytest.raises(BudgetExceededError):
        PrepareRuntimeContext(
            unit_of_work_factory=factory,
            artifact_store=InMemoryArtifactStore(),
            clock=FixedClock(NOW),
            id_generator=DeterministicIdGenerator(),
        ).execute(
            PrepareRuntimeContextCommand(
                context_package_id=package.context_package_id,
                max_tokens=45,
                correlation_id=CorrelationId("correlation-runtime-budget"),
                run_id=RunId("run-runtime-budget"),
            ),
            execution_guard=_RejectCommitGuard(),
        )

    verification = factory()
    assert verification.runtime_context.list_snapshots(package.context_package_id) == ()
    verification.close()
