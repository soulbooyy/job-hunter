"""Evidence eligibility, retrieval outcomes, and authoritative run lineage."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

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
    EvidenceValidity,
)
from job_hunter.errors import InputValidationError


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


class RetrievalStatus(StrEnum):
    COMPLETED = "completed"
    NO_RELEVANT_EVIDENCE = "no_relevant_evidence"
    NOT_EXECUTABLE = "not_executable"


class EvidenceExclusionReason(StrEnum):
    INVALID = "invalid"
    SENSITIVITY_NOT_ALLOWED = "sensitivity_not_allowed"


class RetrievalMatchReason(StrEnum):
    FULL_CONTEXT = "full_context"
    EXACT_PHRASE = "exact_phrase"
    TOKEN_OVERLAP = "token_overlap"
    METADATA_OVERLAP = "metadata_overlap"


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

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise InputValidationError("retrieval rank must be positive")
        if self.score < 0:
            raise InputValidationError("retrieval score cannot be negative")
        if not self.reasons:
            raise InputValidationError("retrieval hit requires at least one reason")


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
        _require_aware(self.created_at, "created_at")

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
