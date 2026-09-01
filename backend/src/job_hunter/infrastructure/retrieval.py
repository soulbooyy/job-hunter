"""Deterministic retrieval adapters that require no external services."""

import re

from job_hunter.application.ports import EvidenceRetriever
from job_hunter.domain.ids import EvidenceChunkId, EvidenceItemId
from job_hunter.domain.knowledge import EvidenceItemVersion
from job_hunter.domain.retrieval import (
    TOKEN_ESTIMATOR_VERSION,
    RetrievalHit,
    RetrievalMatchReason,
    RetrievalQuery,
    RetrievalStatus,
    RetrievalStrategy,
    RetrieverResult,
    estimate_tokens,
)
from job_hunter.errors import DependencyUnavailableError

_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def _estimated_evidence_tokens(evidence: tuple[EvidenceItemVersion, ...]) -> int:
    return sum(estimate_tokens(item.canonical_content) for item in evidence)


class FullContextRetriever:
    @property
    def strategy(self) -> RetrievalStrategy:
        return RetrievalStrategy.FULL_CONTEXT

    @property
    def version(self) -> str:
        return "full-context-v1"

    @property
    def token_estimator_version(self) -> str:
        return TOKEN_ESTIMATOR_VERSION

    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> RetrieverResult:
        ordered = tuple(
            sorted(evidence, key=lambda item: (str(item.evidence_id), str(item.version_id)))
        )
        eligible_estimated_tokens = _estimated_evidence_tokens(ordered)
        if not ordered:
            status = RetrievalStatus.NO_RELEVANT_EVIDENCE
            hits: tuple[RetrievalHit, ...] = ()
        elif eligible_estimated_tokens > query.max_tokens:
            # Full Context means all eligible Evidence. Returning no hits preserves
            # that semantic instead of silently turning a budget failure into top-k.
            status = RetrievalStatus.NOT_EXECUTABLE
            hits = ()
        else:
            status = RetrievalStatus.COMPLETED
            hits = tuple(
                RetrievalHit(
                    evidence_id=item.evidence_id,
                    evidence_version_id=item.version_id,
                    rank=index,
                    score=1.0,
                    reasons=(RetrievalMatchReason.FULL_CONTEXT,),
                )
                for index, item in enumerate(ordered, start=1)
            )
        selected_estimated_tokens = (
            eligible_estimated_tokens if status is RetrievalStatus.COMPLETED else 0
        )
        return RetrieverResult(
            status=status,
            hits=hits,
            eligible_count=len(ordered),
            eligible_estimated_tokens=eligible_estimated_tokens,
            selected_estimated_tokens=selected_estimated_tokens,
        )


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _word_tokens(value: str) -> set[str]:
    return {token for token in _TOKEN_PATTERN.findall(value.casefold()) if token.isalnum()}


class LexicalMetadataRetriever:
    @property
    def strategy(self) -> RetrievalStrategy:
        return RetrievalStrategy.LEXICAL_METADATA

    @property
    def version(self) -> str:
        return "lexical-metadata-v1"

    @property
    def token_estimator_version(self) -> str:
        return TOKEN_ESTIMATOR_VERSION

    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> RetrieverResult:
        query_text = _normalized(query.text)
        query_tokens = _word_tokens(query.text)
        eligible_estimated_tokens = _estimated_evidence_tokens(evidence)
        candidates: list[
            tuple[float, tuple[RetrievalMatchReason, ...], EvidenceItemVersion, int]
        ] = []
        for item in evidence:
            content = _normalized(item.canonical_content)
            content_overlap = query_tokens & _word_tokens(item.canonical_content)
            metadata_overlap = query_tokens & _word_tokens(
                f"{item.evidence_type.value} {item.source}"
            )
            reasons: list[RetrievalMatchReason] = []
            score = 0.0
            if query_text in content:
                score += 4.0
                reasons.append(RetrievalMatchReason.EXACT_PHRASE)
            if content_overlap:
                score += float(len(content_overlap))
                reasons.append(RetrievalMatchReason.TOKEN_OVERLAP)
            if metadata_overlap:
                score += float(len(metadata_overlap)) * 0.5
                reasons.append(RetrievalMatchReason.METADATA_OVERLAP)
            if score > 0:
                candidates.append(
                    (score, tuple(reasons), item, estimate_tokens(item.canonical_content))
                )
        candidates.sort(
            key=lambda candidate: (
                -candidate[0],
                str(candidate[2].evidence_id),
                str(candidate[2].version_id),
            )
        )
        selected: list[
            tuple[float, tuple[RetrievalMatchReason, ...], EvidenceItemVersion, int]
        ] = []
        selected_estimated_tokens = 0
        for candidate in candidates[: query.top_k]:
            candidate_tokens = candidate[3]
            if selected_estimated_tokens + candidate_tokens > query.max_tokens:
                # Selection is a stable ranked prefix: do not skip a stronger
                # oversized candidate to admit weaker Evidence behind it.
                break
            selected.append(candidate)
            selected_estimated_tokens += candidate_tokens
        hits = tuple(
            RetrievalHit(
                evidence_id=item.evidence_id,
                evidence_version_id=item.version_id,
                rank=index,
                score=score,
                reasons=reasons,
            )
            for index, (score, reasons, item, _tokens) in enumerate(selected, start=1)
        )
        if hits:
            status = RetrievalStatus.COMPLETED
        elif candidates:
            status = RetrievalStatus.NOT_EXECUTABLE
        else:
            status = RetrievalStatus.NO_RELEVANT_EVIDENCE
        return RetrieverResult(
            status=status,
            hits=hits,
            eligible_count=len(evidence),
            eligible_estimated_tokens=eligible_estimated_tokens,
            selected_estimated_tokens=selected_estimated_tokens,
        )


