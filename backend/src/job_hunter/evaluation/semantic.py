"""Local-model semantic evaluation adapter; never used as an authoritative index."""

from job_hunter.application.ports import EmbeddingProvider
from job_hunter.domain.knowledge import EvidenceItemVersion
from job_hunter.domain.retrieval import (
    SEMANTIC_CHROMA_V1_MAX_COSINE_DISTANCE,
    RetrievalHit,
    RetrievalMatchReason,
    RetrievalQuery,
    RetrievalStatus,
    RetrievalStrategy,
    RetrieverResult,
    estimate_tokens,
)


def _cosine_distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 1.0
    return max(0.0, 1.0 - dot / (left_norm * right_norm))


class LocalModelEvaluationRetriever:
    def __init__(self, embedding_provider: EmbeddingProvider) -> None:
        self._embedding_provider = embedding_provider

    @property
    def strategy(self) -> RetrievalStrategy:
        return RetrievalStrategy.SEMANTIC

    @property
    def version(self) -> str:
        return f"evaluation-{self._embedding_provider.version}"

    @property
    def token_estimator_version(self) -> str:
        return "deterministic-token-estimator-v1"

    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> RetrieverResult:
        eligible_tokens = sum(estimate_tokens(item.canonical_content) for item in evidence)
        if not evidence:
            return RetrieverResult(
                status=RetrievalStatus.NO_RELEVANT_EVIDENCE,
                hits=(),
                eligible_count=0,
                eligible_estimated_tokens=0,
                selected_estimated_tokens=0,
            )
        vectors = self._embedding_provider.embed(
            (query.text, *(item.canonical_content for item in evidence))
        )
        query_vector = vectors[0]
        candidates = sorted(
            (
                (_cosine_distance(query_vector, vector), item)
                for item, vector in zip(evidence, vectors[1:], strict=True)
                if _cosine_distance(query_vector, vector) <= SEMANTIC_CHROMA_V1_MAX_COSINE_DISTANCE
            ),
            key=lambda value: (
                value[0],
                str(value[1].evidence_id),
                str(value[1].version_id),
            ),
        )
        selected: list[tuple[float, EvidenceItemVersion]] = []
        selected_tokens = 0
        for distance, item in candidates[: query.top_k]:
            item_tokens = estimate_tokens(item.canonical_content)
            if selected_tokens + item_tokens > query.max_tokens:
                break
            selected.append((distance, item))
            selected_tokens += item_tokens
        hits = tuple(
            RetrievalHit(
                evidence_id=item.evidence_id,
                evidence_version_id=item.version_id,
                rank=rank,
                score=max(0.0, 1.0 - distance),
                reasons=(RetrievalMatchReason.SEMANTIC_SIMILARITY,),
            )
            for rank, (distance, item) in enumerate(selected, start=1)
        )
        return RetrieverResult(
            status=(
                RetrievalStatus.COMPLETED
                if hits
                else (
                    RetrievalStatus.NOT_EXECUTABLE
                    if candidates
                    else RetrievalStatus.NO_RELEVANT_EVIDENCE
                )
            ),
            hits=hits,
            eligible_count=len(evidence),
            eligible_estimated_tokens=eligible_tokens,
            selected_estimated_tokens=selected_tokens,
        )
