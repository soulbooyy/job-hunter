"""Local runtime implementations of deterministic control-plane ports."""

from datetime import UTC, datetime
from uuid import uuid4

from job_hunter.domain.ids import JobId, JobVersionId, SourceReferenceId, SourceSnapshotId


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class UuidIdGenerator:
    def new_job_id(self) -> JobId:
        return JobId(f"job-{uuid4().hex}")

    def new_job_version_id(self) -> JobVersionId:
        return JobVersionId(f"job-version-{uuid4().hex}")

    def new_source_snapshot_id(self) -> SourceSnapshotId:
        return SourceSnapshotId(f"source-snapshot-{uuid4().hex}")

    def new_source_reference_id(self) -> SourceReferenceId:
        return SourceReferenceId(f"source-reference-{uuid4().hex}")
