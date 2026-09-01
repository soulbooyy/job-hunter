"""Immutable runtime-context projection and deterministic compaction policy."""

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from job_hunter.domain.context import ContextEntry, ContextEntryKind, ContextPackage
from job_hunter.domain.ids import (
    ArtifactId,
    ContextPackageId,
    ContextReferenceId,
    CorrelationId,
    JobVersionId,
    RunId,
    RuntimeContextId,
)
from job_hunter.domain.retrieval import estimate_tokens
from job_hunter.errors import ContextBudgetExceededError, InputValidationError

RUNTIME_CONTEXT_POLICY_VERSION = "runtime-context-policy-v1"
ARTIFACT_POLICY_VERSION = "redacted-context-artifact-v1"
_REFERENCE_TEMPLATE = "ArtifactReference {artifact_id}"


class RuntimeContextPriority(StrEnum):
    PROTECTED = "protected"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class RuntimeRetentionClass(StrEnum):
    INLINE_REQUIRED = "inline_required"
    REHYDRATABLE = "rehydratable"


class CompactionDecisionReason(StrEnum):
    RETAINED = "retained"
    EXACT_DUPLICATE = "exact_duplicate"
    EXPLICITLY_OBSOLETE = "explicitly_obsolete"
    EXTERNALIZED = "externalized"


@dataclass(frozen=True, slots=True)
class ContextSupersession:
    obsolete_ordinal: int
    replacement_ordinal: int

    def __post_init__(self) -> None:
        if self.obsolete_ordinal < 1 or self.replacement_ordinal < 1:
            raise InputValidationError("context supersession ordinals must be positive")
        if self.obsolete_ordinal == self.replacement_ordinal:
            raise InputValidationError("context entry cannot supersede itself")


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: ArtifactId
    content_hash: str
    byte_size: int
    estimated_tokens: int
    policy_version: str

    def __post_init__(self) -> None:
        try:
            expected_id = ArtifactId.from_content_hash(self.content_hash)
        except ValueError:
            raise InputValidationError("artifact content hash is invalid") from None
        if self.artifact_id != expected_id:
            raise InputValidationError("artifact identity is invalid")
        if self.byte_size < 1 or self.estimated_tokens < 1 or not self.policy_version:
            raise InputValidationError("artifact metadata is invalid")


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    reference_id: ContextReferenceId
    artifact_id: ArtifactId
    context_package_id: ContextPackageId
    source_ordinals: tuple[int, ...]
    content_hash: str
    source_estimated_tokens: int
    reference_estimated_tokens: int

    def __post_init__(self) -> None:
        if (
            not self.source_ordinals
            or tuple(sorted(set(self.source_ordinals))) != self.source_ordinals
        ):
            raise InputValidationError("artifact reference source ordinals are invalid")
        try:
            expected_artifact_id = ArtifactId.from_content_hash(self.content_hash)
        except ValueError:
            raise InputValidationError("artifact reference content hash is invalid") from None
        if self.artifact_id != expected_artifact_id:
            raise InputValidationError("artifact reference identity is invalid")
        if self.reference_id != ContextReferenceId.from_source(
            self.context_package_id, self.source_ordinals, self.content_hash
        ):
            raise InputValidationError("context reference identity is invalid")
        if self.source_estimated_tokens < 1 or self.reference_estimated_tokens < 1:
            raise InputValidationError("artifact reference token accounting is invalid")


@dataclass(frozen=True, slots=True)
class PlannedArtifact:
    record: ArtifactRecord
    reference: ArtifactReference
    content: str


