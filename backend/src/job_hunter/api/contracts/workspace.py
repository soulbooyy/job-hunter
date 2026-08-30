"""HTTP read contracts for restoring the current local workspace."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from job_hunter.application.workspace_queries import (
    CandidateProfileReadModel,
    EvidenceHistoryResult,
    EvidenceItemReadModel,
    EvidenceVersionReadModel,
    JobListResult,
    JobSummaryReadModel,
    JobVersionReadModel,
    JobVersionReadStatus,
    JobWorkspaceResult,
    ProfileHistoryResult,
    ProfileReadStatus,
    QuickScreenReadModel,
    RequirementReadModel,
    SourceReadModel,
    TriageReadModel,
)
from job_hunter.domain.jobs import FreshnessStatus, JobLifecycleStatus, SourceKind
from job_hunter.domain.knowledge import EvidenceSensitivity, EvidenceType, EvidenceValidity
from job_hunter.domain.screening import (
    QuickScreenRecommendation,
    RequirementPriority,
    RequirementType,
    ScreenReasonCode,
    TriageDecision,
)


class _ResponseModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class SourceReadResponse(_ResponseModel):
    reference_id: str
    snapshot_id: str
    kind: SourceKind
    locator: str | None
    captured_at: datetime
    last_verified_at: datetime
    freshness: FreshnessStatus

    @classmethod
    def from_result(cls, result: SourceReadModel) -> "SourceReadResponse":
        return cls(
            reference_id=str(result.reference_id),
            snapshot_id=str(result.snapshot_id),
            kind=result.kind,
            locator=result.locator,
            captured_at=result.captured_at,
            last_verified_at=result.last_verified_at,
            freshness=result.freshness,
        )


class JobSummaryResponse(_ResponseModel):
    job_id: str
    active_version_id: str
    version_number: int
    title: str
    company: str
    city: str
    lifecycle_status: JobLifecycleStatus
    source: SourceReadResponse
    current_screen_recommendation: QuickScreenRecommendation | None
    current_triage_decision: TriageDecision | None

    @classmethod
    def from_result(cls, result: JobSummaryReadModel) -> "JobSummaryResponse":
        return cls(
            job_id=str(result.job_id),
            active_version_id=str(result.active_version_id),
            version_number=result.version_number,
            title=result.title,
            company=result.company,
            city=result.city,
            lifecycle_status=result.lifecycle_status,
            source=SourceReadResponse.from_result(result.source),
            current_screen_recommendation=result.current_screen_recommendation,
            current_triage_decision=result.current_triage_decision,
        )


class JobListResponse(_ResponseModel):
    items: tuple[JobSummaryResponse, ...]

    @classmethod
    def from_result(cls, result: JobListResult) -> "JobListResponse":
        return cls(items=tuple(JobSummaryResponse.from_result(item) for item in result.items))


class JobVersionReadResponse(_ResponseModel):
    job_version_id: str
    job_id: str
    version_number: int
    title: str
    company: str
    city: str
    description: str
    source_snapshot_id: str
    source: SourceReadResponse
    created_at: datetime
    correlation_id: str
    run_id: str
    is_active: bool

    @classmethod
    def from_result(cls, result: JobVersionReadModel) -> "JobVersionReadResponse":
        return cls(
            job_version_id=str(result.version_id),
            job_id=str(result.job_id),
            version_number=result.version_number,
            title=result.title,
            company=result.company,
            city=result.city,
            description=result.description,
            source_snapshot_id=str(result.source_snapshot_id),
            source=SourceReadResponse.from_result(result.source),
            created_at=result.created_at,
            correlation_id=str(result.correlation_id),
            run_id=str(result.run_id),
            is_active=result.is_active,
        )


class RequirementReadResponse(_ResponseModel):
    requirement_id: str
    job_version_id: str
    source_text: str
    text: str
    requirement_type: RequirementType
    priority: RequirementPriority
    parser_name: str
    parser_version: str
    created_at: datetime
    correlation_id: str
    run_id: str

    @classmethod
    def from_result(cls, result: RequirementReadModel) -> "RequirementReadResponse":
        return cls(
            requirement_id=str(result.requirement_id),
            job_version_id=str(result.job_version_id),
            source_text=result.source_text,
            text=result.text,
            requirement_type=result.requirement_type,
            priority=result.priority,
            parser_name=result.parser_name,
            parser_version=result.parser_version,
            created_at=result.created_at,
            correlation_id=str(result.correlation_id),
            run_id=str(result.run_id),
        )


class QuickScreenReadResponse(_ResponseModel):
    quick_screen_result_id: str
    job_id: str
    job_version_id: str
    candidate_profile_id: str
    requirement_ids: tuple[str, ...]
    recommendation: QuickScreenRecommendation
    reason_codes: tuple[ScreenReasonCode, ...]
    policy_version: str
    lifecycle_status: JobLifecycleStatus
    created_at: datetime
    correlation_id: str
    run_id: str
    profile_status: ProfileReadStatus
    job_version_status: JobVersionReadStatus
    is_latest_result: bool
    triage_eligible: bool

    @classmethod
    def from_result(cls, result: QuickScreenReadModel) -> "QuickScreenReadResponse":
        return cls(
            quick_screen_result_id=str(result.result_id),
            job_id=str(result.job_id),
            job_version_id=str(result.job_version_id),
            candidate_profile_id=str(result.candidate_profile_id),
            requirement_ids=tuple(str(item) for item in result.requirement_ids),
            recommendation=result.recommendation,
            reason_codes=result.reason_codes,
            policy_version=result.policy_version,
            lifecycle_status=result.lifecycle_status,
            created_at=result.created_at,
            correlation_id=str(result.correlation_id),
            run_id=str(result.run_id),
            profile_status=result.profile_status,
            job_version_status=result.job_version_status,
            is_latest_result=result.is_latest_result,
            triage_eligible=result.triage_eligible,
        )


class TriageReadResponse(_ResponseModel):
    triage_decision_id: str
    job_id: str
    quick_screen_result_id: str
    recommendation: QuickScreenRecommendation
    decision: TriageDecision
    lifecycle_status: JobLifecycleStatus
    decided_at: datetime
    correlation_id: str
    run_id: str

    @classmethod
    def from_result(cls, result: TriageReadModel) -> "TriageReadResponse":
        return cls(
            triage_decision_id=str(result.decision_id),
            job_id=str(result.job_id),
            quick_screen_result_id=str(result.quick_screen_result_id),
            recommendation=result.recommendation,
            decision=result.decision,
            lifecycle_status=result.lifecycle_status,
            decided_at=result.decided_at,
            correlation_id=str(result.correlation_id),
            run_id=str(result.run_id),
        )


class JobWorkspaceResponse(_ResponseModel):
    job_id: str
    active_version_id: str
    lifecycle_status: JobLifecycleStatus
    versions: tuple[JobVersionReadResponse, ...]
    requirements: tuple[RequirementReadResponse, ...]
    screening_results: tuple[QuickScreenReadResponse, ...]
    triage_history: tuple[TriageReadResponse, ...]

    @classmethod
    def from_result(cls, result: JobWorkspaceResult) -> "JobWorkspaceResponse":
        return cls(
            job_id=str(result.job_id),
            active_version_id=str(result.active_version_id),
            lifecycle_status=result.lifecycle_status,
            versions=tuple(JobVersionReadResponse.from_result(item) for item in result.versions),
            requirements=tuple(
                RequirementReadResponse.from_result(item) for item in result.requirements
            ),
            screening_results=tuple(
                QuickScreenReadResponse.from_result(item) for item in result.screening_results
            ),
            triage_history=tuple(
                TriageReadResponse.from_result(item) for item in result.triage_history
            ),
        )


class CandidateProfileReadResponse(_ResponseModel):
    profile_id: str
    target_role_keywords: tuple[str, ...]
    skill_keywords: tuple[str, ...]
    preferred_cities: tuple[str, ...]
    created_at: datetime
    correlation_id: str
    run_id: str

    @classmethod
    def from_result(cls, result: CandidateProfileReadModel) -> "CandidateProfileReadResponse":
        return cls(
            profile_id=str(result.profile_id),
            target_role_keywords=result.target_role_keywords,
            skill_keywords=result.skill_keywords,
            preferred_cities=result.preferred_cities,
            created_at=result.created_at,
            correlation_id=str(result.correlation_id),
            run_id=str(result.run_id),
        )


class CandidateProfileHistoryResponse(_ResponseModel):
    active_profile_id: str | None
    items: tuple[CandidateProfileReadResponse, ...]

    @classmethod
    def from_result(cls, result: ProfileHistoryResult) -> "CandidateProfileHistoryResponse":
        return cls(
            active_profile_id=(
                str(result.active_profile_id) if result.active_profile_id is not None else None
            ),
            items=tuple(CandidateProfileReadResponse.from_result(item) for item in result.items),
        )


class EvidenceVersionReadResponse(_ResponseModel):
    evidence_version_id: str
    evidence_id: str
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
    is_active: bool

    @classmethod
    def from_result(cls, result: EvidenceVersionReadModel) -> "EvidenceVersionReadResponse":
        return cls(
            evidence_version_id=str(result.version_id),
            evidence_id=str(result.evidence_id),
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
            is_active=result.is_active,
        )


class EvidenceItemReadResponse(_ResponseModel):
    evidence_id: str
    active_version_id: str
    versions: tuple[EvidenceVersionReadResponse, ...]

    @classmethod
    def from_result(cls, result: EvidenceItemReadModel) -> "EvidenceItemReadResponse":
        return cls(
            evidence_id=str(result.evidence_id),
            active_version_id=str(result.active_version_id),
            versions=tuple(
                EvidenceVersionReadResponse.from_result(item) for item in result.versions
            ),
        )


class EvidenceHistoryResponse(_ResponseModel):
    items: tuple[EvidenceItemReadResponse, ...]

    @classmethod
    def from_result(cls, result: EvidenceHistoryResult) -> "EvidenceHistoryResponse":
        return cls(items=tuple(EvidenceItemReadResponse.from_result(item) for item in result.items))
