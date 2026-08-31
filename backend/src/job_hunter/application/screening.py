"""Deterministic requirement parsing, QuickScreen, and human Job Triage."""

from dataclasses import dataclass
from datetime import datetime

from job_hunter.application.ports import Clock, IdGenerator, UnitOfWorkFactory
from job_hunter.application.quick_screen_policy import (
    QUICK_SCREEN_POLICY_VERSION,
    recommend_quick_screen,
)
from job_hunter.application.requirement_parsing import DeterministicRequirementParser
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
from job_hunter.domain.screening import (
    JobTriageRecord,
    ParsedRequirement,
    QuickScreenRecommendation,
    QuickScreenResult,
    ScreenReasonCode,
    TriageDecision,
)
from job_hunter.errors import ConflictError, DependencyUnavailableError, JobHunterError


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
                parser = DeterministicRequirementParser()
                requirements = tuple(
                    ParsedRequirement(
                        requirement_id=self._id_generator.new_requirement_id(),
                        job_version_id=version.version_id,
                        source_text=draft.source_text,
                        text=draft.text,
                        requirement_type=draft.requirement_type,
                        priority=draft.priority,
                        parser_name=parser.name,
                        parser_version=parser.version,
                        created_at=now,
                        correlation_id=command.correlation_id,
                        run_id=command.run_id,
                    )
                    for draft in parser.parse(version.description)
                )
                unit_of_work.screening.add_requirements(requirements)
            recommendation, reason_codes = recommend_quick_screen(
                title=version.title,
                city=version.city,
                requirement_texts=tuple(item.text for item in requirements),
                target_role_keywords=profile.target_role_keywords,
                skill_keywords=profile.skill_keywords,
                preferred_cities=profile.preferred_cities,
            )
            screen_result = QuickScreenResult(
                result_id=self._id_generator.new_quick_screen_result_id(),
                job_id=job.job_id,
                job_version_id=version.version_id,
                candidate_profile_id=profile.profile_id,
                requirement_ids=tuple(item.requirement_id for item in requirements),
                recommendation=recommendation,
                reason_codes=reason_codes,
                policy_version=QUICK_SCREEN_POLICY_VERSION,
                created_at=now,
                correlation_id=command.correlation_id,
                run_id=command.run_id,
            )
            screened_job = job.with_screening(screen_result.result_id)
            unit_of_work.jobs.save_job(screened_job)
            unit_of_work.screening.add_quick_screen_result(screen_result)
            unit_of_work.commit()
        except JobHunterError:
            unit_of_work.rollback()
            raise
        except Exception:
            unit_of_work.rollback()
            raise DependencyUnavailableError("quick screen dependency is unavailable") from None
        finally:
            unit_of_work.close()
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
            if screen_result.job_id != job.job_id:
                raise ConflictError("quick screen result belongs to another job")
            # The Job pointer is the transactionally guarded authority. Repository
            # append order is history, not permission to triage a concurrent result.
            if job.latest_quick_screen_result_id != screen_result.result_id:
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
        finally:
            unit_of_work.close()
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
