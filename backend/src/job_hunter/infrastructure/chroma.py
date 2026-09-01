"""Optional persistent Chroma derivative with explicit local ONNX embeddings."""

import hashlib
import sys
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from job_hunter.domain.ids import (
    EvidenceChunkId,
    EvidenceItemId,
    EvidenceVersionId,
)
from job_hunter.domain.knowledge import (
    EvidenceSensitivity,
    EvidenceType,
    EvidenceValidity,
)
from job_hunter.domain.retrieval import (
    EVIDENCE_CHUNK_POLICY_VERSION,
    SemanticChunkMatch,
    SemanticIndexRecord,
)
from job_hunter.errors import (
    DependencyUnavailableError,
    SemanticIndexIntegrityError,
    SemanticUnavailableError,
)

INDEX_VERSION = "chroma-evidence-v1"
EMBEDDING_PROVIDER_VERSION = "semantic-onnx-minilm-v1"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384
MODEL_ARCHIVE_SHA256 = "913d7300ceae3b2dbc2c50d1de4baacab4be7b9380491c27fab7418616a16ec3"
COLLECTION_NAME = "job-hunter-evidence-v1"
_SAFE_INDEX_ERROR = "semantic index is unavailable"
_SAFE_MODEL_ERROR = "semantic embedding model is unavailable"
_MODEL_FILES = (
    "config.json",
    "model.onnx",
    "special_tokens_map.json",
    "tokenizer_config.json",
    "tokenizer.json",
    "vocab.txt",
)


@runtime_checkable
class _ArrayLike(Protocol):
    def tolist(self) -> object: ...


class _EmbeddingFunction(Protocol):
    def __call__(self, input: list[str]) -> object: ...


class _EmbeddingFactory(Protocol):
    def __call__(self) -> _EmbeddingFunction: ...


class _EmbeddingModule(Protocol):
    ONNXMiniLM_L6_V2: _EmbeddingFactory


class _Collection(Protocol):
    @property
    def metadata(self) -> dict[str, str | int | float | bool]: ...

    def count(self) -> int: ...

    def get(self, *, include: list[str]) -> object: ...

    def upsert(
        self,
        *,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, str | int | float | bool]],
    ) -> None: ...

    def delete(self, *, ids: list[str]) -> None: ...

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        where: dict[str, object],
        include: list[str],
    ) -> object: ...


class _Client(Protocol):
    def get_or_create_collection(
        self,
        *,
        name: str,
        metadata: dict[str, str | int | float | bool],
        embedding_function: None,
    ) -> _Collection: ...


class _ClientFactory(Protocol):
    def __call__(self, *, path: str, settings: object) -> _Client: ...


class _ChromaModule(Protocol):
    PersistentClient: _ClientFactory


class _SettingsFactory(Protocol):
    def __call__(self, *, anonymized_telemetry: bool) -> object: ...


class _ConfigModule(Protocol):
    Settings: _SettingsFactory


class _StoredMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    evidence_id: str
    evidence_version_id: str
    evidence_type: EvidenceType
    sensitivity: EvidenceSensitivity
    validity: EvidenceValidity
    ordinal: int
    content_hash: str
    index_version: str
    embedding_provider_version: str
    embedding_dimension: int
    chunk_policy_version: str


class _GetResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ids: list[str]
    metadatas: list[dict[str, object] | None] | None
    documents: list[str | None] | None


class _QueryResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ids: list[list[str]]
    metadatas: list[list[dict[str, object] | None]] | None
    distances: list[list[float]] | None


_EMBEDDINGS = TypeAdapter(list[list[float]])


def _default_model_path() -> Path:
    return Path.home() / ".cache" / "chroma" / "onnx_models" / EMBEDDING_MODEL


def _archive_matches(path: Path) -> bool:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as archive:
            for block in iter(lambda: archive.read(64 * 1024), b""):
                digest.update(block)
    except OSError:
        return False
    return digest.hexdigest() == MODEL_ARCHIVE_SHA256


class LocalOnnxMiniLmEmbeddingProvider:
    """Guard Chroma's provider so request-time execution can never download."""

    def __init__(self, *, model_path: Path | None = None) -> None:
        self._model_path = model_path or _default_model_path()
        extracted = self._model_path / "onnx"
        archive = self._model_path / "onnx.tar.gz"
        if self._model_path != _default_model_path() or not _archive_matches(archive):
            raise SemanticUnavailableError(_SAFE_MODEL_ERROR)
        if any(not (extracted / name).is_file() for name in _MODEL_FILES):
            raise SemanticUnavailableError(_SAFE_MODEL_ERROR)
        try:
            module = cast(
                _EmbeddingModule,
                import_module("chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2"),
            )
            self._function = module.ONNXMiniLM_L6_V2()
        except Exception:
            raise SemanticUnavailableError(_SAFE_MODEL_ERROR) from None

    @property
    def version(self) -> str:
        return EMBEDDING_PROVIDER_VERSION

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIMENSION

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        try:
            raw = self._function(list(texts))
            if not isinstance(raw, list):
                raise ValueError("invalid embedding container")
            raw_values = cast(list[object], raw)
            normalized: list[object] = [
                item.tolist() if isinstance(item, _ArrayLike) else item for item in raw_values
            ]
            vectors = _EMBEDDINGS.validate_python(normalized)
            if len(vectors) != len(texts) or any(
                len(vector) != EMBEDDING_DIMENSION for vector in vectors
            ):
                raise ValueError("invalid embedding dimensions")
            return tuple(tuple(vector) for vector in vectors)
        except (ValidationError, ValueError, TypeError):
            raise SemanticUnavailableError(_SAFE_MODEL_ERROR) from None
        except SemanticUnavailableError:
            raise
        except Exception:
            raise SemanticUnavailableError(_SAFE_MODEL_ERROR) from None


