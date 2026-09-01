from datetime import UTC, datetime

import pytest

from job_hunter.application.context import BuildContextPackageCommand, BuildContextPackageResult
from job_hunter.application.ports import CapabilityExecutionGuard
from job_hunter.application.retrieval import RetrieveEvidenceCommand, RetrieveEvidenceResult
from job_hunter.application.runtime_context import (
    PrepareRuntimeContextCommand,
    PrepareRuntimeContextResult,
)
from job_hunter.domain.capabilities import (
    CapabilityId,
    CapabilityInvocation,
    CapabilityLedger,
    CapabilityUsage,
    ResourceScope,
    SideEffectClass,
)
from job_hunter.domain.ids import (
    ContextPackageId,
    CorrelationId,
    JobVersionId,
    RequirementId,
    RetrievalRunId,
    RunId,
    RuntimeContextId,
    WorkflowRunId,
)
from job_hunter.domain.knowledge import EvidenceSensitivity
from job_hunter.domain.retrieval import RetrievalStatus, RetrievalStrategy
from job_hunter.workflows.context_preparation import (
    CONTEXT_PREPARATION_POLICY_VERSION,
    ContextPreparationGraphState,
    ContextPreparationRequest,
    ContextPreparationStatus,
    ContextPreparationWorkflow,
    context_preparation_policy,
)

NOW = datetime(2026, 9, 1, 18, 0, tzinfo=UTC)


class _Clock:
    def __init__(self) -> None:
        self.value = 0

    def now_ms(self) -> int:
        self.value += 1
        return self.value


class _Retrieve:
    def __init__(self, status: RetrievalStatus) -> None:
        self.status = status
        self.calls = 0

    def execute(
        self,
        command: RetrieveEvidenceCommand,
        *,
        execution_guard: CapabilityExecutionGuard | None = None,
    ) -> RetrieveEvidenceResult:
        if execution_guard is not None:
            execution_guard.check()
        result = RetrieveEvidenceResult(
            retrieval_run_id=RetrievalRunId("retrieval-run-1"),
            requirement_id=command.requirement_id,
            job_version_id=JobVersionId("job-version-1"),
            strategy=RetrievalStrategy.FULL_CONTEXT,
            retriever_version="full-context-v1",
            status=self.status,
            hits=(),
            exclusions=(),
            eligible_count=0,
            eligible_estimated_tokens=0,
            selected_estimated_tokens=0,
            created_at=NOW,
            correlation_id=command.correlation_id,
            run_id=command.run_id,
            policy_version=None,
            initial_strategy=None,
            decision_reason=None,
            fallback_reason=None,
            promotion_dataset_version=None,
            semantic_ready=False,
            query_count=1,
        )
        if execution_guard is not None:
            execution_guard.check_before_commit(result_bytes=1)
        self.calls += 1
        return result


class _Build:
    def __init__(self) -> None:
        self.calls = 0

    def execute(
        self,
        command: BuildContextPackageCommand,
        *,
        execution_guard: CapabilityExecutionGuard | None = None,
    ) -> BuildContextPackageResult:
        if execution_guard is not None:
            execution_guard.check()
        result = BuildContextPackageResult(
            context_package_id=ContextPackageId("context-package-1"),
            retrieval_run_id=command.retrieval_run_id,
            total_estimated_tokens=30,
            max_tokens=command.max_tokens,
            created_at=NOW,
            correlation_id=command.correlation_id,
            run_id=command.run_id,
        )
        if execution_guard is not None:
            execution_guard.check_before_commit(result_bytes=1)
        self.calls += 1
        return result


class _Prepare:
    def __init__(self) -> None:
        self.calls = 0

    def execute(
        self,
        command: PrepareRuntimeContextCommand,
        *,
        execution_guard: CapabilityExecutionGuard | None = None,
    ) -> PrepareRuntimeContextResult:
        if execution_guard is not None:
            execution_guard.check()
        result = PrepareRuntimeContextResult(
            runtime_context_id=RuntimeContextId("runtime-context-1"),
            context_package_id=command.context_package_id,
            total_estimated_tokens=25,
            max_tokens=command.max_tokens,
            artifact_count=1,
            created_at=NOW,
            correlation_id=command.correlation_id,
            run_id=command.run_id,
        )
        if execution_guard is not None:
            execution_guard.check_before_commit(result_bytes=1)
        self.calls += 1
        return result


class _ControlledClock:
    def __init__(self, value: int = 0) -> None:
        self.value = value

    def now_ms(self) -> int:
        return self.value


