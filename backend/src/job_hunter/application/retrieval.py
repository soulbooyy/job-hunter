"""Retrieve eligible Candidate Evidence with authoritative Requirement lineage."""

from dataclasses import dataclass
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
    RetrievalHit,
    RetrievalMatchReason,
    RetrievalQuery,
    RetrievalRun,
    RetrievalStatus,
    RetrievalStrategy,
    RetrievalTaskType,
    RetrieverResult,
)
from job_hunter.errors import ConflictError, DependencyUnavailableError, JobHunterError


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
        retriever: EvidenceRetriever,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._retriever = retriever
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
            retriever_result = self._retriever.retrieve(query, eligibility.eligible)
            if retriever_result.eligible_count != len(eligibility.eligible):
                raise DependencyUnavailableError(
                    "evidence retriever returned invalid input accounting"
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
            if self._retriever.strategy is RetrievalStrategy.FULL_CONTEXT:
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
            created_at = self._clock.now()
            retrieval_run = RetrievalRun(
                retrieval_run_id=self._id_generator.new_retrieval_run_id(),
                requirement_id=requirement.requirement_id,
                job_version_id=version.version_id,
                strategy=self._retriever.strategy,
                retriever_version=self._retriever.version,
                eligibility_policy_version=self._eligibility.version,
                token_estimator_version=self._retriever.token_estimator_version,
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
        )
