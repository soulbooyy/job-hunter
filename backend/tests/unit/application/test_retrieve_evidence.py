from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Never, cast

import pytest

from job_hunter.application.candidate_knowledge import (
    CreateCandidateProfile,
    CreateCandidateProfileCommand,
    SaveEvidence,
    SaveEvidenceCommand,
)
from job_hunter.application.context import (
    BuildContextPackage,
    BuildContextPackageCommand,
)
from job_hunter.application.import_job import ImportJob, ImportJobCommand
from job_hunter.application.ports import (
    CandidateKnowledgeRepository,
    ContextRepository,
    JobRepository,
    RetrievalRepository,
    ScreeningRepository,
    UnitOfWork,
)
from job_hunter.application.retrieval import RetrieveEvidence, RetrieveEvidenceCommand
from job_hunter.application.screening import (
    RecordJobTriage,
    RecordJobTriageCommand,
    RunQuickScreen,
    RunQuickScreenCommand,
)
from job_hunter.domain.context import ContextEntryKind, ContextRedaction
from job_hunter.domain.ids import (
    CorrelationId,
    EvidenceChunkId,
    EvidenceItemId,
    EvidenceVersionId,
    JobId,
    QuickScreenResultId,
    RequirementId,
    RunId,
)
from job_hunter.domain.knowledge import (
    EvidenceItem,
    EvidenceItemVersion,
    EvidenceSensitivity,
    EvidenceType,
    EvidenceValidity,
)
from job_hunter.domain.retrieval import (
    DeterministicEvidenceChunker,
    EvidenceExclusionReason,
    RetrievalFallbackReason,
    RetrievalHit,
    RetrievalMatchReason,
    RetrievalPromotionEvidence,
    RetrievalQuery,
    RetrievalStatus,
    RetrievalStrategy,
    RetrieverResult,
)
from job_hunter.domain.screening import TriageDecision
from job_hunter.errors import (
    ConflictError,
    ContextBudgetExceededError,
    DependencyUnavailableError,
    SemanticUnavailableError,
)
from job_hunter.infrastructure.memory import InMemoryStore, InMemoryUnitOfWorkFactory
from job_hunter.infrastructure.retrieval import (
    FullContextRetriever,
    LexicalMetadataRetriever,
    estimate_tokens,
)
from job_hunter.ingestion.manual import JobSourceRegistry, ManualJDInput, ManualJDSource
from tests.helpers import DeterministicIdGenerator, FixedClock

NOW = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)


class _FailingRetriever:
    @property
    def strategy(self) -> RetrievalStrategy:
        return RetrievalStrategy.FULL_CONTEXT

    @property
    def version(self) -> str:
        return "failing-v1"

    @property
    def token_estimator_version(self) -> str:
        return "failing-token-v1"

    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> Never:
        del query, evidence
        raise RuntimeError("secret retriever failure")


class _FabricatingRetriever:
    @property
    def strategy(self) -> RetrievalStrategy:
        return RetrievalStrategy.FULL_CONTEXT

    @property
    def version(self) -> str:
        return "fabricating-v1"

    @property
    def token_estimator_version(self) -> str:
        return "fabricating-token-v1"

    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> RetrieverResult:
        del query, evidence
        return RetrieverResult(
            status=RetrievalStatus.COMPLETED,
            hits=(
                RetrievalHit(
                    evidence_id=EvidenceItemId("fabricated-evidence"),
                    evidence_version_id=EvidenceVersionId("fabricated-version"),
                    rank=1,
                    score=1.0,
                    reasons=(RetrievalMatchReason.FULL_CONTEXT,),
                ),
            ),
            eligible_count=0,
            eligible_estimated_tokens=0,
            selected_estimated_tokens=0,
        )


