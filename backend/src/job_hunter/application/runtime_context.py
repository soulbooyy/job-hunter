"""Prepare and rehydrate governed runtime context from immutable ContextPackage lineage."""

from dataclasses import dataclass
from datetime import datetime

from job_hunter.application.execution import serialized_result_size
from job_hunter.application.ports import (
    ArtifactStore,
    CapabilityExecutionGuard,
    Clock,
    IdGenerator,
    RuntimeContextUnitOfWorkFactory,
)
from job_hunter.domain.ids import (
    ContextPackageId,
    ContextReferenceId,
    CorrelationId,
    RunId,
    RuntimeContextId,
)
from job_hunter.domain.runtime_context import RuntimeContextPolicy
from job_hunter.errors import DependencyUnavailableError, JobHunterError


@dataclass(frozen=True, slots=True)
class PrepareRuntimeContextCommand:
    context_package_id: ContextPackageId
    max_tokens: int
    correlation_id: CorrelationId
    run_id: RunId


@dataclass(frozen=True, slots=True)
class PrepareRuntimeContextResult:
    runtime_context_id: RuntimeContextId
    context_package_id: ContextPackageId
    total_estimated_tokens: int
    max_tokens: int
    artifact_count: int
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId


@dataclass(frozen=True, slots=True)
class RehydrateContextReferenceCommand:
    runtime_context_id: RuntimeContextId
    reference_id: ContextReferenceId


@dataclass(frozen=True, slots=True)
class RehydrateContextReferenceResult:
    runtime_context_id: RuntimeContextId
    context_package_id: ContextPackageId
    reference_id: ContextReferenceId
    source_ordinals: tuple[int, ...]
    content: str


class PrepareRuntimeContext:
    def __init__(
        self,
        *,
        unit_of_work_factory: RuntimeContextUnitOfWorkFactory,
        artifact_store: ArtifactStore,
        clock: Clock,
        id_generator: IdGenerator,
        policy: RuntimeContextPolicy | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._artifact_store = artifact_store
        self._clock = clock
        self._id_generator = id_generator
        self._policy = policy if policy is not None else RuntimeContextPolicy()

    def execute(
        self,
        command: PrepareRuntimeContextCommand,
        *,
        execution_guard: CapabilityExecutionGuard | None = None,
    ) -> PrepareRuntimeContextResult:
        if execution_guard is not None:
            execution_guard.check()
        try:
            unit_of_work = self._unit_of_work_factory()
        except JobHunterError:
            raise
        except Exception:
            raise DependencyUnavailableError("runtime context dependency is unavailable") from None
        try:
            package = unit_of_work.context.get_package(command.context_package_id)
            plan = self._policy.compact(
                package,
                runtime_context_id=self._id_generator.new_runtime_context_id(),
                max_tokens=command.max_tokens,
                created_at=self._clock.now(),
                correlation_id=command.correlation_id,
                run_id=command.run_id,
            )
            # Artifact bytes are immutable derivatives. A failed SQL commit can leave
            # an unreferenced blob, but never a reference to missing committed bytes.
            for artifact in plan.artifacts:
                if execution_guard is not None:
                    execution_guard.check()
                self._artifact_store.write(artifact.record, artifact.content)
                if execution_guard is not None:
                    execution_guard.check()
            snapshot = plan.snapshot
            result = PrepareRuntimeContextResult(
                runtime_context_id=snapshot.runtime_context_id,
                context_package_id=snapshot.context_package_id,
                total_estimated_tokens=snapshot.total_estimated_tokens,
                max_tokens=snapshot.max_tokens,
                artifact_count=len(plan.artifacts),
                created_at=snapshot.created_at,
                correlation_id=snapshot.correlation_id,
                run_id=snapshot.run_id,
            )
            unit_of_work.runtime_context.add_plan(plan)
            if execution_guard is not None:
                execution_guard.check_before_commit(
                    result_bytes=serialized_result_size(
                        (
                            str(result.runtime_context_id),
                            str(result.context_package_id),
                            result.total_estimated_tokens,
                            result.max_tokens,
                            result.artifact_count,
                            result.created_at.isoformat(),
                            str(result.correlation_id),
                            str(result.run_id),
                        )
                    )
                )
            unit_of_work.commit()
        except JobHunterError:
            unit_of_work.rollback()
            raise
        except Exception:
            unit_of_work.rollback()
            raise DependencyUnavailableError("runtime context dependency is unavailable") from None
        finally:
            unit_of_work.close()
        return result


class RehydrateContextReference:
    def __init__(
        self,
        *,
        unit_of_work_factory: RuntimeContextUnitOfWorkFactory,
        artifact_store: ArtifactStore,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._artifact_store = artifact_store

    def execute(self, command: RehydrateContextReferenceCommand) -> RehydrateContextReferenceResult:
        try:
            unit_of_work = self._unit_of_work_factory()
        except JobHunterError:
            raise
        except Exception:
            raise DependencyUnavailableError("runtime context dependency is unavailable") from None
        try:
            snapshot = unit_of_work.runtime_context.get_snapshot(command.runtime_context_id)
            matching_entries = tuple(
                entry for entry in snapshot.entries if entry.reference_id == command.reference_id
            )
            if len(matching_entries) != 1:
                raise DependencyUnavailableError("runtime context reference is invalid")
            reference = unit_of_work.runtime_context.get_reference(command.reference_id)
            if reference.context_package_id != snapshot.context_package_id:
                raise DependencyUnavailableError("runtime context reference is invalid")
            entry = matching_entries[0]
            if (
                reference.source_ordinals != entry.source_ordinals
                or reference.content_hash != entry.content_hash
            ):
                raise DependencyUnavailableError("runtime context reference is invalid")
            record = unit_of_work.runtime_context.get_artifact(reference.artifact_id)
            if record.content_hash != reference.content_hash:
                raise DependencyUnavailableError("runtime context reference is invalid")
            content = self._artifact_store.read(record)
        except JobHunterError:
            unit_of_work.rollback()
            raise
        except Exception:
            unit_of_work.rollback()
            raise DependencyUnavailableError("runtime context dependency is unavailable") from None
        finally:
            unit_of_work.close()
        return RehydrateContextReferenceResult(
            runtime_context_id=snapshot.runtime_context_id,
            context_package_id=snapshot.context_package_id,
            reference_id=reference.reference_id,
            source_ordinals=reference.source_ordinals,
            content=content,
        )
