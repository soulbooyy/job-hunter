"""Deterministic synthetic evaluation for runtime-context compaction mechanics."""

import hashlib
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

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
    RuntimeContextId,
)
from job_hunter.domain.retrieval import TOKEN_ESTIMATOR_VERSION, estimate_tokens
from job_hunter.domain.runtime_context import RuntimeContextPolicy
from job_hunter.infrastructure.artifacts import InMemoryArtifactStore

_FIXTURE_TIME = datetime(2000, 1, 1, tzinfo=UTC)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeContextCase(_FrozenModel):
    case_id: str = Field(min_length=1)
    protected: tuple[str, str, str, str]
    evidence: tuple[str, ...] = Field(min_length=1)
    max_tokens: int = Field(ge=1)


class RuntimeContextDataset(_FrozenModel):
    dataset_version: str
    policy_version: str
    synthetic_fixture: bool
    cases: tuple[RuntimeContextCase, ...] = Field(min_length=1)


class RuntimeContextEvaluationReport(_FrozenModel):
    dataset_version: str
    policy_version: str
    case_count: int
    protected_loss_count: int
    reference_rehydration_accuracy: float
    provenance_accuracy: float
    unsupported_fact_count: int
    silent_truncation_count: int
    source_estimated_tokens: int
    runtime_estimated_tokens: int
    token_reduction: float
    evidence_lineage_coverage: float
    effective_evidence_recall_degradation: float | None
    workflow_completion_degradation: float | None
    mechanics_gate_passed: bool
    product_quality_claim: bool
    limitation: str


def _entry(
    kind: ContextEntryKind,
    content: str,
    *,
    case_id: str,
    evidence_ordinal: int | None = None,
) -> ContextEntry:
    protected = evidence_ordinal is None
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    return ContextEntry(
        kind=kind,
        content=content,
        estimated_tokens=estimate_tokens(content),
        protected=protected,
        requirement_id=(
            RequirementId(f"requirement-{case_id}")
            if kind in {ContextEntryKind.REQUIREMENT, ContextEntryKind.EVIDENCE}
            else None
        ),
        evidence_id=(
            EvidenceItemId(f"evidence-{case_id}-{evidence_ordinal}")
            if evidence_ordinal is not None
            else None
        ),
        evidence_version_id=(
            EvidenceVersionId(f"evidence-version-{case_id}-{evidence_ordinal}")
            if evidence_ordinal is not None
            else None
        ),
        evidence_chunk_id=(
            EvidenceChunkId(f"evidence-chunk-{case_id}-{evidence_ordinal}")
            if evidence_ordinal is not None
            else None
        ),
        redaction=ContextRedaction.NONE,
        content_hash=content_hash,
        inclusion_reason=(
            ContextInclusionReason.REQUIRED_PROTECTED
            if protected
            else ContextInclusionReason.RETRIEVAL_HIT
        ),
    )


def _package(case: RuntimeContextCase) -> ContextPackage:
    entries = (
        _entry(ContextEntryKind.REQUIREMENT, case.protected[0], case_id=case.case_id),
        _entry(ContextEntryKind.INSTRUCTION, case.protected[1], case_id=case.case_id),
        _entry(ContextEntryKind.WORKFLOW, case.protected[2], case_id=case.case_id),
        _entry(ContextEntryKind.PROFILE, case.protected[3], case_id=case.case_id),
        *(
            _entry(
                ContextEntryKind.EVIDENCE,
                content,
                case_id=case.case_id,
                evidence_ordinal=ordinal,
            )
            for ordinal, content in enumerate(case.evidence, start=1)
        ),
    )
    return ContextPackage(
        context_package_id=ContextPackageId(f"context-package-{case.case_id}"),
        job_version_id=JobVersionId(f"job-version-{case.case_id}"),
        requirement_ids=(RequirementId(f"requirement-{case.case_id}"),),
        retrieval_run_id=RetrievalRunId(f"retrieval-run-{case.case_id}"),
        candidate_profile_id=CandidateProfileId(f"profile-{case.case_id}"),
        entries=entries,
        builder_version="context-builder-v1",
        redaction_policy_version="context-redaction-v1",
        token_estimator_version=TOKEN_ESTIMATOR_VERSION,
        packaging_overhead_tokens=3,
        total_estimated_tokens=3 + sum(entry.estimated_tokens for entry in entries),
        max_tokens=1_000_000,
        created_at=_FIXTURE_TIME,
        correlation_id=CorrelationId(f"correlation-{case.case_id}"),
        run_id=RunId(f"run-{case.case_id}"),
    )


