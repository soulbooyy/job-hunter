"""Immutable, budgeted context assembled from authoritative lineage."""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

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
)
from job_hunter.domain.knowledge import CandidateProfile, EvidenceItemVersion
from job_hunter.domain.retrieval import (
    DeterministicEvidenceChunker,
    EvidenceChunk,
    RetrievalHit,
    estimate_tokens,
)
from job_hunter.errors import ContextBudgetExceededError, InputValidationError

_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d ()-]{7,}\d(?!\w)")
CONTEXT_BUILDER_VERSION = "context-builder-v1"
CONTEXT_REDACTION_POLICY_VERSION = "context-redaction-v1"
CONTEXT_PACKAGING_OVERHEAD_TOKENS = 3


def context_content_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def redact_context_content(value: str) -> tuple[str, "ContextRedaction"]:
    redacted = _EMAIL.sub("[redacted-email]", value)
    redacted = _PHONE.sub("[redacted-phone]", redacted)
    status = ContextRedaction.APPLIED if redacted != value else ContextRedaction.NONE
    return redacted, status


def candidate_profile_context_projection(profile: CandidateProfile) -> str:
    return (
        f"Target roles: {', '.join(profile.target_role_keywords)}; "
        f"Skills: {', '.join(profile.skill_keywords)}; "
        f"Preferred cities: {', '.join(profile.preferred_cities)}"
    )


class ContextEntryKind(StrEnum):
    REQUIREMENT = "requirement"
    EVIDENCE = "evidence"
    PROFILE = "profile"
    PREFERENCE = "preference"
    INSTRUCTION = "instruction"
    WORKFLOW = "workflow"


class ContextRedaction(StrEnum):
    NONE = "none"
    APPLIED = "applied"


class ContextInclusionReason(StrEnum):
    REQUIRED_PROTECTED = "required_protected"
    RETRIEVAL_HIT = "retrieval_hit"


class ContextExclusionReason(StrEnum):
    BUDGET_RANKED_PREFIX = "budget_ranked_prefix"


@dataclass(frozen=True, slots=True)
class ContextEvidenceExclusion:
    requirement_id: RequirementId
    evidence_id: EvidenceItemId
    evidence_version_id: EvidenceVersionId
    evidence_chunk_id: EvidenceChunkId
    reason: ContextExclusionReason


@dataclass(frozen=True, slots=True)
class ContextEntry:
    kind: ContextEntryKind
    content: str
    estimated_tokens: int
    protected: bool
    requirement_id: RequirementId | None
    evidence_id: EvidenceItemId | None
    evidence_version_id: EvidenceVersionId | None
    evidence_chunk_id: EvidenceChunkId | None
    redaction: ContextRedaction
    content_hash: str
    inclusion_reason: ContextInclusionReason

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise InputValidationError("context entry content is required")
        if self.estimated_tokens < 1:
            raise InputValidationError("context entry token estimate must be positive")
        if self.estimated_tokens != estimate_tokens(self.content):
            raise InputValidationError("context entry token accounting is inconsistent")
        expected_hash = context_content_hash(self.content)
        if self.content_hash != expected_hash:
            raise InputValidationError("context entry content hash is invalid")
        evidence_lineage = (
            self.evidence_id,
            self.evidence_version_id,
            self.evidence_chunk_id,
        )
        if self.kind is ContextEntryKind.EVIDENCE:
            if any(value is None for value in evidence_lineage):
                raise InputValidationError("Evidence context requires complete lineage")
            if self.requirement_id is None:
                raise InputValidationError("Evidence context requires Requirement lineage")
            if self.inclusion_reason is not ContextInclusionReason.RETRIEVAL_HIT:
                raise InputValidationError("Evidence context requires retrieval-hit inclusion")
            if self.protected:
                raise InputValidationError("Evidence context cannot be protected")
        elif any(value is not None for value in evidence_lineage):
            raise InputValidationError("only Evidence context may carry Evidence lineage")
        elif self.inclusion_reason is not ContextInclusionReason.REQUIRED_PROTECTED:
            raise InputValidationError("protected context requires protected inclusion")
        elif not self.protected:
            raise InputValidationError("non-Evidence context must be protected")
        if self.kind is ContextEntryKind.REQUIREMENT and self.requirement_id is None:
            raise InputValidationError("Requirement context requires Requirement lineage")
        if self.kind not in {ContextEntryKind.REQUIREMENT, ContextEntryKind.EVIDENCE} and (
            self.requirement_id is not None
        ):
            raise InputValidationError(
                "only Requirement or Evidence context may reference a Requirement"
            )


