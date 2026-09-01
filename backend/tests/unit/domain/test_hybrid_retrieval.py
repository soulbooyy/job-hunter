from datetime import UTC, date, datetime

from job_hunter.domain.ids import (
    CorrelationId,
    EvidenceItemId,
    EvidenceVersionId,
    RequirementId,
    RunId,
)
from job_hunter.domain.knowledge import (
    EvidenceItemVersion,
    EvidenceSensitivity,
    EvidenceType,
    EvidenceValidity,
)
from job_hunter.domain.retrieval import (
    EVIDENCE_CHUNK_POLICY_VERSION,
    DeterministicEvidenceChunker,
    RetrievalFallbackReason,
    RetrievalPolicy,
    RetrievalPolicyInput,
    RetrievalPolicyReason,
    RetrievalPromotionEvidence,
    RetrievalStrategy,
)

NOW = datetime(2026, 8, 31, 18, 0, tzinfo=UTC)


def _evidence(content: str) -> EvidenceItemVersion:
    return EvidenceItemVersion(
        version_id=EvidenceVersionId("evidence-version-1"),
        evidence_id=EvidenceItemId("evidence-1"),
        version_number=1,
        evidence_type=EvidenceType.PROJECT,
        canonical_content=content,
        occurred_on=date(2026, 1, 1),
        source="manual",
        provenance="human-confirmed fixture",
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.VALID,
        created_at=NOW,
        correlation_id=CorrelationId("correlation-evidence"),
        run_id=RunId("run-evidence"),
    )


def test_evidence_chunking_is_versioned_bounded_overlapping_and_stable() -> None:
    evidence = _evidence(" ".join(f"token{index}" for index in range(400)))
    chunker = DeterministicEvidenceChunker()

    first = chunker.chunk((evidence,))
    second = chunker.chunk((evidence,))

    assert first == second
    assert len(first) == 3
    assert all(chunk.policy_version == EVIDENCE_CHUNK_POLICY_VERSION for chunk in first)
    assert all(chunk.estimated_tokens <= 192 for chunk in first)
    assert len({chunk.chunk_id for chunk in first}) == len(first)
    assert first[0].tokens[-32:] == first[1].tokens[:32]
    assert first[1].tokens[-32:] == first[2].tokens[:32]
    assert all(chunk.evidence_version_id == evidence.version_id for chunk in first)


def test_retrieval_policy_uses_fixed_precedence_and_explicit_fallback() -> None:
    policy = RetrievalPolicy()
    small = policy.decide(
        RetrievalPolicyInput(
            requirement_id=RequirementId("requirement-small"),
            query_text="semantic leadership experience",
            eligible_count=4,
            eligible_estimated_tokens=900,
            max_tokens=2_000,
            hybrid_promoted=True,
            semantic_ready=True,
            promotion_dataset_version="holdout-v1",
        )
    )
    precise = policy.decide(
        RetrievalPolicyInput(
            requirement_id=RequirementId("requirement-precise"),
            query_text="AWS Solutions Architect certification",
            eligible_count=20,
            eligible_estimated_tokens=4_000,
            max_tokens=1_000,
            hybrid_promoted=True,
            semantic_ready=True,
            promotion_dataset_version="holdout-v1",
        )
    )
    experimental = policy.decide(
        RetrievalPolicyInput(
            requirement_id=RequirementId("requirement-semantic"),
            query_text="led ambiguous cross-functional delivery",
            eligible_count=20,
            eligible_estimated_tokens=4_000,
            max_tokens=1_000,
            hybrid_promoted=False,
            semantic_ready=True,
            promotion_dataset_version="holdout-v1",
        )
    )

    assert small.selected_strategy is RetrievalStrategy.FULL_CONTEXT
    assert small.reason is RetrievalPolicyReason.SMALL_ELIGIBLE_CONTEXT
    assert small.fallback_reason is None
    assert precise.selected_strategy is RetrievalStrategy.LEXICAL_METADATA
    assert precise.reason is RetrievalPolicyReason.PRECISE_LOOKUP
    assert experimental.initial_strategy is RetrievalStrategy.HYBRID
    assert experimental.selected_strategy is RetrievalStrategy.LEXICAL_METADATA
    assert experimental.reason is RetrievalPolicyReason.SEMANTIC_MATCH
    assert experimental.fallback_reason is RetrievalFallbackReason.HYBRID_NOT_PROMOTED


def test_hybrid_promotion_requires_exact_human_reviewed_holdout_gates() -> None:
    synthetic = RetrievalPromotionEvidence(
        dataset_version="hybrid-synthetic-v1",
        split="synthetic",
        human_reviewed=False,
        minimum_dataset_gate=True,
        recall_at_5=1.0,
        direct_mrr=0.925,
        no_evidence_accuracy=1.0,
        no_evidence_total=5,
        final_context_token_reduction=0.46,
        large_context_case_count=10,
        large_context_no_evidence_count=2,
        recall_degradation=0.0,
        no_evidence_degradation=0.0,
    )

    assert not synthetic.promoted
