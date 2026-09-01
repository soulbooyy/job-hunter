"""Build and persist the exact redacted context for a later model boundary."""

from dataclasses import dataclass
from datetime import datetime

from job_hunter.application.ports import Clock, IdGenerator, UnitOfWorkFactory
from job_hunter.domain.context import (
    CONTEXT_BUILDER_VERSION,
    CONTEXT_PACKAGING_OVERHEAD_TOKENS,
    CONTEXT_REDACTION_POLICY_VERSION,
    ContextPackage,
    assemble_context,
)
from job_hunter.domain.ids import (
    ContextPackageId,
    CorrelationId,
    RetrievalRunId,
    RunId,
)
from job_hunter.domain.jobs import JobLifecycleStatus
from job_hunter.domain.knowledge import EvidenceItemVersion
from job_hunter.domain.retrieval import (
    TOKEN_ESTIMATOR_VERSION,
    RetrievalStatus,
)
from job_hunter.errors import (
    ConflictError,
    DependencyUnavailableError,
    InputValidationError,
    JobHunterError,
)


@dataclass(frozen=True, slots=True)
class BuildContextPackageCommand:
    retrieval_run_id: RetrievalRunId
    task_instruction: str
    workflow_identity: str
    max_tokens: int
    correlation_id: CorrelationId
    run_id: RunId


@dataclass(frozen=True, slots=True)
class BuildContextPackageResult:
    context_package_id: ContextPackageId
    retrieval_run_id: RetrievalRunId
    total_estimated_tokens: int
    max_tokens: int
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId


class BuildContextPackage:
    builder_version = CONTEXT_BUILDER_VERSION
    redaction_policy_version = CONTEXT_REDACTION_POLICY_VERSION
    packaging_overhead_tokens = CONTEXT_PACKAGING_OVERHEAD_TOKENS

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._id_generator = id_generator

    def execute(self, command: BuildContextPackageCommand) -> BuildContextPackageResult:
        try:
            unit_of_work = self._unit_of_work_factory()
        except JobHunterError:
            raise
        except Exception:
            raise DependencyUnavailableError("context dependency is unavailable") from None
        try:
            retrieval_run = unit_of_work.retrieval.get_run(command.retrieval_run_id)
            requirement = unit_of_work.screening.get_requirement(retrieval_run.requirement_id)
            if requirement.job_version_id != retrieval_run.job_version_id:
                raise DependencyUnavailableError(
                    "repository returned invalid Context Requirement lineage"
                )
            version = unit_of_work.jobs.get_version(retrieval_run.job_version_id)
            job = unit_of_work.jobs.get_job(version.job_id)
            if (
                job.active_version_id != version.version_id
                or job.lifecycle_status is not JobLifecycleStatus.SHORTLISTED
            ):
                raise ConflictError("context requires a shortlisted current JobVersion")
            if retrieval_run.status is RetrievalStatus.NOT_EXECUTABLE:
                raise ConflictError("not-executable retrieval cannot build context")
            profile = unit_of_work.knowledge.get_active_profile()
            evidence_versions: list[EvidenceItemVersion] = []
            for hit in retrieval_run.hits:
                evidence = unit_of_work.knowledge.get_evidence_version(hit.evidence_version_id)
                if evidence.evidence_id != hit.evidence_id:
                    raise DependencyUnavailableError(
                        "repository returned invalid Context Evidence lineage"
                    )
                evidence_versions.append(evidence)
            try:
                assembly = assemble_context(
                    requirement_id=requirement.requirement_id,
                    requirement_text=requirement.text,
                    profile=profile,
                    task_instruction=command.task_instruction,
                    workflow_identity=command.workflow_identity,
                    hits=retrieval_run.hits,
                    evidence=tuple(evidence_versions),
                    max_tokens=command.max_tokens,
                    packaging_overhead_tokens=self.packaging_overhead_tokens,
                )
            except InputValidationError:
                # Retrieval/source lineage is adapter-owned input here; it must
                # not be reclassified as a caller validation failure.
                raise DependencyUnavailableError(
                    "retrieval returned invalid Context lineage"
                ) from None
            package = ContextPackage(
                context_package_id=self._id_generator.new_context_package_id(),
                job_version_id=version.version_id,
                requirement_ids=(requirement.requirement_id,),
                retrieval_run_id=retrieval_run.retrieval_run_id,
                candidate_profile_id=profile.profile_id,
                entries=assembly.entries,
                builder_version=self.builder_version,
                redaction_policy_version=self.redaction_policy_version,
                token_estimator_version=TOKEN_ESTIMATOR_VERSION,
                packaging_overhead_tokens=assembly.packaging_overhead_tokens,
                total_estimated_tokens=assembly.total_estimated_tokens,
                max_tokens=command.max_tokens,
                created_at=self._clock.now(),
                correlation_id=command.correlation_id,
                run_id=command.run_id,
                exclusions=assembly.exclusions,
            )
            unit_of_work.context.add_package(package)
            unit_of_work.commit()
        except JobHunterError:
            unit_of_work.rollback()
            raise
        except Exception:
            unit_of_work.rollback()
            raise DependencyUnavailableError("context dependency is unavailable") from None
        finally:
            unit_of_work.close()
        return BuildContextPackageResult(
            context_package_id=package.context_package_id,
            retrieval_run_id=package.retrieval_run_id,
            total_estimated_tokens=package.total_estimated_tokens,
            max_tokens=package.max_tokens,
            created_at=package.created_at,
            correlation_id=package.correlation_id,
            run_id=package.run_id,
        )