@dataclass(frozen=True, slots=True)
class ContextAssembly:
    entries: tuple[ContextEntry, ...]
    exclusions: tuple[ContextEvidenceExclusion, ...]
    packaging_overhead_tokens: int
    total_estimated_tokens: int


def _protected_context_entry(
    *,
    kind: ContextEntryKind,
    content: str,
    requirement_id: RequirementId | None = None,
) -> ContextEntry:
    redacted_content, redaction = redact_context_content(content)
    return ContextEntry(
        kind=kind,
        content=redacted_content,
        estimated_tokens=estimate_tokens(redacted_content),
        protected=True,
        requirement_id=requirement_id,
        evidence_id=None,
        evidence_version_id=None,
        evidence_chunk_id=None,
        redaction=redaction,
        content_hash=context_content_hash(redacted_content),
        inclusion_reason=ContextInclusionReason.REQUIRED_PROTECTED,
    )


def assemble_context(
    *,
    requirement_id: RequirementId,
    requirement_text: str,
    profile: CandidateProfile,
    task_instruction: str,
    workflow_identity: str,
    hits: tuple[RetrievalHit, ...],
    evidence: tuple[EvidenceItemVersion, ...],
    max_tokens: int,
    packaging_overhead_tokens: int,
) -> ContextAssembly:
    """Build the exact deterministic projection used by runtime and evaluation."""
    entries: list[ContextEntry] = [
        _protected_context_entry(
            kind=ContextEntryKind.REQUIREMENT,
            content=requirement_text,
            requirement_id=requirement_id,
        ),
        _protected_context_entry(
            kind=ContextEntryKind.INSTRUCTION,
            content=task_instruction,
        ),
        _protected_context_entry(
            kind=ContextEntryKind.WORKFLOW,
            content=workflow_identity,
        ),
        _protected_context_entry(
            kind=ContextEntryKind.PROFILE,
            content=candidate_profile_context_projection(profile),
        ),
    ]
    protected_tokens = packaging_overhead_tokens + sum(entry.estimated_tokens for entry in entries)
    if max_tokens < 1 or protected_tokens > max_tokens:
        raise ContextBudgetExceededError("protected context exceeds the final context budget")
    evidence_by_identity = {(item.evidence_id, item.version_id): item for item in evidence}
    chunker = DeterministicEvidenceChunker()
    candidate_chunks: list[tuple[EvidenceItemVersion, EvidenceChunk]] = []
    for hit in hits:
        item = evidence_by_identity.get((hit.evidence_id, hit.evidence_version_id))
        if item is None:
            raise InputValidationError("context assembly Evidence lineage is invalid")
        all_chunks = chunker.chunk((item,))
        chunks_by_id = {chunk.chunk_id: chunk for chunk in all_chunks}
        if hit.evidence_chunk_ids:
            try:
                selected_chunks = tuple(
                    chunks_by_id[chunk_id] for chunk_id in hit.evidence_chunk_ids
                )
            except KeyError:
                raise InputValidationError("context assembly chunk lineage is invalid") from None
        else:
            selected_chunks = all_chunks
        candidate_chunks.extend((item, chunk) for chunk in selected_chunks)
    remaining = max_tokens - protected_tokens
    exclusions: list[ContextEvidenceExclusion] = []
    for position, (item, chunk) in enumerate(candidate_chunks):
        content, redaction = redact_context_content(chunk.content)
        estimated_tokens = estimate_tokens(content)
        if estimated_tokens > remaining:
            for excluded_evidence, excluded_chunk in candidate_chunks[position:]:
                exclusions.append(
                    ContextEvidenceExclusion(
                        requirement_id=requirement_id,
                        evidence_id=excluded_evidence.evidence_id,
                        evidence_version_id=excluded_evidence.version_id,
                        evidence_chunk_id=excluded_chunk.chunk_id,
                        reason=ContextExclusionReason.BUDGET_RANKED_PREFIX,
                    )
                )
            break
        entries.append(
            ContextEntry(
                kind=ContextEntryKind.EVIDENCE,
                content=content,
                estimated_tokens=estimated_tokens,
                protected=False,
                requirement_id=requirement_id,
                evidence_id=item.evidence_id,
                evidence_version_id=item.version_id,
                evidence_chunk_id=chunk.chunk_id,
                redaction=redaction,
                content_hash=context_content_hash(content),
                inclusion_reason=ContextInclusionReason.RETRIEVAL_HIT,
            )
        )
        remaining -= estimated_tokens
    total_tokens = packaging_overhead_tokens + sum(entry.estimated_tokens for entry in entries)
    return ContextAssembly(
        entries=tuple(entries),
        exclusions=tuple(exclusions),
        packaging_overhead_tokens=packaging_overhead_tokens,
        total_estimated_tokens=total_tokens,
    )


