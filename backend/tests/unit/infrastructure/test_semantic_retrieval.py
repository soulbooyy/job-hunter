from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from job_hunter.application.candidate_knowledge import SaveEvidence, SaveEvidenceCommand
from job_hunter.domain.ids import (
    CorrelationId,
    EvidenceChunkId,
    EvidenceItemId,
    EvidenceVersionId,
    RequirementId,
    RunId,
)
from job_hunter.domain.knowledge import (
    EvidenceItemVersion,
    EvidenceSensitivity,
    EvidenceType,
    EvidenceValidity,
)
from job_hunter.domain.retrieval import (
    DeterministicEvidenceChunker,
    RetrievalQuery,
    RetrievalStatus,
    RetrievalStrategy,
    RetrievalTaskType,
    SemanticChunkMatch,
    SemanticIndexRecord,
)
from job_hunter.errors import DependencyUnavailableError, SemanticIndexIntegrityError
from job_hunter.infrastructure.chroma import LocalOnnxMiniLmEmbeddingProvider
from job_hunter.infrastructure.memory import InMemoryStore, InMemoryUnitOfWorkFactory
from job_hunter.infrastructure.semantic import SemanticIndexRebuilder, SemanticRetriever
from tests.helpers import DeterministicIdGenerator, FixedClock

NOW = datetime(2026, 8, 31, 18, 0, tzinfo=UTC)


def _evidence(identifier: str, content: str) -> EvidenceItemVersion:
    return EvidenceItemVersion(
        version_id=EvidenceVersionId(f"{identifier}-version"),
        evidence_id=EvidenceItemId(identifier),
        version_number=1,
        evidence_type=EvidenceType.PROJECT,
        canonical_content=content,
        occurred_on=date(2026, 1, 1),
        source="manual",
        provenance="human-confirmed fixture",
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.VALID,
        created_at=NOW,
        correlation_id=CorrelationId("correlation-evidence"),
        run_id=RunId("run-evidence"),
    )


class _EmbeddingProvider:
    @property
    def version(self) -> str:
        return "semantic-test-v1"

    @property
    def dimension(self) -> int:
        return 2

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple((1.0, 0.0) for _text in texts)


class _SemanticIndex:
    def __init__(self, matches: tuple[SemanticChunkMatch, ...] = ()) -> None:
        self.records: tuple[SemanticIndexRecord, ...] = ()
        self.matches = matches

    @property
    def version(self) -> str:
        return "semantic-index-test-v1"

    @property
    def chunk_policy_version(self) -> str:
        return "evidence-chunk-v1"

    @property
    def embedding_provider_version(self) -> str:
        return "semantic-test-v1"

    @property
    def embedding_dimension(self) -> int:
        return 2

    def is_ready(self) -> bool:
        return True

    def reconcile(
        self,
        records: tuple[SemanticIndexRecord, ...],
        embeddings: tuple[tuple[float, ...], ...],
    ) -> None:
        assert len(records) == len(embeddings)
        self.records = records

    def query(
        self,
        embedding: tuple[float, ...],
        *,
        allowed_sensitivities: tuple[EvidenceSensitivity, ...],
        limit: int,
    ) -> tuple[SemanticChunkMatch, ...]:
        del embedding, allowed_sensitivities, limit
        return self.matches


def test_semantic_retriever_rejects_stale_index_lineage_and_keeps_chunk_identity() -> None:
    alpha = _evidence("alpha", "synthetic alpha evidence")
    beta = _evidence("beta", "synthetic beta evidence")
    chunks = DeterministicEvidenceChunker().chunk((alpha, beta))
    chunks_by_version = {chunk.evidence_version_id: chunk for chunk in chunks}
    beta_chunk = chunks_by_version[beta.version_id]
    retriever = SemanticRetriever(
        embedding_provider=_EmbeddingProvider(),
        index=_SemanticIndex(
            (
                SemanticChunkMatch(
                    chunk_id=beta_chunk.chunk_id,
                    evidence_id=beta.evidence_id,
                    evidence_version_id=beta.version_id,
                    distance=0.1,
                ),
            )
        ),
        allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
    )

    result = retriever.retrieve(
        RetrievalQuery(
            requirement_id=RequirementId("requirement-1"),
            text="ambiguous delivery leadership",
            task_type=RetrievalTaskType.DEEP_FIT,
            max_tokens=20,
            top_k=5,
        ),
        (alpha, beta),
    )

    assert retriever.strategy is RetrievalStrategy.SEMANTIC
    assert result.status is RetrievalStatus.COMPLETED
    assert tuple(hit.evidence_id for hit in result.hits) == (beta.evidence_id,)
    assert result.hits[0].evidence_chunk_ids == (beta_chunk.chunk_id,)