class HybridRetriever:
    """Fuse lexical and semantic ranks without trusting either score scale."""

    _rrf_constant = 60

    def __init__(self, *, lexical: EvidenceRetriever, semantic: EvidenceRetriever) -> None:
        if lexical.strategy is not RetrievalStrategy.LEXICAL_METADATA:
            raise ValueError("Hybrid lexical retriever has the wrong strategy")
        if semantic.strategy is not RetrievalStrategy.SEMANTIC:
            raise ValueError("Hybrid semantic retriever has the wrong strategy")
        self._lexical = lexical
        self._semantic = semantic

    @property
    def strategy(self) -> RetrievalStrategy:
        return RetrievalStrategy.HYBRID

    @property
    def version(self) -> str:
        return "hybrid-rrf-v1"

    @property
    def token_estimator_version(self) -> str:
        return TOKEN_ESTIMATOR_VERSION

    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> RetrieverResult:
        source_results = (
            self._lexical.retrieve(query, evidence),
            self._semantic.retrieve(query, evidence),
        )
        by_id = {item.evidence_id: item for item in evidence}
        scores: dict[EvidenceItemId, float] = {}
        reasons: dict[EvidenceItemId, list[RetrievalMatchReason]] = {}
        chunks: dict[EvidenceItemId, list[EvidenceChunkId]] = {}
        for result in source_results:
            if result.eligible_count != len(evidence) or any(
                hit.evidence_id not in by_id
                or by_id[hit.evidence_id].version_id != hit.evidence_version_id
                for hit in result.hits
            ):
                raise DependencyUnavailableError("Hybrid source retriever returned invalid lineage")
            for hit in result.hits:
                scores[hit.evidence_id] = scores.get(hit.evidence_id, 0.0) + 1.0 / (
                    self._rrf_constant + hit.rank
                )
                accumulated = reasons.setdefault(hit.evidence_id, [])
                for reason in hit.reasons:
                    if reason not in accumulated:
                        accumulated.append(reason)
                accumulated_chunks = chunks.setdefault(hit.evidence_id, [])
                for chunk_id in hit.evidence_chunk_ids:
                    if chunk_id not in accumulated_chunks:
                        accumulated_chunks.append(chunk_id)
        ordered_ids = sorted(
            scores,
            key=lambda evidence_id: (
                -scores[evidence_id],
                str(evidence_id),
                str(by_id[evidence_id].version_id),
            ),
        )
        selected_ids: list[EvidenceItemId] = []
        selected_estimated_tokens = 0
        for evidence_id in ordered_ids[: query.top_k]:
            candidate_tokens = estimate_tokens(by_id[evidence_id].canonical_content)
            if selected_estimated_tokens + candidate_tokens > query.max_tokens:
                break
            selected_ids.append(evidence_id)
            selected_estimated_tokens += candidate_tokens
        hits = tuple(
            RetrievalHit(
                evidence_id=evidence_id,
                evidence_version_id=by_id[evidence_id].version_id,
                rank=rank,
                score=scores[evidence_id],
                reasons=tuple((*reasons[evidence_id], RetrievalMatchReason.HYBRID_FUSION)),
                evidence_chunk_ids=tuple(chunks.get(evidence_id, [])),
            )
            for rank, evidence_id in enumerate(selected_ids, start=1)
        )
        if hits:
            status = RetrievalStatus.COMPLETED
        elif ordered_ids:
            status = RetrievalStatus.NOT_EXECUTABLE
        else:
            status = RetrievalStatus.NO_RELEVANT_EVIDENCE
        return RetrieverResult(
            status=status,
            hits=hits,
            eligible_count=len(evidence),
            eligible_estimated_tokens=_estimated_evidence_tokens(evidence),
            selected_estimated_tokens=selected_estimated_tokens,
        )
