"""Deterministic in-memory Repository and UnitOfWork adapter."""

from job_hunter.application.ports import JobRepository, UnitOfWork
from job_hunter.domain.ids import JobId, JobVersionId, SourceSnapshotId
from job_hunter.domain.jobs import Job, JobVersion, SourceSnapshot
from job_hunter.errors import ConflictError, EntityNotFoundError


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[JobId, Job] = {}
        self._versions: dict[JobVersionId, JobVersion] = {}
        self._snapshots: dict[SourceSnapshotId, SourceSnapshot] = {}

    def get_job(self, job_id: JobId) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError:
            raise EntityNotFoundError(f"job not found: {job_id}") from None

    def get_version(self, version_id: JobVersionId) -> JobVersion:
        try:
            return self._versions[version_id]
        except KeyError:
            raise EntityNotFoundError(f"job version not found: {version_id}") from None

    def get_snapshot(self, snapshot_id: SourceSnapshotId) -> SourceSnapshot:
        try:
            return self._snapshots[snapshot_id]
        except KeyError:
            raise EntityNotFoundError(f"source snapshot not found: {snapshot_id}") from None

    def is_empty(self) -> bool:
        return not self._jobs and not self._versions and not self._snapshots

    def copy_state(
        self,
    ) -> tuple[
        dict[JobId, Job],
        dict[JobVersionId, JobVersion],
        dict[SourceSnapshotId, SourceSnapshot],
    ]:
        # Frozen domain values make shallow copies sufficient. The copies isolate
        # staged writes until UnitOfWork.commit replaces the authoritative state.
        return dict(self._jobs), dict(self._versions), dict(self._snapshots)

    def replace_state(
        self,
        jobs: dict[JobId, Job],
        versions: dict[JobVersionId, JobVersion],
        snapshots: dict[SourceSnapshotId, SourceSnapshot],
    ) -> None:
        self._jobs = jobs
        self._versions = versions
        self._snapshots = snapshots


class _InMemoryJobRepository(JobRepository):
    def __init__(
        self,
        jobs: dict[JobId, Job],
        versions: dict[JobVersionId, JobVersion],
        snapshots: dict[SourceSnapshotId, SourceSnapshot],
    ) -> None:
        self.jobs = jobs
        self.versions = versions
        self.snapshots = snapshots

    def get_job(self, job_id: JobId) -> Job:
        try:
            return self.jobs[job_id]
        except KeyError:
            raise EntityNotFoundError(f"job not found: {job_id}") from None

    def get_version(self, version_id: JobVersionId) -> JobVersion:
        try:
            return self.versions[version_id]
        except KeyError:
            raise EntityNotFoundError(f"job version not found: {version_id}") from None

    def get_snapshot(self, snapshot_id: SourceSnapshotId) -> SourceSnapshot:
        try:
            return self.snapshots[snapshot_id]
        except KeyError:
            raise EntityNotFoundError(f"source snapshot not found: {snapshot_id}") from None

    def add_job(self, job: Job) -> None:
        if job.job_id in self.jobs:
            raise ConflictError(f"job already exists: {job.job_id}")
        self.jobs[job.job_id] = job

    def save_job(self, job: Job) -> None:
        if job.job_id not in self.jobs:
            raise EntityNotFoundError(f"job not found: {job.job_id}")
        self.jobs[job.job_id] = job

    def add_version(self, version: JobVersion) -> None:
        if version.version_id in self.versions:
            raise ConflictError(f"job version already exists: {version.version_id}")
        self.versions[version.version_id] = version

    def add_snapshot(self, snapshot: SourceSnapshot) -> None:
        if snapshot.snapshot_id in self.snapshots:
            raise ConflictError(f"source snapshot already exists: {snapshot.snapshot_id}")
        self.snapshots[snapshot.snapshot_id] = snapshot


class _InMemoryUnitOfWork(UnitOfWork):
    def __init__(self, store: InMemoryJobStore) -> None:
        self._store = store
        self._jobs_data, self._versions_data, self._snapshots_data = store.copy_state()
        self._repository = _InMemoryJobRepository(
            self._jobs_data,
            self._versions_data,
            self._snapshots_data,
        )

    @property
    def jobs(self) -> JobRepository:
        return self._repository

    def commit(self) -> None:
        # Replace all three collections as one in-memory transaction so a Job cannot
        # point at a version or snapshot that was not committed with it.
        self._store.replace_state(
            self._jobs_data,
            self._versions_data,
            self._snapshots_data,
        )

    def rollback(self) -> None:
        self._jobs_data.clear()
        self._versions_data.clear()
        self._snapshots_data.clear()


class InMemoryUnitOfWorkFactory:
    def __init__(self, store: InMemoryJobStore) -> None:
        self._store = store

    def __call__(self) -> UnitOfWork:
        return _InMemoryUnitOfWork(self._store)
