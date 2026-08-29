"""HTTP contracts for human-confirmed Candidate Knowledge."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from job_hunter.application.candidate_knowledge import (
    CreateCandidateProfileCommand,
    CreateCandidateProfileResult,
    SaveEvidenceCommand,
    SaveEvidenceResult,
)
from job_hunter.domain.ids import CorrelationId, EvidenceItemId, RunId
from job_hunter.domain.knowledge import EvidenceSensitivity, EvidenceType, EvidenceValidity


class _RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CandidateProfileRequest(_RequestModel):
    target_role_keywords: tuple[str, ...] = Field(min_length=1)
    skill_keywords: tuple[str, ...] = Field(min_length=1)
    preferred_cities: tuple[str, ...] = ()
    correlation_id: str = Field(min_length=1, pattern=r"^\S+$")
    run_id: str = Field(min_length=1, pattern=r"^\S+$")

    def to_command(self) -> CreateCandidateProfileCommand:
        return CreateCandidateProfileCommand(
            target_role_keywords=self.target_role_keywords,
            skill_keywords=self.skill_keywords,
            preferred_cities=self.preferred_cities,
            correlation_id=CorrelationId(self.correlation_id),
            run_id=RunId(self.run_id),
        )


class CandidateProfileResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile_id: str
    target_role_keywords: tuple[str, ...]
    skill_keywords: tuple[str, ...]
    preferred_cities: tuple[str, ...]
    created_at: datetime
    correlation_id: str
    run_id: str

    @classmethod
    def from_result(cls, result: CreateCandidateProfileResult) -> "CandidateProfileResponse":
        return cls(
            profile_id=str(result.profile_id),
            target_role_keywords=result.target_role_keywords,
            skill_keywords=result.skill_keywords,
            preferred_cities=result.preferred_cities,
            created_at=result.created_at,
            correlation_id=str(result.correlation_id),
            run_id=str(result.run_id),
        )


class EvidenceRequest(_RequestModel):
    existing_evidence_id: str | None = Field(default=None, min_length=1, pattern=r"^\S+$")
    evidence_type: EvidenceType
    canonical_content: str = Field(min_length=1)
    occurred_on: date | None = None
    source: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    sensitivity: EvidenceSensitivity
    validity: EvidenceValidity
    correlation_id: str = Field(min_length=1, pattern=r"^\S+$")
    run_id: str = Field(min_length=1, pattern=r"^\S+$")

    def to_command(self) -> SaveEvidenceCommand:
        return SaveEvidenceCommand(
            existing_evidence_id=(
                EvidenceItemId(self.existing_evidence_id) if self.existing_evidence_id else None
            ),
            evidence_type=self.evidence_type,
            canonical_content=self.canonical_content,
            occurred_on=self.occurred_on,
            source=self.source,
            provenance=self.provenance,
            sensitivity=self.sensitivity,
            validity=self.validity,
            correlation_id=CorrelationId(self.correlation_id),
            run_id=RunId(self.run_id),
        )


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str
    evidence_version_id: str
    active_version_id: str
    version_number: int
    evidence_type: EvidenceType
    canonical_content: str
    occurred_on: date | None
    source: str
    provenance: str
    sensitivity: EvidenceSensitivity
    validity: EvidenceValidity
    created_at: datetime
    correlation_id: str
    run_id: str

    @classmethod
    def from_result(cls, result: SaveEvidenceResult) -> "EvidenceResponse":
        return cls(
            evidence_id=str(result.evidence_id),
            evidence_version_id=str(result.evidence_version_id),
            active_version_id=str(result.active_version_id),
            version_number=result.version_number,
            evidence_type=result.evidence_type,
            canonical_content=result.canonical_content,
            occurred_on=result.occurred_on,
            source=result.source,
            provenance=result.provenance,
            sensitivity=result.sensitivity,
            validity=result.validity,
            created_at=result.created_at,
            correlation_id=str(result.correlation_id),
            run_id=str(result.run_id),
        )
