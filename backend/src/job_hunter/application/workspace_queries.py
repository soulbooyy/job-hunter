"""Typed read projections for restoring the current local workspace."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from job_hunter.application.ports import UnitOfWork, UnitOfWorkFactory
from job_hunter.domain.ids import (
    CandidateProfileId,
    CorrelationId,
    EvidenceItemId,
    EvidenceVersionId,
    JobId,
    JobVersionId,
    QuickScreenResultId,
    RequirementId,
    RunId,
    SourceReferenceId,
    SourceSnapshotId,
    TriageDecisionId,
)
from job_hunter.domain.jobs import FreshnessStatus, Job, JobLifecycleStatus, SourceKind
from job_hunter.domain.knowledge import EvidenceSensitivity, EvidenceType, EvidenceValidity
from job_hunter.domain.screening import (
    QuickScreenRecommendation,
    RequirementPriority,
    RequirementType,
    ScreenReasonCode,
    TriageDecision,
)
from job_hunter.errors import DependencyUnavailableError, JobHunterError


class ProfileReadStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"


class JobVersionReadStatus(StrEnum):
    CURRENT = "current"
    HISTORICAL = "historical"


@dataclass(frozen=True, slots=True)
class SourceReadModel:
    reference_id: SourceReferenceId
    snapshot_id: SourceSnapshotId
    kind: SourceKind
    locator: str | None
    captured_at: datetime
    last_verified_at: datetime
    freshness: FreshnessStatus


@dataclass(frozen=True, slots=True)
class JobVersionReadModel:
    version_id: JobVersionId
    job_id: JobId
    version_number: int
    title: str
    company: str
    city: str
    description: str
    source_snapshot_id: SourceSnapshotId
    source: SourceReadModel
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId
    is_active: bool


@dataclass(frozen=True, slots=True)
class RequirementReadModel:
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


@dataclass(frozen=True, slots=True)
class QuickScreenReadModel:
    result_id: QuickScreenResultId
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
    profile_status: ProfileReadStatus
    job_version_status: JobVersionReadStatus
    is_latest_result: bool
    triage_eligible: bool


@dataclass(frozen=True, slots=True)
class TriageReadModel:
    decision_id: TriageDecisionId
    job_id: JobId
    quick_screen_result_id: QuickScreenResultId
    recommendation: QuickScreenRecommendation
    decision: TriageDecision
    lifecycle_status: JobLifecycleStatus
    decided_at: datetime
    correlation_id: CorrelationId
    run_id: RunId


@dataclass(frozen=True, slots=True)
class JobSummaryReadModel:
    job_id: JobId
    active_version_id: JobVersionId
    version_number: int
    title: str
    company: str
    city: str
    lifecycle_status: JobLifecycleStatus
    source: SourceReadModel
    current_screen_recommendation: QuickScreenRecommendation | None
    current_triage_decision: TriageDecision | None


@dataclass(frozen=True, slots=True)
class JobListResult:
    items: tuple[JobSummaryReadModel, ...]


@dataclass(frozen=True, slots=True)
class JobWorkspaceResult:
    job_id: JobId
    active_version_id: JobVersionId
    lifecycle_status: JobLifecycleStatus
    versions: tuple[JobVersionReadModel, ...]
    requirements: tuple[RequirementReadModel, ...]
    screening_results: tuple[QuickScreenReadModel, ...]
    triage_history: tuple[TriageReadModel, ...]


@dataclass(frozen=True, slots=True)
class CandidateProfileReadModel:
    profile_id: CandidateProfileId
    target_role_keywords: tuple[str, ...]
    skill_keywords: tuple[str, ...]
    preferred_cities: tuple[str, ...]
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId


@dataclass(frozen=True, slots=True)
class ProfileHistoryResult:
    active_profile_id: CandidateProfileId | None
    items: tuple[CandidateProfileReadModel, ...]


@dataclass(frozen=True, slots=True)
class EvidenceVersionReadModel:
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
    is_active: bool


@dataclass(frozen=True, slots=True)
class EvidenceItemReadModel:
    evidence_id: EvidenceItemId
    active_version_id: EvidenceVersionId
    versions: tuple[EvidenceVersionReadModel, ...]


@dataclass(frozen=True, slots=True)
class EvidenceHistoryResult:
    items: tuple[EvidenceItemReadModel, ...]


class WorkspaceQueries:
    """Build read models from one consistent UnitOfWork snapshot per request."""

    def __init__(self, *, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def _read[T](self, operation: Callable[[UnitOfWork], T]) -> T:
        try:
            unit_of_work = self._unit_of_work_factory()
        except JobHunterError:
            raise
        except Exception:
            raise DependencyUnavailableError("workspace read dependency is unavailable") from None
        try:
            return operation(unit_of_work)
        except JobHunterError:
            unit_of_work.rollback()
            raise
        except Exception:
            unit_of_work.rollback()
            raise DependencyUnavailableError("workspace read dependency is unavailable") from None
        finally:
            unit_of_work.close()

    def list_jobs(self) -> JobListResult:
        return self._read(self._list_jobs)

    def get_job(self, job_id: JobId) -> JobWorkspaceResult:
        return self._read(lambda unit_of_work: self._get_job(unit_of_work, job_id))

    def list_profiles(self) -> ProfileHistoryResult:
        return self._read(self._list_profiles)

    def list_evidence(self) -> EvidenceHistoryResult:
        return self._read(self._list_evidence)

    @staticmethod
    def _source(unit_of_work: UnitOfWork, job: Job, version_id: JobVersionId) -> SourceReadModel:
        version_index = job.version_ids.index(version_id)
        reference = job.source_references[version_index]
        snapshot = unit_of_work.jobs.get_snapshot(reference.snapshot_id)
        return SourceReadModel(
            reference_id=reference.reference_id,
            snapshot_id=snapshot.snapshot_id,
            kind=snapshot.source_kind,
            locator=snapshot.source_locator,
            captured_at=snapshot.captured_at,
            last_verified_at=snapshot.last_verified_at,
            freshness=snapshot.freshness.status,
        )

    @classmethod
    def _version(
        cls,
        unit_of_work: UnitOfWork,
        job: Job,
        version_id: JobVersionId,
    ) -> JobVersionReadModel:
        version = unit_of_work.jobs.get_version(version_id)
        return JobVersionReadModel(
            version_id=version.version_id,
            job_id=version.job_id,
            version_number=version.version_number,
            title=version.title,
            company=version.company,
            city=version.city,
            description=version.description,
            source_snapshot_id=version.source_snapshot_id,
            source=cls._source(unit_of_work, job, version.version_id),
            created_at=version.created_at,
            correlation_id=version.correlation_id,
            run_id=version.run_id,
            is_active=version.version_id == job.active_version_id,
        )

    @classmethod
    def _summary(cls, unit_of_work: UnitOfWork, job: Job) -> JobSummaryReadModel:
        version = cls._version(unit_of_work, job, job.active_version_id)
        screens = unit_of_work.screening.list_quick_screen_results(job.job_id)
        current_screen = next(
            (
                screen
                for screen in screens
                if screen.result_id == job.latest_quick_screen_result_id
                and screen.job_version_id == version.version_id
            ),
            None,
        )
        triage_records = unit_of_work.screening.list_triage_records(job.job_id)
        current_triage = next(
            (
                record
                for record in reversed(triage_records)
                if current_screen is not None
                and record.quick_screen_result_id == current_screen.result_id
            ),
            None,
        )
        return JobSummaryReadModel(
            job_id=job.job_id,
            active_version_id=job.active_version_id,
            version_number=version.version_number,
            title=version.title,
            company=version.company,
            city=version.city,
            lifecycle_status=job.lifecycle_status,
            source=version.source,
            current_screen_recommendation=(
                current_screen.recommendation if current_screen is not None else None
            ),
            current_triage_decision=(
                current_triage.decision if current_triage is not None else None
            ),
        )

    @classmethod
    def _list_jobs(cls, unit_of_work: UnitOfWork) -> JobListResult:
        summaries = [cls._summary(unit_of_work, job) for job in unit_of_work.jobs.list_jobs()]
        # Stable ID ordering is the tie-breaker when deterministic clocks produce
        # identical timestamps in tests or batch imports.
        summaries.sort(key=lambda item: str(item.job_id))
        summaries.sort(key=lambda item: item.source.captured_at, reverse=True)
        return JobListResult(items=tuple(summaries))

    @classmethod
    def _get_job(cls, unit_of_work: UnitOfWork, job_id: JobId) -> JobWorkspaceResult:
        job = unit_of_work.jobs.get_job(job_id)
        versions = tuple(cls._version(unit_of_work, job, item_id) for item_id in job.version_ids)
        requirements = tuple(
            RequirementReadModel(
                requirement_id=requirement.requirement_id,
                job_version_id=requirement.job_version_id,
                source_text=requirement.source_text,
                text=requirement.text,
                requirement_type=requirement.requirement_type,
                priority=requirement.priority,
                parser_name=requirement.parser_name,
                parser_version=requirement.parser_version,
                created_at=requirement.created_at,
                correlation_id=requirement.correlation_id,
                run_id=requirement.run_id,
            )
            for version_id in job.version_ids
            for requirement in unit_of_work.screening.list_requirements(version_id)
        )
        screens = unit_of_work.screening.list_quick_screen_results(job.job_id)
        active_profile_id = unit_of_work.knowledge.get_active_profile_id()
        latest_result_id = job.latest_quick_screen_result_id
        screening_results = tuple(
            QuickScreenReadModel(
                result_id=result.result_id,
                job_id=result.job_id,
                job_version_id=result.job_version_id,
                candidate_profile_id=result.candidate_profile_id,
                requirement_ids=result.requirement_ids,
                recommendation=result.recommendation,
                reason_codes=result.reason_codes,
                policy_version=result.policy_version,
                lifecycle_status=JobLifecycleStatus.SCREENED,
                created_at=result.created_at,
                correlation_id=result.correlation_id,
                run_id=result.run_id,
                profile_status=(
                    ProfileReadStatus.CURRENT
                    if result.candidate_profile_id == active_profile_id
                    else ProfileReadStatus.STALE
                ),
                job_version_status=(
                    JobVersionReadStatus.CURRENT
                    if result.job_version_id == job.active_version_id
                    else JobVersionReadStatus.HISTORICAL
                ),
                is_latest_result=result.result_id == latest_result_id,
                # Profile freshness is advisory. Only superseded results or an old
                # JobVersion make a historical recommendation ineligible for Triage.
                triage_eligible=(
                    result.result_id == latest_result_id
                    and result.job_version_id == job.active_version_id
                ),
            )
            for result in screens
        )
        recommendations = {result.result_id: result.recommendation for result in screens}
        triage_history = tuple(
            TriageReadModel(
                decision_id=record.decision_id,
                job_id=record.job_id,
                quick_screen_result_id=record.quick_screen_result_id,
                recommendation=recommendations[record.quick_screen_result_id],
                decision=record.decision,
                lifecycle_status=(
                    JobLifecycleStatus.SHORTLISTED
                    if record.decision is TriageDecision.SHORTLISTED
                    else JobLifecycleStatus.SKIPPED
                ),
                decided_at=record.decided_at,
                correlation_id=record.correlation_id,
                run_id=record.run_id,
            )
            for record in unit_of_work.screening.list_triage_records(job.job_id)
        )
        return JobWorkspaceResult(
            job_id=job.job_id,
            active_version_id=job.active_version_id,
            lifecycle_status=job.lifecycle_status,
            versions=versions,
            requirements=requirements,
            screening_results=screening_results,
            triage_history=triage_history,
        )

    @staticmethod
    def _list_profiles(unit_of_work: UnitOfWork) -> ProfileHistoryResult:
        profiles = sorted(
            unit_of_work.knowledge.list_profiles(),
            key=lambda profile: (profile.created_at, str(profile.profile_id)),
        )
        return ProfileHistoryResult(
            active_profile_id=unit_of_work.knowledge.get_active_profile_id(),
            items=tuple(
                CandidateProfileReadModel(
                    profile_id=profile.profile_id,
                    target_role_keywords=profile.target_role_keywords,
                    skill_keywords=profile.skill_keywords,
                    preferred_cities=profile.preferred_cities,
                    created_at=profile.created_at,
                    correlation_id=profile.correlation_id,
                    run_id=profile.run_id,
                )
                for profile in profiles
            ),
        )

    @staticmethod
    def _list_evidence(unit_of_work: UnitOfWork) -> EvidenceHistoryResult:
        items: list[EvidenceItemReadModel] = []
        for evidence in unit_of_work.knowledge.list_evidence():
            versions = tuple(
                unit_of_work.knowledge.get_evidence_version(version_id)
                for version_id in evidence.version_ids
            )
            items.append(
                EvidenceItemReadModel(
                    evidence_id=evidence.evidence_id,
                    active_version_id=evidence.active_version_id,
                    versions=tuple(
                        EvidenceVersionReadModel(
                            version_id=version.version_id,
                            evidence_id=version.evidence_id,
                            version_number=version.version_number,
                            evidence_type=version.evidence_type,
                            canonical_content=version.canonical_content,
                            occurred_on=version.occurred_on,
                            source=version.source,
                            provenance=version.provenance,
                            sensitivity=version.sensitivity,
                            validity=version.validity,
                            created_at=version.created_at,
                            correlation_id=version.correlation_id,
                            run_id=version.run_id,
                            is_active=version.version_id == evidence.active_version_id,
                        )
                        for version in versions
                    ),
                )
            )
        items.sort(key=lambda item: str(item.evidence_id))
        items.sort(key=lambda item: item.versions[-1].created_at, reverse=True)
        return EvidenceHistoryResult(items=tuple(items))
