"""Semantic derivative lifecycle and retriever over explicit typed ports."""

from dataclasses import dataclass

from job_hunter.application.ports import (
    EmbeddingProvider,
    SemanticIndex,
    UnitOfWorkFactory,
)
from job_hunter.domain.ids import EvidenceChunkId, EvidenceVersionId
from job_hunter.domain.knowledge import EvidenceItemVersion, EvidenceSensitivity
from job_hunter.domain.retrieval import (
    SEMANTIC_CHROMA_V1_MAX_COSINE_DISTANCE,
    DeterministicEvidenceChunker,
    RetrievalHit,
    RetrievalMatchReason,
    RetrievalQuery,
    RetrievalStatus,
    RetrievalStrategy,
    RetrieverResult,
    SemanticIndexRecord,
    estimate_tokens,
)
from job_hunter.errors import (
    DependencyUnavailableError,
    JobHunterError,
    SemanticIndexIntegrityError,
    SemanticUnavailableError,
)


@dataclass(frozen=True, slots=True)
class SemanticRebuildResult:
    active_evidence_count: int
    chunk_count: int
    index_version: str
    embedding_provider_version: str
    chunk_policy_version: str


class SemanticIndexRebuilder:
    """Reconcile the derivative index only from active authoritative SQLite Evidence."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        embedding_provider: EmbeddingProvider,
        index: SemanticIndex,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._embedding_provider = embedding_provider
        self._index = index
        self._chunker = DeterministicEvidenceChunker()

    def rebuild(self) -> SemanticRebuildResult:
        try:
            unit_of_work = self._unit_of_work_factory()
            try:
                items = unit_of_work.knowledge.list_evidence()
                versions = tuple(
                    unit_of_work.knowledge.get_evidence_version(item.active_version_id)
                    for item in items
                )
            finally:
                unit_of_work.close()
            chunks = self._chunker.chunk(versions)
            versions_by_id = {item.version_id: item for item in versions}
            records = tuple(
                SemanticIndexRecord(
                    chunk=chunk,
                    evidence_type=versions_by_id[chunk.evidence_version_id].evidence_type,
                    sensitivity=versions_by_id[chunk.evidence_version_id].sensitivity,
                    validity=versions_by_id[chunk.evidence_version_id].validity,
                )
                for chunk in chunks
            )
            embeddings = self._embedding_provider.embed(tuple(chunk.content for chunk in chunks))
            if len(embeddings) != len(chunks):
                raise DependencyUnavailableError(
                    "semantic embedding provider returned invalid accounting"
                )
            self._index.reconcile(records, embeddings)
        except JobHunterError:
            raise
        except Exception:
            raise DependencyUnavailableError("semantic index rebuild is unavailable") from None
        return SemanticRebuildResult(
            active_evidence_count=len(versions),
            chunk_count=len(chunks),
            index_version=self._index.version,
            embedding_provider_version=self._embedding_provider.version,
            chunk_policy_version=self._index.chunk_policy_version,
        )


class SemanticRetriever:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        index: SemanticIndex,
        allowed_sensitivities: tuple[EvidenceSensitivity, ...],
    ) -> None:
        self._embedding_provider = embedding_provider
        self._index = index
        self._allowed_sensitivities = allowed_sensitivities

    @property
    def strategy(self) -> RetrievalStrategy:
        return RetrievalStrategy.SEMANTIC

    @property
    def version(self) -> str:
        return "semantic-chroma-v1"

    @property
    def token_estimator_version(self) -> str:
        return "deterministic-token-estimator-v1"

    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> RetrieverResult:
        if not self._index.is_ready():
            raise SemanticUnavailableError("semantic index is unavailable")
        try:
            query_embeddings = self._embedding_provider.embed((query.text,))
            if len(query_embeddings) != 1:
                raise SemanticUnavailableError(
                    "semantic embedding provider returned invalid accounting"
                )
            matches = self._index.query(
                query_embeddings[0],
                allowed_sensitivities=self._allowed_sensitivities,
                limit=max(query.top_k * 4, query.top_k),
            )
        except (SemanticUnavailableError, SemanticIndexIntegrityError):
            raise
        except JobHunterError:
            raise
        except Exception:
            # Only explicitly typed runtime-unavailable failures may activate
            # policy fallback; an unexpected contract failure stays fail-closed.
            raise DependencyUnavailableError("semantic retrieval failed safely") from None
        authoritative_chunks = DeterministicEvidenceChunker().chunk(evidence)
        authority_by_chunk = {chunk.chunk_id: chunk for chunk in authoritative_chunks}
        if len(authority_by_chunk) != len(authoritative_chunks):
            raise DependencyUnavailableError("semantic authority contains duplicate chunks")
        by_version = {item.version_id: item for item in evidence}
        aggregated: dict[
            EvidenceVersionId,
            tuple[float, EvidenceItemVersion, list[EvidenceChunkId]],
        ] = {}
        for match in matches:
            authoritative_chunk = authority_by_chunk.get(match.chunk_id)
            if (
                authoritative_chunk is None
                or authoritative_chunk.evidence_id != match.evidence_id
                or authoritative_chunk.evidence_version_id != match.evidence_version_id
            ):
                # Validate every source result before applying relevance cutoff;
                # an irrelevant corrupt match is still persisted-index corruption.
                raise DependencyUnavailableError("semantic index returned invalid lineage")
            if match.distance > SEMANTIC_CHROMA_V1_MAX_COSINE_DISTANCE:
                # semantic-chroma-v1 freezes an explicit relevance boundary so
                # the nearest vector is not automatically treated as evidence.
                continue
            item = by_version.get(match.evidence_version_id)
            if item is None or item.evidence_id != match.evidence_id:
                raise DependencyUnavailableError("semantic index returned invalid lineage")
            existing = aggregated.get(match.evidence_version_id)
            if existing is None:
                aggregated[match.evidence_version_id] = (
                    match.distance,
                    item,
                    [match.chunk_id],
                )
            else:
                if match.chunk_id not in existing[2]:
                    existing[2].append(match.chunk_id)
                if match.distance < existing[0]:
                    aggregated[match.evidence_version_id] = (
                        match.distance,
                        item,
                        existing[2],
                    )
        candidates = sorted(
            aggregated.values(),
            key=lambda value: (
                value[0],
                str(value[1].evidence_id),
                str(value[1].version_id),
            ),
        )
        selected: list[tuple[float, EvidenceItemVersion, list[EvidenceChunkId]]] = []
        selected_tokens = 0
        for distance, item, chunk_ids in candidates[: query.top_k]:
            item_tokens = estimate_tokens(item.canonical_content)
            if selected_tokens + item_tokens > query.max_tokens:
                break
            selected.append((distance, item, chunk_ids))
            selected_tokens += item_tokens
        hits = tuple(
            RetrievalHit(
                evidence_id=item.evidence_id,
                evidence_version_id=item.version_id,
                rank=rank,
                score=max(0.0, 1.0 - distance),
                reasons=(RetrievalMatchReason.SEMANTIC_SIMILARITY,),
                evidence_chunk_ids=tuple(chunk_ids),
            )
            for rank, (distance, item, chunk_ids) in enumerate(selected, start=1)
        )
        if hits:
            status = RetrievalStatus.COMPLETED
        elif candidates:
            status = RetrievalStatus.NOT_EXECUTABLE
        else:
            status = RetrievalStatus.NO_RELEVANT_EVIDENCE
        return RetrieverResult(
            status=status,
            hits=hits,
            eligible_count=len(evidence),
            eligible_estimated_tokens=sum(
                estimate_tokens(item.canonical_content) for item in evidence
            ),
            selected_estimated_tokens=selected_tokens,
        )