class _TruncatingFullContextRetriever:
    @property
    def strategy(self) -> RetrievalStrategy:
        return RetrievalStrategy.FULL_CONTEXT

    @property
    def version(self) -> str:
        return "truncating-v1"

    @property
    def token_estimator_version(self) -> str:
        return "test-token-v1"

    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> RetrieverResult:
        del query
        selected = evidence[0]
        return RetrieverResult(
            status=RetrievalStatus.COMPLETED,
            hits=(
                RetrievalHit(
                    evidence_id=selected.evidence_id,
                    evidence_version_id=selected.version_id,
                    rank=1,
                    score=1.0,
                    reasons=(RetrievalMatchReason.FULL_CONTEXT,),
                ),
            ),
            eligible_count=len(evidence),
            eligible_estimated_tokens=2,
            selected_estimated_tokens=1,
        )


class _UnderreportingLexicalRetriever:
    @property
    def strategy(self) -> RetrievalStrategy:
        return RetrievalStrategy.LEXICAL_METADATA

    @property
    def version(self) -> str:
        return "underreporting-v1"

    @property
    def token_estimator_version(self) -> str:
        return "deterministic-token-estimator-v1"

    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> RetrieverResult:
        del query
        selected = evidence[0]
        return RetrieverResult(
            status=RetrievalStatus.COMPLETED,
            hits=(
                RetrievalHit(
                    evidence_id=selected.evidence_id,
                    evidence_version_id=selected.version_id,
                    rank=1,
                    score=1.0,
                    reasons=(RetrievalMatchReason.TOKEN_OVERLAP,),
                ),
            ),
            eligible_count=len(evidence),
            eligible_estimated_tokens=1,
            selected_estimated_tokens=1,
        )


class _CountingFullContextRetriever:
    def __init__(self) -> None:
        self.called = False
        self._delegate = FullContextRetriever()

    @property
    def strategy(self) -> RetrievalStrategy:
        return self._delegate.strategy

    @property
    def version(self) -> str:
        return self._delegate.version

    @property
    def token_estimator_version(self) -> str:
        return self._delegate.token_estimator_version

    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> RetrieverResult:
        self.called = True
        return self._delegate.retrieve(query, evidence)


class _SupplementalHybridRetriever:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.selected_chunk_id: EvidenceChunkId | None = None

    @property
    def strategy(self) -> RetrievalStrategy:
        return RetrievalStrategy.HYBRID

    @property
    def version(self) -> str:
        return "hybrid-rrf-v1"

    @property
    def token_estimator_version(self) -> str:
        return "deterministic-token-estimator-v1"

    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> RetrieverResult:
        self.queries.append(query.text)
        eligible_tokens = sum(estimate_tokens(item.canonical_content) for item in evidence)
        if len(self.queries) == 1:
            return RetrieverResult(
                status=RetrievalStatus.NO_RELEVANT_EVIDENCE,
                hits=(),
                eligible_count=len(evidence),
                eligible_estimated_tokens=eligible_tokens,
                selected_estimated_tokens=0,
            )
        selected = evidence[0]
        chunks = DeterministicEvidenceChunker().chunk((selected,))
        selected_chunk_id = chunks[-1].chunk_id
        self.selected_chunk_id = selected_chunk_id
        selected_tokens = estimate_tokens(selected.canonical_content)
        return RetrieverResult(
            status=RetrievalStatus.COMPLETED,
            hits=(
                RetrievalHit(
                    evidence_id=selected.evidence_id,
                    evidence_version_id=selected.version_id,
                    rank=1,
                    score=1.0,
                    reasons=(RetrievalMatchReason.HYBRID_FUSION,),
                    evidence_chunk_ids=(selected_chunk_id,),
                ),
            ),
            eligible_count=len(evidence),
            eligible_estimated_tokens=eligible_tokens,
            selected_estimated_tokens=selected_tokens,
        )


class _UnavailableHybridRetriever(_SupplementalHybridRetriever):
    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> Never:
        del query, evidence
        raise SemanticUnavailableError("semantic retrieval is unavailable")


class _EmptyHybridRetriever(_SupplementalHybridRetriever):
    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> RetrieverResult:
        self.queries.append(query.text)
        return RetrieverResult(
            status=RetrievalStatus.NO_RELEVANT_EVIDENCE,
            hits=(),
            eligible_count=len(evidence),
            eligible_estimated_tokens=sum(
                estimate_tokens(item.canonical_content) for item in evidence
            ),
            selected_estimated_tokens=0,
        )


