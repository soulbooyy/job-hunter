from datetime import UTC, datetime
from typing import Never

import pytest

from job_hunter.application.import_job import ImportJob, ImportJobCommand
from job_hunter.application.ports import Clock
from job_hunter.domain.ids import CorrelationId, RunId
from job_hunter.domain.jobs import FreshnessStatus, SourceKind
from job_hunter.errors import DependencyUnavailableError, InputValidationError
from job_hunter.infrastructure.memory import InMemoryStore, InMemoryUnitOfWorkFactory
from job_hunter.ingestion.manual import (
    JobSource,
    JobSourceRegistry,
    ManualJDInput,
    ManualJDSource,
    ManualURLInput,
    ManualURLSource,
    ValidatedSourceData,
)
from tests.helpers import DeterministicIdGenerator, FixedClock

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def _use_case(
    store: InMemoryStore,
    *,
    sources: tuple[JobSource, ...] | None = None,
    clock: Clock | None = None,
) -> ImportJob:
    return ImportJob(
        source_registry=JobSourceRegistry(sources or (ManualJDSource(), ManualURLSource())),
        unit_of_work_factory=InMemoryUnitOfWorkFactory(store),
        clock=clock or FixedClock(NOW),
        id_generator=DeterministicIdGenerator(),
    )


def test_manual_jd_import_creates_normalized_job_and_traversable_lineage() -> None:
    store = InMemoryStore()
    result = _use_case(store).execute(
        ImportJobCommand(
            source_input=ManualJDInput(
                title="  Senior   AI Engineer ",
                company=" Example   AI ",
                city=" Shenzhen ",
                content=" Build grounded agents. ",
            ),
            correlation_id=CorrelationId("correlation-001"),
            run_id=RunId("run-001"),
        )
    )

    job = store.get_job(result.job_id)
    version = store.get_version(result.job_version_id)
    snapshot = store.get_snapshot(result.source_snapshot_id)

    assert job.active_version_id == version.version_id
    assert version.title == "Senior AI Engineer"
    assert version.company == "Example AI"
    assert version.source_snapshot_id == snapshot.snapshot_id
    assert snapshot.source_kind is SourceKind.MANUAL_JD
    assert snapshot.captured_at == NOW
    assert snapshot.last_verified_at == NOW
    assert snapshot.freshness.status is FreshnessStatus.FRESH
    assert result.correlation_id == snapshot.correlation_id == version.correlation_id
    assert result.run_id == snapshot.run_id == version.run_id


def test_manual_url_import_updates_active_version_without_losing_history() -> None:
    store = InMemoryStore()
    importer = _use_case(store)
    first = importer.execute(
        ImportJobCommand(
            source_input=ManualJDInput(
                title="AI Engineer",
                company="Example AI",
                city="Shenzhen",
                content="Original content.",
            ),
            correlation_id=CorrelationId("correlation-001"),
            run_id=RunId("run-001"),
        )
    )

    second = importer.execute(
        ImportJobCommand(
            source_input=ManualURLInput(
                url="https://jobs.example/roles/1",
                title="AI Engineer",
                company="Example AI",
                city="Shenzhen",
                content="Updated content.",
            ),
            correlation_id=CorrelationId("correlation-002"),
            run_id=RunId("run-002"),
            existing_job_id=first.job_id,
        )
    )

    job = store.get_job(first.job_id)
    historical = store.get_version(first.job_version_id)
    active = store.get_version(second.job_version_id)
    historical_snapshot = store.get_snapshot(historical.source_snapshot_id)
    active_snapshot = store.get_snapshot(active.source_snapshot_id)

    assert job.active_version_id == second.job_version_id
    assert job.version_ids == (first.job_version_id, second.job_version_id)
    assert historical.description == "Original content."
    assert active.description == "Updated content."
    assert historical_snapshot.source_kind is SourceKind.MANUAL_JD
    assert active_snapshot.source_kind is SourceKind.MANUAL_URL
    assert active_snapshot.source_locator == "https://jobs.example/roles/1"


def test_invalid_input_does_not_enter_domain_state() -> None:
    store = InMemoryStore()

    with pytest.raises(InputValidationError, match="content is required"):
        _use_case(store).execute(
            ImportJobCommand(
                source_input=ManualJDInput(
                    title="AI Engineer",
                    company="Example AI",
                    city="Shenzhen",
                    content=" ",
                ),
                correlation_id=CorrelationId("correlation-001"),
                run_id=RunId("run-001"),
            )
        )

    assert store.is_empty()


def test_sensitive_manual_url_does_not_enter_domain_state() -> None:
    store = InMemoryStore()

    with pytest.raises(InputValidationError, match="sensitive credential"):
        _use_case(store).execute(
            ImportJobCommand(
                source_input=ManualURLInput(
                    url="https://jobs.example/roles/1?access_token=do-not-store",
                    title="AI Engineer",
                    company="Example AI",
                    city="Shenzhen",
                    content="Build agents.",
                ),
                correlation_id=CorrelationId("correlation-001"),
                run_id=RunId("run-001"),
            )
        )

    assert store.is_empty()


class _VendorFailureSource:
    kind = SourceKind.MANUAL_JD

    def capture(self, source_input: ManualJDInput | ManualURLInput) -> ValidatedSourceData:
        del source_input
        raise RuntimeError("raw vendor secret and stack detail")


def test_unexpected_boundary_errors_are_translated_before_application_escape() -> None:
    store = InMemoryStore()

    with pytest.raises(DependencyUnavailableError) as raised:
        _use_case(store, sources=(_VendorFailureSource(),)).execute(
            ImportJobCommand(
                source_input=ManualJDInput(
                    title="AI Engineer",
                    company="Example AI",
                    city="Shenzhen",
                    content="Build agents.",
                ),
                correlation_id=CorrelationId("correlation-001"),
                run_id=RunId("run-001"),
            )
        )

    assert "vendor" not in str(raised.value)
    assert store.is_empty()


class _FailingClock:
    def now(self) -> datetime:
        raise RuntimeError("raw clock dependency detail")


def test_control_plane_dependency_errors_are_also_translated() -> None:
    store = InMemoryStore()

    with pytest.raises(DependencyUnavailableError) as raised:
        _use_case(store, clock=_FailingClock()).execute(
            ImportJobCommand(
                source_input=ManualJDInput(
                    title="AI Engineer",
                    company="Example AI",
                    city="Shenzhen",
                    content="Build agents.",
                ),
                correlation_id=CorrelationId("correlation-001"),
                run_id=RunId("run-001"),
            )
        )

    assert "clock" not in str(raised.value)
    assert store.is_empty()


class _FailingUnitOfWorkFactory:
    def __call__(self) -> Never:
        raise RuntimeError("raw session factory and local path detail")


def test_unit_of_work_factory_failure_uses_stable_import_error() -> None:
    use_case = ImportJob(
        source_registry=JobSourceRegistry((ManualJDSource(),)),
        unit_of_work_factory=_FailingUnitOfWorkFactory(),
        clock=FixedClock(NOW),
        id_generator=DeterministicIdGenerator(),
    )

    with pytest.raises(DependencyUnavailableError) as raised:
        use_case.execute(
            ImportJobCommand(
                source_input=ManualJDInput(
                    title="AI Engineer",
                    company="Example AI",
                    city="Shenzhen",
                    content="Build agents.",
                ),
                correlation_id=CorrelationId("correlation-001"),
                run_id=RunId("run-001"),
            )
        )

    assert str(raised.value) == "job import dependency is unavailable"
    assert "session" not in str(raised.value)
