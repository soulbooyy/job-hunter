"""Deterministic single-writer in-memory Repository and UnitOfWork adapter."""

from dataclasses import dataclass

from job_hunter.application.ports import (
    CandidateKnowledgeRepository,
    JobRepository,
    ScreeningRepository,
    UnitOfWork,
)
from job_hunter.domain.ids import (
    CandidateProfileId,
    EvidenceItemId,
    EvidenceVersionId,
    JobId,
    JobVersionId,
    QuickScreenResultId,
    RequirementId,
    SourceSnapshotId,
    TriageDecisionId,
)
from job_hunter.domain.jobs import Job, JobVersion, SourceSnapshot
from job_hunter.domain.knowledge import CandidateProfile, EvidenceItem, EvidenceItemVersion
from job_hunter.domain.screening import JobTriageRecord, ParsedRequirement, QuickScreenResult
from job_hunter.errors import ConflictError, EntityNotFoundError


@dataclass(slots=True)
class _MemoryState:
    jobs: dict[JobId, Job]
    job_versions: dict[JobVersionId, JobVersion]
    snapshots: dict[SourceSnapshotId, SourceSnapshot]
    profiles: dict[CandidateProfileId, CandidateProfile]
    active_profile_id: CandidateProfileId | None
    evidence_items: dict[EvidenceItemId, EvidenceItem]
    evidence_versions: dict[EvidenceVersionId, EvidenceItemVersion]
    requirements: dict[RequirementId, ParsedRequirement]
    requirement_ids_by_version: dict[JobVersionId, tuple[RequirementId, ...]]
    screen_results: dict[QuickScreenResultId, QuickScreenResult]
    screen_result_ids_by_job: dict[JobId, tuple[QuickScreenResultId, ...]]
    triage_records: dict[TriageDecisionId, JobTriageRecord]
    triage_ids_by_job: dict[JobId, tuple[TriageDecisionId, ...]]

    def copy(self) -> "_MemoryState":
        # Frozen domain values make shallow copies sufficient. Copying every index
        # keeps staged writes and their lineage invisible until one atomic commit.
        return _MemoryState(
            jobs=dict(self.jobs),
            job_versions=dict(self.job_versions),
            snapshots=dict(self.snapshots),
            profiles=dict(self.profiles),
            active_profile_id=self.active_profile_id,
            evidence_items=dict(self.evidence_items),
            evidence_versions=dict(self.evidence_versions),
            requirements=dict(self.requirements),
            requirement_ids_by_version=dict(self.requirement_ids_by_version),
            screen_results=dict(self.screen_results),
            screen_result_ids_by_job=dict(self.screen_result_ids_by_job),
            triage_records=dict(self.triage_records),
            triage_ids_by_job=dict(self.triage_ids_by_job),
        )


def _empty_state() -> _MemoryState:
    return _MemoryState({}, {}, {}, {}, None, {}, {}, {}, {}, {}, {}, {}, {})


class InMemoryStore:
    def __init__(self) -> None:
        self._state = _empty_state()

    def get_job(self, job_id: JobId) -> Job:
        return _InMemoryJobRepository(self._state).get_job(job_id)

    def get_version(self, version_id: JobVersionId) -> JobVersion:
        return _InMemoryJobRepository(self._state).get_version(version_id)

    def get_snapshot(self, snapshot_id: SourceSnapshotId) -> SourceSnapshot:
        return _InMemoryJobRepository(self._state).get_snapshot(snapshot_id)

    def get_active_profile(self) -> CandidateProfile:
        return _InMemoryCandidateKnowledgeRepository(self._state).get_active_profile()

    def get_profile(self, profile_id: CandidateProfileId) -> CandidateProfile:
        return _InMemoryCandidateKnowledgeRepository(self._state).get_profile(profile_id)

    def get_evidence(self, evidence_id: EvidenceItemId) -> EvidenceItem:
        return _InMemoryCandidateKnowledgeRepository(self._state).get_evidence(evidence_id)

    def get_evidence_version(self, version_id: EvidenceVersionId) -> EvidenceItemVersion:
        return _InMemoryCandidateKnowledgeRepository(self._state).get_evidence_version(version_id)

    def list_requirements(self, job_version_id: JobVersionId) -> tuple[ParsedRequirement, ...]:
        return _InMemoryScreeningRepository(self._state).list_requirements(job_version_id)

    def get_requirement(self, requirement_id: RequirementId) -> ParsedRequirement:
        return _InMemoryScreeningRepository(self._state).get_requirement(requirement_id)

    def get_quick_screen_result(self, result_id: QuickScreenResultId) -> QuickScreenResult:
        return _InMemoryScreeningRepository(self._state).get_quick_screen_result(result_id)

    def list_triage_records(self, job_id: JobId) -> tuple[JobTriageRecord, ...]:
        return _InMemoryScreeningRepository(self._state).list_triage_records(job_id)

    def is_empty(self) -> bool:
        state = self._state
        return not any(
            (
                state.jobs,
                state.job_versions,
                state.snapshots,
                state.profiles,
                state.evidence_items,
                state.evidence_versions,
                state.requirements,
                state.screen_results,
                state.triage_records,
            )
        )

    def copy_state(self) -> _MemoryState:
        return self._state.copy()

    def replace_state(self, state: _MemoryState) -> None:
        self._state = state