@dataclass(frozen=True, slots=True)
class ContextPackage:
    context_package_id: ContextPackageId
    job_version_id: JobVersionId
    requirement_ids: tuple[RequirementId, ...]
    retrieval_run_id: RetrievalRunId
    candidate_profile_id: CandidateProfileId
    entries: tuple[ContextEntry, ...]
    builder_version: str
    redaction_policy_version: str
    token_estimator_version: str
    packaging_overhead_tokens: int
    total_estimated_tokens: int
    max_tokens: int
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId
    exclusions: tuple[ContextEvidenceExclusion, ...] = ()

    def __post_init__(self) -> None:
        if not self.requirement_ids or len(set(self.requirement_ids)) != len(self.requirement_ids):
            raise InputValidationError("ContextPackage requires unique Requirements")
        if not self.entries:
            raise InputValidationError("ContextPackage requires context entries")
        required_prefix = (
            *(ContextEntryKind.REQUIREMENT for _item in self.requirement_ids),
            ContextEntryKind.INSTRUCTION,
            ContextEntryKind.WORKFLOW,
            ContextEntryKind.PROFILE,
        )
        actual_prefix = tuple(entry.kind for entry in self.entries[: len(required_prefix)])
        if actual_prefix != required_prefix or any(
            entry.kind is not ContextEntryKind.EVIDENCE
            for entry in self.entries[len(required_prefix) :]
        ):
            raise InputValidationError("ContextPackage requires complete ordered protected entries")
        requirement_entries = self.entries[: len(self.requirement_ids)]
        if tuple(entry.requirement_id for entry in requirement_entries) != self.requirement_ids:
            raise InputValidationError(
                "ContextPackage protected entries have invalid Requirement lineage"
            )
        for value, field_name in (
            (self.builder_version, "builder_version"),
            (self.redaction_policy_version, "redaction_policy_version"),
            (self.token_estimator_version, "token_estimator_version"),
        ):
            if not value.strip():
                raise InputValidationError(f"{field_name} is required")
        if self.packaging_overhead_tokens < 0:
            raise InputValidationError("packaging overhead cannot be negative")
        accounted_tokens = self.packaging_overhead_tokens + sum(
            entry.estimated_tokens for entry in self.entries
        )
        if self.total_estimated_tokens != accounted_tokens:
            raise InputValidationError("ContextPackage token accounting is inconsistent")
        if self.max_tokens < 1 or self.total_estimated_tokens > self.max_tokens:
            raise InputValidationError("ContextPackage exceeds max_tokens")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise InputValidationError("created_at must be timezone-aware")
        exclusion_chunks = tuple(item.evidence_chunk_id for item in self.exclusions)
        included_chunks = tuple(
            entry.evidence_chunk_id for entry in self.entries if entry.evidence_chunk_id is not None
        )
        if len(set(included_chunks)) != len(included_chunks):
            raise InputValidationError("context Evidence chunks must be unique")
        if len(set(exclusion_chunks)) != len(exclusion_chunks):
            raise InputValidationError("context Evidence exclusions must be unique")
        if set(exclusion_chunks) & set(included_chunks):
            raise InputValidationError("context chunk cannot be included and excluded")
        if any(
            entry.requirement_id is not None and entry.requirement_id not in self.requirement_ids
            for entry in self.entries
        ) or any(
            exclusion.requirement_id not in self.requirement_ids for exclusion in self.exclusions
        ):
            raise InputValidationError("context lineage references another Requirement")
