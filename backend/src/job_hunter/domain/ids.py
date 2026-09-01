"""Stable identifiers used across workflow and trace boundaries."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _StableId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or any(character.isspace() for character in self.value):
            raise ValueError("IDs must be non-empty and contain no whitespace")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class RunId(_StableId):
    """Stable identity for one application or workflow run."""


@dataclass(frozen=True, slots=True)
class CorrelationId(_StableId):
    """Stable identity connecting work across local boundaries."""


@dataclass(frozen=True, slots=True)
class JobId(_StableId):
    """Stable identity of a logical job across its versions."""


@dataclass(frozen=True, slots=True)
class JobVersionId(_StableId):
    """Stable identity of one immutable job version."""


@dataclass(frozen=True, slots=True)
class SourceSnapshotId(_StableId):
    """Stable identity of validated source data captured at one point in time."""


@dataclass(frozen=True, slots=True)
class SourceReferenceId(_StableId):
    """Stable identity of a job-to-source provenance reference."""


@dataclass(frozen=True, slots=True)
class CandidateProfileId(_StableId):
    """Stable identity of one immutable human-confirmed profile snapshot."""


@dataclass(frozen=True, slots=True)
class EvidenceItemId(_StableId):
    """Stable identity of a logical candidate evidence item."""


@dataclass(frozen=True, slots=True)
class EvidenceVersionId(_StableId):
    """Stable identity of one immutable evidence version."""


@dataclass(frozen=True, slots=True)
class EvidenceChunkId(_StableId):
    """Stable identity of one deterministic derivative Evidence chunk."""


@dataclass(frozen=True, slots=True)
class RequirementId(_StableId):
    """Stable identity of one parsed atomic job requirement."""


@dataclass(frozen=True, slots=True)
class QuickScreenResultId(_StableId):
    """Stable identity of one version-bound screening recommendation."""


@dataclass(frozen=True, slots=True)
class TriageDecisionId(_StableId):
    """Stable identity of one append-only human job decision."""


@dataclass(frozen=True, slots=True)
class RetrievalRunId(_StableId):
    """Stable identity of one immutable Evidence retrieval run."""


@dataclass(frozen=True, slots=True)
class ContextPackageId(_StableId):
    """Stable identity of one immutable, budgeted context package."""