class _InMemoryJobRepository(JobRepository):
    def __init__(self, state: _MemoryState) -> None:
        self._state = state

    def list_jobs(self) -> tuple[Job, ...]:
        return tuple(self._state.jobs.values())

    def get_job(self, job_id: JobId) -> Job:
        try:
            return self._state.jobs[job_id]
        except KeyError:
            raise EntityNotFoundError(f"job not found: {job_id}") from None

    def get_version(self, version_id: JobVersionId) -> JobVersion:
        try:
            return self._state.job_versions[version_id]
        except KeyError:
            raise EntityNotFoundError(f"job version not found: {version_id}") from None

    def get_snapshot(self, snapshot_id: SourceSnapshotId) -> SourceSnapshot:
        try:
            return self._state.snapshots[snapshot_id]
        except KeyError:
            raise EntityNotFoundError(f"source snapshot not found: {snapshot_id}") from None

    def add_job(self, job: Job) -> None:
        if job.job_id in self._state.jobs:
            raise ConflictError(f"job already exists: {job.job_id}")
        self._state.jobs[job.job_id] = job

    def save_job(self, job: Job) -> None:
        if job.job_id not in self._state.jobs:
            raise EntityNotFoundError(f"job not found: {job.job_id}")
        self._state.jobs[job.job_id] = job

    def add_version(self, version: JobVersion) -> None:
        if version.version_id in self._state.job_versions:
            raise ConflictError(f"job version already exists: {version.version_id}")
        self._state.job_versions[version.version_id] = version

    def add_snapshot(self, snapshot: SourceSnapshot) -> None:
        if snapshot.snapshot_id in self._state.snapshots:
            raise ConflictError(f"source snapshot already exists: {snapshot.snapshot_id}")
        self._state.snapshots[snapshot.snapshot_id] = snapshot


class _InMemoryCandidateKnowledgeRepository(CandidateKnowledgeRepository):
    def __init__(self, state: _MemoryState) -> None:
        self._state = state

    def list_profiles(self) -> tuple[CandidateProfile, ...]:
        return tuple(self._state.profiles.values())

    def get_active_profile_id(self) -> CandidateProfileId | None:
        return self._state.active_profile_id

    def get_profile(self, profile_id: CandidateProfileId) -> CandidateProfile:
        try:
            return self._state.profiles[profile_id]
        except KeyError:
            raise EntityNotFoundError(f"candidate profile not found: {profile_id}") from None

    def get_active_profile(self) -> CandidateProfile:
        profile_id = self._state.active_profile_id
        if profile_id is None:
            raise EntityNotFoundError("candidate profile not found")
        return self.get_profile(profile_id)

    def add_profile(self, profile: CandidateProfile) -> None:
        if profile.profile_id in self._state.profiles:
            raise ConflictError(f"candidate profile already exists: {profile.profile_id}")
        self._state.profiles[profile.profile_id] = profile
        self._state.active_profile_id = profile.profile_id

    def get_evidence(self, evidence_id: EvidenceItemId) -> EvidenceItem:
        try:
            return self._state.evidence_items[evidence_id]
        except KeyError:
            raise EntityNotFoundError(f"evidence not found: {evidence_id}") from None

    def list_evidence(self) -> tuple[EvidenceItem, ...]:
        return tuple(self._state.evidence_items.values())

    def get_evidence_version(self, version_id: EvidenceVersionId) -> EvidenceItemVersion:
        try:
            return self._state.evidence_versions[version_id]
        except KeyError:
            raise EntityNotFoundError(f"evidence version not found: {version_id}") from None

    def add_evidence(self, evidence: EvidenceItem) -> None:
        if evidence.evidence_id in self._state.evidence_items:
            raise ConflictError(f"evidence already exists: {evidence.evidence_id}")
        self._state.evidence_items[evidence.evidence_id] = evidence

    def save_evidence(self, evidence: EvidenceItem) -> None:
        if evidence.evidence_id not in self._state.evidence_items:
            raise EntityNotFoundError(f"evidence not found: {evidence.evidence_id}")
        self._state.evidence_items[evidence.evidence_id] = evidence

    def add_evidence_version(self, version: EvidenceItemVersion) -> None:
        if version.version_id in self._state.evidence_versions:
            raise ConflictError(f"evidence version already exists: {version.version_id}")
        self._state.evidence_versions[version.version_id] = version