def test_semantic_retriever_does_not_promote_the_nearest_irrelevant_vector() -> None:
    alpha = _evidence("alpha", "synthetic alpha evidence")
    chunk = DeterministicEvidenceChunker().chunk((alpha,))[0]
    retriever = SemanticRetriever(
        embedding_provider=_EmbeddingProvider(),
        index=_SemanticIndex(
            (
                SemanticChunkMatch(
                    chunk_id=chunk.chunk_id,
                    evidence_id=alpha.evidence_id,
                    evidence_version_id=alpha.version_id,
                    distance=0.750_001,
                ),
            )
        ),
        allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
    )

    result = retriever.retrieve(
        RetrievalQuery(
            requirement_id=RequirementId("requirement-1"),
            text="unrelated synthetic query",
            task_type=RetrievalTaskType.DEEP_FIT,
            max_tokens=20,
            top_k=5,
        ),
        (alpha,),
    )

    assert result.status is RetrievalStatus.NO_RELEVANT_EVIDENCE
    assert result.hits == ()
    assert result.selected_estimated_tokens == 0


@pytest.mark.parametrize("distance", (0.1, 0.9))
def test_semantic_retriever_fails_closed_on_unknown_authoritative_chunk(
    distance: float,
) -> None:
    alpha = _evidence("alpha", "synthetic alpha evidence")
    retriever = SemanticRetriever(
        embedding_provider=_EmbeddingProvider(),
        index=_SemanticIndex(
            (
                SemanticChunkMatch(
                    chunk_id=EvidenceChunkId("chunk-fabricated"),
                    evidence_id=alpha.evidence_id,
                    evidence_version_id=alpha.version_id,
                    distance=distance,
                ),
            )
        ),
        allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
    )

    with pytest.raises(DependencyUnavailableError, match="invalid lineage"):
        retriever.retrieve(
            RetrievalQuery(
                requirement_id=RequirementId("requirement-1"),
                text="synthetic query",
                task_type=RetrievalTaskType.DEEP_FIT,
                max_tokens=20,
                top_k=5,
            ),
            (alpha,),
        )


class _CorruptSemanticIndex(_SemanticIndex):
    def query(
        self,
        embedding: tuple[float, ...],
        *,
        allowed_sensitivities: tuple[EvidenceSensitivity, ...],
        limit: int,
    ) -> tuple[SemanticChunkMatch, ...]:
        del embedding, allowed_sensitivities, limit
        raise SemanticIndexIntegrityError("semantic index is invalid")


def test_semantic_retriever_preserves_index_integrity_failure() -> None:
    retriever = SemanticRetriever(
        embedding_provider=_EmbeddingProvider(),
        index=_CorruptSemanticIndex(),
        allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
    )

    with pytest.raises(SemanticIndexIntegrityError):
        retriever.retrieve(
            RetrievalQuery(
                requirement_id=RequirementId("requirement-1"),
                text="synthetic query",
                task_type=RetrievalTaskType.DEEP_FIT,
                max_tokens=20,
                top_k=5,
            ),
            (_evidence("alpha", "synthetic alpha evidence"),),
        )


def test_semantic_rebuild_projects_only_active_sqlite_evidence_version() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    save = SaveEvidence(
        unit_of_work_factory=factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    )
    first = save.execute(
        SaveEvidenceCommand(
            evidence_type=EvidenceType.PROJECT,
            canonical_content="Synthetic first version",
            occurred_on=date(2026, 1, 1),
            source="manual",
            provenance="synthetic fixture",
            sensitivity=EvidenceSensitivity.PUBLIC,
            validity=EvidenceValidity.VALID,
            existing_evidence_id=None,
            correlation_id=CorrelationId("correlation-first"),
            run_id=RunId("run-first"),
        )
    )
    second = save.execute(
        SaveEvidenceCommand(
            evidence_type=EvidenceType.PROJECT,
            canonical_content="Synthetic active second version",
            occurred_on=date(2026, 1, 2),
            source="manual",
            provenance="synthetic fixture",
            sensitivity=EvidenceSensitivity.PUBLIC,
            validity=EvidenceValidity.VALID,
            existing_evidence_id=first.evidence_id,
            correlation_id=CorrelationId("correlation-second"),
            run_id=RunId("run-second"),
        )
    )
    index = _SemanticIndex()

    result = SemanticIndexRebuilder(
        unit_of_work_factory=factory,
        embedding_provider=_EmbeddingProvider(),
        index=index,
    ).rebuild()

    assert result.active_evidence_count == 1
    assert {record.chunk.evidence_version_id for record in index.records} == {
        second.active_version_id
    }


def test_missing_embedding_artifact_is_redacted_dependency_failure(tmp_path: Path) -> None:
    missing = tmp_path / "candidate-name-must-not-leak"

    with pytest.raises(
        DependencyUnavailableError,
        match="semantic embedding model is unavailable",
    ) as error:
        LocalOnnxMiniLmEmbeddingProvider(model_path=missing)

    assert str(missing) not in str(error.value)
