"""Retrieve eligible Candidate Evidence with authoritative Requirement lineage."""

from dataclasses import dataclass, replace
from datetime import datetime

from job_hunter.application.ports import (
    Clock,
    EvidenceRetriever,
    IdGenerator,
    UnitOfWorkFactory,
)
from job_hunter.domain.ids import (
    CorrelationId,
    EvidenceItemId,
    EvidenceVersionId,
    JobVersionId,
    RequirementId,
    RetrievalRunId,
    RunId,
)
from job_hunter.domain.jobs import JobLifecycleStatus
from job_hunter.domain.knowledge import EvidenceItemVersion, EvidenceSensitivity
from job_hunter.domain.retrieval import (
    EvidenceEligibilityPolicy,
    EvidenceExclusion,
    RetrievalFallbackReason,
    RetrievalHit,
    RetrievalMatchReason,
    RetrievalPolicy,
    RetrievalPolicyDecision,
    RetrievalPolicyInput,
    RetrievalPolicyReason,
    RetrievalPromotionEvidence,
    RetrievalQuery,
    RetrievalRun,
    RetrievalStatus,
    RetrievalStrategy,
    RetrievalTaskType,
    RetrieverResult,
    estimate_tokens,
)
from job_hunter.errors import (
    ConflictError,
    DependencyUnavailableError,
    JobHunterError,
    SemanticUnavailableError,
)


@dataclass(frozen=True, slots=True)
class RetrieveEvidenceCommand:
    requirement_id: RequirementId
    allowed_sensitivities: tuple[EvidenceSensitivity, ...]
    max_tokens: int
    top_k: int
    correlation_id: CorrelationId
    run_id: RunId


@dataclass(frozen=True, slots=True)
class RetrieveEvidenceResult:
    retrieval_run_id: RetrievalRunId
    requirement_id: RequirementId
    job_version_id: JobVersionId
    strategy: RetrievalStrategy
    retriever_version: str
    status: RetrievalStatus
    hits: tuple[RetrievalHit, ...]
    exclusions: tuple[EvidenceExclusion, ...]
    eligible_count: int
    eligible_estimated_tokens: int
    selected_estimated_tokens: int
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId
    policy_version: str | None
    initial_strategy: RetrievalStrategy | None
    decision_reason: RetrievalPolicyReason | None
    fallback_reason: RetrievalFallbackReason | None
    promotion_dataset_version: str | None
    semantic_ready: bool
    query_count: int


def _validate_full_context_result(
    result: RetrieverResult,
    *,
    eligible_versions: set[tuple[EvidenceItemId, EvidenceVersionId]],
    max_tokens: int,
) -> None:
    hit_versions = {(hit.evidence_id, hit.evidence_version_id) for hit in result.hits}
    if not eligible_versions:
        valid = (
            result.status is RetrievalStatus.NO_RELEVANT_EVIDENCE
            and not result.hits
            and result.eligible_estimated_tokens == 0
            and result.selected_estimated_tokens == 0
        )
    elif result.eligible_estimated_tokens > max_tokens:
        valid = (
            result.status is RetrievalStatus.NOT_EXECUTABLE
            and not result.hits
            and result.selected_estimated_tokens == 0
        )
    else:
        valid = (
            result.status is RetrievalStatus.COMPLETED
            and hit_versions == eligible_versions
            and all(hit.reasons == (RetrievalMatchReason.FULL_CONTEXT,) for hit in result.hits)
            and result.selected_estimated_tokens == result.eligible_estimated_tokens
            and result.selected_estimated_tokens <= max_tokens
        )
    if not valid:
        raise DependencyUnavailableError("evidence retriever violated full-context contract")


