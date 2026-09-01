"""Evidence eligibility, retrieval outcomes, and authoritative run lineage."""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from job_hunter.domain.ids import (
    CorrelationId,
    EvidenceChunkId,
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
from job_hunter.errors import InputValidationError

TOKEN_ESTIMATOR_VERSION = "deterministic-token-estimator-v1"
EVIDENCE_CHUNK_POLICY_VERSION = "evidence-chunk-v1"
EVIDENCE_CHUNK_MAX_TOKENS = 192
EVIDENCE_CHUNK_OVERLAP_TOKENS = 32
SEMANTIC_CHROMA_V1_MAX_COSINE_DISTANCE = 0.75
_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def estimate_tokens(value: str) -> int:
    """Return a versioned deterministic budget estimate, not a provider token claim."""
    return len(_TOKEN_PATTERN.findall(value.casefold()))


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise InputValidationError(f"{field_name} is required")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InputValidationError(f"{field_name} must be timezone-aware")


class RetrievalTaskType(StrEnum):
    DEEP_FIT = "deep_fit"


class RetrievalStrategy(StrEnum):
    FULL_CONTEXT = "full_context"
    LEXICAL_METADATA = "lexical_metadata"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class RetrievalStatus(StrEnum):
    COMPLETED = "completed"
    NO_RELEVANT_EVIDENCE = "no_relevant_evidence"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_EXECUTABLE = "not_executable"


class EvidenceExclusionReason(StrEnum):
    INVALID = "invalid"
    SENSITIVITY_NOT_ALLOWED = "sensitivity_not_allowed"


class RetrievalMatchReason(StrEnum):
    FULL_CONTEXT = "full_context"
    EXACT_PHRASE = "exact_phrase"
    TOKEN_OVERLAP = "token_overlap"
    METADATA_OVERLAP = "metadata_overlap"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    HYBRID_FUSION = "hybrid_fusion"


class RetrievalPolicyReason(StrEnum):
    SMALL_ELIGIBLE_CONTEXT = "small_eligible_context"
    PRECISE_LOOKUP = "precise_lookup"
    SEMANTIC_MATCH = "semantic_match"


class RetrievalFallbackReason(StrEnum):
    HYBRID_NOT_PROMOTED = "hybrid_not_promoted"
    SEMANTIC_UNAVAILABLE = "semantic_unavailable"
    FULL_CONTEXT_NOT_EXECUTABLE = "full_context_not_executable"


@dataclass(frozen=True, slots=True)
class RetrievalPromotionEvidence:
    dataset_version: str
    split: str
    human_reviewed: bool
    minimum_dataset_gate: bool
    recall_at_5: float
    direct_mrr: float
    no_evidence_accuracy: float
    no_evidence_total: int
    final_context_token_reduction: float
    large_context_case_count: int
    large_context_no_evidence_count: int
    recall_degradation: float
    no_evidence_degradation: float

    def __post_init__(self) -> None:
        _require_text(self.dataset_version, "promotion dataset_version")
        _require_text(self.split, "promotion split")
        metrics = (
            self.recall_at_5,
            self.direct_mrr,
            self.no_evidence_accuracy,
            self.final_context_token_reduction,
            self.recall_degradation,
            self.no_evidence_degradation,
        )
        if any(value < 0 or value > 1 for value in metrics):
            raise InputValidationError("promotion metrics must be between zero and one")
        if self.no_evidence_total < 0:
            raise InputValidationError("promotion No-Evidence count cannot be negative")
        if self.large_context_case_count < 0 or self.large_context_no_evidence_count < 0:
            raise InputValidationError("promotion large-context counts cannot be negative")
        if self.large_context_no_evidence_count > self.large_context_case_count:
            raise InputValidationError("promotion large-context counts are inconsistent")

    @property
    def promoted(self) -> bool:
        return (
            self.split == "frozen_holdout"
            and self.human_reviewed
            and self.minimum_dataset_gate
            and self.recall_at_5 >= 0.85
            and self.direct_mrr >= 0.70
            and self.no_evidence_total > 0
            and self.no_evidence_accuracy >= 0.90
            and self.large_context_case_count > 0
            and self.large_context_no_evidence_count > 0
            and self.final_context_token_reduction >= 0.30
            and self.recall_degradation <= 0.05
            and self.no_evidence_degradation <= 0.02
        )


@dataclass(frozen=True, slots=True)
class RetrievalPolicyInput:
    requirement_id: RequirementId
    query_text: str
    eligible_count: int
    eligible_estimated_tokens: int
    max_tokens: int
    hybrid_promoted: bool
    semantic_ready: bool
    promotion_dataset_version: str | None

    def __post_init__(self) -> None:
        _require_text(self.query_text, "retrieval policy query text")
        if self.eligible_count < 0:
            raise InputValidationError("eligible_count cannot be negative")
        if self.eligible_estimated_tokens < 0:
            raise InputValidationError("eligible_estimated_tokens cannot be negative")
        if self.max_tokens < 1:
            raise InputValidationError("max_tokens must be positive")
        if self.hybrid_promoted and not self.promotion_dataset_version:
            raise InputValidationError("promoted Hybrid requires a dataset version")


@dataclass(frozen=True, slots=True)
class RetrievalPolicyDecision:
    policy_version: str
    initial_strategy: RetrievalStrategy
    selected_strategy: RetrievalStrategy
    reason: RetrievalPolicyReason
    fallback_reason: RetrievalFallbackReason | None
    promotion_dataset_version: str | None


class RetrievalPolicy:
    """Deterministic first-retrieval routing; no model chooses the initial strategy."""

    version = "retrieval-policy-v1"
    small_context_threshold = 1_200
    _precise_terms = frozenset(
        {
            "certificate",
            "certification",
            "certified",
            "credential",
            "identifier",
            "project",
            "skill",
        }
    )

    def decide(self, policy_input: RetrievalPolicyInput) -> RetrievalPolicyDecision:
        if (
            policy_input.eligible_estimated_tokens <= self.small_context_threshold
            and policy_input.eligible_estimated_tokens <= policy_input.max_tokens
        ):
            return self._decision(
                selected=RetrievalStrategy.FULL_CONTEXT,
                reason=RetrievalPolicyReason.SMALL_ELIGIBLE_CONTEXT,
                promotion_dataset_version=policy_input.promotion_dataset_version,
            )
        query_terms = {
            term.casefold().strip(".,:;()[]{}") for term in policy_input.query_text.split()
        }
        if query_terms & self._precise_terms:
            return self._decision(
                selected=RetrievalStrategy.LEXICAL_METADATA,
                reason=RetrievalPolicyReason.PRECISE_LOOKUP,
                promotion_dataset_version=policy_input.promotion_dataset_version,
            )
        if policy_input.hybrid_promoted and policy_input.semantic_ready:
            return self._decision(
                selected=RetrievalStrategy.HYBRID,
                reason=RetrievalPolicyReason.SEMANTIC_MATCH,
                promotion_dataset_version=policy_input.promotion_dataset_version,
            )
        fallback_reason = (
            RetrievalFallbackReason.HYBRID_NOT_PROMOTED
            if not policy_input.hybrid_promoted
            else RetrievalFallbackReason.SEMANTIC_UNAVAILABLE
        )
        fallback_strategy = (
            RetrievalStrategy.FULL_CONTEXT
            if policy_input.eligible_estimated_tokens <= policy_input.max_tokens
            else RetrievalStrategy.LEXICAL_METADATA
        )
        return RetrievalPolicyDecision(
            policy_version=self.version,
            initial_strategy=RetrievalStrategy.HYBRID,
            selected_strategy=fallback_strategy,
            reason=RetrievalPolicyReason.SEMANTIC_MATCH,
            fallback_reason=fallback_reason,
            promotion_dataset_version=policy_input.promotion_dataset_version,
        )

    def _decision(
        self,
        *,
        selected: RetrievalStrategy,
        reason: RetrievalPolicyReason,
        promotion_dataset_version: str | None,
    ) -> RetrievalPolicyDecision:
        return RetrievalPolicyDecision(
            policy_version=self.version,
            initial_strategy=selected,
            selected_strategy=selected,
            reason=reason,
            fallback_reason=None,
            promotion_dataset_version=promotion_dataset_version,
        )


@dataclass(frozen=True, slots=True)
class EvidenceChunk:
    """Version-bound derivative content; SQLite Evidence remains authoritative."""

    chunk_id: EvidenceChunkId
    evidence_id: EvidenceItemId
    evidence_version_id: EvidenceVersionId
    ordinal: int
    content: str
    tokens: tuple[str, ...]
    estimated_tokens: int
    policy_version: str
    content_hash: str

    def __post_init__(self) -> None:
        _require_text(self.content, "chunk content")
        _require_text(self.policy_version, "chunk policy_version")
        _require_text(self.content_hash, "chunk content_hash")
        if self.ordinal < 1:
            raise InputValidationError("chunk ordinal must be positive")
        if not self.tokens or self.estimated_tokens != len(self.tokens):
            raise InputValidationError("chunk token accounting must match content tokens")


@dataclass(frozen=True, slots=True)
class SemanticChunkMatch:
    chunk_id: EvidenceChunkId
    evidence_id: EvidenceItemId
    evidence_version_id: EvidenceVersionId
    distance: float

    def __post_init__(self) -> None:
        if self.distance < 0:
            raise InputValidationError("semantic distance cannot be negative")


@dataclass(frozen=True, slots=True)
class SemanticIndexRecord:
    chunk: EvidenceChunk
    evidence_type: EvidenceType
    sensitivity: EvidenceSensitivity
    validity: EvidenceValidity


class DeterministicEvidenceChunker:
    """Build stable derivative chunks without giving an index authority."""

    def chunk(self, evidence: tuple[EvidenceItemVersion, ...]) -> tuple[EvidenceChunk, ...]:
        chunks: list[EvidenceChunk] = []
        ordered = sorted(evidence, key=lambda item: (str(item.evidence_id), str(item.version_id)))
        step = EVIDENCE_CHUNK_MAX_TOKENS - EVIDENCE_CHUNK_OVERLAP_TOKENS
        for item in ordered:
            tokens = tuple(_TOKEN_PATTERN.findall(item.canonical_content.casefold()))
            for ordinal, start in enumerate(range(0, len(tokens), step), start=1):
                selected = tokens[start : start + EVIDENCE_CHUNK_MAX_TOKENS]
                normalized_content = " ".join(selected)
                content_hash = hashlib.sha256(normalized_content.encode()).hexdigest()
                identity = ":".join(
                    (
                        str(item.version_id),
                        EVIDENCE_CHUNK_POLICY_VERSION,
                        str(ordinal),
                        content_hash,
                    )
                )
                chunk_hash = hashlib.sha256(identity.encode()).hexdigest()
                chunks.append(
                    EvidenceChunk(
                        chunk_id=EvidenceChunkId(f"chunk-{chunk_hash[:32]}"),
                        evidence_id=item.evidence_id,
                        evidence_version_id=item.version_id,
                        ordinal=ordinal,
                        content=normalized_content,
                        tokens=selected,
                        estimated_tokens=len(selected),
                        policy_version=EVIDENCE_CHUNK_POLICY_VERSION,
                        content_hash=content_hash,
                    )
                )
                if start + EVIDENCE_CHUNK_MAX_TOKENS >= len(tokens):
                    break
        return tuple(chunks)


@dataclass(frozen=True, slots=True)
class EvidenceExclusion:
    evidence_id: EvidenceItemId
    evidence_version_id: EvidenceVersionId
    reason: EvidenceExclusionReason


@dataclass(frozen=True, slots=True)
class EvidenceEligibilityResult:
    eligible: tuple[EvidenceItemVersion, ...]
    exclusions: tuple[EvidenceExclusion, ...]


class EvidenceEligibilityPolicy:
    version = "evidence-eligibility-v1"

    @staticmethod
    def exclusion_reason(
        *,
        validity: EvidenceValidity,
        sensitivity: EvidenceSensitivity,
        allowed_sensitivities: tuple[EvidenceSensitivity, ...],
    ) -> EvidenceExclusionReason | None:
        if validity is not EvidenceValidity.VALID:
            return EvidenceExclusionReason.INVALID
        if sensitivity not in set(allowed_sensitivities):
            return EvidenceExclusionReason.SENSITIVITY_NOT_ALLOWED
        return None

    def evaluate(
        self,
        evidence: tuple[EvidenceItemVersion, ...],
        *,
        allowed_sensitivities: tuple[EvidenceSensitivity, ...],
    ) -> EvidenceEligibilityResult:
        eligible: list[EvidenceItemVersion] = []
        exclusions: list[EvidenceExclusion] = []
        for version in evidence:
            reason = self.exclusion_reason(
                validity=version.validity,
                sensitivity=version.sensitivity,
                allowed_sensitivities=allowed_sensitivities,
            )
            if reason is None:
                eligible.append(version)
            else:
                exclusions.append(
                    EvidenceExclusion(
                        evidence_id=version.evidence_id,
                        evidence_version_id=version.version_id,
                        reason=reason,
                    )
                )
        # Repository iteration order is adapter-specific. Stable ID ordering keeps
        # baseline retrieval and reports reproducible across adapters.
        eligible.sort(key=lambda item: (str(item.evidence_id), str(item.version_id)))
        exclusions.sort(key=lambda item: (str(item.evidence_id), str(item.evidence_version_id)))
        return EvidenceEligibilityResult(tuple(eligible), tuple(exclusions))


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    requirement_id: RequirementId
    text: str
    task_type: RetrievalTaskType
    max_tokens: int
    top_k: int

    def __post_init__(self) -> None:
        _require_text(self.text, "retrieval query text")
        if self.max_tokens < 1:
            raise InputValidationError("max_tokens must be positive")
        if self.top_k < 1:
            raise InputValidationError("top_k must be positive")


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    evidence_id: EvidenceItemId
    evidence_version_id: EvidenceVersionId
    rank: int
    score: float
    reasons: tuple[RetrievalMatchReason, ...]
    evidence_chunk_ids: tuple[EvidenceChunkId, ...] = ()

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise InputValidationError("retrieval rank must be positive")
        if self.score < 0:
            raise InputValidationError("retrieval score cannot be negative")
        if not self.reasons:
            raise InputValidationError("retrieval hit requires at least one reason")
        if len(set(self.evidence_chunk_ids)) != len(self.evidence_chunk_ids):
            raise InputValidationError("retrieval EvidenceChunk IDs must be unique")


def _validate_hits(
    status: RetrievalStatus,
    hits: tuple[RetrievalHit, ...],
) -> None:
    if status is RetrievalStatus.COMPLETED and not hits:
        raise InputValidationError("completed retrieval requires at least one hit")
    if status is not RetrievalStatus.COMPLETED and hits:
        raise InputValidationError("non-completed retrieval cannot contain hits")
    if tuple(hit.rank for hit in hits) != tuple(range(1, len(hits) + 1)):
        raise InputValidationError("retrieval ranks must be contiguous")
    evidence_ids = tuple(hit.evidence_id for hit in hits)
    version_ids = tuple(hit.evidence_version_id for hit in hits)
    if len(set(evidence_ids)) != len(evidence_ids):
        raise InputValidationError("retrieval EvidenceItem IDs must be unique")
    if len(set(version_ids)) != len(version_ids):
        raise InputValidationError("retrieval EvidenceVersion IDs must be unique")


@dataclass(frozen=True, slots=True)
class RetrieverResult:
    status: RetrievalStatus
    hits: tuple[RetrievalHit, ...]
    eligible_count: int
    eligible_estimated_tokens: int
    selected_estimated_tokens: int

    def __post_init__(self) -> None:
        _validate_hits(self.status, self.hits)
        if self.eligible_count < 0:
            raise InputValidationError("eligible_count cannot be negative")
        if self.eligible_estimated_tokens < 0:
            raise InputValidationError("eligible_estimated_tokens cannot be negative")
        if self.selected_estimated_tokens < 0:
            raise InputValidationError("selected_estimated_tokens cannot be negative")
        if self.selected_estimated_tokens > self.eligible_estimated_tokens:
            raise InputValidationError("selected token estimate cannot exceed eligible estimate")
        if self.status is not RetrievalStatus.COMPLETED and self.selected_estimated_tokens:
            raise InputValidationError("non-completed retrieval cannot select token content")


@dataclass(frozen=True, slots=True)
class RetrievalRun:
    retrieval_run_id: RetrievalRunId
    requirement_id: RequirementId
    job_version_id: JobVersionId
    strategy: RetrievalStrategy
    retriever_version: str
    eligibility_policy_version: str
    token_estimator_version: str
    status: RetrievalStatus
    hits: tuple[RetrievalHit, ...]
    exclusions: tuple[EvidenceExclusion, ...]
    eligible_count: int
    eligible_estimated_tokens: int
    selected_estimated_tokens: int
    max_tokens: int
    top_k: int
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId
    policy_version: str | None = None
    initial_strategy: RetrievalStrategy | None = None
    decision_reason: RetrievalPolicyReason | None = None
    fallback_reason: RetrievalFallbackReason | None = None
    promotion_dataset_version: str | None = None
    semantic_ready: bool = False
    index_version: str | None = None
    embedding_provider_version: str | None = None
    chunk_policy_version: str | None = None
    query_count: int = 1
    supplemental_query_text: str | None = None

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.retriever_version, "retriever_version"),
            (self.eligibility_policy_version, "eligibility_policy_version"),
            (self.token_estimator_version, "token_estimator_version"),
        ):
            _require_text(value, field_name)
        _validate_hits(self.status, self.hits)
        excluded_versions = tuple(item.evidence_version_id for item in self.exclusions)
        if len(set(excluded_versions)) != len(excluded_versions):
            raise InputValidationError("retrieval exclusions must be unique")
        hit_versions = {item.evidence_version_id for item in self.hits}
        if hit_versions & set(excluded_versions):
            raise InputValidationError("EvidenceVersion cannot be both hit and excluded")
        if self.eligible_count < 0:
            raise InputValidationError("eligible_count cannot be negative")
        if self.eligible_estimated_tokens < 0:
            raise InputValidationError("eligible_estimated_tokens cannot be negative")
        if self.selected_estimated_tokens < 0:
            raise InputValidationError("selected_estimated_tokens cannot be negative")
        if self.selected_estimated_tokens > self.eligible_estimated_tokens:
            raise InputValidationError("selected token estimate cannot exceed eligible estimate")
        if self.status is not RetrievalStatus.COMPLETED and self.selected_estimated_tokens:
            raise InputValidationError("non-completed retrieval cannot select token content")
        if self.max_tokens < 1:
            raise InputValidationError("max_tokens must be positive")
        if self.top_k < 1:
            raise InputValidationError("top_k must be positive")
        if (
            self.status is RetrievalStatus.COMPLETED
            and self.selected_estimated_tokens > self.max_tokens
        ):
            raise InputValidationError("selected retrieval content exceeds max_tokens")
        self._validate_full_context()
        self._validate_policy_lineage()
        _require_aware(self.created_at, "created_at")

    def _validate_policy_lineage(self) -> None:
        if self.query_count not in (1, 2):
            raise InputValidationError("retrieval query_count must be one or two")
        if self.query_count == 2 and not self.supplemental_query_text:
            raise InputValidationError("supplemental retrieval requires its query text")
        if self.query_count == 1 and self.supplemental_query_text is not None:
            raise InputValidationError("single-query retrieval cannot record supplemental text")
        policy_values = (
            self.policy_version,
            self.initial_strategy,
            self.decision_reason,
        )
        if any(value is not None for value in policy_values) and any(
            value is None for value in policy_values
        ):
            raise InputValidationError("retrieval policy lineage must be complete")
        if self.fallback_reason is not None and self.policy_version is None:
            raise InputValidationError("retrieval fallback requires policy lineage")
        if self.policy_version is not None:
            _require_text(self.policy_version, "policy_version")
            if self.initial_strategy is None or self.decision_reason is None:
                raise InputValidationError("retrieval policy lineage must be complete")
            if self.initial_strategy != self.strategy and self.fallback_reason is None:
                raise InputValidationError("changed retrieval strategy requires a fallback reason")
        if self.strategy is RetrievalStrategy.HYBRID and not (
            self.semantic_ready
            and self.promotion_dataset_version
            and self.index_version
            and self.embedding_provider_version
            and self.chunk_policy_version
        ):
            raise InputValidationError("Hybrid retrieval requires promoted semantic index lineage")
        for value, field_name in (
            (self.index_version, "index_version"),
            (self.embedding_provider_version, "embedding_provider_version"),
            (self.chunk_policy_version, "chunk_policy_version"),
        ):
            if value is not None:
                _require_text(value, field_name)

    def _validate_full_context(self) -> None:
        if self.strategy is not RetrievalStrategy.FULL_CONTEXT:
            return
        if self.status is RetrievalStatus.COMPLETED:
            if len(self.hits) != self.eligible_count:
                raise InputValidationError("Full Context must include all eligible Evidence")
            if self.selected_estimated_tokens != self.eligible_estimated_tokens:
                raise InputValidationError("Full Context token accounting must cover all Evidence")
            if any(hit.reasons != (RetrievalMatchReason.FULL_CONTEXT,) for hit in self.hits):
                raise InputValidationError("Full Context hits require full-context reasons")
        elif self.status is RetrievalStatus.NOT_EXECUTABLE:
            if self.eligible_count < 1 or self.eligible_estimated_tokens <= self.max_tokens:
                raise InputValidationError("Full Context budget failure must exceed max_tokens")
        elif self.eligible_count or self.eligible_estimated_tokens:
            raise InputValidationError("Full Context No-Evidence requires an empty eligible set")
