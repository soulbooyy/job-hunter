"""Job, version, source provenance, and freshness domain model."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from job_hunter.domain.ids import (
    CorrelationId,
    JobId,
    JobVersionId,
    RunId,
    SourceReferenceId,
    SourceSnapshotId,
)
from job_hunter.domain.screening import TriageDecision
from job_hunter.errors import ConflictError, InputValidationError


class SourceKind(StrEnum):
    MANUAL_JD = "manual_jd"
    MANUAL_URL = "manual_url"


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"


class JobLifecycleStatus(StrEnum):
    IMPORTED = "imported"
    SCREENED = "screened"
    SHORTLISTED = "shortlisted"
    SKIPPED = "skipped"


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InputValidationError(f"{field_name} must be timezone-aware")


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise InputValidationError(f"{field_name} is required")


@dataclass(frozen=True, slots=True)
class Freshness:
    status: FreshnessStatus
    checked_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.checked_at, "checked_at")

    @property
    def is_stale(self) -> bool:
        return self.status is FreshnessStatus.STALE


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    # Raw fields remain unnormalized so this immutable record preserves exactly what
    # crossed the validated source boundary; JobVersion owns canonical normalization.
    snapshot_id: SourceSnapshotId
    source_kind: SourceKind
    source_locator: str | None
    raw_title: str
    raw_company: str
    raw_city: str
    raw_description: str
    captured_at: datetime
    freshness: Freshness
    correlation_id: CorrelationId
    run_id: RunId

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        for field_name, value in (
            ("title", self.raw_title),
            ("company", self.raw_company),
            ("city", self.raw_city),
            ("content", self.raw_description),
        ):
            _require_text(value, field_name)
        if self.freshness.checked_at < self.captured_at:
            raise InputValidationError("last verification cannot predate capture")
        if self.source_kind is SourceKind.MANUAL_URL and self.source_locator is None:
            raise InputValidationError("manual URL source requires a locator")
        if self.source_kind is SourceKind.MANUAL_JD and self.source_locator is not None:
            raise InputValidationError("manual JD source cannot carry a URL locator")

    @property
    def last_verified_at(self) -> datetime:
        return self.freshness.checked_at


@dataclass(frozen=True, slots=True)
class SourceReference:
    reference_id: SourceReferenceId
    snapshot_id: SourceSnapshotId
    source_kind: SourceKind
    source_locator: str | None

    def __post_init__(self) -> None:
        if self.source_kind is SourceKind.MANUAL_URL and self.source_locator is None:
            raise InputValidationError("manual URL source requires a locator")
        if self.source_kind is SourceKind.MANUAL_JD and self.source_locator is not None:
            raise InputValidationError("manual JD source cannot carry a URL locator")


@dataclass(frozen=True, slots=True)
class JobVersion:
    version_id: JobVersionId
    job_id: JobId
    version_number: int
    title: str
    company: str
    city: str
    description: str
    source_snapshot_id: SourceSnapshotId
    freshness: Freshness
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId

    def __post_init__(self) -> None:
        if self.version_number < 1:
            raise InputValidationError("version_number must be positive")
        _require_aware(self.created_at, "created_at")
        for field_name, value in (
            ("title", self.title),
            ("company", self.company),
            ("city", self.city),
            ("description", self.description),
        ):
            _require_text(value, field_name)


@dataclass(frozen=True, slots=True)
class Job:
    job_id: JobId
    active_version_id: JobVersionId
    version_ids: tuple[JobVersionId, ...]
    source_references: tuple[SourceReference, ...]
    lifecycle_status: JobLifecycleStatus

    def __post_init__(self) -> None:
        # Persistence hydration and direct construction share this aggregate-local
        # guard; factories add cross-object checks that Job cannot perform by IDs alone.
        if not self.version_ids:
            raise InputValidationError("job must contain at least one version")
        if len(set(self.version_ids)) != len(self.version_ids):
            raise InputValidationError("job version IDs must be unique")
        if self.active_version_id not in self.version_ids:
            raise InputValidationError("active version must belong to history")
        if len(self.source_references) != len(self.version_ids):
            raise InputValidationError("job must contain one source reference per version")
        reference_ids = tuple(reference.reference_id for reference in self.source_references)
        if len(set(reference_ids)) != len(reference_ids):
            raise InputValidationError("source reference IDs must be unique")

    @classmethod
    def create(cls, version: JobVersion, source_reference: SourceReference) -> "Job":
        if version.version_number != 1:
            raise InputValidationError("a new job must start at version 1")
        if version.source_snapshot_id != source_reference.snapshot_id:
            raise InputValidationError("source reference must target the version snapshot")
        return cls(
            job_id=version.job_id,
            active_version_id=version.version_id,
            version_ids=(version.version_id,),
            source_references=(source_reference,),
            lifecycle_status=JobLifecycleStatus.IMPORTED,
        )

    def with_version(self, version: JobVersion, source_reference: SourceReference) -> "Job":
        if version.job_id != self.job_id:
            raise ConflictError("job version belongs to another job")
        if version.version_id in self.version_ids:
            raise ConflictError("job version already exists")
        if version.version_number != len(self.version_ids) + 1:
            raise ConflictError("job version number must be sequential")
        if version.source_snapshot_id != source_reference.snapshot_id:
            raise InputValidationError("source reference must target the version snapshot")
        # Return a new aggregate instead of mutating the active pointer. Historical
        # Job values and every referenced JobVersion therefore remain reviewable.
        return Job(
            job_id=self.job_id,
            active_version_id=version.version_id,
            version_ids=(*self.version_ids, version.version_id),
            source_references=(*self.source_references, source_reference),
            # A new active JobVersion invalidates any recommendation or human decision
            # made against the previous version and returns the checkpoint to Imported.
            lifecycle_status=JobLifecycleStatus.IMPORTED,
        )

    def with_screening(self) -> "Job":
        return Job(
            job_id=self.job_id,
            active_version_id=self.active_version_id,
            version_ids=self.version_ids,
            source_references=self.source_references,
            lifecycle_status=JobLifecycleStatus.SCREENED,
        )

    def with_triage_decision(self, decision: TriageDecision) -> "Job":
        if self.lifecycle_status is JobLifecycleStatus.IMPORTED:
            raise ConflictError("job must be screened before triage")
        lifecycle_status = (
            JobLifecycleStatus.SHORTLISTED
            if decision is TriageDecision.SHORTLISTED
            else JobLifecycleStatus.SKIPPED
        )
        # Decisions are recorded separately as append-only history. The Job aggregate
        # stores only the latest business checkpoint so a user can restore/override it.
        return Job(
            job_id=self.job_id,
            active_version_id=self.active_version_id,
            version_ids=self.version_ids,
            source_references=self.source_references,
            lifecycle_status=lifecycle_status,
        )
