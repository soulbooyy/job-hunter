from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from job_hunter.domain.ids import (
    CorrelationId,
    JobId,
    JobVersionId,
    QuickScreenResultId,
    RunId,
    SourceReferenceId,
    SourceSnapshotId,
)
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
from job_hunter.domain.screening import TriageDecision
from job_hunter.errors import ConflictError, InputValidationError

CAPTURED_AT = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def _snapshot(*, kind: SourceKind = SourceKind.MANUAL_JD) -> SourceSnapshot:
    return SourceSnapshot(
        snapshot_id=SourceSnapshotId("snapshot-001"),
        source_kind=kind,
        source_locator=None if kind is SourceKind.MANUAL_JD else "https://jobs.example/1",
        raw_title="AI Engineer",
        raw_company="Example AI",
        raw_city="Shenzhen",
        raw_description="Build grounded agents.",
        captured_at=CAPTURED_AT,
        freshness=Freshness(status=FreshnessStatus.FRESH, checked_at=CAPTURED_AT),
        correlation_id=CorrelationId("correlation-001"),
        run_id=RunId("run-001"),
    )


def _version(*, number: int = 1, snapshot_id: str = "snapshot-001") -> JobVersion:
    return JobVersion(
        version_id=JobVersionId(f"version-{number:03d}"),
        job_id=JobId("job-001"),
        version_number=number,
        title="AI Engineer",
        company="Example AI",
        city="Shenzhen",
        description="Build grounded agents.",
        source_snapshot_id=SourceSnapshotId(snapshot_id),
        freshness=Freshness(status=FreshnessStatus.FRESH, checked_at=CAPTURED_AT),
        created_at=CAPTURED_AT,
        correlation_id=CorrelationId("correlation-001"),
        run_id=RunId("run-001"),
    )


def _reference(*, number: int = 1, kind: SourceKind = SourceKind.MANUAL_JD) -> SourceReference:
    return SourceReference(
        reference_id=SourceReferenceId(f"reference-{number:03d}"),
        snapshot_id=SourceSnapshotId(f"snapshot-{number:03d}"),
        source_kind=kind,
        source_locator=None if kind is SourceKind.MANUAL_JD else "https://jobs.example/1",
    )


def test_job_version_is_immutable_after_creation() -> None:
    version = _version()

    with pytest.raises(FrozenInstanceError):
        version.__setattr__("title", "Changed in place")


def test_new_version_changes_active_pointer_and_keeps_history() -> None:
    first_version = _version()
    job = Job.create(first_version, _reference())
    second_version = _version(number=2, snapshot_id="snapshot-002")

    updated = job.with_version(second_version, _reference(number=2))

    assert job.active_version_id == first_version.version_id
    assert updated.active_version_id == second_version.version_id
    assert updated.version_ids == (first_version.version_id, second_version.version_id)
    assert tuple(reference.snapshot_id for reference in updated.source_references) == (
        SourceSnapshotId("snapshot-001"),
        SourceSnapshotId("snapshot-002"),
    )
    assert updated.lifecycle_status is JobLifecycleStatus.IMPORTED


def test_screening_and_human_triage_are_explicit_reversible_transitions() -> None:
    imported = Job.create(_version(), _reference())

    screened = imported.with_screening(QuickScreenResultId("screen-001"))
    skipped = screened.with_triage_decision(TriageDecision.SKIPPED)
    restored = skipped.with_triage_decision(TriageDecision.SHORTLISTED)

    assert screened.lifecycle_status is JobLifecycleStatus.SCREENED
    assert screened.latest_quick_screen_result_id == QuickScreenResultId("screen-001")
    assert skipped.lifecycle_status is JobLifecycleStatus.SKIPPED
    assert skipped.latest_quick_screen_result_id == screened.latest_quick_screen_result_id
    assert restored.lifecycle_status is JobLifecycleStatus.SHORTLISTED


def test_imported_job_cannot_be_triaged_before_screening() -> None:
    imported = Job.create(_version(), _reference())

    with pytest.raises(ConflictError, match="must be screened"):
        imported.with_triage_decision(TriageDecision.SHORTLISTED)


