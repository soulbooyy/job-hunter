"""Deterministic requirement parsing, QuickScreen, and human Job Triage."""

import re
from dataclasses import dataclass
from datetime import datetime

from job_hunter.application.ports import Clock, IdGenerator, UnitOfWorkFactory
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
from job_hunter.domain.jobs import JobLifecycleStatus
from job_hunter.domain.knowledge import CandidateProfile
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
from job_hunter.errors import ConflictError, DependencyUnavailableError, JobHunterError

_PARSER_NAME = "deterministic-line-parser"
_PARSER_VERSION = "1"
_POLICY_VERSION = "quick-screen-v1"
_BULLET_PREFIX = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


def _normalized(value: str) -> str:
    return " ".join(value.split())


def _requirement_lines(description: str) -> tuple[str, ...]:
    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in description.splitlines():
        line = _normalized(_BULLET_PREFIX.sub("", raw_line))
        key = line.casefold()
        if line and key not in seen:
            seen.add(key)
            lines.append(line)
    return tuple(lines) if lines else (_normalized(description),)


def _priority(text: str) -> RequirementPriority:
    normalized = text.casefold()
    if any(token in normalized for token in ("preferred", "nice to have", "优先", "加分")):
        return RequirementPriority.PREFERRED
    if any(token in normalized for token in ("must", "required", "要求", "必须")):
        return RequirementPriority.REQUIRED
    return RequirementPriority.UNSPECIFIED


def _requirement_type(text: str) -> RequirementType:
    normalized = text.casefold()
    if any(token in normalized for token in ("python", "langgraph", "llm", "skill", "技能")):
        return RequirementType.SKILL
    if any(token in normalized for token in ("degree", "bachelor", "master", "学历", "本科")):
        return RequirementType.EDUCATION
    if any(token in normalized for token in ("experience", "years", "经验", "年")):
        return RequirementType.EXPERIENCE
    if any(token in normalized for token in ("location", "remote", "on-site", "地点", "城市")):
        return RequirementType.LOCATION
    if any(token in normalized for token in ("build", "develop", "design", "负责", "开发")):
        return RequirementType.RESPONSIBILITY
    return RequirementType.OTHER


def _matches_any(value: str, candidates: tuple[str, ...]) -> bool:
    normalized = value.casefold()
    return any(candidate.casefold() in normalized for candidate in candidates)


def _recommend(
    *,
    title: str,
    city: str,
    requirements: tuple[ParsedRequirement, ...],
    profile: CandidateProfile,
) -> tuple[QuickScreenRecommendation, tuple[ScreenReasonCode, ...]]:
    if profile.preferred_cities and not _matches_any(city, profile.preferred_cities):
        return (
            QuickScreenRecommendation.SCREEN_OUT,
            (ScreenReasonCode.CITY_OUTSIDE_PREFERENCE,),
        )
    title_matches = _matches_any(title, profile.target_role_keywords)
    requirement_text = " ".join(requirement.text for requirement in requirements)
    skill_matches = _matches_any(requirement_text, profile.skill_keywords)
    if title_matches and skill_matches:
        return (
            QuickScreenRecommendation.SCREEN_IN,
            (ScreenReasonCode.TARGET_ROLE_MATCH, ScreenReasonCode.SKILL_OVERLAP),
        )
    return QuickScreenRecommendation.UNCERTAIN, (ScreenReasonCode.INSUFFICIENT_SIGNAL,)


@dataclass(frozen=True, slots=True)
class RunQuickScreenCommand:
    job_id: JobId
    correlation_id: CorrelationId
    run_id: RunId


@dataclass(frozen=True, slots=True)
class RunQuickScreenResult:
    quick_screen_result_id: QuickScreenResultId
    job_id: JobId
    job_version_id: JobVersionId
    candidate_profile_id: CandidateProfileId
    requirement_ids: tuple[RequirementId, ...]
    recommendation: QuickScreenRecommendation
    reason_codes: tuple[ScreenReasonCode, ...]
    policy_version: str
    lifecycle_status: JobLifecycleStatus
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId


