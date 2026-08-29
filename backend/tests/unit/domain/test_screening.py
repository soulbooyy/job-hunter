from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

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
from job_hunter.domain.screening import (
    JobTriageRecord,
    ParsedRequirement,
    QuickScreenRecommendation,
    QuickScreenResult,
    RequirementPriority,
    RequirementType,
    ScreenReasonCode,
    TriageDecision,
)
from job_hunter.errors import InputValidationError

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)


def _requirement() -> ParsedRequirement:
    return ParsedRequirement(
        requirement_id=RequirementId("requirement-001"),
        job_version_id=JobVersionId("job-version-001"),
        source_text="Must have Python experience",
        text="Must have Python experience",
        requirement_type=RequirementType.SKILL,
        priority=RequirementPriority.REQUIRED,
        parser_name="deterministic-line-parser",
        parser_version="1",
        created_at=NOW,
        correlation_id=CorrelationId("correlation-001"),
        run_id=RunId("run-001"),
    )


def test_parsed_requirement_is_immutable_and_requires_parser_provenance() -> None:
    requirement = _requirement()

    with pytest.raises(FrozenInstanceError):
        requirement.__setattr__("text", "Changed")

    with pytest.raises(InputValidationError, match="parser_version is required"):
        ParsedRequirement(
            requirement_id=RequirementId("requirement-002"),
            job_version_id=JobVersionId("job-version-001"),
            source_text="Python",
            text="Python",
            requirement_type=RequirementType.SKILL,
            priority=RequirementPriority.UNSPECIFIED,
            parser_name="deterministic-line-parser",
            parser_version=" ",
            created_at=NOW,
            correlation_id=CorrelationId("correlation-001"),
            run_id=RunId("run-001"),
        )


def test_quick_screen_result_requires_lineage_and_reasons() -> None:
    with pytest.raises(InputValidationError, match="at least one requirement"):
        QuickScreenResult(
            result_id=QuickScreenResultId("screen-001"),
            job_id=JobId("job-001"),
            job_version_id=JobVersionId("job-version-001"),
            candidate_profile_id=CandidateProfileId("profile-001"),
            requirement_ids=(),
            recommendation=QuickScreenRecommendation.UNCERTAIN,
            reason_codes=(ScreenReasonCode.INSUFFICIENT_SIGNAL,),
            policy_version="quick-screen-v1",
            created_at=NOW,
            correlation_id=CorrelationId("correlation-001"),
            run_id=RunId("run-001"),
        )


def test_triage_record_retains_system_result_and_human_decision() -> None:
    record = JobTriageRecord(
        decision_id=TriageDecisionId("triage-001"),
        job_id=JobId("job-001"),
        quick_screen_result_id=QuickScreenResultId("screen-001"),
        decision=TriageDecision.SHORTLISTED,
        decided_at=NOW,
        correlation_id=CorrelationId("correlation-001"),
        run_id=RunId("run-001"),
    )

    assert record.quick_screen_result_id == QuickScreenResultId("screen-001")
    assert record.decision is TriageDecision.SHORTLISTED
