"""Import a validated manual source into versioned Job domain state."""

from dataclasses import dataclass
from datetime import datetime

from job_hunter.application.ports import Clock, IdGenerator, UnitOfWorkFactory
from job_hunter.domain.ids import CorrelationId, JobId, JobVersionId, RunId, SourceSnapshotId
from job_hunter.domain.jobs import (
    Freshness,
    FreshnessStatus,
    Job,
    JobLifecycleStatus,
    JobVersion,
    SourceKind,
    SourceReference,
    SourceSnapshot,
)
from job_hunter.errors import DependencyUnavailableError, JobHunterError
from job_hunter.ingestion.manual import (
    JobSourceRegistry,
    ManualJDInput,
    ManualSourceInput,
    ValidatedSourceData,
)


@dataclass(frozen=True, slots=True)
class ImportJobCommand:
    source_input: ManualSourceInput
    correlation_id: CorrelationId
    run_id: RunId
    existing_job_id: JobId | None = None


@dataclass(frozen=True, slots=True)
class ImportJobResult:
    job_id: JobId
    job_version_id: JobVersionId
    active_version_id: JobVersionId
    source_snapshot_id: SourceSnapshotId
    version_number: int
    lifecycle_status: JobLifecycleStatus
    source_kind: SourceKind
    source_locator: str | None
    captured_at: datetime
    last_verified_at: datetime
    freshness_status: FreshnessStatus
    correlation_id: CorrelationId
    run_id: RunId


def _source_kind(source_input: ManualSourceInput) -> SourceKind:
    if isinstance(source_input, ManualJDInput):
        return SourceKind.MANUAL_JD
    return SourceKind.MANUAL_URL


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _normalize_description(value: str) -> str:
    # Preserve validated line boundaries because deterministic requirement parsing
    # treats JD bullets/lines as reviewable source units; normalize only within lines.
    lines = tuple(_normalize_whitespace(line) for line in value.splitlines() if line.strip())
    return "\n".join(lines)


class ImportJob:
    def __init__(
        self,
        *,
        source_registry: JobSourceRegistry,
        unit_of_work_factory: UnitOfWorkFactory,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._source_registry = source_registry
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._id_generator = id_generator

    def execute(self, command: ImportJobCommand) -> ImportJobResult:
        try:
            return self._execute(command)
        except JobHunterError:
            raise
        except Exception:
            # Control-plane adapters must not leak implementation or secret-bearing
            # exception text into the application/API contract.
            raise DependencyUnavailableError("job import dependency is unavailable") from None

    def _execute(self, command: ImportJobCommand) -> ImportJobResult:
        # Source validation deliberately precedes ID allocation and UnitOfWork creation:
        # invalid external input must never produce or stage domain state.
        captured = self._capture(command.source_input)
        now = self._clock.now()
        freshness = Freshness(status=FreshnessStatus.FRESH, checked_at=now)
        snapshot = SourceSnapshot(
            snapshot_id=self._id_generator.new_source_snapshot_id(),
            source_kind=captured.source_kind,
            source_locator=captured.source_locator,
            raw_title=captured.raw_title,
            raw_company=captured.raw_company,
            raw_city=captured.raw_city,
            raw_description=captured.raw_description,
            captured_at=now,
            freshness=freshness,
            correlation_id=command.correlation_id,
            run_id=command.run_id,
        )
        source_reference = SourceReference(
            reference_id=self._id_generator.new_source_reference_id(),
            snapshot_id=snapshot.snapshot_id,
            source_kind=snapshot.source_kind,
            source_locator=snapshot.source_locator,
        )
        # Each UnitOfWork stages one snapshot, one immutable version, and the logical
        # Job pointer together so lineage cannot be committed partially.
        try:
            unit_of_work = self._unit_of_work_factory()
        except JobHunterError:
            raise
        except Exception:
            # Construction failure has no transaction to roll back or close.
            raise DependencyUnavailableError("job import dependency is unavailable") from None
        try:
            existing_job = (
                unit_of_work.jobs.get_job(command.existing_job_id)
                if command.existing_job_id is not None
                else None
            )
            job_id = existing_job.job_id if existing_job else self._id_generator.new_job_id()
            version_number = len(existing_job.version_ids) + 1 if existing_job else 1
            version = JobVersion(
                version_id=self._id_generator.new_job_version_id(),
                job_id=job_id,
                version_number=version_number,
                title=_normalize_whitespace(snapshot.raw_title),
                company=_normalize_whitespace(snapshot.raw_company),
                city=_normalize_whitespace(snapshot.raw_city),
                description=_normalize_description(snapshot.raw_description),
                source_snapshot_id=snapshot.snapshot_id,
                freshness=snapshot.freshness,
                created_at=now,
                correlation_id=command.correlation_id,
                run_id=command.run_id,
            )
            if existing_job is None:
                job = Job.create(version, source_reference)
                unit_of_work.jobs.add_job(job)
            else:
                # Re-importing never edits the active version in place; it appends a
                # new version and advances only the logical Job's active pointer.
                job = existing_job.with_version(version, source_reference)
                unit_of_work.jobs.save_job(job)
            unit_of_work.jobs.add_snapshot(snapshot)
            unit_of_work.jobs.add_version(version)
            unit_of_work.commit()
        except JobHunterError:
            unit_of_work.rollback()
            raise
        except Exception:
            unit_of_work.rollback()
            raise DependencyUnavailableError("job persistence is unavailable") from None
        finally:
            unit_of_work.close()

        return ImportJobResult(
            job_id=job.job_id,
            job_version_id=version.version_id,
            active_version_id=job.active_version_id,
            source_snapshot_id=snapshot.snapshot_id,
            version_number=version.version_number,
            lifecycle_status=job.lifecycle_status,
            source_kind=snapshot.source_kind,
            source_locator=snapshot.source_locator,
            captured_at=snapshot.captured_at,
            last_verified_at=snapshot.last_verified_at,
            freshness_status=snapshot.freshness.status,
            correlation_id=command.correlation_id,
            run_id=command.run_id,
        )

    def _capture(self, source_input: ManualSourceInput) -> ValidatedSourceData:
        try:
            source = self._source_registry.get(_source_kind(source_input))
            return source.capture(source_input)
        except JobHunterError:
            raise
        except Exception:
            raise DependencyUnavailableError("job source is unavailable") from None
