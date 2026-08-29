"""Authoritative human-confirmed Candidate Knowledge domain values."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from job_hunter.domain.ids import (
    CandidateProfileId,
    CorrelationId,
    EvidenceItemId,
    EvidenceVersionId,
    RunId,
)
from job_hunter.errors import ConflictError, InputValidationError


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InputValidationError(f"{field_name} must be timezone-aware")


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise InputValidationError(f"{field_name} is required")


def _require_unique_texts(values: tuple[str, ...], field_name: str) -> None:
    if not values:
        raise InputValidationError(f"{field_name} is required")
    if any(not value.strip() for value in values):
        raise InputValidationError(f"{field_name} cannot contain empty values")
    normalized = tuple(value.casefold() for value in values)
    if len(set(normalized)) != len(normalized):
        raise InputValidationError(f"{field_name} must be unique")


class EvidenceType(StrEnum):
    PROJECT = "project"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    SKILL = "skill"
    OTHER = "other"


class EvidenceSensitivity(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    SENSITIVE = "sensitive"


class EvidenceValidity(StrEnum):
    VALID = "valid"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class CandidateProfile:
    # Each profile value is an immutable human-confirmed snapshot. A later editing
    # slice may add logical versioning only when profile replacement is required.
    profile_id: CandidateProfileId
    target_role_keywords: tuple[str, ...]
    skill_keywords: tuple[str, ...]
    preferred_cities: tuple[str, ...]
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId

    def __post_init__(self) -> None:
        _require_unique_texts(self.target_role_keywords, "target role keywords")
        _require_unique_texts(self.skill_keywords, "skill keywords")
        if self.preferred_cities:
            _require_unique_texts(self.preferred_cities, "preferred cities")
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class EvidenceItemVersion:
    version_id: EvidenceVersionId
    evidence_id: EvidenceItemId
    version_number: int
    evidence_type: EvidenceType
    canonical_content: str
    occurred_on: date | None
    source: str
    provenance: str
    sensitivity: EvidenceSensitivity
    validity: EvidenceValidity
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId

    def __post_init__(self) -> None:
        if self.version_number < 1:
            raise InputValidationError("version_number must be positive")
        _require_text(self.canonical_content, "canonical_content")
        _require_text(self.source, "source")
        _require_text(self.provenance, "provenance")
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: EvidenceItemId
    active_version_id: EvidenceVersionId
    version_ids: tuple[EvidenceVersionId, ...]

    def __post_init__(self) -> None:
        if not self.version_ids:
            raise InputValidationError("evidence item must contain at least one version")
        if len(set(self.version_ids)) != len(self.version_ids):
            raise InputValidationError("evidence version IDs must be unique")
        if self.active_version_id not in self.version_ids:
            raise InputValidationError("active version must belong to history")

    @classmethod
    def create(cls, version: EvidenceItemVersion) -> "EvidenceItem":
        if version.version_number != 1:
            raise InputValidationError("new evidence must start at version 1")
        return cls(
            evidence_id=version.evidence_id,
            active_version_id=version.version_id,
            version_ids=(version.version_id,),
        )

    def with_version(self, version: EvidenceItemVersion) -> "EvidenceItem":
        if version.evidence_id != self.evidence_id:
            raise ConflictError("evidence version belongs to another evidence item")
        if version.version_id in self.version_ids:
            raise ConflictError("evidence version already exists")
        if version.version_number != len(self.version_ids) + 1:
            raise ConflictError("evidence version number must be sequential")
        return EvidenceItem(
            evidence_id=self.evidence_id,
            active_version_id=version.version_id,
            version_ids=(*self.version_ids, version.version_id),
        )