class _BudgetedRetrieve(_Retrieve):
    def __init__(self, clock: _ControlledClock, *, post_commit_overrun: bool) -> None:
        super().__init__(RetrievalStatus.COMPLETED)
        self._clock = clock
        self._post_commit_overrun = post_commit_overrun
        self.commits = 0

    def execute(
        self,
        command: RetrieveEvidenceCommand,
        *,
        execution_guard: CapabilityExecutionGuard | None = None,
    ) -> RetrieveEvidenceResult:
        assert execution_guard is not None
        execution_guard.check()
        result = super().execute(command)
        self._clock.value = 30_001 if not self._post_commit_overrun else 1
        execution_guard.check_before_commit(result_bytes=1)
        self.commits += 1
        if self._post_commit_overrun:
            self._clock.value = 30_001
        return result


class _ExplodingGraph:
    def invoke(self, input: ContextPreparationGraphState) -> ContextPreparationGraphState:
        del input
        raise RuntimeError("third-party secret path /private/candidate")


def _compile_failure(ledger: object) -> _ExplodingGraph:
    del ledger
    raise RuntimeError("third-party compile secret /private/candidate")


def _committed_then_invoke_failure(ledger: CapabilityLedger) -> _ExplodingGraph:
    scope = ResourceScope(requirement_id=RequirementId("requirement-1"))
    token = ledger.start(
        context_preparation_policy("retrieve_evidence", CapabilityId.RETRIEVE_EVIDENCE, scope),
        CapabilityInvocation(
            capability=CapabilityId.RETRIEVE_EVIDENCE,
            resource_scope=scope,
            side_effect_class=SideEffectClass.LOCAL_PERSISTENT_WRITE,
            iteration=1,
            input_tokens=1,
        ),
    )
    ledger.complete(
        token,
        CapabilityUsage(elapsed_ms=5, output_tokens=0, result_bytes=10, cost_microusd=0),
    )
    return _ExplodingGraph()


def _request() -> ContextPreparationRequest:
    return ContextPreparationRequest(
        workflow_run_id=WorkflowRunId("workflow-run-1"),
        retrieve=RetrieveEvidenceCommand(
            requirement_id=RequirementId("requirement-1"),
            allowed_sensitivities=(EvidenceSensitivity.PRIVATE,),
            max_tokens=100,
            top_k=5,
            correlation_id=CorrelationId("correlation-workflow"),
            run_id=RunId("run-workflow"),
        ),
        task_instruction="Use grounded facts only.",
        workflow_identity="context-preparation",
        context_max_tokens=100,
        runtime_max_tokens=50,
    )


def test_graph_executes_only_concrete_context_prefix_to_context_ready() -> None:
    retrieve = _Retrieve(RetrievalStatus.COMPLETED)
    build = _Build()
    prepare = _Prepare()

    result = ContextPreparationWorkflow(
        retrieve_evidence=retrieve,
        build_context_package=build,
        prepare_runtime_context=prepare,
        monotonic_clock=_Clock(),
    ).run(_request())

    assert result.status is ContextPreparationStatus.CONTEXT_READY
    assert result.retrieval_run_id == RetrievalRunId("retrieval-run-1")
    assert result.context_package_id == ContextPackageId("context-package-1")
    assert result.runtime_context_id == RuntimeContextId("runtime-context-1")
    assert result.capability_calls == 3
    assert result.attempted_calls == 3
    assert result.completed_calls == 3
    assert result.committed_calls == 3
    assert (retrieve.calls, build.calls, prepare.calls) == (1, 1, 1)


@pytest.mark.parametrize(
    ("retrieval_status", "terminal_status"),
    (
        (RetrievalStatus.NO_RELEVANT_EVIDENCE, ContextPreparationStatus.NO_RELEVANT_EVIDENCE),
        (RetrievalStatus.INSUFFICIENT_EVIDENCE, ContextPreparationStatus.INSUFFICIENT_EVIDENCE),
        (RetrievalStatus.NOT_EXECUTABLE, ContextPreparationStatus.NOT_EXECUTABLE),
    ),
)
def test_graph_stops_before_context_build_for_explicit_retrieval_terminal(
    retrieval_status: RetrievalStatus,
    terminal_status: ContextPreparationStatus,
) -> None:
    build = _Build()
    prepare = _Prepare()

    result = ContextPreparationWorkflow(
        retrieve_evidence=_Retrieve(retrieval_status),
        build_context_package=build,
        prepare_runtime_context=prepare,
        monotonic_clock=_Clock(),
    ).run(_request())

    assert result.status is terminal_status
    assert result.capability_calls == 1
    assert build.calls == 0
    assert prepare.calls == 0