class _InMemoryScreeningRepository(ScreeningRepository):
    def __init__(self, state: _MemoryState) -> None:
        self._state = state

    def get_requirement(self, requirement_id: RequirementId) -> ParsedRequirement:
        try:
            return self._state.requirements[requirement_id]
        except KeyError:
            raise EntityNotFoundError(f"requirement not found: {requirement_id}") from None

    def list_requirements(self, job_version_id: JobVersionId) -> tuple[ParsedRequirement, ...]:
        requirement_ids = self._state.requirement_ids_by_version.get(job_version_id, ())
        return tuple(self.get_requirement(item_id) for item_id in requirement_ids)

    def add_requirements(self, requirements: tuple[ParsedRequirement, ...]) -> None:
        if not requirements:
            return
        job_version_id = requirements[0].job_version_id
        if job_version_id in self._state.requirement_ids_by_version:
            raise ConflictError(f"requirements already exist for job version: {job_version_id}")
        if any(requirement.job_version_id != job_version_id for requirement in requirements):
            raise ConflictError("requirements must belong to one job version")
        for requirement in requirements:
            if requirement.requirement_id in self._state.requirements:
                raise ConflictError(f"requirement already exists: {requirement.requirement_id}")
            self._state.requirements[requirement.requirement_id] = requirement
        self._state.requirement_ids_by_version[job_version_id] = tuple(
            requirement.requirement_id for requirement in requirements
        )

    def get_quick_screen_result(self, result_id: QuickScreenResultId) -> QuickScreenResult:
        try:
            return self._state.screen_results[result_id]
        except KeyError:
            raise EntityNotFoundError(f"quick screen result not found: {result_id}") from None

    def get_latest_quick_screen_result(self, job_id: JobId) -> QuickScreenResult:
        result_ids = self._state.screen_result_ids_by_job.get(job_id, ())
        if not result_ids:
            raise EntityNotFoundError(f"quick screen result not found for job: {job_id}")
        return self._state.screen_results[result_ids[-1]]

    def list_quick_screen_results(self, job_id: JobId) -> tuple[QuickScreenResult, ...]:
        result_ids = self._state.screen_result_ids_by_job.get(job_id, ())
        return tuple(self._state.screen_results[item_id] for item_id in result_ids)

    def add_quick_screen_result(self, result: QuickScreenResult) -> None:
        if result.result_id in self._state.screen_results:
            raise ConflictError(f"quick screen result already exists: {result.result_id}")
        self._state.screen_results[result.result_id] = result
        existing = self._state.screen_result_ids_by_job.get(result.job_id, ())
        self._state.screen_result_ids_by_job[result.job_id] = (*existing, result.result_id)

    def add_triage_record(self, record: JobTriageRecord) -> None:
        if record.decision_id in self._state.triage_records:
            raise ConflictError(f"triage decision already exists: {record.decision_id}")
        self._state.triage_records[record.decision_id] = record
        existing = self._state.triage_ids_by_job.get(record.job_id, ())
        self._state.triage_ids_by_job[record.job_id] = (*existing, record.decision_id)

    def list_triage_records(self, job_id: JobId) -> tuple[JobTriageRecord, ...]:
        decision_ids = self._state.triage_ids_by_job.get(job_id, ())
        return tuple(self._state.triage_records[item_id] for item_id in decision_ids)


class _InMemoryUnitOfWork(UnitOfWork):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self._state = store.copy_state()
        self._jobs = _InMemoryJobRepository(self._state)
        self._knowledge = _InMemoryCandidateKnowledgeRepository(self._state)
        self._screening = _InMemoryScreeningRepository(self._state)

    @property
    def jobs(self) -> JobRepository:
        return self._jobs

    @property
    def knowledge(self) -> CandidateKnowledgeRepository:
        return self._knowledge

    @property
    def screening(self) -> ScreeningRepository:
        return self._screening

    def commit(self) -> None:
        # All aggregate and lineage indexes move together; this is atomic only for a
        # single writer and deliberately does not claim concurrent isolation.
        self._store.replace_state(self._state)

    def rollback(self) -> None:
        self._state = _empty_state()


class InMemoryUnitOfWorkFactory:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def __call__(self) -> UnitOfWork:
        return _InMemoryUnitOfWork(self._store)
