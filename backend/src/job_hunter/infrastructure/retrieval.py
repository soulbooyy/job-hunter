"""Deterministic retrieval adapters that require no external services."""

import re

from job_hunter.domain.knowledge import EvidenceItemVersion
from job_hunter.domain.retrieval import (
    RetrievalHit,
    RetrievalMatchReason,
    RetrievalQuery,
    RetrievalStatus,
    RetrievalStrategy,
    RetrieverResult,
)

TOKEN_ESTIMATOR_VERSION = "deterministic-token-estimator-v1"
_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def estimate_tokens(value: str) -> int:
    """Return a versioned deterministic budget estimate, not a provider token claim."""
    return len(_TOKEN_PATTERN.findall(value.casefold()))


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
