from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol, cast

import pytest

from job_hunter.domain.ids import CorrelationId, EvidenceItemId, EvidenceVersionId, RunId
from job_hunter.domain.knowledge import (
    EvidenceItemVersion,
    EvidenceSensitivity,
    EvidenceType,
    EvidenceValidity,
)
from job_hunter.domain.retrieval import DeterministicEvidenceChunker, SemanticIndexRecord
from job_hunter.errors import DependencyUnavailableError, SemanticIndexIntegrityError
from job_hunter.infrastructure.chroma import (
    EMBEDDING_DIMENSION,
    ChromaSemanticIndex,
    LocalOnnxMiniLmEmbeddingProvider,
)

NOW = datetime(2026, 8, 31, 18, 0, tzinfo=UTC)


class _MutableCollection(Protocol):
    def upsert(
        self,
        *,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, str | int | float | bool]],
    ) -> None: ...


def _version(
    identifier: str,
    *,
    sensitivity: EvidenceSensitivity = EvidenceSensitivity.PUBLIC,
    validity: EvidenceValidity = EvidenceValidity.VALID,
) -> EvidenceItemVersion:
    return EvidenceItemVersion(
        version_id=EvidenceVersionId(f"{identifier}-version"),
        evidence_id=EvidenceItemId(identifier),
        version_number=1,
        evidence_type=EvidenceType.PROJECT,
        canonical_content=f"Synthetic {identifier} delivery evidence",
        occurred_on=date(2026, 1, 1),
        source="manual",
        provenance="human-confirmed synthetic fixture",
        sensitivity=sensitivity,
        validity=validity,
        created_at=NOW,
        correlation_id=CorrelationId("correlation-evidence"),
        run_id=RunId("run-evidence"),
    )


def _records(
    versions: tuple[EvidenceItemVersion, ...],
) -> tuple[SemanticIndexRecord, ...]:
    chunks = DeterministicEvidenceChunker().chunk(versions)
    by_id = {version.version_id: version for version in versions}
    return tuple(
        SemanticIndexRecord(
            chunk=chunk,
            evidence_type=by_id[chunk.evidence_version_id].evidence_type,
            sensitivity=by_id[chunk.evidence_version_id].sensitivity,
            validity=by_id[chunk.evidence_version_id].validity,
        )
        for chunk in chunks
    )


def _embedding(axis: int) -> tuple[float, ...]:
    return tuple(1.0 if position == axis else 0.0 for position in range(EMBEDDING_DIMENSION))


def test_chroma_reconcile_reopen_filter_and_no_document_storage(tmp_path: Path) -> None:
    public = _version("public")
    private = _version("private", sensitivity=EvidenceSensitivity.PRIVATE)
    expired = _version("expired", validity=EvidenceValidity.EXPIRED)
    records = _records((public, private, expired))
    index = ChromaSemanticIndex(tmp_path / "semantic")
    index.reconcile(records, (_embedding(0), _embedding(1), _embedding(2)))

    reopened = ChromaSemanticIndex(tmp_path / "semantic")
    hits = reopened.query(
        _embedding(0),
        allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
        limit=5,
    )

    assert reopened.count() == 3
    assert reopened.documents_absent()
    assert tuple(hit.evidence_id for hit in hits) == (public.evidence_id,)

    replacement = _version("replacement")
    replacement_records = _records((replacement,))
    reopened.reconcile(replacement_records, (_embedding(3),))
    assert reopened.count() == 1
    assert (
        reopened.query(
            _embedding(3),
            allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
            limit=5,
        )[0].evidence_version_id
        == replacement.version_id
    )


def test_chroma_query_classifies_corrupt_metadata_as_integrity_failure(
    tmp_path: Path,
) -> None:
    record = _records((_version("corrupt"),))[0]
    index = ChromaSemanticIndex(tmp_path / "semantic-corrupt")
    embedding = _embedding(0)
    index.reconcile((record,), (embedding,))
    collection_attribute = "_collection"
    collection = cast(_MutableCollection, getattr(index, collection_attribute))
    metadata: dict[str, str | int | float | bool] = {
        "chunk_id": "forged-chunk-id",
        "evidence_id": str(record.chunk.evidence_id),
        "evidence_version_id": str(record.chunk.evidence_version_id),
        "evidence_type": record.evidence_type.value,
        "sensitivity": record.sensitivity.value,
        "validity": record.validity.value,
        "ordinal": record.chunk.ordinal,
        "content_hash": record.chunk.content_hash,
        "index_version": index.version,
        "embedding_provider_version": index.embedding_provider_version,
        "embedding_dimension": index.embedding_dimension,
        "chunk_policy_version": index.chunk_policy_version,
    }
    collection.upsert(
        ids=[str(record.chunk.chunk_id)],
        embeddings=[list(embedding)],
        metadatas=[metadata],
    )

    with pytest.raises(SemanticIndexIntegrityError):
        index.query(
            embedding,
            allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
            limit=5,
        )


def test_local_onnx_provider_returns_stable_384_dimension_embeddings() -> None:
    try:
        provider = LocalOnnxMiniLmEmbeddingProvider()
    except DependencyUnavailableError:
        pytest.skip("explicit local ONNX model setup has not run")

    first = provider.embed(("Synthetic Python backend delivery",))
    second = provider.embed(("Synthetic Python backend delivery",))

    assert provider.version == "semantic-onnx-minilm-v1"
    assert provider.dimension == EMBEDDING_DIMENSION
    assert first == second
    assert len(first) == 1
    assert len(first[0]) == EMBEDDING_DIMENSION
