from datetime import UTC, date, datetime

from job_hunter.domain.ids import (
    EvidenceChunkId,
    EvidenceItemId,
    EvidenceVersionId,
    RequirementId,
)
from job_hunter.domain.knowledge import (
    EvidenceItemVersion,
    EvidenceSensitivity,
    EvidenceType,
    EvidenceValidity,
)
from job_hunter.domain.retrieval import (
    RetrievalHit,
    RetrievalMatchReason,
    RetrievalQuery,
    RetrievalStatus,
    RetrievalStrategy,
    RetrievalTaskType,
    RetrieverResult,
)
from job_hunter.infrastructure.retrieval import HybridRetriever, estimate_tokens

NOW = datetime(2026, 8, 31, 18, 0, tzinfo=UTC)


def _evidence(identifier: str, content: str) -> EvidenceItemVersion:
    from job_hunter.domain.ids import CorrelationId, RunId

    return EvidenceItemVersion(
        version_id=EvidenceVersionId(f"{identifier}-version"),
        evidence_id=EvidenceItemId(identifier),
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


class _RankedRetriever:
    def __init__(
        self,
        strategy: RetrievalStrategy,
        ordering: tuple[EvidenceItemId, ...],
        reason: RetrievalMatchReason,
    ) -> None:
        self._strategy = strategy
        self._ordering = ordering
        self._reason = reason

    @property
    def strategy(self) -> RetrievalStrategy:
        return self._strategy

    @property
    def version(self) -> str:
        return f"{self._strategy.value}-test-v1"

    @property
    def token_estimator_version(self) -> str:
        return "deterministic-token-estimator-v1"

    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> RetrieverResult:
        del query
        by_id = {item.evidence_id: item for item in evidence}
        hits = tuple(
            RetrievalHit(
                evidence_id=evidence_id,
                evidence_version_id=by_id[evidence_id].version_id,
                rank=rank,
                score=float(len(self._ordering) - rank + 1),
                reasons=(self._reason,),
                evidence_chunk_ids=(
                    (EvidenceChunkId(f"chunk-{evidence_id}"),)
                    if self._strategy is RetrievalStrategy.SEMANTIC
                    else ()
                ),
            )
            for rank, evidence_id in enumerate(self._ordering, start=1)
        )
        return RetrieverResult(
            status=RetrievalStatus.COMPLETED,
            hits=hits,
            eligible_count=len(evidence),
            eligible_estimated_tokens=sum(
                estimate_tokens(item.canonical_content) for item in evidence
            ),
            selected_estimated_tokens=sum(
                estimate_tokens(by_id[item].canonical_content) for item in self._ordering
            ),
        )


def test_hybrid_rrf_fuses_independent_ranks_with_stable_lineage() -> None:
    alpha = _evidence("alpha", "alpha " * 10)
    beta = _evidence("beta", "beta " * 10)
    gamma = _evidence("gamma", "gamma " * 10)
    lexical = _RankedRetriever(
        RetrievalStrategy.LEXICAL_METADATA,
        (alpha.evidence_id, beta.evidence_id),
        RetrievalMatchReason.TOKEN_OVERLAP,
    )
    semantic = _RankedRetriever(
        RetrievalStrategy.SEMANTIC,
        (beta.evidence_id, gamma.evidence_id),
        RetrievalMatchReason.SEMANTIC_SIMILARITY,
    )
    hybrid = HybridRetriever(lexical=lexical, semantic=semantic)

    result = hybrid.retrieve(
        RetrievalQuery(
            requirement_id=RequirementId("requirement-1"),
            text="cross-functional leadership",
            task_type=RetrievalTaskType.DEEP_FIT,
            max_tokens=25,
            top_k=2,
        ),
        (gamma, alpha, beta),
    )

    assert hybrid.strategy is RetrievalStrategy.HYBRID
    assert hybrid.version == "hybrid-rrf-v1"
    assert result.status is RetrievalStatus.COMPLETED
    assert tuple(hit.evidence_id for hit in result.hits) == (
        beta.evidence_id,
        alpha.evidence_id,
    )
    assert result.hits[0].reasons == (
        RetrievalMatchReason.TOKEN_OVERLAP,
        RetrievalMatchReason.SEMANTIC_SIMILARITY,
        RetrievalMatchReason.HYBRID_FUSION,
    )
    assert result.selected_estimated_tokens == 20
    assert result.hits[0].evidence_chunk_ids == (EvidenceChunkId("chunk-beta"),)