def test_graph_policy_surface_is_exact_and_closed() -> None:
    scope = ResourceScope(requirement_id=RequirementId("requirement-1"))
    policy = context_preparation_policy("retrieve_evidence", CapabilityId.RETRIEVE_EVIDENCE, scope)

    assert policy.version == CONTEXT_PREPARATION_POLICY_VERSION
    assert policy.allowed_capabilities == (CapabilityId.RETRIEVE_EVIDENCE,)
    assert policy.resource_scope == scope
    assert policy.budget.max_calls == 1
    assert policy.budget.max_iterations == 1
    assert policy.budget.max_cost_microusd == 0
    with pytest.raises(ValueError, match="node capability"):
        context_preparation_policy("retrieve_evidence", CapabilityId.BUILD_CONTEXT_PACKAGE, scope)


def test_precommit_timeout_rolls_back_cooperatively_and_records_attempt() -> None:
    clock = _ControlledClock()
    retrieve = _BudgetedRetrieve(clock, post_commit_overrun=False)

    result = ContextPreparationWorkflow(
        retrieve_evidence=retrieve,
        build_context_package=_Build(),
        prepare_runtime_context=_Prepare(),
        monotonic_clock=clock,
    ).run(_request())

    assert result.status is ContextPreparationStatus.BUDGET_EXCEEDED
    assert result.retrieval_run_id is None
    assert retrieve.commits == 0
    assert result.attempted_calls == 1
    assert result.completed_calls == 0
    assert result.committed_calls == 0
    assert result.capability_usage[0].usage.elapsed_ms == 30_001


def test_postcommit_timeout_preserves_committed_identity_and_stops_graph() -> None:
    clock = _ControlledClock()
    retrieve = _BudgetedRetrieve(clock, post_commit_overrun=True)

    result = ContextPreparationWorkflow(
        retrieve_evidence=retrieve,
        build_context_package=_Build(),
        prepare_runtime_context=_Prepare(),
        monotonic_clock=clock,
    ).run(_request())

    assert result.status is ContextPreparationStatus.BUDGET_EXCEEDED
    assert result.retrieval_run_id == RetrievalRunId("retrieval-run-1")
    assert retrieve.commits == 1
    assert result.attempted_calls == 1
    assert result.completed_calls == 1
    assert result.committed_calls == 1
    assert result.capability_usage[0].usage.elapsed_ms == 30_001


def test_langgraph_exception_is_translated_without_raw_details() -> None:
    result = ContextPreparationWorkflow(
        retrieve_evidence=_Retrieve(RetrievalStatus.COMPLETED),
        build_context_package=_Build(),
        prepare_runtime_context=_Prepare(),
        monotonic_clock=_Clock(),
        graph_compiler=lambda ledger: _ExplodingGraph(),
    ).run(_request())

    assert result.status is ContextPreparationStatus.DEPENDENCY_UNAVAILABLE
    assert result.error_code == "dependency_unavailable"
    assert result.attempted_calls == 0
    assert result.completed_calls == 0


def test_langgraph_compile_exception_is_translated_without_raw_details() -> None:
    result = ContextPreparationWorkflow(
        retrieve_evidence=_Retrieve(RetrievalStatus.COMPLETED),
        build_context_package=_Build(),
        prepare_runtime_context=_Prepare(),
        monotonic_clock=_Clock(),
        graph_compiler=_compile_failure,
    ).run(_request())

    assert result.status is ContextPreparationStatus.DEPENDENCY_UNAVAILABLE
    assert result.error_code == "dependency_unavailable"
    assert result.attempted_calls == 0


def test_invoke_failure_preserves_completed_usage_observed_before_failure() -> None:
    result = ContextPreparationWorkflow(
        retrieve_evidence=_Retrieve(RetrievalStatus.COMPLETED),
        build_context_package=_Build(),
        prepare_runtime_context=_Prepare(),
        monotonic_clock=_Clock(),
        graph_compiler=_committed_then_invoke_failure,
    ).run(_request())

    assert result.status is ContextPreparationStatus.DEPENDENCY_UNAVAILABLE
    assert result.attempted_calls == 1
    assert result.completed_calls == 1
    assert result.committed_calls == 1
    assert result.capability_usage[0].usage.elapsed_ms == 5