@dataclass(frozen=True, slots=True)
class RuntimeContextEntry:
    kind: ContextEntryKind
    source_ordinals: tuple[int, ...]
    content_hash: str
    inline_content: str | None
    reference_id: ContextReferenceId | None
    estimated_tokens: int
    protected: bool
    priority: RuntimeContextPriority
    retention_class: RuntimeRetentionClass

    def __post_init__(self) -> None:
        if (
            not self.source_ordinals
            or tuple(sorted(set(self.source_ordinals))) != self.source_ordinals
        ):
            raise InputValidationError("runtime source ordinals must be unique and ordered")
        if (self.inline_content is None) == (self.reference_id is None):
            raise InputValidationError("runtime entry requires exactly one representation")
        if self.estimated_tokens < 1:
            raise InputValidationError("runtime entry token estimate must be positive")
        if self.protected and self.inline_content is None:
            raise InputValidationError("protected runtime context must remain inline")
        if self.inline_content is not None:
            if (
                hashlib.sha256(self.inline_content.encode()).hexdigest() != self.content_hash
                or estimate_tokens(self.inline_content) != self.estimated_tokens
            ):
                raise InputValidationError("inline runtime context is invalid")
        elif self.reference_id is not None:
            try:
                artifact_id = ArtifactId.from_content_hash(self.content_hash)
            except ValueError:
                raise InputValidationError("runtime reference content hash is invalid") from None
            reference_tokens = estimate_tokens(
                _REFERENCE_TEMPLATE.format(artifact_id=str(artifact_id))
            )
            if self.estimated_tokens != reference_tokens:
                raise InputValidationError("runtime reference token accounting is invalid")
        if self.protected and (
            self.priority is not RuntimeContextPriority.PROTECTED
            or self.retention_class is not RuntimeRetentionClass.INLINE_REQUIRED
        ):
            raise InputValidationError("protected runtime context policy is invalid")
        if self.reference_id is not None and (
            self.retention_class is not RuntimeRetentionClass.REHYDRATABLE
        ):
            raise InputValidationError("referenced runtime context must be rehydratable")


@dataclass(frozen=True, slots=True)
class CompactionDecision:
    source_ordinals: tuple[int, ...]
    reason: CompactionDecisionReason
    retained_source_ordinals: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.source_ordinals or not self.retained_source_ordinals:
            raise InputValidationError("compaction decision requires source lineage")
        if any(value < 1 for value in (*self.source_ordinals, *self.retained_source_ordinals)):
            raise InputValidationError("compaction decision source lineage is invalid")


@dataclass(frozen=True, slots=True)
class RuntimeContextSnapshot:
    runtime_context_id: RuntimeContextId
    context_package_id: ContextPackageId
    job_version_id: JobVersionId
    entries: tuple[RuntimeContextEntry, ...]
    decisions: tuple[CompactionDecision, ...]
    source_entry_count: int
    policy_version: str
    artifact_policy_version: str
    packaging_overhead_tokens: int
    source_estimated_tokens: int
    total_estimated_tokens: int
    max_tokens: int
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId

    def __post_init__(self) -> None:
        if not self.entries or self.source_entry_count < 1:
            raise InputValidationError("runtime context requires source entries")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise InputValidationError("created_at must be timezone-aware")
        covered = tuple(
            sorted(ordinal for entry in self.entries for ordinal in entry.source_ordinals)
        )
        if covered != tuple(range(1, self.source_entry_count + 1)):
            raise InputValidationError("runtime context must preserve complete source coverage")
        accounted = self.packaging_overhead_tokens + sum(
            entry.estimated_tokens for entry in self.entries
        )
        if accounted != self.total_estimated_tokens:
            raise InputValidationError("runtime context token accounting is inconsistent")
        if self.max_tokens < 1 or self.total_estimated_tokens > self.max_tokens:
            raise InputValidationError("runtime context exceeds max_tokens")

    @property
    def covered_source_ordinals(self) -> tuple[int, ...]:
        return tuple(sorted(ordinal for entry in self.entries for ordinal in entry.source_ordinals))


@dataclass(frozen=True, slots=True)
class RuntimeContextPlan:
    snapshot: RuntimeContextSnapshot
    artifacts: tuple[PlannedArtifact, ...]


