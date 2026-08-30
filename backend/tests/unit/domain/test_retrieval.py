from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime

import pytest

from job_hunter.domain.ids import (
    CorrelationId,
    EvidenceItemId,
    EvidenceVersionId,
    JobVersionId,
    RequirementId,
    RetrievalRunId,
    RunId,
)
from job_hunter.domain.knowledge import (
    EvidenceItemVersion,
    EvidenceSensitivity,
    EvidenceType,
    EvidenceValidity,
)
from job_hunter.domain.retrieval import (
    EvidenceEligibilityPolicy,
    EvidenceExclusion,
    EvidenceExclusionReason,
    RetrievalHit,
    RetrievalMatchReason,
    RetrievalRun,
    RetrievalStatus,
    RetrievalStrategy,
)
from job_hunter.errors import InputValidationError

NOW = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)


def _evidence(
    identifier: str,
    *,
    sensitivity: EvidenceSensitivity = EvidenceSensitivity.PUBLIC,
    validity: EvidenceValidity = EvidenceValidity.VALID,
) -> EvidenceItemVersion:
    return EvidenceItemVersion(
        version_id=EvidenceVersionId(f"{identifier}-version"),
        evidence_id=EvidenceItemId(identifier),
        version_number=1,
        evidence_type=EvidenceType.PROJECT,
        canonical_content=f"Evidence content for {identifier}",
        occurred_on=date(2026, 1, 1),
        source="manual",
        provenance="human-confirmed fixture",
        sensitivity=sensitivity,
        validity=validity,
        created_at=NOW,
        correlation_id=CorrelationId("correlation-evidence"),
        run_id=RunId("run-evidence"),
    )


def test_eligibility_requires_validity_and_explicit_sensitivity_permission() -> None:
    result = EvidenceEligibilityPolicy().evaluate(
        (
            _evidence("public"),
            _evidence("private", sensitivity=EvidenceSensitivity.PRIVATE),
            _evidence("sensitive", sensitivity=EvidenceSensitivity.SENSITIVE),
            _evidence("expired", validity=EvidenceValidity.EXPIRED),
            _evidence("revoked", validity=EvidenceValidity.REVOKED),
        ),
        allowed_sensitivities=(
            EvidenceSensitivity.PUBLIC,
            EvidenceSensitivity.PRIVATE,
        ),
    )

    assert tuple(item.evidence_id for item in result.eligible) == (
        EvidenceItemId("private"),
        EvidenceItemId("public"),
    )
    assert {item.evidence_id: item.reason for item in result.exclusions} == {
        EvidenceItemId("expired"): EvidenceExclusionReason.INVALID,
        EvidenceItemId("revoked"): EvidenceExclusionReason.INVALID,
        EvidenceItemId("sensitive"): EvidenceExclusionReason.SENSITIVITY_NOT_ALLOWED,
    }


def test_retrieval_run_is_immutable_and_rejects_non_contiguous_ranks() -> None:
    hit = RetrievalHit(
        evidence_id=EvidenceItemId("evidence-1"),
        evidence_version_id=EvidenceVersionId("evidence-version-1"),
        rank=1,
        score=2.0,
        reasons=(RetrievalMatchReason.TOKEN_OVERLAP,),
    )
    run = RetrievalRun(
        retrieval_run_id=RetrievalRunId("retrieval-run-1"),
        requirement_id=RequirementId("requirement-1"),
        job_version_id=JobVersionId("job-version-1"),
        strategy=RetrievalStrategy.LEXICAL_METADATA,
        retriever_version="lexical-metadata-v1",
        eligibility_policy_version="evidence-eligibility-v1",
        token_estimator_version="deterministic-token-estimator-v1",
        status=RetrievalStatus.COMPLETED,
        hits=(hit,),
        exclusions=(),
        eligible_count=1,
        eligible_estimated_tokens=5,
        selected_estimated_tokens=5,
        max_tokens=100,
        top_k=5,
        created_at=NOW,
        correlation_id=CorrelationId("correlation-retrieval"),
        run_id=RunId("run-retrieval"),
    )

    with pytest.raises(FrozenInstanceError):
        run.status = RetrievalStatus.NO_RELEVANT_EVIDENCE  # type: ignore[misc]

    with pytest.raises(InputValidationError, match="ranks must be contiguous"):
        RetrievalRun(
            retrieval_run_id=run.retrieval_run_id,
            requirement_id=run.requirement_id,
            job_version_id=run.job_version_id,
            strategy=run.strategy,
            retriever_version=run.retriever_version,
            eligibility_policy_version=run.eligibility_policy_version,
            token_estimator_version=run.token_estimator_version,
            status=run.status,
            hits=(
                RetrievalHit(
                    evidence_id=hit.evidence_id,
                    evidence_version_id=hit.evidence_version_id,
                    rank=2,
                    score=hit.score,
                    reasons=hit.reasons,
                ),
            ),
            exclusions=(),
            eligible_count=1,
            eligible_estimated_tokens=5,
            selected_estimated_tokens=5,
            max_tokens=100,
            top_k=5,
            created_at=NOW,
            correlation_id=run.correlation_id,
            run_id=run.run_id,
        )


