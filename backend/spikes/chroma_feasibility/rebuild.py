"""Exact reconciliation from authoritative SQLite Candidate Evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from job_hunter.application.ports import UnitOfWorkFactory
from job_hunter.errors import DependencyUnavailableError
from spikes.chroma_feasibility.contracts import IndexRecord
from spikes.chroma_feasibility.index import ChromaFeasibilityIndex


@dataclass(frozen=True, slots=True)
class RebuildResult:
    authoritative_count: int
    indexed_count: int
    deleted_count: int
    identity_digest: str


def _identity_digest(records: tuple[IndexRecord, ...]) -> str:
    canonical = [
        {
            "evidence_id": str(record.evidence_id),
            "evidence_version_id": str(record.evidence_version_id),
            "evidence_type": record.evidence_type.value,
            "sensitivity": record.sensitivity.value,
            "validity": record.validity.value,
        }
        for record in records
    ]
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def identity_metadata_match(
    actual: tuple[IndexRecord, ...], expected: tuple[IndexRecord, ...]
) -> bool:
    if len(actual) != len(expected):
        return False
    return all(
        (
            left.evidence_id,
            left.evidence_version_id,
            left.evidence_type,
            left.sensitivity,
            left.validity,
        )
        == (
            right.evidence_id,
            right.evidence_version_id,
            right.evidence_type,
            right.sensitivity,
            right.validity,
        )
        for left, right in zip(actual, expected, strict=True)
    )


def reconcile_records(
    index: ChromaFeasibilityIndex,
    records: tuple[IndexRecord, ...],
) -> RebuildResult:
    ordered = tuple(
        sorted(
            records,
            key=lambda record: (
                str(record.evidence_id),
                str(record.evidence_version_id),
            ),
        )
    )
    desired_ids = {record.evidence_version_id for record in ordered}
    current_ids = {record.evidence_version_id for record in index.list_records()}
    stale_ids = tuple(sorted(current_ids - desired_ids, key=str))
    index.delete(stale_ids)
    index.upsert(ordered)
    persisted = index.list_records()
    if not identity_metadata_match(persisted, ordered):
        raise DependencyUnavailableError("Chroma feasibility rebuild verification failed")
    return RebuildResult(
        authoritative_count=len(ordered),
        indexed_count=len(persisted),
        deleted_count=len(stale_ids),
        identity_digest=_identity_digest(persisted),
    )


def reconcile_from_sqlite(
    index: ChromaFeasibilityIndex,
    unit_of_work_factory: UnitOfWorkFactory,
) -> RebuildResult:
    unit_of_work = unit_of_work_factory()
    try:
        # SQLite owns the graph. Only each logical item's active immutable version
        # is projected into the derivative index; history remains SQLite-only.
        items = unit_of_work.knowledge.list_evidence()
        versions = tuple(
            unit_of_work.knowledge.get_evidence_version(item.active_version_id) for item in items
        )
    finally:
        unit_of_work.close()
    records = tuple(index.record_from_evidence(version) for version in versions)
    return reconcile_records(index, records)
