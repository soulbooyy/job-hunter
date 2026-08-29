from collections import defaultdict
from datetime import datetime

from job_hunter.domain.ids import (
    JobId,
    JobVersionId,
    SourceReferenceId,
    SourceSnapshotId,
)


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def now(self) -> datetime:
        return self._value


class DeterministicIdGenerator:
    def __init__(self) -> None:
        self._counts: defaultdict[str, int] = defaultdict(int)

    def _next(self, kind: str) -> str:
        self._counts[kind] += 1
        return f"{kind}-{self._counts[kind]:03d}"

    def new_job_id(self) -> JobId:
        return JobId(self._next("job"))

    def new_job_version_id(self) -> JobVersionId:
        return JobVersionId(self._next("job-version"))

    def new_source_snapshot_id(self) -> SourceSnapshotId:
        return SourceSnapshotId(self._next("source-snapshot"))

    def new_source_reference_id(self) -> SourceReferenceId:
        return SourceReferenceId(self._next("source-reference"))
