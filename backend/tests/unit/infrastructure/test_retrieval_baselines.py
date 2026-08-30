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
    RetrievalMatchReason,
    RetrievalQuery,
    RetrievalStatus,
    RetrievalStrategy,
    RetrievalTaskType,
)
from job_hunter.infrastructure.retrieval import FullContextRetriever, LexicalMetadataRetriever

NOW = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)


def _evidence(
    identifier: str,
    content: str,
    *,
    evidence_type: EvidenceType = EvidenceType.PROJECT,
) -> EvidenceItemVersion:
    return EvidenceItemVersion(
        version_id=EvidenceVersionId(f"{identifier}-version"),
        evidence_id=EvidenceItemId(identifier),
        version_number=1,
        evidence_type=evidence_type,
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


def _query(*, text: str = "Python evaluation pipeline", max_tokens: int = 100) -> RetrievalQuery:
    return RetrievalQuery(
        requirement_id=RequirementId("requirement-1"),
        text=text,
        task_type=RetrievalTaskType.DEEP_FIT,
        max_tokens=max_tokens,
        top_k=2,
    )


def test_full_context_returns_every_eligible_item_in_stable_order() -> None:
    retriever = FullContextRetriever()

    result = retriever.retrieve(
        _query(),
        (
            _evidence("evidence-2", "Built a Java service"),
            _evidence("evidence-1", "Built a Python evaluation pipeline"),
        ),
    )

    assert retriever.strategy is RetrievalStrategy.FULL_CONTEXT
    assert retriever.version == "full-context-v1"
    assert result.status is RetrievalStatus.COMPLETED
    assert tuple(hit.evidence_id for hit in result.hits) == (
        EvidenceItemId("evidence-1"),
        EvidenceItemId("evidence-2"),
    )
    assert tuple(hit.rank for hit in result.hits) == (1, 2)
    assert all(hit.reasons == (RetrievalMatchReason.FULL_CONTEXT,) for hit in result.hits)
    assert result.selected_estimated_tokens == result.eligible_estimated_tokens
    assert result.selected_estimated_tokens <= 100


def test_full_context_fails_explicitly_instead_of_truncating() -> None:
    result = FullContextRetriever().retrieve(
        _query(max_tokens=1),
        (_evidence("evidence-1", "Built a Python evaluation pipeline"),),
    )

    assert result.status is RetrievalStatus.NOT_EXECUTABLE
    assert result.hits == ()
    assert result.eligible_count == 1
    assert result.eligible_estimated_tokens > 1
    assert result.selected_estimated_tokens == 0


def test_lexical_metadata_ranks_signal_and_uses_stable_id_ties() -> None:
    result = LexicalMetadataRetriever().retrieve(
        _query(text="Python evaluation"),
        (
            _evidence("evidence-3", "Operated Kubernetes clusters"),
            _evidence("evidence-2", "Python service"),
            _evidence("evidence-1", "Python service"),
            _evidence("evidence-0", "Built a Python evaluation platform"),
        ),
    )

    assert result.status is RetrievalStatus.COMPLETED
    assert tuple(hit.evidence_id for hit in result.hits) == (
        EvidenceItemId("evidence-0"),
        EvidenceItemId("evidence-1"),
    )
    assert RetrievalMatchReason.TOKEN_OVERLAP in result.hits[0].reasons


def test_lexical_metadata_returns_explicit_no_evidence_for_zero_signal() -> None:
    result = LexicalMetadataRetriever().retrieve(
        _query(text="Rust compiler"),
        (_evidence("evidence-1", "Designed marketing campaigns"),),
    )

    assert result.status is RetrievalStatus.NO_RELEVANT_EVIDENCE
    assert result.hits == ()
    assert result.selected_estimated_tokens == 0


def test_lexical_metadata_applies_token_budget_to_ranked_prefix() -> None:
    result = LexicalMetadataRetriever().retrieve(
        _query(text="Python", max_tokens=4),
        (
            _evidence("evidence-2", "Python service delivery"),
            _evidence("evidence-1", "Python platform"),
        ),
    )

    assert result.status is RetrievalStatus.COMPLETED
    assert tuple(hit.evidence_id for hit in result.hits) == (EvidenceItemId("evidence-1"),)
    assert result.selected_estimated_tokens == 2
    assert result.eligible_estimated_tokens == 5
    assert result.selected_estimated_tokens <= 4


def test_lexical_metadata_is_not_executable_when_top_hit_exceeds_budget() -> None:
    result = LexicalMetadataRetriever().retrieve(
        _query(text="Python", max_tokens=1),
        (_evidence("evidence-1", "Python platform"),),
    )

    assert result.status is RetrievalStatus.NOT_EXECUTABLE
    assert result.hits == ()
    assert result.eligible_estimated_tokens == 2
    assert result.selected_estimated_tokens == 0
