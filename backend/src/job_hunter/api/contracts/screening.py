"""HTTP contracts for deterministic QuickScreen and human Job Triage."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from job_hunter.application.screening import (
    RecordJobTriageCommand,
    RecordJobTriageResult,
    RunQuickScreenCommand,
    RunQuickScreenResult,
)
from job_hunter.domain.ids import CorrelationId, JobId, QuickScreenResultId, RunId
from job_hunter.domain.jobs import JobLifecycleStatus
from job_hunter.domain.screening import (
    QuickScreenRecommendation,
    ScreenReasonCode,
    TriageDecision,
)


class _RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class QuickScreenRequest(_RequestModel):
    correlation_id: str = Field(min_length=1, pattern=r"^\S+$")
    run_id: str = Field(min_length=1, pattern=r"^\S+$")

    def to_command(self, job_id: str) -> RunQuickScreenCommand:
        return RunQuickScreenCommand(
            job_id=JobId(job_id),
            correlation_id=CorrelationId(self.correlation_id),
            run_id=RunId(self.run_id),
        )


class QuickScreenResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

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

    @classmethod
    def from_result(cls, result: RunQuickScreenResult) -> "QuickScreenResponse":
        return cls(
            quick_screen_result_id=str(result.quick_screen_result_id),
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
        )


class TriageRequest(_RequestModel):
    quick_screen_result_id: str = Field(min_length=1, pattern=r"^\S+$")
    decision: TriageDecision
    correlation_id: str = Field(min_length=1, pattern=r"^\S+$")
    run_id: str = Field(min_length=1, pattern=r"^\S+$")

    def to_command(self, job_id: str) -> RecordJobTriageCommand:
        return RecordJobTriageCommand(
            job_id=JobId(job_id),
            quick_screen_result_id=QuickScreenResultId(self.quick_screen_result_id),
            decision=self.decision,
            correlation_id=CorrelationId(self.correlation_id),
            run_id=RunId(self.run_id),
        )


class TriageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

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
    def from_result(cls, result: RecordJobTriageResult) -> "TriageResponse":
        return cls(
            triage_decision_id=str(result.triage_decision_id),
            job_id=str(result.job_id),
            quick_screen_result_id=str(result.quick_screen_result_id),
            recommendation=result.recommendation,
            decision=result.decision,
            lifecycle_status=result.lifecycle_status,
            decided_at=result.decided_at,
            correlation_id=str(result.correlation_id),
            run_id=str(result.run_id),
        )
