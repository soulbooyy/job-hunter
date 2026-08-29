"""Version-bound requirements, screening recommendations, and human triage."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from job_hunter.domain.ids import (
    CandidateProfileId,
    CorrelationId,
    JobId,
    JobVersionId,
    QuickScreenResultId,
    RequirementId,
    RunId,
    TriageDecisionId,
)
from job_hunter.errors import InputValidationError


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InputValidationError(f"{field_name} must be timezone-aware")


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise InputValidationError(f"{field_name} is required")


class RequirementType(StrEnum):
    SKILL = "skill"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    LOCATION = "location"
    RESPONSIBILITY = "responsibility"
    OTHER = "other"


class RequirementPriority(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    UNSPECIFIED = "unspecified"


class QuickScreenRecommendation(StrEnum):
    SCREEN_IN = "screen_in"
    SCREEN_OUT = "screen_out"
    UNCERTAIN = "uncertain"


class ScreenReasonCode(StrEnum):
    CITY_OUTSIDE_PREFERENCE = "city_outside_preference"
    TARGET_ROLE_MATCH = "target_role_match"
    SKILL_OVERLAP = "skill_overlap"
    INSUFFICIENT_SIGNAL = "insufficient_signal"


class TriageDecision(StrEnum):
    SHORTLISTED = "shortlisted"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ParsedRequirement:
    requirement_id: RequirementId
    job_version_id: JobVersionId
    source_text: str
    text: str
    requirement_type: RequirementType
    priority: RequirementPriority
    parser_name: str
    parser_version: str
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId

    def __post_init__(self) -> None:
        for field_name, value in (
            ("source_text", self.source_text),
            ("text", self.text),
            ("parser_name", self.parser_name),
            ("parser_version", self.parser_version),
        ):
            _require_text(value, field_name)
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class QuickScreenResult:
    result_id: QuickScreenResultId
    job_id: JobId
    job_version_id: JobVersionId
    candidate_profile_id: CandidateProfileId
    requirement_ids: tuple[RequirementId, ...]
    recommendation: QuickScreenRecommendation
    reason_codes: tuple[ScreenReasonCode, ...]
    policy_version: str
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId

    def __post_init__(self) -> None:
        if not self.requirement_ids:
            raise InputValidationError("quick screen requires at least one requirement")
        if len(set(self.requirement_ids)) != len(self.requirement_ids):
            raise InputValidationError("quick screen requirement IDs must be unique")
        if not self.reason_codes:
            raise InputValidationError("quick screen requires at least one reason")
        _require_text(self.policy_version, "policy_version")
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class JobTriageRecord:
    decision_id: TriageDecisionId
    job_id: JobId
    quick_screen_result_id: QuickScreenResultId
    decision: TriageDecision
    decided_at: datetime
    correlation_id: CorrelationId
    run_id: RunId

    def __post_init__(self) -> None:
        _require_aware(self.decided_at, "decided_at")
