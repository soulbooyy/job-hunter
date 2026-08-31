"""Process-boundary probe that emits identity-only JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from job_hunter.domain.ids import EvidenceItemId, EvidenceVersionId
from job_hunter.domain.knowledge import EvidenceSensitivity, EvidenceType, EvidenceValidity
from spikes.chroma_feasibility.contracts import IndexRecord, deterministic_embedding
from spikes.chroma_feasibility.index import ChromaFeasibilityIndex
from spikes.chroma_feasibility.network import NetworkGuard

_CONTENT = "Synthetic capability evidence for deterministic process testing only."


def _record() -> IndexRecord:
    return IndexRecord(
        evidence_id=EvidenceItemId("evidence-0001"),
        evidence_version_id=EvidenceVersionId("evidence-version-0001"),
        evidence_type=EvidenceType.SKILL,
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.VALID,
        embedding=deterministic_embedding(_CONTENT),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("write", "read", "query"))
    parser.add_argument("path", type=Path)
    arguments = parser.parse_args()

    with NetworkGuard() as network:
        started = perf_counter()
        index = ChromaFeasibilityIndex(arguments.path)
        if arguments.operation == "write":
            index.upsert((_record(),))
            payload: dict[str, object] = {"count": index.count()}
        elif arguments.operation == "read":
            records = index.list_records()
            payload = {
                "count": len(records),
                "ids": [str(record.evidence_version_id) for record in records],
                "documents_absent": index.documents_absent(),
            }
        else:
            hits = index.query(
                _record().embedding,
                allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
                limit=5,
            )
            payload = {
                "count": index.count(),
                "hit_count": len(hits),
                "elapsed_ms": (perf_counter() - started) * 1000,
            }
    payload["hidden_network_used"] = network.used
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