def test_retrieval_run_rejects_hit_and_exclusion_lineage_overlap() -> None:
    hit = RetrievalHit(
        evidence_id=EvidenceItemId("evidence-1"),
        evidence_version_id=EvidenceVersionId("evidence-version-1"),
        rank=1,
        score=1.0,
        reasons=(RetrievalMatchReason.FULL_CONTEXT,),
    )

    with pytest.raises(InputValidationError, match="both hit and excluded"):
        RetrievalRun(
            retrieval_run_id=RetrievalRunId("retrieval-run-1"),
            requirement_id=RequirementId("requirement-1"),
            job_version_id=JobVersionId("job-version-1"),
            strategy=RetrievalStrategy.FULL_CONTEXT,
            retriever_version="full-context-v1",
            eligibility_policy_version="evidence-eligibility-v1",
            token_estimator_version="deterministic-token-estimator-v1",
            status=RetrievalStatus.COMPLETED,
            hits=(hit,),
            exclusions=(
                EvidenceExclusion(
                    evidence_id=hit.evidence_id,
                    evidence_version_id=hit.evidence_version_id,
                    reason=EvidenceExclusionReason.INVALID,
                ),
            ),
            eligible_count=1,
            eligible_estimated_tokens=5,
            selected_estimated_tokens=5,
            max_tokens=100,
            top_k=5,
            created_at=NOW,
            correlation_id=CorrelationId("correlation-retrieval"),
            run_id=RunId("run-retrieval"),
        )


def test_full_context_run_rejects_incomplete_completed_result() -> None:
    hit = RetrievalHit(
        evidence_id=EvidenceItemId("evidence-1"),
        evidence_version_id=EvidenceVersionId("evidence-version-1"),
        rank=1,
        score=1.0,
        reasons=(RetrievalMatchReason.FULL_CONTEXT,),
    )

    with pytest.raises(InputValidationError, match="all eligible Evidence"):
        RetrievalRun(
            retrieval_run_id=RetrievalRunId("retrieval-run-1"),
            requirement_id=RequirementId("requirement-1"),
            job_version_id=JobVersionId("job-version-1"),
            strategy=RetrievalStrategy.FULL_CONTEXT,
            retriever_version="full-context-v1",
            eligibility_policy_version="evidence-eligibility-v1",
            token_estimator_version="deterministic-token-estimator-v1",
            status=RetrievalStatus.COMPLETED,
            hits=(hit,),
            exclusions=(),
            eligible_count=2,
            eligible_estimated_tokens=10,
            selected_estimated_tokens=5,
            max_tokens=100,
            top_k=5,
            created_at=NOW,
            correlation_id=CorrelationId("correlation-retrieval"),
            run_id=RunId("run-retrieval"),
        )


@pytest.mark.parametrize(
    ("status", "eligible_count", "eligible_tokens", "selected_tokens"),
    (
        (RetrievalStatus.NO_RELEVANT_EVIDENCE, 1, 5, 0),
        (RetrievalStatus.NOT_EXECUTABLE, 1, 5, 0),
        (RetrievalStatus.COMPLETED, 1, 101, 101),
    ),
)
def test_full_context_run_rejects_inconsistent_status_and_budget(
    status: RetrievalStatus,
    eligible_count: int,
    eligible_tokens: int,
    selected_tokens: int,
) -> None:
    hits = (
        (
            RetrievalHit(
                evidence_id=EvidenceItemId("evidence-1"),
                evidence_version_id=EvidenceVersionId("evidence-version-1"),
                rank=1,
                score=1.0,
                reasons=(RetrievalMatchReason.FULL_CONTEXT,),
            ),
        )
        if status is RetrievalStatus.COMPLETED
        else ()
    )

    with pytest.raises(InputValidationError, match="Full Context|exceeds max_tokens"):
        RetrievalRun(
            retrieval_run_id=RetrievalRunId("retrieval-run-1"),
            requirement_id=RequirementId("requirement-1"),
            job_version_id=JobVersionId("job-version-1"),
            strategy=RetrievalStrategy.FULL_CONTEXT,
            retriever_version="full-context-v1",
            eligibility_policy_version="evidence-eligibility-v1",
            token_estimator_version="deterministic-token-estimator-v1",
            status=status,
            hits=hits,
            exclusions=(),
            eligible_count=eligible_count,
            eligible_estimated_tokens=eligible_tokens,
            selected_estimated_tokens=selected_tokens,
            max_tokens=100,
            top_k=5,
            created_at=NOW,
            correlation_id=CorrelationId("correlation-retrieval"),
            run_id=RunId("run-retrieval"),
        )
