"""Frozen synthetic contracts for the bounded Chroma feasibility spike."""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from job_hunter.domain.ids import EvidenceItemId, EvidenceVersionId
from job_hunter.domain.knowledge import EvidenceSensitivity, EvidenceType, EvidenceValidity
from job_hunter.errors import InputValidationError

SCHEMA_VERSION = "chroma-feasibility-v1"
EMBEDDING_PROVIDER = "job-hunter-synthetic"
EMBEDDING_MODEL = "deterministic-hash-v1"
EMBEDDING_DIMENSION = 64
CHUNK_POLICY_VERSION = "whole-evidence-spike-v1"
INDEX_VERSION = "chroma-index-spike-v1"
DISTANCE_METRIC = "cosine"


class IndexManifest(BaseModel):
    """Versioned parameters required to interpret a persisted spike collection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    chunk_policy_version: str
    index_version: str
    distance_metric: str

    @classmethod
    def default(cls) -> IndexManifest:
        return cls(
            schema_version=SCHEMA_VERSION,
            embedding_provider=EMBEDDING_PROVIDER,
            embedding_model=EMBEDDING_MODEL,
            embedding_dimension=EMBEDDING_DIMENSION,
            chunk_policy_version=CHUNK_POLICY_VERSION,
            index_version=INDEX_VERSION,
            distance_metric=DISTANCE_METRIC,
        )

    def collection_metadata(self) -> dict[str, str | int | float | bool]:
        metadata: dict[str, str | int | float | bool] = self.model_dump()
        # Chroma reads this reserved collection key when creating the HNSW index.
        metadata["hnsw:space"] = self.distance_metric
        return metadata


def _float32(value: float) -> float:
    return struct.unpack("!f", struct.pack("!f", value))[0]


def deterministic_embedding(value: str) -> tuple[float, ...]:
    """Return an offline test vector; it is deliberately not a semantic model."""
    if not value.strip():
        raise InputValidationError("synthetic embedding input is required")
    raw_values: list[float] = []
    for block in range(4):
        digest = hashlib.sha256(f"{block}:{value}".encode()).digest()
        for offset in range(0, len(digest), 2):
            integer = int.from_bytes(digest[offset : offset + 2], byteorder="big")
            raw_values.append((integer / 32767.5) - 1.0)
    norm = math.sqrt(sum(component * component for component in raw_values))
    return tuple(_float32(component / norm) for component in raw_values)


@dataclass(frozen=True, slots=True)
class IndexRecord:
    """One active EvidenceVersion identity plus explicit synthetic embedding."""

    evidence_id: EvidenceItemId
    evidence_version_id: EvidenceVersionId
    evidence_type: EvidenceType
    sensitivity: EvidenceSensitivity
    validity: EvidenceValidity
    embedding: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.embedding) != EMBEDDING_DIMENSION:
            raise InputValidationError(
                f"spike embedding must contain {EMBEDDING_DIMENSION} dimensions"
            )

    def metadata(self, manifest: IndexManifest) -> dict[str, str | int | float | bool]:
        return {
            "evidence_id": str(self.evidence_id),
            "evidence_version_id": str(self.evidence_version_id),
            "evidence_type": self.evidence_type.value,
            "sensitivity": self.sensitivity.value,
            "validity": self.validity.value,
            "index_version": manifest.index_version,
            "chunk_policy_version": manifest.chunk_policy_version,
        }


@dataclass(frozen=True, slots=True)
class QueryHit:
    evidence_id: EvidenceItemId
    evidence_version_id: EvidenceVersionId
    distance: float
