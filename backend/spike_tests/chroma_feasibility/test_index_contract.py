from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from job_hunter.domain.ids import EvidenceItemId, EvidenceVersionId
from job_hunter.domain.knowledge import EvidenceSensitivity, EvidenceType, EvidenceValidity
from job_hunter.errors import DependencyUnavailableError
from spikes.chroma_feasibility.contracts import (
    EMBEDDING_DIMENSION,
    IndexManifest,
    IndexRecord,
    deterministic_embedding,
)
from spikes.chroma_feasibility.index import ChromaFeasibilityIndex

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _record(
    number: int,
    *,
    sensitivity: EvidenceSensitivity = EvidenceSensitivity.PUBLIC,
    validity: EvidenceValidity = EvidenceValidity.VALID,
) -> IndexRecord:
    content = f"Synthetic capability evidence {number} for deterministic testing only."
    return IndexRecord(
        evidence_id=EvidenceItemId(f"evidence-{number:04d}"),
        evidence_version_id=EvidenceVersionId(f"evidence-version-{number:04d}"),
        evidence_type=EvidenceType.SKILL,
        sensitivity=sensitivity,
        validity=validity,
        embedding=deterministic_embedding(content),
    )


def test_explicit_embeddings_have_a_stable_dimension_and_identity() -> None:
    first = deterministic_embedding("synthetic alpha")
    second = deterministic_embedding("synthetic alpha")
    different = deterministic_embedding("synthetic beta")

    assert len(first) == EMBEDDING_DIMENSION == 64
    assert first == second
    assert first != different


def test_persistent_collection_reopens_in_a_new_process_without_documents(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "chroma"
    probe = "spikes.chroma_feasibility.process_probe"

    write = subprocess.run(
        [sys.executable, "-m", probe, "write", str(index_path)],
        cwd=BACKEND_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert write.returncode == 0, write.stderr
    assert "Synthetic capability" not in write.stdout + write.stderr

    read = subprocess.run(
        [sys.executable, "-m", probe, "read", str(index_path)],
        cwd=BACKEND_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert read.returncode == 0, read.stderr
    assert "Synthetic capability" not in read.stdout + read.stderr
    assert json.loads(read.stdout) == {
        "count": 1,
        "ids": ["evidence-version-0001"],
        "documents_absent": True,
        "hidden_network_used": False,
    }


def test_filtering_update_delete_and_deterministic_ordering(tmp_path: Path) -> None:
    index = ChromaFeasibilityIndex(tmp_path / "chroma")
    public = _record(1)
    confidential = _record(2, sensitivity=EvidenceSensitivity.SENSITIVE)
    invalid = _record(3, validity=EvidenceValidity.REVOKED)
    index.add((public, confidential, invalid))

    public_hits = index.query(
        public.embedding,
        allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
        limit=10,
    )
    assert tuple(hit.evidence_version_id for hit in public_hits) == (public.evidence_version_id,)

    replacement = _record(1, sensitivity=EvidenceSensitivity.SENSITIVE)
    index.update((replacement,))
    assert (
        index.query(
            public.embedding,
            allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
            limit=10,
        )
        == ()
    )
    assert tuple(
        hit.evidence_version_id
        for hit in index.query(
            public.embedding,
            allowed_sensitivities=(EvidenceSensitivity.SENSITIVE,),
            limit=10,
        )
    ) == (replacement.evidence_version_id, confidential.evidence_version_id)

    index.delete((replacement.evidence_version_id,))
    assert tuple(
        (
            record.evidence_id,
            record.evidence_version_id,
            record.evidence_type,
            record.sensitivity,
            record.validity,
        )
        for record in index.list_records()
    ) == (
        (
            confidential.evidence_id,
            confidential.evidence_version_id,
            confidential.evidence_type,
            confidential.sensitivity,
            confidential.validity,
        ),
        (
            invalid.evidence_id,
            invalid.evidence_version_id,
            invalid.evidence_type,
            invalid.sensitivity,
            invalid.validity,
        ),
    )


def test_manifest_mismatch_fails_closed_without_local_path(tmp_path: Path) -> None:
    index_path = tmp_path / "private-candidate-index"
    ChromaFeasibilityIndex(index_path)
    incompatible = IndexManifest.default().model_copy(
        update={"embedding_dimension": EMBEDDING_DIMENSION + 1}
    )

    with pytest.raises(DependencyUnavailableError) as captured:
        ChromaFeasibilityIndex(index_path, manifest=incompatible)

    message = str(captured.value)
    assert message == "Chroma feasibility index configuration is incompatible"
    assert str(index_path) not in message


def test_third_party_failure_is_translated_and_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index_path = tmp_path / "private-candidate-index"
    index = ChromaFeasibilityIndex(index_path)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(
            f"third-party secret content at {index_path}: Synthetic capability evidence"
        )

    monkeypatch.setattr(index, "_upsert", fail)

    with pytest.raises(DependencyUnavailableError) as captured:
        index.upsert((_record(1),))

    message = str(captured.value)
    assert message == "Chroma feasibility index is unavailable"
    assert str(index_path) not in message
    assert "Synthetic capability" not in message
