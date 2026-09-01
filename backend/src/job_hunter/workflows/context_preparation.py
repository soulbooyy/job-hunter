"""Concrete governed LangGraph prefix for preparing model-ready context."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import NotRequired, Protocol, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from job_hunter.application.context import (
    BuildContextPackageCommand,
    BuildContextPackageResult,
)
from job_hunter.application.ports import CapabilityExecutionGuard
from job_hunter.application.retrieval import RetrieveEvidenceCommand, RetrieveEvidenceResult
from job_hunter.application.runtime_context import (
    PrepareRuntimeContextCommand,
    PrepareRuntimeContextResult,
)
from job_hunter.domain.capabilities import (
    CapabilityBudget,
    CapabilityCallRecord,
    CapabilityId,
    CapabilityInvocation,
    CapabilityLedger,
    CapabilityToken,
    CapabilityUsage,
    NodeToolPolicy,
    ResourceScope,
    SideEffectClass,
)
from job_hunter.domain.ids import (
    ContextPackageId,
    JobVersionId,
    RequirementId,
    RetrievalRunId,
    RuntimeContextId,
    WorkflowRunId,
)
from job_hunter.domain.retrieval import RetrievalStatus, estimate_tokens
from job_hunter.errors import BudgetExceededError, DependencyUnavailableError, JobHunterError

CONTEXT_PREPARATION_POLICY_VERSION = "context-preparation-capabilities-v1"


class ContextPreparationStatus(StrEnum):
    RETRIEVAL_COMPLETED = "retrieval_completed"
    CONTEXT_BUILT = "context_built"
    CONTEXT_READY = "context_ready"
    NO_RELEVANT_EVIDENCE = "no_relevant_evidence"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_EXECUTABLE = "not_executable"
    BUDGET_EXCEEDED = "budget_exceeded"
    POLICY_DENIED = "policy_denied"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ContextPreparationRequest:
    workflow_run_id: WorkflowRunId
    retrieve: RetrieveEvidenceCommand
    task_instruction: str
    workflow_identity: str
    context_max_tokens: int
    runtime_max_tokens: int


@dataclass(frozen=True, slots=True)
class ContextPreparationResult:
    workflow_run_id: WorkflowRunId
    status: ContextPreparationStatus
    requirement_id: RequirementId
    retrieval_run_id: RetrievalRunId | None
    context_package_id: ContextPackageId | None
    runtime_context_id: RuntimeContextId | None
    capability_calls: int
    attempted_calls: int
    completed_calls: int
    committed_calls: int
    capability_usage: tuple[CapabilityCallRecord, ...]
    error_code: str | None


class MonotonicClock(Protocol):
    def now_ms(self) -> int: ...


class SystemMonotonicClock:
    def now_ms(self) -> int:
        return time.monotonic_ns() // 1_000_000


class RetrieveAction(Protocol):
    def execute(
        self,
        command: RetrieveEvidenceCommand,
        *,
        execution_guard: CapabilityExecutionGuard | None = None,
    ) -> RetrieveEvidenceResult: ...


class BuildContextAction(Protocol):
    def execute(
        self,
        command: BuildContextPackageCommand,
        *,
        execution_guard: CapabilityExecutionGuard | None = None,
    ) -> BuildContextPackageResult: ...


class PrepareRuntimeAction(Protocol):
    def execute(
        self,
        command: PrepareRuntimeContextCommand,
        *,
        execution_guard: CapabilityExecutionGuard | None = None,
    ) -> PrepareRuntimeContextResult: ...


class ContextPreparationGraphState(TypedDict):
    request: ContextPreparationRequest
    requirement_id: RequirementId
    status: NotRequired[ContextPreparationStatus]
    job_version_id: NotRequired[JobVersionId]
    retrieval_run_id: NotRequired[RetrievalRunId]
    context_package_id: NotRequired[ContextPackageId]
    runtime_context_id: NotRequired[RuntimeContextId]
    error_code: NotRequired[str]


class _StateUpdate(TypedDict, total=False):
    status: ContextPreparationStatus
    job_version_id: JobVersionId
    retrieval_run_id: RetrievalRunId
    context_package_id: ContextPackageId
    runtime_context_id: RuntimeContextId
    error_code: str


class ContextPreparationGraph(Protocol):
    def invoke(self, input: ContextPreparationGraphState) -> ContextPreparationGraphState: ...


class ContextPreparationGraphCompiler(Protocol):
    def __call__(self, ledger: CapabilityLedger) -> ContextPreparationGraph: ...


class _CooperativeCapabilityGuard:
    def __init__(
        self,
        *,
        ledger: CapabilityLedger,
        token: CapabilityToken,
        clock: MonotonicClock,
        started_ms: int,
    ) -> None:
        self._ledger = ledger
        self._token = token
        self._clock = clock
        self._started_ms = started_ms
        self._result_bytes = 0

    def check(self) -> None:
        self._ledger.enforce(self._token, self.usage())

    def check_before_commit(self, *, result_bytes: int) -> None:
        self._result_bytes = result_bytes
        self.check()

    def usage(self) -> CapabilityUsage:
        return CapabilityUsage(
            elapsed_ms=max(0, self._clock.now_ms() - self._started_ms),
            output_tokens=0,
            result_bytes=self._result_bytes,
            cost_microusd=0,
        )


@dataclass(frozen=True, slots=True)
class _InvocationOutcome[T]:
    result: T
    committed_budget_error: BudgetExceededError | None = None


def _budget() -> CapabilityBudget:
    return CapabilityBudget(
        max_calls=1,
        max_iterations=1,
        timeout_ms=30_000,
        max_input_tokens=512,
        max_output_tokens=1,
        max_result_bytes=4_096,
        max_cost_microusd=0,
    )


def context_preparation_policy(
    node_name: str,
    capability: CapabilityId,
    scope: ResourceScope,
) -> NodeToolPolicy:
    """Return a closed policy; no node or prompt can add capabilities."""
    expected = {
        "retrieve_evidence": CapabilityId.RETRIEVE_EVIDENCE,
        "build_context_package": CapabilityId.BUILD_CONTEXT_PACKAGE,
        "prepare_runtime_context": CapabilityId.PREPARE_RUNTIME_CONTEXT,
    }
    if expected.get(node_name) is not capability:
        raise ValueError("context preparation node capability is invalid")
    return NodeToolPolicy(
        version=CONTEXT_PREPARATION_POLICY_VERSION,
        node_name=node_name,
        allowed_capabilities=(capability,),
        resource_scope=scope,
        side_effect_ceiling=SideEffectClass.LOCAL_PERSISTENT_WRITE,
        budget=_budget(),
    )


class ContextPreparationWorkflow:
    def __init__(
        self,
        *,
        retrieve_evidence: RetrieveAction,
        build_context_package: BuildContextAction,
        prepare_runtime_context: PrepareRuntimeAction,
        monotonic_clock: MonotonicClock | None = None,
        graph_compiler: ContextPreparationGraphCompiler | None = None,
    ) -> None:
        self._retrieve = retrieve_evidence
        self._build = build_context_package
        self._prepare = prepare_runtime_context
        self._clock = monotonic_clock if monotonic_clock is not None else SystemMonotonicClock()
        self._graph_compiler = graph_compiler

    def run(self, request: ContextPreparationRequest) -> ContextPreparationResult:
        ledger = CapabilityLedger(request.workflow_run_id)
        try:
            graph = (
                self._graph_compiler(ledger)
                if self._graph_compiler is not None
                else self._compile(ledger)
            )
            final = graph.invoke(
                {
                    "request": request,
                    "requirement_id": request.retrieve.requirement_id,
                }
            )
        except JobHunterError as error:
            return self._terminal_result(request, ledger, error)
        except Exception:
            return self._terminal_result(
                request,
                ledger,
                DependencyUnavailableError("workflow dependency is unavailable"),
            )
        status = final.get("status", ContextPreparationStatus.FAILED)
        return ContextPreparationResult(
            workflow_run_id=request.workflow_run_id,
            status=status,
            requirement_id=request.retrieve.requirement_id,
            retrieval_run_id=final.get("retrieval_run_id"),
            context_package_id=final.get("context_package_id"),
            runtime_context_id=final.get("runtime_context_id"),
            capability_calls=ledger.completed_calls,
            attempted_calls=ledger.attempted_calls,
            completed_calls=ledger.completed_calls,
            committed_calls=ledger.committed_calls,
            capability_usage=ledger.records,
            error_code=final.get("error_code"),
        )

    def _compile(self, ledger: CapabilityLedger) -> ContextPreparationGraph:
        builder = StateGraph(ContextPreparationGraphState)
        builder.add_node("retrieve_evidence", lambda state: self._retrieve_node(state, ledger))
        builder.add_node("build_context_package", lambda state: self._build_node(state, ledger))
        builder.add_node("prepare_runtime_context", lambda state: self._prepare_node(state, ledger))
        builder.add_edge(START, "retrieve_evidence")
        builder.add_conditional_edges(
            "retrieve_evidence",
            lambda state: (
                "build_context_package"
                if state.get("status") is ContextPreparationStatus.RETRIEVAL_COMPLETED
                else END
            ),
            ["build_context_package", END],
        )
        builder.add_conditional_edges(
            "build_context_package",
            lambda state: (
                "prepare_runtime_context"
                if state.get("status") is ContextPreparationStatus.CONTEXT_BUILT
                else END
            ),
            ["prepare_runtime_context", END],
        )
        builder.add_edge("prepare_runtime_context", END)
        return cast(ContextPreparationGraph, builder.compile())

    def _retrieve_node(
        self, state: ContextPreparationGraphState, ledger: CapabilityLedger
    ) -> _StateUpdate:
        request = state["request"]
        scope = ResourceScope(requirement_id=request.retrieve.requirement_id)
        try:
            outcome = self._invoke(
                ledger=ledger,
                policy=context_preparation_policy(
                    "retrieve_evidence", CapabilityId.RETRIEVE_EVIDENCE, scope
                ),
                invocation=CapabilityInvocation(
                    capability=CapabilityId.RETRIEVE_EVIDENCE,
                    resource_scope=scope,
                    side_effect_class=SideEffectClass.LOCAL_PERSISTENT_WRITE,
                    iteration=1,
                    input_tokens=estimate_tokens(str(request.retrieve.requirement_id)),
                ),
                action=lambda guard: self._retrieve.execute(
                    request.retrieve, execution_guard=guard
                ),
            )
        except JobHunterError as error:
            return self._failure(state, error)
        result = outcome.result
        if outcome.committed_budget_error is not None:
            return {
                "status": ContextPreparationStatus.BUDGET_EXCEEDED,
                "job_version_id": result.job_version_id,
                "retrieval_run_id": result.retrieval_run_id,
                "error_code": outcome.committed_budget_error.code,
            }
        status = {
            RetrievalStatus.COMPLETED: ContextPreparationStatus.RETRIEVAL_COMPLETED,
            RetrievalStatus.NO_RELEVANT_EVIDENCE: ContextPreparationStatus.NO_RELEVANT_EVIDENCE,
            RetrievalStatus.INSUFFICIENT_EVIDENCE: ContextPreparationStatus.INSUFFICIENT_EVIDENCE,
            RetrievalStatus.NOT_EXECUTABLE: ContextPreparationStatus.NOT_EXECUTABLE,
        }[result.status]
        return {
            "status": status,
            "job_version_id": result.job_version_id,
            "retrieval_run_id": result.retrieval_run_id,
        }

    def _build_node(
        self, state: ContextPreparationGraphState, ledger: CapabilityLedger
    ) -> _StateUpdate:
        request = state["request"]
        retrieval_run_id = state.get("retrieval_run_id")
        job_version_id = state.get("job_version_id")
        if retrieval_run_id is None or job_version_id is None:
            return self._failure(state, DependencyUnavailableError("workflow state is invalid"))
        scope = ResourceScope(
            job_version_id=job_version_id,
            requirement_id=request.retrieve.requirement_id,
            retrieval_run_id=retrieval_run_id,
        )
        command = BuildContextPackageCommand(
            retrieval_run_id=retrieval_run_id,
            task_instruction=request.task_instruction,
            workflow_identity=request.workflow_identity,
            max_tokens=request.context_max_tokens,
            correlation_id=request.retrieve.correlation_id,
            run_id=request.retrieve.run_id,
        )
        try:
            outcome = self._invoke(
                ledger=ledger,
                policy=context_preparation_policy(
                    "build_context_package", CapabilityId.BUILD_CONTEXT_PACKAGE, scope
                ),
                invocation=CapabilityInvocation(
                    capability=CapabilityId.BUILD_CONTEXT_PACKAGE,
                    resource_scope=scope,
                    side_effect_class=SideEffectClass.LOCAL_PERSISTENT_WRITE,
                    iteration=1,
                    input_tokens=estimate_tokens(
                        " ".join((request.task_instruction, request.workflow_identity))
                    ),
                ),
                action=lambda guard: self._build.execute(command, execution_guard=guard),
            )
        except JobHunterError as error:
            return self._failure(state, error)
        result = outcome.result
        if outcome.committed_budget_error is not None:
            return {
                "status": ContextPreparationStatus.BUDGET_EXCEEDED,
                "context_package_id": result.context_package_id,
                "error_code": outcome.committed_budget_error.code,
            }
        return {
            "status": ContextPreparationStatus.CONTEXT_BUILT,
            "context_package_id": result.context_package_id,
        }

    def _prepare_node(
        self, state: ContextPreparationGraphState, ledger: CapabilityLedger
    ) -> _StateUpdate:
        request = state["request"]
        context_package_id = state.get("context_package_id")
        job_version_id = state.get("job_version_id")
        if context_package_id is None or job_version_id is None:
            return self._failure(state, DependencyUnavailableError("workflow state is invalid"))
        scope = ResourceScope(
            job_version_id=job_version_id,
            context_package_id=context_package_id,
        )
        command = PrepareRuntimeContextCommand(
            context_package_id=context_package_id,
            max_tokens=request.runtime_max_tokens,
            correlation_id=request.retrieve.correlation_id,
            run_id=request.retrieve.run_id,
        )
        try:
            outcome = self._invoke(
                ledger=ledger,
                policy=context_preparation_policy(
                    "prepare_runtime_context", CapabilityId.PREPARE_RUNTIME_CONTEXT, scope
                ),
                invocation=CapabilityInvocation(
                    capability=CapabilityId.PREPARE_RUNTIME_CONTEXT,
                    resource_scope=scope,
                    side_effect_class=SideEffectClass.LOCAL_PERSISTENT_WRITE,
                    iteration=1,
                    input_tokens=estimate_tokens(str(context_package_id)),
                ),
                action=lambda guard: self._prepare.execute(command, execution_guard=guard),
            )
        except JobHunterError as error:
            return self._failure(state, error)
        result = outcome.result
        if outcome.committed_budget_error is not None:
            return {
                "status": ContextPreparationStatus.BUDGET_EXCEEDED,
                "runtime_context_id": result.runtime_context_id,
                "error_code": outcome.committed_budget_error.code,
            }
        return {
            "status": ContextPreparationStatus.CONTEXT_READY,
            "runtime_context_id": result.runtime_context_id,
        }

    def _invoke[T](
        self,
        *,
        ledger: CapabilityLedger,
        policy: NodeToolPolicy,
        invocation: CapabilityInvocation,
        action: Callable[[CapabilityExecutionGuard], T],
    ) -> _InvocationOutcome[T]:
        token = ledger.start(policy, invocation)
        started = self._clock.now_ms()
        guard = _CooperativeCapabilityGuard(
            ledger=ledger,
            token=token,
            clock=self._clock,
            started_ms=started,
        )
        try:
            result = action(guard)
        except JobHunterError:
            ledger.fail(token, guard.usage())
            raise
        except Exception:
            ledger.fail(token, guard.usage())
            raise DependencyUnavailableError("workflow dependency is unavailable") from None
        try:
            ledger.complete(token, guard.usage())
        except BudgetExceededError as error:
            # The application action has committed by the time it returns. Preserve
            # that identity and stop the graph instead of claiming rollback.
            return _InvocationOutcome(result=result, committed_budget_error=error)
        return _InvocationOutcome(result=result)

    @staticmethod
    def _failure(state: ContextPreparationGraphState, error: JobHunterError) -> _StateUpdate:
        if error.code == "context_budget_exceeded" or error.code == "budget_exceeded":
            status = ContextPreparationStatus.BUDGET_EXCEEDED
        elif error.code == "capability_denied":
            status = ContextPreparationStatus.POLICY_DENIED
        elif error.code == "dependency_unavailable":
            status = ContextPreparationStatus.DEPENDENCY_UNAVAILABLE
        else:
            status = ContextPreparationStatus.FAILED
        return {
            "status": status,
            "error_code": error.code,
        }

    @classmethod
    def _terminal_result(
        cls,
        request: ContextPreparationRequest,
        ledger: CapabilityLedger,
        error: JobHunterError,
    ) -> ContextPreparationResult:
        failure = cls._failure(
            {
                "request": request,
                "requirement_id": request.retrieve.requirement_id,
            },
            error,
        )
        return ContextPreparationResult(
            workflow_run_id=request.workflow_run_id,
            status=failure.get("status", ContextPreparationStatus.FAILED),
            requirement_id=request.retrieve.requirement_id,
            retrieval_run_id=None,
            context_package_id=None,
            runtime_context_id=None,
            capability_calls=ledger.completed_calls,
            attempted_calls=ledger.attempted_calls,
            completed_calls=ledger.completed_calls,
            committed_calls=ledger.committed_calls,
            capability_usage=ledger.records,
            error_code=failure.get("error_code"),
        )
