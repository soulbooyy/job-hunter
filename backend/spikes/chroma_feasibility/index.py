"""Local persistent Chroma harness isolated from the production package."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import chromadb
import numpy as np
from chromadb import Collection
from chromadb.api.types import Metadata, Where
from chromadb.config import Settings
from chromadb.errors import NotFoundError
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from job_hunter.domain.ids import EvidenceItemId, EvidenceVersionId
from job_hunter.domain.knowledge import (
    EvidenceItemVersion,
    EvidenceSensitivity,
    EvidenceType,
    EvidenceValidity,
)
from job_hunter.errors import DependencyUnavailableError
from spikes.chroma_feasibility.contracts import (
    EMBEDDING_DIMENSION,
    IndexManifest,
    IndexRecord,
    QueryHit,
    deterministic_embedding,
)

COLLECTION_NAME = "job-hunter-chroma-feasibility-v1"
_SAFE_UNAVAILABLE = "Chroma feasibility index is unavailable"
_SAFE_INCOMPATIBLE = "Chroma feasibility index configuration is incompatible"


class _StoredMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    evidence_version_id: str
    evidence_type: EvidenceType
    sensitivity: EvidenceSensitivity
    validity: EvidenceValidity
    index_version: str
    chunk_policy_version: str


class _GetResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ids: list[str]
    embeddings: object | None
    metadatas: list[dict[str, object] | None] | None
    documents: list[str | None] | None


class _QueryResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ids: list[list[str]]
    metadatas: list[list[dict[str, object] | None]] | None
    distances: list[list[float]] | None


_EMBEDDINGS_ADAPTER = TypeAdapter(list[list[float]])


class ChromaFeasibilityIndex:
    """Concrete spike adapter; Chroma exceptions never cross this boundary."""

    def __init__(
        self,
        path: Path,
        *,
        manifest: IndexManifest | None = None,
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        self.manifest = manifest or IndexManifest.default()
        try:
            self._client = chromadb.PersistentClient(
                path=str(path),
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._open_collection(collection_name)
            self._validate_manifest()
        except DependencyUnavailableError:
            raise
        except Exception:
            raise DependencyUnavailableError(_SAFE_UNAVAILABLE) from None

    def _open_collection(self, collection_name: str) -> Collection:
        try:
            return self._client.get_collection(collection_name, embedding_function=None)
        except NotFoundError:
            return self._client.create_collection(
                collection_name,
                metadata=self.manifest.collection_metadata(),
                embedding_function=None,
            )

    def _validate_manifest(self) -> None:
        actual = self._collection.metadata
        expected = self.manifest.collection_metadata()
        if any(actual.get(key) != value for key, value in expected.items()):
            raise DependencyUnavailableError(_SAFE_INCOMPATIBLE)

    @staticmethod
    def record_from_evidence(version: EvidenceItemVersion) -> IndexRecord:
        return IndexRecord(
            evidence_id=version.evidence_id,
            evidence_version_id=version.version_id,
            evidence_type=version.evidence_type,
            sensitivity=version.sensitivity,
            validity=version.validity,
            embedding=deterministic_embedding(version.canonical_content),
        )

    def _safe_call(self, operation: Callable[[], None]) -> None:
        try:
            operation()
        except DependencyUnavailableError:
            raise
        except Exception:
            raise DependencyUnavailableError(_SAFE_UNAVAILABLE) from None

    def _ids(self, records: tuple[IndexRecord, ...]) -> list[str]:
        return [str(record.evidence_version_id) for record in records]

    def _embeddings(self, records: tuple[IndexRecord, ...]) -> NDArray[np.float32]:
        # Chroma's PyEmbedding alias accepts generic sequences, but its runtime
        # validator rejects tuples. A float32 array satisfies both boundaries.
        return np.asarray([record.embedding for record in records], dtype=np.float32)

    def _metadatas(self, records: tuple[IndexRecord, ...]) -> list[Metadata]:
        metadatas: list[Metadata] = []
        for record in records:
            metadatas.append(record.metadata(self.manifest))
        return metadatas

    def _add(self, records: tuple[IndexRecord, ...]) -> None:
        self._collection.add(
            ids=self._ids(records),
            embeddings=self._embeddings(records),
            metadatas=self._metadatas(records),
        )

    def add(self, records: tuple[IndexRecord, ...]) -> None:
        if records:
            self._safe_call(lambda: self._add(records))

    def _update(self, records: tuple[IndexRecord, ...]) -> None:
        self._collection.update(
            ids=self._ids(records),
            embeddings=self._embeddings(records),
            metadatas=self._metadatas(records),
        )

    def update(self, records: tuple[IndexRecord, ...]) -> None:
        if records:
            self._safe_call(lambda: self._update(records))

    def _upsert(self, records: tuple[IndexRecord, ...]) -> None:
        self._collection.upsert(
            ids=self._ids(records),
            embeddings=self._embeddings(records),
            metadatas=self._metadatas(records),
        )

    def upsert(self, records: tuple[IndexRecord, ...]) -> None:
        if records:
            self._safe_call(lambda: self._upsert(records))

    def _delete(self, version_ids: tuple[EvidenceVersionId, ...]) -> None:
        self._collection.delete(ids=[str(version_id) for version_id in version_ids])

    def delete(self, version_ids: tuple[EvidenceVersionId, ...]) -> None:
        if version_ids:
            self._safe_call(lambda: self._delete(version_ids))

    def _validated_get(self) -> tuple[_GetResult, list[list[float]]]:
        raw = self._collection.get(include=["metadatas", "embeddings", "documents"])
        parsed = _GetResult.model_validate(raw)
        embeddings = _EMBEDDINGS_ADAPTER.validate_python(parsed.embeddings)
        if parsed.metadatas is None or len(parsed.metadatas) != len(parsed.ids):
            raise ValueError("missing Chroma metadata")
        if len(embeddings) != len(parsed.ids):
            raise ValueError("missing Chroma embeddings")
        return parsed, embeddings

    def list_records(self) -> tuple[IndexRecord, ...]:
        try:
            parsed, embeddings = self._validated_get()
            metadatas = parsed.metadatas
            if metadatas is None:
                raise ValueError("missing Chroma metadata")
            records: list[IndexRecord] = []
            for position, identity in enumerate(parsed.ids):
                metadata_value = metadatas[position]
                if metadata_value is None:
                    raise ValueError("missing Chroma metadata")
                metadata = _StoredMetadata.model_validate(metadata_value)
                if identity != metadata.evidence_version_id:
                    raise ValueError("Chroma identity mismatch")
                if (
                    metadata.index_version != self.manifest.index_version
                    or metadata.chunk_policy_version != self.manifest.chunk_policy_version
                ):
                    raise ValueError("Chroma record manifest mismatch")
                embedding = tuple(embeddings[position])
                if len(embedding) != EMBEDDING_DIMENSION:
                    raise ValueError("Chroma embedding dimension mismatch")
                records.append(
                    IndexRecord(
                        evidence_id=EvidenceItemId(metadata.evidence_id),
                        evidence_version_id=EvidenceVersionId(metadata.evidence_version_id),
                        evidence_type=metadata.evidence_type,
                        sensitivity=metadata.sensitivity,
                        validity=metadata.validity,
                        embedding=embedding,
                    )
                )
            records.sort(
                key=lambda record: (
                    str(record.evidence_id),
                    str(record.evidence_version_id),
                )
            )
            return tuple(records)
        except (ValidationError, ValueError, TypeError):
            raise DependencyUnavailableError(_SAFE_UNAVAILABLE) from None
        except DependencyUnavailableError:
            raise
        except Exception:
            raise DependencyUnavailableError(_SAFE_UNAVAILABLE) from None

    def documents_absent(self) -> bool:
        try:
            parsed, _embeddings = self._validated_get()
            return parsed.documents is None or all(
                document is None for document in parsed.documents
            )
        except (ValidationError, ValueError, TypeError):
            raise DependencyUnavailableError(_SAFE_UNAVAILABLE) from None
        except Exception:
            raise DependencyUnavailableError(_SAFE_UNAVAILABLE) from None

    def count(self) -> int:
        try:
            return self._collection.count()
        except Exception:
            raise DependencyUnavailableError(_SAFE_UNAVAILABLE) from None

    def query(
        self,
        embedding: tuple[float, ...],
        *,
        allowed_sensitivities: tuple[EvidenceSensitivity, ...],
        limit: int,
    ) -> tuple[QueryHit, ...]:
        if len(embedding) != self.manifest.embedding_dimension or limit < 1:
            raise DependencyUnavailableError(_SAFE_UNAVAILABLE)
        if not allowed_sensitivities or self.count() == 0:
            return ()
        validity_where: Where = {"validity": EvidenceValidity.VALID.value}
        sensitivity_where: Where = {
            "sensitivity": {"$in": [value.value for value in allowed_sensitivities]}
        }
        where: Where = {
            "$and": [
                validity_where,
                sensitivity_where,
            ]
        }
        try:
            raw = self._collection.query(
                query_embeddings=[list(embedding)],
                n_results=min(limit, self.count()),
                where=where,
                include=["metadatas", "distances"],
            )
            parsed = _QueryResult.model_validate(raw)
            if parsed.metadatas is None or parsed.distances is None:
                raise ValueError("missing Chroma query lineage")
            identities = parsed.ids[0]
            metadatas = parsed.metadatas[0]
            distances = parsed.distances[0]
            if not (len(identities) == len(metadatas) == len(distances)):
                raise ValueError("incomplete Chroma query lineage")
            hits: list[QueryHit] = []
            for identity, metadata_value, distance in zip(
                identities, metadatas, distances, strict=True
            ):
                if metadata_value is None:
                    raise ValueError("missing Chroma query metadata")
                metadata = _StoredMetadata.model_validate(metadata_value)
                if identity != metadata.evidence_version_id:
                    raise ValueError("Chroma query identity mismatch")
                hits.append(
                    QueryHit(
                        evidence_id=EvidenceItemId(metadata.evidence_id),
                        evidence_version_id=EvidenceVersionId(identity),
                        distance=distance,
                    )
                )
            hits.sort(key=lambda hit: (hit.distance, str(hit.evidence_version_id)))
            return tuple(hits)
        except (ValidationError, ValueError, TypeError):
            raise DependencyUnavailableError(_SAFE_UNAVAILABLE) from None
        except DependencyUnavailableError:
            raise
        except Exception:
            raise DependencyUnavailableError(_SAFE_UNAVAILABLE) from None
