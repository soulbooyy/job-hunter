"""Ports required by the current application slice."""

from datetime import datetime
from typing import Protocol

from job_hunter.domain.ids import (
    JobId,
    JobVersionId,
    SourceReferenceId,
    SourceSnapshotId,
)
from job_hunter.domain.jobs import Job, JobVersion, SourceSnapshot


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdGenerator(Protocol):
    def new_job_id(self) -> JobId: ...

    def new_job_version_id(self) -> JobVersionId: ...

    def new_source_snapshot_id(self) -> SourceSnapshotId: ...

    def new_source_reference_id(self) -> SourceReferenceId: ...


class JobRepository(Protocol):
    def get_job(self, job_id: JobId) -> Job: ...

    def get_version(self, version_id: JobVersionId) -> JobVersion: ...

    def get_snapshot(self, snapshot_id: SourceSnapshotId) -> SourceSnapshot: ...

    def add_job(self, job: Job) -> None: ...

    def save_job(self, job: Job) -> None: ...

    def add_version(self, version: JobVersion) -> None: ...

    def add_snapshot(self, snapshot: SourceSnapshot) -> None: ...


class UnitOfWork(Protocol):
    @property
    def jobs(self) -> JobRepository: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...
