from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from job_hunter.domain.ids import CorrelationId, EvidenceItemId, EvidenceVersionId, RunId
from job_hunter.domain.knowledge import (
    EvidenceItem,
    EvidenceItemVersion,
    EvidenceSensitivity,
    EvidenceType,
    EvidenceValidity,
)
from job_hunter.infrastructure.persistence.database import (
    create_database_runtime,
    upgrade_database,
)
from job_hunter.infrastructure.persistence.uow import SqlAlchemyUnitOfWorkFactory
from spikes.chroma_feasibility.index import ChromaFeasibilityIndex
from spikes.chroma_feasibility.rebuild import reconcile_from_sqlite


def _version(
    item_id: EvidenceItemId,
    version_id: EvidenceVersionId,
    content: str,
    *,
    version_number: int = 1,
) -> EvidenceItemVersion:
    return EvidenceItemVersion(
        version_id=version_id,
        evidence_id=item_id,
        version_number=version_number,
        evidence_type=EvidenceType.SKILL,
        canonical_content=content,
        occurred_on=date(2026, 1, 1),
        provenance="synthetic-spike-fixture",
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.VALID,
        source="synthetic-spike-fixture",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        correlation_id=CorrelationId(f"correlation-{version_id}"),
        run_id=RunId(f"run-{version_id}"),
    )


@pytest.fixture
def authority_factory(tmp_path: Path) -> Iterator[SqlAlchemyUnitOfWorkFactory]:
    database_path = tmp_path / "workspace.db"
    upgrade_database(database_path)
    runtime = create_database_runtime(database_path)
    try:
        yield SqlAlchemyUnitOfWorkFactory(runtime.session_factory)
    finally:
        runtime.dispose()


def _save_item(
    factory: SqlAlchemyUnitOfWorkFactory,
    item: EvidenceItem,
    *versions: EvidenceItemVersion,
) -> None:
    unit_of_work = factory()
    try:
        unit_of_work.knowledge.add_evidence(item)
        for version in versions:
            unit_of_work.knowledge.add_evidence_version(version)
        unit_of_work.commit()
    finally:
        unit_of_work.close()


def test_full_rebuild_uses_only_active_sqlite_versions_and_is_idempotent(
    tmp_path: Path,
    authority_factory: SqlAlchemyUnitOfWorkFactory,
) -> None:
    factory = authority_factory
    first_item_id = EvidenceItemId("evidence-0001")
    stale = _version(
        first_item_id,
        EvidenceVersionId("evidence-version-stale"),
        "Synthetic stale Python evidence.",
    )
    active = _version(
        first_item_id,
        EvidenceVersionId("evidence-version-active"),
        "Synthetic active Python evidence.",
        version_number=2,
    )
    second_item_id = EvidenceItemId("evidence-0002")
    second = _version(
        second_item_id,
        EvidenceVersionId("evidence-version-second"),
        "Synthetic active SQL evidence.",
    )
    _save_item(
        factory,
        EvidenceItem(
            evidence_id=first_item_id,
            active_version_id=active.version_id,
            version_ids=(stale.version_id, active.version_id),
        ),
        stale,
        active,
    )
    _save_item(
        factory,
        EvidenceItem.create(second),
        second,
    )

    index = ChromaFeasibilityIndex(tmp_path / "chroma")
    index.upsert(
        (
            index.record_from_evidence(stale),
            index.record_from_evidence(
                _version(
                    EvidenceItemId("orphan-evidence"),
                    EvidenceVersionId("orphan-version"),
                    "Synthetic orphan content.",
                )
            ),
        )
    )

    first_rebuild = reconcile_from_sqlite(index, factory)
    second_rebuild = reconcile_from_sqlite(index, factory)

    assert first_rebuild.authoritative_count == 2
    assert first_rebuild.deleted_count == 2
    assert first_rebuild.indexed_count == 2
    assert second_rebuild.deleted_count == 0
    assert second_rebuild.indexed_count == 2
    assert second_rebuild.identity_digest == first_rebuild.identity_digest
    assert tuple(record.evidence_version_id for record in index.list_records()) == (
        active.version_id,
        second.version_id,
    )


def test_active_version_change_removes_stale_index_record(
    tmp_path: Path,
    authority_factory: SqlAlchemyUnitOfWorkFactory,
) -> None:
    factory = authority_factory
    item_id = EvidenceItemId("evidence-0001")
    first = _version(
        item_id,
        EvidenceVersionId("evidence-version-0001"),
        "Synthetic first active version.",
    )
    _save_item(
        factory,
        EvidenceItem.create(first),
        first,
    )
    index = ChromaFeasibilityIndex(tmp_path / "chroma")
    reconcile_from_sqlite(index, factory)

    second = _version(
        item_id,
        EvidenceVersionId("evidence-version-0002"),
        "Synthetic replacement active version.",
        version_number=2,
    )
    unit_of_work = factory()
    try:
        loaded = unit_of_work.knowledge.get_evidence(item_id)
        unit_of_work.knowledge.add_evidence_version(second)
        unit_of_work.knowledge.save_evidence(loaded.with_version(second))
        unit_of_work.commit()
    finally:
        unit_of_work.close()

    result = reconcile_from_sqlite(index, factory)

    assert result.deleted_count == 1
    assert tuple(record.evidence_version_id for record in index.list_records()) == (
        second.version_id,
    )