class RetrieveEvidence:
    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        retriever: EvidenceRetriever | None = None,
        full_context_retriever: EvidenceRetriever | None = None,
        lexical_retriever: EvidenceRetriever | None = None,
        hybrid_retriever: EvidenceRetriever | None = None,
        policy: RetrievalPolicy | None = None,
        promotion_evidence: RetrievalPromotionEvidence | None = None,
        semantic_ready: bool = False,
        index_version: str | None = None,
        embedding_provider_version: str | None = None,
        chunk_policy_version: str | None = None,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        policy_retrievers = (
            full_context_retriever,
            lexical_retriever,
            hybrid_retriever,
        )
        if retriever is None and any(item is None for item in policy_retrievers):
            raise ValueError("policy retrieval requires Full, Lexical, and Hybrid retrievers")
        if retriever is not None and any(item is not None for item in policy_retrievers):
            raise ValueError("explicit and policy retrieval modes cannot be combined")
        if (
            promotion_evidence is not None
            and promotion_evidence.promoted
            and any(
                value is None
                for value in (
                    index_version,
                    embedding_provider_version,
                    chunk_policy_version,
                )
            )
        ):
            raise ValueError("promoted Hybrid requires complete semantic version lineage")
        self._unit_of_work_factory = unit_of_work_factory
        self._retriever = retriever
        self._full_context_retriever = full_context_retriever
        self._lexical_retriever = lexical_retriever
        self._hybrid_retriever = hybrid_retriever
        self._policy = policy or RetrievalPolicy()
        self._promotion_evidence = promotion_evidence
        self._hybrid_promoted = (
            promotion_evidence.promoted if promotion_evidence is not None else False
        )
        self._semantic_ready = semantic_ready
        self._promotion_dataset_version = (
            promotion_evidence.dataset_version if promotion_evidence is not None else None
        )
        self._index_version = index_version
        self._embedding_provider_version = embedding_provider_version
        self._chunk_policy_version = chunk_policy_version
        self._clock = clock
        self._id_generator = id_generator
        self._eligibility = EvidenceEligibilityPolicy()

    def execute(self, command: RetrieveEvidenceCommand) -> RetrieveEvidenceResult:
        try:
            unit_of_work = self._unit_of_work_factory()
        except JobHunterError:
            raise
        except Exception:
            raise DependencyUnavailableError(
                "evidence retrieval dependency is unavailable"
            ) from None
        try:
            requirement = unit_of_work.screening.get_requirement(command.requirement_id)
            version = unit_of_work.jobs.get_version(requirement.job_version_id)
            job = unit_of_work.jobs.get_job(version.job_id)
            if job.active_version_id != version.version_id:
                raise ConflictError("retrieval requirement must belong to the current JobVersion")
            if job.lifecycle_status is not JobLifecycleStatus.SHORTLISTED:
                raise ConflictError("job must be shortlisted before evidence retrieval")
            active_evidence: list[EvidenceItemVersion] = []
            for item in unit_of_work.knowledge.list_evidence():
                active_version = unit_of_work.knowledge.get_evidence_version(item.active_version_id)
                if (
                    active_version.version_id != item.active_version_id
                    or active_version.evidence_id != item.evidence_id
                ):
                    # Repository lookup is an adapter boundary. Both identity axes
                    # must agree before this value can enter eligibility or lineage.
                    raise DependencyUnavailableError(
                        "repository returned invalid active Evidence lineage"
                    )
                active_evidence.append(active_version)
            eligibility = self._eligibility.evaluate(
                tuple(active_evidence),
                allowed_sensitivities=command.allowed_sensitivities,
            )
            query = RetrievalQuery(
                requirement_id=requirement.requirement_id,
                text=requirement.text,
                task_type=RetrievalTaskType.DEEP_FIT,
                max_tokens=command.max_tokens,
                top_k=command.top_k,
            )
            policy_decision: RetrievalPolicyDecision | None = None
            selected_retriever = self._retriever
            if selected_retriever is None:
                eligible_tokens = sum(
                    estimate_tokens(item.canonical_content) for item in eligibility.eligible
                )
                policy_decision = self._policy.decide(
                    RetrievalPolicyInput(
                        requirement_id=requirement.requirement_id,
                        query_text=requirement.text,
                        eligible_count=len(eligibility.eligible),
                        eligible_estimated_tokens=eligible_tokens,
                        max_tokens=command.max_tokens,
                        hybrid_promoted=self._hybrid_promoted,
                        semantic_ready=self._semantic_ready,
                        promotion_dataset_version=self._promotion_dataset_version,
                    )
                )
                selected_retriever = self._retriever_for(policy_decision.selected_strategy)
            try:
                retriever_result = selected_retriever.retrieve(query, eligibility.eligible)
            except SemanticUnavailableError:
                if policy_decision is None:
                    raise
                fallback = (
                    RetrievalStrategy.FULL_CONTEXT
                    if sum(estimate_tokens(item.canonical_content) for item in eligibility.eligible)
                    <= command.max_tokens
                    else RetrievalStrategy.LEXICAL_METADATA
                )
                policy_decision = replace(
                    policy_decision,
                    selected_strategy=fallback,
                    fallback_reason=RetrievalFallbackReason.SEMANTIC_UNAVAILABLE,
                )
                selected_retriever = self._retriever_for(fallback)
                retriever_result = selected_retriever.retrieve(query, eligibility.eligible)
            query_count = 1
            supplemental_query_text: str | None = None
            if (
                policy_decision is not None
                and policy_decision.initial_strategy is RetrievalStrategy.HYBRID
                and policy_decision.selected_strategy is RetrievalStrategy.HYBRID
                and retriever_result.status is RetrievalStatus.NO_RELEVANT_EVIDENCE
            ):
                supplemental_query_text = " ".join(
                    (
                        requirement.text,
                        requirement.requirement_type.value,
                        requirement.priority.value,
                    )
                )
                supplemental_query = replace(query, text=supplemental_query_text)
                retriever_result = selected_retriever.retrieve(
                    supplemental_query, eligibility.eligible
                )
                query_count = 2
                if retriever_result.status is RetrievalStatus.NO_RELEVANT_EVIDENCE:
                    retriever_result = replace(
                        retriever_result,
                        status=RetrievalStatus.INSUFFICIENT_EVIDENCE,
                    )
            if retriever_result.eligible_count != len(eligibility.eligible):
                raise DependencyUnavailableError(
                    "evidence retriever returned invalid input accounting"
                )
            authoritative_eligible_tokens = sum(
                estimate_tokens(item.canonical_content) for item in eligibility.eligible
            )
            eligible_versions = {
                (item.evidence_id, item.version_id) for item in eligibility.eligible
            }
            if any(
                (hit.evidence_id, hit.evidence_version_id) not in eligible_versions
                for hit in retriever_result.hits
            ):
                # A retriever is an adapter and cannot establish new factual lineage.
                # Reject any returned ID that did not cross the eligibility boundary.
                raise DependencyUnavailableError("evidence retriever returned invalid lineage")
            evidence_by_identity = {
                (item.evidence_id, item.version_id): item for item in eligibility.eligible
            }
            authoritative_selected_tokens = sum(
                estimate_tokens(
                    evidence_by_identity[
                        (hit.evidence_id, hit.evidence_version_id)
                    ].canonical_content
                )
                for hit in retriever_result.hits
            )
            if selected_retriever.strategy is RetrievalStrategy.FULL_CONTEXT:
                _validate_full_context_result(
                    retriever_result,
                    eligible_versions=eligible_versions,
                    max_tokens=query.max_tokens,
                )
            elif (
                retriever_result.status is RetrievalStatus.COMPLETED
                and retriever_result.selected_estimated_tokens > query.max_tokens
            ):
                raise DependencyUnavailableError(
                    "evidence retriever returned invalid budget accounting"
                )
            if (
                retriever_result.eligible_estimated_tokens != authoritative_eligible_tokens
                or retriever_result.selected_estimated_tokens != authoritative_selected_tokens
            ):
                raise DependencyUnavailableError(
                    "evidence retriever returned invalid token accounting"
                )
            created_at = self._clock.now()
            retrieval_run = RetrievalRun(
                retrieval_run_id=self._id_generator.new_retrieval_run_id(),
                requirement_id=requirement.requirement_id,
                job_version_id=version.version_id,
                strategy=selected_retriever.strategy,
                retriever_version=selected_retriever.version,
                eligibility_policy_version=self._eligibility.version,
                token_estimator_version=selected_retriever.token_estimator_version,
                status=retriever_result.status,
                hits=retriever_result.hits,
                exclusions=eligibility.exclusions,
                eligible_count=len(eligibility.eligible),
                eligible_estimated_tokens=retriever_result.eligible_estimated_tokens,
                selected_estimated_tokens=retriever_result.selected_estimated_tokens,
                max_tokens=query.max_tokens,
                top_k=query.top_k,
                created_at=created_at,
                correlation_id=command.correlation_id,
                run_id=command.run_id,
                policy_version=(
                    policy_decision.policy_version if policy_decision is not None else None
                ),
                initial_strategy=(
                    policy_decision.initial_strategy if policy_decision is not None else None
                ),
                decision_reason=(policy_decision.reason if policy_decision is not None else None),
                fallback_reason=(
                    policy_decision.fallback_reason if policy_decision is not None else None
                ),
                promotion_dataset_version=(
                    policy_decision.promotion_dataset_version
                    if policy_decision is not None
                    else None
                ),
                semantic_ready=self._semantic_ready,
                index_version=self._index_version,
                embedding_provider_version=self._embedding_provider_version,
                chunk_policy_version=self._chunk_policy_version,
                query_count=query_count,
                supplemental_query_text=supplemental_query_text,
            )
            unit_of_work.retrieval.add_run(retrieval_run)
            unit_of_work.commit()
        except JobHunterError:
            unit_of_work.rollback()
            raise
        except Exception:
            unit_of_work.rollback()
            raise DependencyUnavailableError(
                "evidence retrieval dependency is unavailable"
            ) from None
        finally:
            unit_of_work.close()
        return RetrieveEvidenceResult(
            retrieval_run_id=retrieval_run.retrieval_run_id,
            requirement_id=retrieval_run.requirement_id,
            job_version_id=retrieval_run.job_version_id,
            strategy=retrieval_run.strategy,
            retriever_version=retrieval_run.retriever_version,
            status=retrieval_run.status,
            hits=retrieval_run.hits,
            exclusions=retrieval_run.exclusions,
            eligible_count=retrieval_run.eligible_count,
            eligible_estimated_tokens=retrieval_run.eligible_estimated_tokens,
            selected_estimated_tokens=retrieval_run.selected_estimated_tokens,
            created_at=retrieval_run.created_at,
            correlation_id=retrieval_run.correlation_id,
            run_id=retrieval_run.run_id,
            policy_version=retrieval_run.policy_version,
            initial_strategy=retrieval_run.initial_strategy,
            decision_reason=retrieval_run.decision_reason,
            fallback_reason=retrieval_run.fallback_reason,
            promotion_dataset_version=retrieval_run.promotion_dataset_version,
            semantic_ready=retrieval_run.semantic_ready,
            query_count=retrieval_run.query_count,
        )

    def _retriever_for(self, strategy: RetrievalStrategy) -> EvidenceRetriever:
        retriever = {
            RetrievalStrategy.FULL_CONTEXT: self._full_context_retriever,
            RetrievalStrategy.LEXICAL_METADATA: self._lexical_retriever,
            RetrievalStrategy.HYBRID: self._hybrid_retriever,
        }.get(strategy)
        if retriever is None or retriever.strategy is not strategy:
            raise DependencyUnavailableError("configured evidence retriever is unavailable")
        return retriever