class _InvalidHybridLineageRetriever(_SupplementalHybridRetriever):
    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> Never:
        del query, evidence
        raise DependencyUnavailableError("Hybrid source retriever returned invalid lineage")


def _promotion_evidence() -> RetrievalPromotionEvidence:
    return RetrievalPromotionEvidence(
        dataset_version="frozen-holdout-v1",
        split="frozen_holdout",
        human_reviewed=True,
        minimum_dataset_gate=True,
        recall_at_5=0.90,
        direct_mrr=0.80,
        no_evidence_accuracy=0.95,
        no_evidence_total=10,
        final_context_token_reduction=0.40,
        large_context_case_count=10,
        large_context_no_evidence_count=2,
        recall_degradation=0.02,
        no_evidence_degradation=0.01,
    )


class _CorruptKnowledgeRepository:
    def __init__(
        self,
        delegate: CandidateKnowledgeRepository,
        returned_version: EvidenceItemVersion,
    ) -> None:
        self._delegate = delegate
        self._returned_version = returned_version

    def list_evidence(self) -> tuple[EvidenceItem, ...]:
        return self._delegate.list_evidence()

    def get_evidence_version(self, version_id: EvidenceVersionId) -> EvidenceItemVersion:
        del version_id
        return self._returned_version


class _CorruptUnitOfWork:
    def __init__(self, delegate: UnitOfWork, returned_version: EvidenceItemVersion) -> None:
        self._delegate = delegate
        self._knowledge = cast(
            CandidateKnowledgeRepository,
            _CorruptKnowledgeRepository(delegate.knowledge, returned_version),
        )
        self.commit_count = 0

    @property
    def jobs(self) -> JobRepository:
        return self._delegate.jobs

    @property
    def knowledge(self) -> CandidateKnowledgeRepository:
        return self._knowledge

    @property
    def screening(self) -> ScreeningRepository:
        return self._delegate.screening

    @property
    def retrieval(self) -> RetrievalRepository:
        return self._delegate.retrieval

    @property
    def context(self) -> ContextRepository:
        return self._delegate.context

    def commit(self) -> None:
        self.commit_count += 1
        self._delegate.commit()

    def rollback(self) -> None:
        self._delegate.rollback()

    def close(self) -> None:
        self._delegate.close()