class RunQuickScreen:
    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._id_generator = id_generator

    def execute(self, command: RunQuickScreenCommand) -> RunQuickScreenResult:
        try:
            unit_of_work = self._unit_of_work_factory()
        except JobHunterError:
            raise
        except Exception:
            # Factory failures happen before a transaction exists and must still
            # cross the Application boundary as a stable, non-sensitive error.
            raise DependencyUnavailableError("quick screen dependency is unavailable") from None
        try:
            job = unit_of_work.jobs.get_job(command.job_id)
            version = unit_of_work.jobs.get_version(job.active_version_id)
            profile = unit_of_work.knowledge.get_active_profile()
            requirements = unit_of_work.screening.list_requirements(version.version_id)
            now = self._clock.now()
            if not requirements:
                # Requirement IDs are allocated only once per immutable JobVersion;
                # reruns reuse lineage instead of fabricating equivalent identities.
                requirements = tuple(
                    ParsedRequirement(
                        requirement_id=self._id_generator.new_requirement_id(),
                        job_version_id=version.version_id,
                        source_text=line,
                        text=line,
                        requirement_type=_requirement_type(line),
                        priority=_priority(line),
                        parser_name=_PARSER_NAME,
                        parser_version=_PARSER_VERSION,
                        created_at=now,
                        correlation_id=command.correlation_id,
                        run_id=command.run_id,
                    )
                    for line in _requirement_lines(version.description)
                )
                unit_of_work.screening.add_requirements(requirements)
            recommendation, reason_codes = _recommend(
                title=version.title,
                city=version.city,
                requirements=requirements,
                profile=profile,
            )
            screen_result = QuickScreenResult(
                result_id=self._id_generator.new_quick_screen_result_id(),
                job_id=job.job_id,
                job_version_id=version.version_id,
                candidate_profile_id=profile.profile_id,
                requirement_ids=tuple(item.requirement_id for item in requirements),
                recommendation=recommendation,
                reason_codes=reason_codes,
                policy_version=_POLICY_VERSION,
                created_at=now,
                correlation_id=command.correlation_id,
                run_id=command.run_id,
            )
            screened_job = job.with_screening()
            unit_of_work.jobs.save_job(screened_job)
            unit_of_work.screening.add_quick_screen_result(screen_result)
            unit_of_work.commit()
        except JobHunterError:
            unit_of_work.rollback()
            raise
        except Exception:
            unit_of_work.rollback()
            raise DependencyUnavailableError("quick screen dependency is unavailable") from None
        return RunQuickScreenResult(
            quick_screen_result_id=screen_result.result_id,
            job_id=screen_result.job_id,
            job_version_id=screen_result.job_version_id,
            candidate_profile_id=screen_result.candidate_profile_id,
            requirement_ids=screen_result.requirement_ids,
            recommendation=screen_result.recommendation,
            reason_codes=screen_result.reason_codes,
            policy_version=screen_result.policy_version,
            lifecycle_status=screened_job.lifecycle_status,
            created_at=screen_result.created_at,
            correlation_id=screen_result.correlation_id,
            run_id=screen_result.run_id,
        )


@dataclass(frozen=True, slots=True)
class RecordJobTriageCommand:
    job_id: JobId
    quick_screen_result_id: QuickScreenResultId
    decision: TriageDecision
    correlation_id: CorrelationId
    run_id: RunId


@dataclass(frozen=True, slots=True)
class RecordJobTriageResult:
    triage_decision_id: TriageDecisionId
    job_id: JobId
    quick_screen_result_id: QuickScreenResultId
    recommendation: QuickScreenRecommendation
    decision: TriageDecision
    lifecycle_status: JobLifecycleStatus
    decided_at: datetime
    correlation_id: CorrelationId
    run_id: RunId


class RecordJobTriage:
    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._id_generator = id_generator

    def execute(self, command: RecordJobTriageCommand) -> RecordJobTriageResult:
        try:
            unit_of_work = self._unit_of_work_factory()
        except JobHunterError:
            raise
        except Exception:
            # Do not attempt rollback when construction itself failed.
            raise DependencyUnavailableError("job triage dependency is unavailable") from None
        try:
            job = unit_of_work.jobs.get_job(command.job_id)
            screen_result = unit_of_work.screening.get_quick_screen_result(
                command.quick_screen_result_id
            )
            latest = unit_of_work.screening.get_latest_quick_screen_result(command.job_id)
            if screen_result.job_id != job.job_id:
                raise ConflictError("quick screen result belongs to another job")
            if latest.result_id != screen_result.result_id:
                raise ConflictError("quick screen result is stale")
            if screen_result.job_version_id != job.active_version_id:
                raise ConflictError("quick screen result targets a stale job version")
            record = JobTriageRecord(
                decision_id=self._id_generator.new_triage_decision_id(),
                job_id=job.job_id,
                quick_screen_result_id=screen_result.result_id,
                decision=command.decision,
                decided_at=self._clock.now(),
                correlation_id=command.correlation_id,
                run_id=command.run_id,
            )
            triaged_job = job.with_triage_decision(command.decision)
            unit_of_work.jobs.save_job(triaged_job)
            unit_of_work.screening.add_triage_record(record)
            unit_of_work.commit()
        except JobHunterError:
            unit_of_work.rollback()
            raise
        except Exception:
            unit_of_work.rollback()
            raise DependencyUnavailableError("job triage dependency is unavailable") from None
        return RecordJobTriageResult(
            triage_decision_id=record.decision_id,
            job_id=record.job_id,
            quick_screen_result_id=record.quick_screen_result_id,
            recommendation=screen_result.recommendation,
            decision=record.decision,
            lifecycle_status=triaged_job.lifecycle_status,
            decided_at=record.decided_at,
            correlation_id=record.correlation_id,
            run_id=record.run_id,
        )