def setup_local_embedding_model() -> None:
    """Explicitly acquire Chroma's checksum-pinned model outside request handling."""
    try:
        module = cast(
            _EmbeddingModule,
            import_module("chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2"),
        )
        function = module.ONNXMiniLM_L6_V2()
        function(["Job Hunter local embedding readiness probe"])
        LocalOnnxMiniLmEmbeddingProvider()
    except SemanticUnavailableError:
        raise
    except Exception:
        raise SemanticUnavailableError(_SAFE_MODEL_ERROR) from None


def main() -> None:
    try:
        setup_local_embedding_model()
    except SemanticUnavailableError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    print(
        f"ready: {EMBEDDING_PROVIDER_VERSION} ({EMBEDDING_MODEL}, {EMBEDDING_DIMENSION} dimensions)"
    )


class ChromaSemanticIndex:
    """Persistent non-authoritative vectors and identity/filter metadata only."""

    def __init__(self, path: Path) -> None:
        try:
            chroma = cast(_ChromaModule, import_module("chromadb"))
            config = cast(_ConfigModule, import_module("chromadb.config"))
            client = chroma.PersistentClient(
                path=str(path),
                settings=config.Settings(anonymized_telemetry=False),
            )
            self._collection = client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata=self._manifest(),
                embedding_function=None,
            )
        except Exception:
            raise SemanticUnavailableError(_SAFE_INDEX_ERROR) from None
        self._validate_manifest()

    @property
    def version(self) -> str:
        return INDEX_VERSION

    @property
    def chunk_policy_version(self) -> str:
        return EVIDENCE_CHUNK_POLICY_VERSION

    @property
    def embedding_provider_version(self) -> str:
        return EMBEDDING_PROVIDER_VERSION

    @property
    def embedding_dimension(self) -> int:
        return EMBEDDING_DIMENSION

    def _manifest(self) -> dict[str, str | int | float | bool]:
        return {
            "index_version": self.version,
            "embedding_provider_version": self.embedding_provider_version,
            "embedding_dimension": self.embedding_dimension,
            "chunk_policy_version": self.chunk_policy_version,
            "hnsw:space": "cosine",
        }

    def _safe(self, operation: Callable[[], None]) -> None:
        try:
            operation()
        except SemanticIndexIntegrityError:
            raise
        except (ValidationError, ValueError, TypeError):
            raise SemanticIndexIntegrityError(_SAFE_INDEX_ERROR) from None
        except Exception:
            raise SemanticUnavailableError(_SAFE_INDEX_ERROR) from None

    def _validate_manifest(self) -> None:
        try:
            metadata = self._collection.metadata
        except Exception:
            raise SemanticUnavailableError(_SAFE_INDEX_ERROR) from None
        if any(metadata.get(key) != value for key, value in self._manifest().items()):
            raise SemanticIndexIntegrityError(_SAFE_INDEX_ERROR)

    def is_ready(self) -> bool:
        self._validate_manifest()
        return True

    def count(self) -> int:
        try:
            return self._collection.count()
        except Exception:
            raise SemanticUnavailableError(_SAFE_INDEX_ERROR) from None

    def documents_absent(self) -> bool:
        try:
            parsed = _GetResult.model_validate(
                self._collection.get(include=["metadatas", "documents"])
            )
            return parsed.documents is None or all(
                document is None for document in parsed.documents
            )
        except (ValidationError, ValueError, TypeError):
            raise SemanticIndexIntegrityError(_SAFE_INDEX_ERROR) from None
        except Exception:
            raise SemanticUnavailableError(_SAFE_INDEX_ERROR) from None

    def reconcile(
        self,
        records: tuple[SemanticIndexRecord, ...],
        embeddings: tuple[tuple[float, ...], ...],
    ) -> None:
        if len(records) != len(embeddings) or any(
            len(vector) != self.embedding_dimension for vector in embeddings
        ):
            raise DependencyUnavailableError(_SAFE_INDEX_ERROR)
        ordered = sorted(records, key=lambda record: str(record.chunk.chunk_id))
        vectors_by_id = {
            record.chunk.chunk_id: vector
            for record, vector in zip(records, embeddings, strict=True)
        }
        desired_ids = {str(record.chunk.chunk_id) for record in ordered}

        def operation() -> None:
            existing = _GetResult.model_validate(
                self._collection.get(include=["metadatas", "documents"])
            )
            stale = sorted(set(existing.ids) - desired_ids)
            if stale:
                self._collection.delete(ids=stale)
            if ordered:
                self._collection.upsert(
                    ids=[str(record.chunk.chunk_id) for record in ordered],
                    embeddings=[list(vectors_by_id[record.chunk.chunk_id]) for record in ordered],
                    metadatas=[self._metadata(record) for record in ordered],
                )
            persisted = self._validated_records()
            expected = tuple(
                (str(record.chunk.chunk_id), self._metadata(record)) for record in ordered
            )
            if persisted != expected:
                raise ValueError("semantic index reconciliation mismatch")

        self._safe(operation)

    def _metadata(self, record: SemanticIndexRecord) -> dict[str, str | int | float | bool]:
        chunk = record.chunk
        return {
            "chunk_id": str(chunk.chunk_id),
            "evidence_id": str(chunk.evidence_id),
            "evidence_version_id": str(chunk.evidence_version_id),
            "evidence_type": record.evidence_type.value,
            "sensitivity": record.sensitivity.value,
            "validity": record.validity.value,
            "ordinal": chunk.ordinal,
            "content_hash": chunk.content_hash,
            "index_version": self.version,
            "embedding_provider_version": self.embedding_provider_version,
            "embedding_dimension": self.embedding_dimension,
            "chunk_policy_version": self.chunk_policy_version,
        }

    def _validated_records(
        self,
    ) -> tuple[tuple[str, dict[str, str | int | float | bool]], ...]:
        parsed = _GetResult.model_validate(self._collection.get(include=["metadatas", "documents"]))
        if parsed.metadatas is None or len(parsed.metadatas) != len(parsed.ids):
            raise ValueError("missing semantic metadata")
        if parsed.documents is not None and any(
            document is not None for document in parsed.documents
        ):
            raise ValueError("semantic index must not persist Candidate documents")
        values: list[tuple[str, dict[str, str | int | float | bool]]] = []
        for identity, raw in zip(parsed.ids, parsed.metadatas, strict=True):
            if raw is None:
                raise ValueError("missing semantic metadata")
            metadata = _StoredMetadata.model_validate(raw)
            if (
                identity != metadata.chunk_id
                or metadata.index_version != self.version
                or metadata.embedding_provider_version != self.embedding_provider_version
                or metadata.embedding_dimension != self.embedding_dimension
                or metadata.chunk_policy_version != self.chunk_policy_version
            ):
                raise ValueError("invalid semantic identity")
            values.append((identity, metadata.model_dump(mode="json")))
        values.sort(key=lambda value: value[0])
        return tuple(values)

    def query(
        self,
        embedding: tuple[float, ...],
        *,
        allowed_sensitivities: tuple[EvidenceSensitivity, ...],
        limit: int,
    ) -> tuple[SemanticChunkMatch, ...]:
        if len(embedding) != self.embedding_dimension or limit < 1 or not allowed_sensitivities:
            return ()
        try:
            count = self._collection.count()
            if count == 0:
                return ()
            parsed = _QueryResult.model_validate(
                self._collection.query(
                    query_embeddings=[list(embedding)],
                    n_results=min(limit, count),
                    where={
                        "$and": [
                            {"validity": EvidenceValidity.VALID.value},
                            {
                                "sensitivity": {
                                    "$in": [value.value for value in allowed_sensitivities]
                                }
                            },
                        ]
                    },
                    include=["metadatas", "distances"],
                )
            )
            if parsed.metadatas is None or parsed.distances is None:
                raise ValueError("missing semantic query lineage")
            identities = parsed.ids[0]
            metadata_values = parsed.metadatas[0]
            distances = parsed.distances[0]
            if not (len(identities) == len(metadata_values) == len(distances)):
                raise ValueError("incomplete semantic query lineage")
            matches: list[SemanticChunkMatch] = []
            for identity, raw, distance in zip(identities, metadata_values, distances, strict=True):
                if raw is None:
                    raise ValueError("missing semantic query metadata")
                metadata = _StoredMetadata.model_validate(raw)
                if (
                    identity != metadata.chunk_id
                    or metadata.index_version != self.version
                    or metadata.embedding_provider_version != self.embedding_provider_version
                    or metadata.embedding_dimension != self.embedding_dimension
                    or metadata.chunk_policy_version != self.chunk_policy_version
                ):
                    raise ValueError("incompatible semantic query metadata")
                matches.append(
                    SemanticChunkMatch(
                        chunk_id=EvidenceChunkId(identity),
                        evidence_id=EvidenceItemId(metadata.evidence_id),
                        evidence_version_id=EvidenceVersionId(metadata.evidence_version_id),
                        distance=distance,
                    )
                )
            matches.sort(key=lambda item: (item.distance, str(item.chunk_id)))
            return tuple(matches)
        except (ValidationError, ValueError, TypeError):
            raise SemanticIndexIntegrityError(_SAFE_INDEX_ERROR) from None
        except (SemanticIndexIntegrityError, SemanticUnavailableError):
            raise
        except Exception:
            raise SemanticUnavailableError(_SAFE_INDEX_ERROR) from None


if __name__ == "__main__":
    main()