@dataclass(frozen=True, slots=True)
class _Candidate:
    entry: ContextEntry
    source_ordinals: tuple[int, ...]


def _same_logical_source(left: ContextEntry, right: ContextEntry) -> bool:
    if left.kind is not right.kind or left.protected or right.protected:
        return False
    if left.kind is ContextEntryKind.EVIDENCE:
        return left.evidence_id == right.evidence_id
    return left.requirement_id == right.requirement_id


class RuntimeContextPolicy:
    version = RUNTIME_CONTEXT_POLICY_VERSION

    def compact(
        self,
        package: ContextPackage,
        *,
        runtime_context_id: RuntimeContextId,
        max_tokens: int,
        created_at: datetime,
        correlation_id: CorrelationId,
        run_id: RunId,
        supersessions: tuple[ContextSupersession, ...] = (),
    ) -> RuntimeContextPlan:
        indexed = {ordinal: entry for ordinal, entry in enumerate(package.entries, start=1)}
        obsolete: set[int] = set()
        decisions: list[CompactionDecision] = []
        for supersession in supersessions:
            old = indexed.get(supersession.obsolete_ordinal)
            replacement_entry = indexed.get(supersession.replacement_ordinal)
            if (
                old is None
                or replacement_entry is None
                or not _same_logical_source(old, replacement_entry)
            ):
                raise InputValidationError("context supersession requires the same logical source")
            obsolete.add(supersession.obsolete_ordinal)
            decisions.append(
                CompactionDecision(
                    source_ordinals=(supersession.obsolete_ordinal,),
                    reason=CompactionDecisionReason.EXPLICITLY_OBSOLETE,
                    retained_source_ordinals=(supersession.replacement_ordinal,),
                )
            )
        candidates: list[_Candidate] = []
        dedupe_by_identity: dict[tuple[object, ...], int] = {}
        for ordinal, entry in indexed.items():
            if ordinal in obsolete:
                # Coverage is transferred to the explicit replacement entry.
                continue
            identity = (
                entry.kind,
                entry.content_hash,
                entry.requirement_id,
                entry.protected,
            )
            duplicate_index = dedupe_by_identity.get(identity) if not entry.protected else None
            if duplicate_index is not None:
                existing = candidates[duplicate_index]
                candidates[duplicate_index] = replace(
                    existing,
                    source_ordinals=tuple((*existing.source_ordinals, ordinal)),
                )
                decisions.append(
                    CompactionDecision(
                        source_ordinals=(ordinal,),
                        reason=CompactionDecisionReason.EXACT_DUPLICATE,
                        retained_source_ordinals=existing.source_ordinals,
                    )
                )
                continue
            dedupe_by_identity[identity] = len(candidates)
            candidates.append(_Candidate(entry=entry, source_ordinals=(ordinal,)))
        # Explicitly obsolete ordinals stay covered by their replacement representation.
        for supersession in supersessions:
            for index, candidate in enumerate(candidates):
                if supersession.replacement_ordinal in candidate.source_ordinals:
                    candidates[index] = replace(
                        candidate,
                        source_ordinals=tuple(
                            sorted((*candidate.source_ordinals, supersession.obsolete_ordinal))
                        ),
                    )
                    break
        runtime_entries = [self._inline(candidate) for candidate in candidates]
        protected_tokens = package.packaging_overhead_tokens + sum(
            entry.estimated_tokens for entry in runtime_entries if entry.protected
        )
        if max_tokens < 1 or protected_tokens > max_tokens:
            raise ContextBudgetExceededError("protected runtime context exceeds budget")
        artifacts: list[PlannedArtifact] = []
        total = package.packaging_overhead_tokens + sum(
            entry.estimated_tokens for entry in runtime_entries
        )
        for index in range(len(runtime_entries) - 1, -1, -1):
            if total <= max_tokens:
                break
            runtime_entry = runtime_entries[index]
            candidate = candidates[index]
            if runtime_entry.protected:
                continue
            artifact = self._externalize(package.context_package_id, candidate)
            runtime_entries[index] = replace(
                runtime_entry,
                inline_content=None,
                reference_id=artifact.reference.reference_id,
                estimated_tokens=artifact.reference.reference_estimated_tokens,
                retention_class=RuntimeRetentionClass.REHYDRATABLE,
            )
            total -= candidate.entry.estimated_tokens
            total += artifact.reference.reference_estimated_tokens
            artifacts.append(artifact)
            decisions.append(
                CompactionDecision(
                    source_ordinals=candidate.source_ordinals,
                    reason=CompactionDecisionReason.EXTERNALIZED,
                    retained_source_ordinals=candidate.source_ordinals,
                )
            )
        if total > max_tokens:
            raise ContextBudgetExceededError("runtime context cannot safely meet budget")
        decided_ordinals = {
            ordinal for decision in decisions for ordinal in decision.source_ordinals
        }
        decisions.extend(
            CompactionDecision(
                source_ordinals=entry.source_ordinals,
                reason=CompactionDecisionReason.RETAINED,
                retained_source_ordinals=entry.source_ordinals,
            )
            for entry in runtime_entries
            if not set(entry.source_ordinals) & decided_ordinals
        )
        snapshot = RuntimeContextSnapshot(
            runtime_context_id=runtime_context_id,
            context_package_id=package.context_package_id,
            job_version_id=package.job_version_id,
            entries=tuple(runtime_entries),
            decisions=tuple(decisions),
            source_entry_count=len(package.entries),
            policy_version=self.version,
            artifact_policy_version=ARTIFACT_POLICY_VERSION,
            packaging_overhead_tokens=package.packaging_overhead_tokens,
            source_estimated_tokens=package.total_estimated_tokens,
            total_estimated_tokens=total,
            max_tokens=max_tokens,
            created_at=created_at,
            correlation_id=correlation_id,
            run_id=run_id,
        )
        return RuntimeContextPlan(snapshot=snapshot, artifacts=tuple(reversed(artifacts)))

    @staticmethod
    def _inline(candidate: _Candidate) -> RuntimeContextEntry:
        entry = candidate.entry
        return RuntimeContextEntry(
            kind=entry.kind,
            source_ordinals=candidate.source_ordinals,
            content_hash=entry.content_hash,
            inline_content=entry.content,
            reference_id=None,
            estimated_tokens=entry.estimated_tokens,
            protected=entry.protected,
            priority=(
                RuntimeContextPriority.PROTECTED
                if entry.protected
                else RuntimeContextPriority.NORMAL
            ),
            retention_class=(
                RuntimeRetentionClass.INLINE_REQUIRED
                if entry.protected
                else RuntimeRetentionClass.REHYDRATABLE
            ),
        )

    @staticmethod
    def _externalize(
        context_package_id: ContextPackageId,
        candidate: _Candidate,
    ) -> PlannedArtifact:
        entry = candidate.entry
        artifact_id = ArtifactId.from_content_hash(entry.content_hash)
        reference_id = ContextReferenceId.from_source(
            context_package_id,
            candidate.source_ordinals,
            entry.content_hash,
        )
        reference_tokens = estimate_tokens(_REFERENCE_TEMPLATE.format(artifact_id=str(artifact_id)))
        record = ArtifactRecord(
            artifact_id=artifact_id,
            content_hash=entry.content_hash,
            byte_size=len(entry.content.encode()),
            estimated_tokens=entry.estimated_tokens,
            policy_version=ARTIFACT_POLICY_VERSION,
        )
        reference = ArtifactReference(
            reference_id=reference_id,
            artifact_id=artifact_id,
            context_package_id=context_package_id,
            source_ordinals=candidate.source_ordinals,
            content_hash=entry.content_hash,
            source_estimated_tokens=entry.estimated_tokens,
            reference_estimated_tokens=reference_tokens,
        )
        return PlannedArtifact(record=record, reference=reference, content=entry.content)