class _SingleUnitOfWorkFactory:
    def __init__(self, unit_of_work: UnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    def __call__(self) -> UnitOfWork:
        return self._unit_of_work


def _import_job(
    factory: InMemoryUnitOfWorkFactory,
    ids: DeterministicIdGenerator,
    *,
    existing_job_id: JobId | None = None,
) -> JobId:
    result = ImportJob(
        source_registry=JobSourceRegistry((ManualJDSource(),)),
        unit_of_work_factory=factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        ImportJobCommand(
            source_input=ManualJDInput(
                title="Senior AI Engineer",
                company="Example AI",
                city="Shenzhen",
                content="- Must have Python evaluation experience",
            ),
            correlation_id=CorrelationId("correlation-import"),
            run_id=RunId("run-import"),
            existing_job_id=existing_job_id,
        )
    )
    return result.job_id


def _screen(
    factory: InMemoryUnitOfWorkFactory,
    ids: DeterministicIdGenerator,
    job_id: JobId,
) -> tuple[RequirementId, QuickScreenResultId]:
    CreateCandidateProfile(
        unit_of_work_factory=factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        CreateCandidateProfileCommand(
            target_role_keywords=("AI Engineer",),
            skill_keywords=("Python",),
            preferred_cities=("Shenzhen",),
            correlation_id=CorrelationId("correlation-profile"),
            run_id=RunId("run-profile"),
        )
    )
    screened = RunQuickScreen(
        unit_of_work_factory=factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        RunQuickScreenCommand(
            job_id=job_id,
            correlation_id=CorrelationId("correlation-screen"),
            run_id=RunId("run-screen"),
        )
    )
    return screened.requirement_ids[0], screened.quick_screen_result_id


def _shortlist(
    factory: InMemoryUnitOfWorkFactory,
    ids: DeterministicIdGenerator,
    job_id: JobId,
) -> RequirementId:
    requirement_id, screen_result_id = _screen(factory, ids, job_id)
    RecordJobTriage(
        unit_of_work_factory=factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        RecordJobTriageCommand(
            job_id=job_id,
            quick_screen_result_id=screen_result_id,
            decision=TriageDecision.SHORTLISTED,
            correlation_id=CorrelationId("correlation-triage"),
            run_id=RunId("run-triage"),
        )
    )
    return requirement_id


def _save_evidence(
    factory: InMemoryUnitOfWorkFactory,
    ids: DeterministicIdGenerator,
    *,
    content: str,
    sensitivity: EvidenceSensitivity,
    validity: EvidenceValidity,
    existing_evidence_id: EvidenceItemId | None = None,
) -> EvidenceItemId:
    result = SaveEvidence(
        unit_of_work_factory=factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        SaveEvidenceCommand(
            evidence_type=EvidenceType.PROJECT,
            canonical_content=content,
            occurred_on=date(2026, 6, 1),
            source="manual",
            provenance="human-confirmed fixture",
            sensitivity=sensitivity,
            validity=validity,
            existing_evidence_id=existing_evidence_id,
            correlation_id=CorrelationId("correlation-evidence"),
            run_id=RunId("run-evidence"),
        )
    )
    return result.evidence_id


def test_retrieve_evidence_persists_authoritative_lineage_and_exclusions() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    job_id = _import_job(factory, ids)
    requirement_id = _shortlist(factory, ids, job_id)
    _save_evidence(
        factory,
        ids,
        content="Built a Python evaluation pipeline",
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.VALID,
    )
    _save_evidence(
        factory,
        ids,
        content="Sensitive private project",
        sensitivity=EvidenceSensitivity.SENSITIVE,
        validity=EvidenceValidity.VALID,
    )
    _save_evidence(
        factory,
        ids,
        content="Expired Python project",
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.EXPIRED,
    )

    result = RetrieveEvidence(
        unit_of_work_factory=factory,
        retriever=FullContextRetriever(),
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        RetrieveEvidenceCommand(
            requirement_id=requirement_id,
            allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
            max_tokens=100,
            top_k=5,
            correlation_id=CorrelationId("correlation-retrieve"),
            run_id=RunId("run-retrieve"),
        )
    )

    stored = store.get_retrieval_run(result.retrieval_run_id)
    assert result.status is RetrievalStatus.COMPLETED
    assert stored.requirement_id == requirement_id
    assert stored.job_version_id == store.get_job(job_id).active_version_id
    assert len(stored.hits) == 1
    assert {item.reason for item in stored.exclusions} == {
        EvidenceExclusionReason.INVALID,
        EvidenceExclusionReason.SENSITIVITY_NOT_ALLOWED,
    }
    assert stored.correlation_id == CorrelationId("correlation-retrieve")
    assert stored.run_id == RunId("run-retrieve")


def test_retrieve_evidence_requires_shortlisted_current_job_version() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    job_id = _import_job(factory, ids)
    _shortlist(factory, ids, job_id)
    _import_job(factory, ids, existing_job_id=job_id)
    old_requirement = store.list_requirements(store.get_job(job_id).version_ids[0])[0]

    with pytest.raises(ConflictError, match="current JobVersion"):
        RetrieveEvidence(
            unit_of_work_factory=factory,
            retriever=FullContextRetriever(),
            clock=FixedClock(NOW),
            id_generator=ids,
        ).execute(
            RetrieveEvidenceCommand(
                requirement_id=old_requirement.requirement_id,
                allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
                max_tokens=100,
                top_k=5,
                correlation_id=CorrelationId("correlation-retrieve"),
                run_id=RunId("run-retrieve"),
            )
        )


def test_retrieve_evidence_rejects_a_job_that_is_only_screened() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    job_id = _import_job(factory, ids)
    requirement_id, _screen_result_id = _screen(factory, ids, job_id)

    with pytest.raises(ConflictError, match="must be shortlisted"):
        RetrieveEvidence(
            unit_of_work_factory=factory,
            retriever=FullContextRetriever(),
            clock=FixedClock(NOW),
            id_generator=ids,
        ).execute(
            RetrieveEvidenceCommand(
                requirement_id=requirement_id,
                allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
                max_tokens=100,
                top_k=5,
                correlation_id=CorrelationId("correlation-retrieve"),
                run_id=RunId("run-retrieve"),
            )
        )


def test_retriever_exception_does_not_cross_application_boundary() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    job_id = _import_job(factory, ids)
    requirement_id = _shortlist(factory, ids, job_id)

    with pytest.raises(
        DependencyUnavailableError,
        match="evidence retrieval dependency is unavailable",
    ) as error:
        RetrieveEvidence(
            unit_of_work_factory=factory,
            retriever=_FailingRetriever(),
            clock=FixedClock(NOW),
            id_generator=ids,
        ).execute(
            RetrieveEvidenceCommand(
                requirement_id=requirement_id,
                allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
                max_tokens=100,
                top_k=5,
                correlation_id=CorrelationId("correlation-retrieve"),
                run_id=RunId("run-retrieve"),
            )
        )

    assert "secret" not in str(error.value)
    assert store.list_retrieval_runs(requirement_id) == ()


def test_retriever_cannot_fabricate_evidence_lineage() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    job_id = _import_job(factory, ids)
    requirement_id = _shortlist(factory, ids, job_id)

    with pytest.raises(
        DependencyUnavailableError,
        match="evidence retriever returned invalid lineage",
    ):
        RetrieveEvidence(
            unit_of_work_factory=factory,
            retriever=_FabricatingRetriever(),
            clock=FixedClock(NOW),
            id_generator=ids,
        ).execute(
            RetrieveEvidenceCommand(
                requirement_id=requirement_id,
                allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
                max_tokens=100,
                top_k=5,
                correlation_id=CorrelationId("correlation-retrieve"),
                run_id=RunId("run-retrieve"),
            )
        )

    assert store.list_retrieval_runs(requirement_id) == ()


def test_full_context_adapter_cannot_silently_truncate_eligible_evidence() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    job_id = _import_job(factory, ids)
    requirement_id = _shortlist(factory, ids, job_id)
    for content in ("Python platform", "Python service"):
        _save_evidence(
            factory,
            ids,
            content=content,
            sensitivity=EvidenceSensitivity.PUBLIC,
            validity=EvidenceValidity.VALID,
        )

    with pytest.raises(
        DependencyUnavailableError,
        match="full-context contract",
    ):
        RetrieveEvidence(
            unit_of_work_factory=factory,
            retriever=_TruncatingFullContextRetriever(),
            clock=FixedClock(NOW),
            id_generator=ids,
        ).execute(
            RetrieveEvidenceCommand(
                requirement_id=requirement_id,
                allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
                max_tokens=100,
                top_k=5,
                correlation_id=CorrelationId("correlation-retrieve"),
                run_id=RunId("run-retrieve"),
            )
        )

    assert store.list_retrieval_runs(requirement_id) == ()


def test_application_recomputes_retriever_token_accounting_from_evidence() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    job_id = _import_job(factory, ids)
    requirement_id = _shortlist(factory, ids, job_id)
    _save_evidence(
        factory,
        ids,
        content=" ".join(f"synthetic{index}" for index in range(100)),
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.VALID,
    )

    with pytest.raises(DependencyUnavailableError, match="token accounting"):
        RetrieveEvidence(
            unit_of_work_factory=factory,
            retriever=_UnderreportingLexicalRetriever(),
            clock=FixedClock(NOW),
            id_generator=ids,
        ).execute(
            RetrieveEvidenceCommand(
                requirement_id=requirement_id,
                allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
                max_tokens=10,
                top_k=5,
                correlation_id=CorrelationId("correlation-retrieve"),
                run_id=RunId("run-retrieve"),
            )
        )

    assert store.list_retrieval_runs(requirement_id) == ()


@pytest.mark.parametrize(
    "corruption",
    ("historical_version", "wrong_evidence_item", "wrong_version_id"),
)
def test_repository_cannot_return_mismatched_active_evidence_lineage(
    corruption: str,
) -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    job_id = _import_job(factory, ids)
    requirement_id = _shortlist(factory, ids, job_id)
    evidence_id = _save_evidence(
        factory,
        ids,
        content="Python platform v1",
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.VALID,
    )
    first_version = store.get_evidence_version(store.get_evidence(evidence_id).active_version_id)
    _save_evidence(
        factory,
        ids,
        content="Python platform v2",
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.VALID,
        existing_evidence_id=evidence_id,
    )
    active_item = store.get_evidence(evidence_id)
    active_version = store.get_evidence_version(active_item.active_version_id)
    if corruption == "historical_version":
        returned_version = first_version
    elif corruption == "wrong_evidence_item":
        returned_version = replace(
            active_version,
            evidence_id=EvidenceItemId("other-evidence"),
        )
    else:
        returned_version = replace(
            active_version,
            version_id=EvidenceVersionId("other-version"),
        )
    corrupt_uow = _CorruptUnitOfWork(factory(), returned_version)
    retriever = _CountingFullContextRetriever()

    with pytest.raises(
        DependencyUnavailableError,
        match="repository returned invalid active Evidence lineage",
    ):
        RetrieveEvidence(
            unit_of_work_factory=_SingleUnitOfWorkFactory(corrupt_uow),
            retriever=retriever,
            clock=FixedClock(NOW),
            id_generator=ids,
        ).execute(
            RetrieveEvidenceCommand(
                requirement_id=requirement_id,
                allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
                max_tokens=100,
                top_k=5,
                correlation_id=CorrelationId("correlation-retrieve"),
                run_id=RunId("run-retrieve"),
            )
        )

    assert not retriever.called
    assert corrupt_uow.commit_count == 0
    assert store.list_retrieval_runs(requirement_id) == ()


def test_context_builder_persists_exact_redacted_budgeted_lineage() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    job_id = _import_job(factory, ids)
    requirement_id = _shortlist(factory, ids, job_id)
    CreateCandidateProfile(
        unit_of_work_factory=factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        CreateCandidateProfileCommand(
            target_role_keywords=("AI Engineer synthetic@example.test",),
            skill_keywords=("Python",),
            preferred_cities=("Shenzhen",),
            correlation_id=CorrelationId("correlation-profile-redacted"),
            run_id=RunId("run-profile-redacted"),
        )
    )
    _save_evidence(
        factory,
        ids,
        content="Built a Python evaluator; contact synthetic@example.test or +1 555 010 9999",
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.VALID,
    )
    retrieval = RetrieveEvidence(
        unit_of_work_factory=factory,
        retriever=FullContextRetriever(),
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        RetrieveEvidenceCommand(
            requirement_id=requirement_id,
            allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
            max_tokens=100,
            top_k=5,
            correlation_id=CorrelationId("correlation-retrieve"),
            run_id=RunId("run-retrieve"),
        )
    )

    result = BuildContextPackage(
        unit_of_work_factory=factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        BuildContextPackageCommand(
            retrieval_run_id=retrieval.retrieval_run_id,
            task_instruction="Assess only evidence-grounded fit.",
            workflow_identity="deep-fit-analysis",
            max_tokens=200,
            correlation_id=CorrelationId("correlation-context"),
            run_id=RunId("run-context"),
        )
    )

    stored = store.get_context_package(result.context_package_id)
    evidence_entries = tuple(
        entry for entry in stored.entries if entry.kind is ContextEntryKind.EVIDENCE
    )
    assert stored.retrieval_run_id == retrieval.retrieval_run_id
    assert stored.total_estimated_tokens <= stored.max_tokens
    assert all(
        entry.protected
        for entry in stored.entries
        if entry.kind
        in {
            ContextEntryKind.REQUIREMENT,
            ContextEntryKind.INSTRUCTION,
            ContextEntryKind.WORKFLOW,
        }
    )
    assert len(evidence_entries) == 1
    assert evidence_entries[0].redaction is ContextRedaction.APPLIED
    assert "synthetic@example.test" not in evidence_entries[0].content
    assert "555 010 9999" not in evidence_entries[0].content
    assert evidence_entries[0].evidence_chunk_id is not None
    assert all("synthetic@example.test" not in entry.content for entry in stored.entries)
    profile_entry = next(
        entry for entry in stored.entries if entry.kind is ContextEntryKind.PROFILE
    )
    assert profile_entry.redaction is ContextRedaction.APPLIED


def test_context_builder_fails_closed_when_protected_content_exceeds_budget() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    job_id = _import_job(factory, ids)
    requirement_id = _shortlist(factory, ids, job_id)
    _save_evidence(
        factory,
        ids,
        content="Built a Python evaluator",
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.VALID,
    )
    retrieval = RetrieveEvidence(
        unit_of_work_factory=factory,
        retriever=FullContextRetriever(),
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        RetrieveEvidenceCommand(
            requirement_id=requirement_id,
            allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
            max_tokens=100,
            top_k=5,
            correlation_id=CorrelationId("correlation-retrieve"),
            run_id=RunId("run-retrieve"),
        )
    )

    with pytest.raises(ContextBudgetExceededError):
        BuildContextPackage(
            unit_of_work_factory=factory,
            clock=FixedClock(NOW),
            id_generator=ids,
        ).execute(
            BuildContextPackageCommand(
                retrieval_run_id=retrieval.retrieval_run_id,
                task_instruction="Assess only evidence-grounded fit.",
                workflow_identity="deep-fit-analysis",
                max_tokens=3,
                correlation_id=CorrelationId("correlation-context"),
                run_id=RunId("run-context"),
            )
        )

    assert store.list_context_packages(retrieval.retrieval_run_id) == ()


def test_policy_retrieval_records_promotion_and_one_supplemental_query() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    job_id = _import_job(factory, ids)
    requirement_id = _shortlist(factory, ids, job_id)
    _save_evidence(
        factory,
        ids,
        content=" ".join(f"synthetic{index}" for index in range(1_300)),
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.VALID,
    )
    hybrid = _SupplementalHybridRetriever()

    result = RetrieveEvidence(
        unit_of_work_factory=factory,
        full_context_retriever=FullContextRetriever(),
        lexical_retriever=LexicalMetadataRetriever(),
        hybrid_retriever=hybrid,
        promotion_evidence=_promotion_evidence(),
        semantic_ready=True,
        index_version="chroma-evidence-v1",
        embedding_provider_version="semantic-onnx-minilm-v1",
        chunk_policy_version="evidence-chunk-v1",
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        RetrieveEvidenceCommand(
            requirement_id=requirement_id,
            allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
            max_tokens=2_000,
            top_k=5,
            correlation_id=CorrelationId("correlation-retrieve"),
            run_id=RunId("run-retrieve"),
        )
    )

    stored = store.get_retrieval_run(result.retrieval_run_id)
    assert result.strategy is RetrievalStrategy.HYBRID
    assert result.initial_strategy is RetrievalStrategy.HYBRID
    assert result.query_count == 2
    assert stored.policy_version == "retrieval-policy-v1"
    assert stored.promotion_dataset_version == "frozen-holdout-v1"
    assert stored.semantic_ready
    assert stored.supplemental_query_text == hybrid.queries[1]
    assert len(hybrid.queries) == 2

    context = BuildContextPackage(
        unit_of_work_factory=factory,
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        BuildContextPackageCommand(
            retrieval_run_id=result.retrieval_run_id,
            task_instruction="Assess only evidence-grounded fit.",
            workflow_identity="deep-fit-analysis",
            max_tokens=300,
            correlation_id=CorrelationId("correlation-context"),
            run_id=RunId("run-context"),
        )
    )
    package = store.get_context_package(context.context_package_id)
    evidence_entries = tuple(
        entry for entry in package.entries if entry.kind is ContextEntryKind.EVIDENCE
    )
    assert tuple(entry.evidence_chunk_id for entry in evidence_entries) == (
        hybrid.selected_chunk_id,
    )


def test_policy_stops_after_one_supplemental_query_with_insufficient_evidence() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    job_id = _import_job(factory, ids)
    requirement_id = _shortlist(factory, ids, job_id)
    _save_evidence(
        factory,
        ids,
        content=" ".join(f"synthetic{index}" for index in range(1_300)),
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.VALID,
    )
    hybrid = _EmptyHybridRetriever()

    result = RetrieveEvidence(
        unit_of_work_factory=factory,
        full_context_retriever=FullContextRetriever(),
        lexical_retriever=LexicalMetadataRetriever(),
        hybrid_retriever=hybrid,
        promotion_evidence=_promotion_evidence(),
        semantic_ready=True,
        index_version="chroma-evidence-v1",
        embedding_provider_version="semantic-onnx-minilm-v1",
        chunk_policy_version="evidence-chunk-v1",
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        RetrieveEvidenceCommand(
            requirement_id=requirement_id,
            allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
            max_tokens=2_000,
            top_k=5,
            correlation_id=CorrelationId("correlation-retrieve"),
            run_id=RunId("run-retrieve"),
        )
    )

    stored = store.get_retrieval_run(result.retrieval_run_id)
    assert result.status is RetrievalStatus.INSUFFICIENT_EVIDENCE
    assert result.query_count == 2
    assert stored.supplemental_query_text == hybrid.queries[1]
    assert len(hybrid.queries) == 2


def test_unavailable_hybrid_falls_back_without_leaking_adapter_failure() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    job_id = _import_job(factory, ids)
    requirement_id = _shortlist(factory, ids, job_id)
    _save_evidence(
        factory,
        ids,
        content=" ".join(f"synthetic{index}" for index in range(1_300)),
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.VALID,
    )

    result = RetrieveEvidence(
        unit_of_work_factory=factory,
        full_context_retriever=FullContextRetriever(),
        lexical_retriever=LexicalMetadataRetriever(),
        hybrid_retriever=_UnavailableHybridRetriever(),
        promotion_evidence=_promotion_evidence(),
        semantic_ready=True,
        index_version="chroma-evidence-v1",
        embedding_provider_version="semantic-onnx-minilm-v1",
        chunk_policy_version="evidence-chunk-v1",
        clock=FixedClock(NOW),
        id_generator=ids,
    ).execute(
        RetrieveEvidenceCommand(
            requirement_id=requirement_id,
            allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
            max_tokens=2_000,
            top_k=5,
            correlation_id=CorrelationId("correlation-retrieve"),
            run_id=RunId("run-retrieve"),
        )
    )

    assert result.initial_strategy is RetrievalStrategy.HYBRID
    assert result.strategy is RetrievalStrategy.FULL_CONTEXT
    assert result.fallback_reason is RetrievalFallbackReason.SEMANTIC_UNAVAILABLE
    assert result.status is RetrievalStatus.COMPLETED


def test_invalid_hybrid_lineage_cannot_be_reclassified_as_runtime_fallback() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    ids = DeterministicIdGenerator()
    job_id = _import_job(factory, ids)
    requirement_id = _shortlist(factory, ids, job_id)
    _save_evidence(
        factory,
        ids,
        content=" ".join(f"synthetic{index}" for index in range(1_300)),
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.VALID,
    )

    with pytest.raises(
        DependencyUnavailableError,
        match="Hybrid source retriever returned invalid lineage",
    ):
        RetrieveEvidence(
            unit_of_work_factory=factory,
            full_context_retriever=FullContextRetriever(),
            lexical_retriever=LexicalMetadataRetriever(),
            hybrid_retriever=_InvalidHybridLineageRetriever(),
            promotion_evidence=_promotion_evidence(),
            semantic_ready=True,
            index_version="chroma-evidence-v1",
            embedding_provider_version="semantic-onnx-minilm-v1",
            chunk_policy_version="evidence-chunk-v1",
            clock=FixedClock(NOW),
            id_generator=ids,
        ).execute(
            RetrieveEvidenceCommand(
                requirement_id=requirement_id,
                allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
                max_tokens=2_000,
                top_k=5,
                correlation_id=CorrelationId("correlation-retrieve"),
                run_id=RunId("run-retrieve"),
            )
        )

    assert store.list_retrieval_runs(requirement_id) == ()