def run_runtime_context_evaluation(
    dataset: RuntimeContextDataset,
) -> RuntimeContextEvaluationReport:
    policy = RuntimeContextPolicy()
    if dataset.policy_version != policy.version or not dataset.synthetic_fixture:
        raise ValueError("runtime-context evaluation dataset manifest is invalid")
    protected_loss = 0
    rehydrated = 0
    reference_count = 0
    provenance_correct = 0
    representation_count = 0
    unsupported = 0
    silent_truncation = 0
    source_tokens = 0
    runtime_tokens = 0
    source_evidence = 0
    covered_evidence = 0
    for index, case in enumerate(dataset.cases, start=1):
        package = _package(case)
        plan = policy.compact(
            package,
            runtime_context_id=RuntimeContextId(f"runtime-context-{case.case_id}"),
            max_tokens=case.max_tokens,
            created_at=_FIXTURE_TIME,
            correlation_id=CorrelationId(f"correlation-runtime-{index}"),
            run_id=RunId(f"run-runtime-{index}"),
        )
        artifact_store = InMemoryArtifactStore()
        artifacts = {item.reference.reference_id: item for item in plan.artifacts}
        for item in plan.artifacts:
            artifact_store.write(item.record, item.content)
        source_tokens += package.total_estimated_tokens
        runtime_tokens += plan.snapshot.total_estimated_tokens
        protected_loss += sum(
            1
            for ordinal, entry in enumerate(package.entries, start=1)
            if entry.protected and ordinal not in plan.snapshot.covered_source_ordinals
        )
        silent_truncation += int(
            plan.snapshot.covered_source_ordinals != tuple(range(1, len(package.entries) + 1))
        )
        source_evidence += sum(not entry.protected for entry in package.entries)
        covered_evidence += sum(
            not package.entries[ordinal - 1].protected
            for ordinal in plan.snapshot.covered_source_ordinals
        )
        for entry in plan.snapshot.entries:
            representation_count += 1
            sources = tuple(package.entries[item - 1] for item in entry.source_ordinals)
            if all(source.kind is entry.kind for source in sources):
                provenance_correct += 1
            matching = tuple(
                source for source in sources if source.content_hash == entry.content_hash
            )
            if not matching:
                unsupported += 1
            if entry.reference_id is not None:
                reference_count += 1
                planned = artifacts.get(entry.reference_id)
                if planned is not None and artifact_store.read(planned.record) == planned.content:
                    rehydrated += 1
    token_reduction = 1.0 - runtime_tokens / source_tokens if source_tokens else 0.0
    evidence_lineage_coverage = covered_evidence / source_evidence if source_evidence else 1.0
    rehydration_accuracy = rehydrated / reference_count if reference_count else 1.0
    provenance_accuracy = provenance_correct / representation_count if representation_count else 1.0
    gate = (
        protected_loss == 0
        and rehydration_accuracy == 1.0
        and provenance_accuracy == 1.0
        and unsupported == 0
        and silent_truncation == 0
        and token_reduction >= 0.25
        and evidence_lineage_coverage == 1.0
    )
    return RuntimeContextEvaluationReport(
        dataset_version=dataset.dataset_version,
        policy_version=dataset.policy_version,
        case_count=len(dataset.cases),
        protected_loss_count=protected_loss,
        reference_rehydration_accuracy=rehydration_accuracy,
        provenance_accuracy=provenance_accuracy,
        unsupported_fact_count=unsupported,
        silent_truncation_count=silent_truncation,
        source_estimated_tokens=source_tokens,
        runtime_estimated_tokens=runtime_tokens,
        token_reduction=token_reduction,
        evidence_lineage_coverage=evidence_lineage_coverage,
        effective_evidence_recall_degradation=None,
        workflow_completion_degradation=None,
        mechanics_gate_passed=gate,
        product_quality_claim=False,
        limitation=(
            "Synthetic fixtures validate deterministic runtime-context mechanics only; "
            "they do not evaluate downstream model or workflow quality."
        ),
    )