def test_new_job_version_invalidates_an_earlier_screening_decision() -> None:
    job = Job.create(_version(), _reference())
    shortlisted = job.with_screening(QuickScreenResultId("screen-001")).with_triage_decision(
        TriageDecision.SHORTLISTED
    )

    updated = shortlisted.with_version(
        _version(number=2, snapshot_id="snapshot-002"),
        _reference(number=2),
    )

    assert updated.lifecycle_status is JobLifecycleStatus.IMPORTED
    assert updated.latest_quick_screen_result_id is None


def test_rescreen_advances_authoritative_latest_result_pointer() -> None:
    job = Job.create(_version(), _reference())

    first = job.with_screening(QuickScreenResultId("screen-z"))
    second = first.with_screening(QuickScreenResultId("screen-a"))

    assert first.latest_quick_screen_result_id == QuickScreenResultId("screen-z")
    assert second.latest_quick_screen_result_id == QuickScreenResultId("screen-a")


def test_job_rejects_a_non_sequential_new_version() -> None:
    job = Job.create(_version(), _reference())

    with pytest.raises(ConflictError, match="version number must be sequential"):
        job.with_version(_version(number=3, snapshot_id="snapshot-003"), _reference(number=3))


def test_job_constructor_rejects_active_version_outside_history() -> None:
    with pytest.raises(InputValidationError, match="active version must belong to history"):
        Job(
            job_id=JobId("job-001"),
            active_version_id=JobVersionId("version-002"),
            version_ids=(JobVersionId("version-001"),),
            source_references=(_reference(),),
            lifecycle_status=JobLifecycleStatus.IMPORTED,
        )


def test_job_constructor_rejects_empty_or_duplicate_version_history() -> None:
    with pytest.raises(InputValidationError, match="at least one version"):
        Job(
            job_id=JobId("job-001"),
            active_version_id=JobVersionId("version-001"),
            version_ids=(),
            source_references=(),
            lifecycle_status=JobLifecycleStatus.IMPORTED,
        )

    with pytest.raises(InputValidationError, match="version IDs must be unique"):
        Job(
            job_id=JobId("job-001"),
            active_version_id=JobVersionId("version-001"),
            version_ids=(JobVersionId("version-001"), JobVersionId("version-001")),
            source_references=(_reference(), _reference(number=2)),
            lifecycle_status=JobLifecycleStatus.IMPORTED,
        )


def test_job_constructor_rejects_incomplete_or_duplicate_source_references() -> None:
    with pytest.raises(InputValidationError, match="one source reference per version"):
        Job(
            job_id=JobId("job-001"),
            active_version_id=JobVersionId("version-001"),
            version_ids=(JobVersionId("version-001"),),
            source_references=(),
            lifecycle_status=JobLifecycleStatus.IMPORTED,
        )

    with pytest.raises(InputValidationError, match="source reference IDs must be unique"):
        Job(
            job_id=JobId("job-001"),
            active_version_id=JobVersionId("version-002"),
            version_ids=(JobVersionId("version-001"), JobVersionId("version-002")),
            source_references=(_reference(), _reference()),
            lifecycle_status=JobLifecycleStatus.IMPORTED,
        )


def test_snapshot_preserves_source_capture_and_freshness() -> None:
    snapshot = _snapshot(kind=SourceKind.MANUAL_URL)

    assert snapshot.source_kind is SourceKind.MANUAL_URL
    assert snapshot.source_locator == "https://jobs.example/1"
    assert snapshot.captured_at == CAPTURED_AT
    assert snapshot.last_verified_at == CAPTURED_AT
    assert snapshot.freshness.status is FreshnessStatus.FRESH


def test_stale_freshness_is_explicitly_representable() -> None:
    checked_at = CAPTURED_AT + timedelta(days=30)
    freshness = Freshness(status=FreshnessStatus.STALE, checked_at=checked_at)

    assert freshness.is_stale is True


def test_domain_rejects_naive_timestamps() -> None:
    with pytest.raises(InputValidationError, match="timezone-aware"):
        Freshness(status=FreshnessStatus.FRESH, checked_at=datetime(2026, 8, 27, 12, 0))
