"""Static capability authorization and deterministic per-run budget accounting."""

from dataclasses import dataclass
from enum import StrEnum

from job_hunter.domain.ids import (
    ContextPackageId,
    JobVersionId,
    RequirementId,
    RetrievalRunId,
    RuntimeContextId,
    WorkflowRunId,
)
from job_hunter.errors import (
    BudgetExceededError,
    CapabilityDeniedError,
    InputValidationError,
)


class CapabilityId(StrEnum):
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    BUILD_CONTEXT_PACKAGE = "build_context_package"
    PREPARE_RUNTIME_CONTEXT = "prepare_runtime_context"


class SideEffectClass(StrEnum):
    READ_ONLY = "read_only"
    LOCAL_REVERSIBLE_WRITE = "local_reversible_write"
    LOCAL_PERSISTENT_WRITE = "local_persistent_write"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"


_SIDE_EFFECT_RANK = {
    SideEffectClass.READ_ONLY: 0,
    SideEffectClass.LOCAL_REVERSIBLE_WRITE: 1,
    SideEffectClass.LOCAL_PERSISTENT_WRITE: 2,
    SideEffectClass.EXTERNAL_SIDE_EFFECT: 3,
}


@dataclass(frozen=True, slots=True)
class ResourceScope:
    job_version_id: JobVersionId | None = None
    requirement_id: RequirementId | None = None
    retrieval_run_id: RetrievalRunId | None = None
    context_package_id: ContextPackageId | None = None
    runtime_context_id: RuntimeContextId | None = None

    def contains(self, requested: "ResourceScope") -> bool:
        return all(
            allowed is None or allowed == actual
            for allowed, actual in zip(
                (
                    self.job_version_id,
                    self.requirement_id,
                    self.retrieval_run_id,
                    self.context_package_id,
                    self.runtime_context_id,
                ),
                (
                    requested.job_version_id,
                    requested.requirement_id,
                    requested.retrieval_run_id,
                    requested.context_package_id,
                    requested.runtime_context_id,
                ),
                strict=True,
            )
        )


@dataclass(frozen=True, slots=True)
class CapabilityBudget:
    max_calls: int
    max_iterations: int
    timeout_ms: int
    max_input_tokens: int
    max_output_tokens: int
    max_result_bytes: int
    max_cost_microusd: int

    def __post_init__(self) -> None:
        values = (
            self.max_calls,
            self.max_iterations,
            self.timeout_ms,
            self.max_input_tokens,
            self.max_output_tokens,
            self.max_result_bytes,
        )
        if any(value < 1 for value in values) or self.max_cost_microusd < 0:
            raise InputValidationError("capability budgets must be bounded positive values")


@dataclass(frozen=True, slots=True)
class NodeToolPolicy:
    version: str
    node_name: str
    allowed_capabilities: tuple[CapabilityId, ...]
    resource_scope: ResourceScope
    side_effect_ceiling: SideEffectClass
    budget: CapabilityBudget

    def __post_init__(self) -> None:
        if not self.version.strip() or not self.node_name.strip():
            raise InputValidationError("capability policy identity is required")
        if not self.allowed_capabilities or len(set(self.allowed_capabilities)) != len(
            self.allowed_capabilities
        ):
            raise InputValidationError("capability policy requires unique allowed capabilities")


@dataclass(frozen=True, slots=True)
class CapabilityInvocation:
    capability: CapabilityId
    resource_scope: ResourceScope
    side_effect_class: SideEffectClass
    iteration: int
    input_tokens: int


@dataclass(frozen=True, slots=True)
class CapabilityUsage:
    elapsed_ms: int
    output_tokens: int
    result_bytes: int
    cost_microusd: int


class CapabilityCallOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED_BEFORE_COMMIT = "failed_before_commit"
    COMMITTED_BUDGET_EXCEEDED = "committed_budget_exceeded"


@dataclass(frozen=True, slots=True)
class CapabilityCallRecord:
    capability: CapabilityId
    node_name: str
    call_number: int
    outcome: CapabilityCallOutcome
    usage: CapabilityUsage


@dataclass(frozen=True, slots=True)
class CapabilityToken:
    workflow_run_id: WorkflowRunId
    policy_version: str
    node_name: str
    capability: CapabilityId
    call_number: int
    budget: CapabilityBudget


class CapabilityLedger:
    """One workflow-run ledger; prompts and nodes cannot mutate policy."""

    def __init__(self, workflow_run_id: WorkflowRunId) -> None:
        self.workflow_run_id = workflow_run_id
        self._calls: dict[tuple[str, CapabilityId], int] = {}
        self._records: list[CapabilityCallRecord] = []
        self._attempted_count = 0

    @property
    def attempted_calls(self) -> int:
        return self._attempted_count

    @property
    def completed_calls(self) -> int:
        return sum(
            record.outcome
            in {
                CapabilityCallOutcome.COMPLETED,
                CapabilityCallOutcome.COMMITTED_BUDGET_EXCEEDED,
            }
            for record in self._records
        )

    @property
    def committed_calls(self) -> int:
        return self.completed_calls

    @property
    def records(self) -> tuple[CapabilityCallRecord, ...]:
        return tuple(self._records)

    def start(
        self,
        policy: NodeToolPolicy,
        invocation: CapabilityInvocation,
    ) -> CapabilityToken:
        self._attempted_count += 1
        if (
            invocation.capability not in policy.allowed_capabilities
            or not policy.resource_scope.contains(invocation.resource_scope)
            or _SIDE_EFFECT_RANK[invocation.side_effect_class]
            > _SIDE_EFFECT_RANK[policy.side_effect_ceiling]
        ):
            raise CapabilityDeniedError("workflow capability is not authorized")
        if invocation.iteration < 1 or invocation.iteration > policy.budget.max_iterations:
            raise BudgetExceededError("workflow iteration budget exceeded")
        if invocation.input_tokens < 0 or invocation.input_tokens > policy.budget.max_input_tokens:
            raise BudgetExceededError("workflow input token budget exceeded")
        key = (policy.node_name, invocation.capability)
        call_number = self._calls.get(key, 0) + 1
        if call_number > policy.budget.max_calls:
            raise BudgetExceededError("workflow call budget exceeded")
        self._calls[key] = call_number
        return CapabilityToken(
            workflow_run_id=self.workflow_run_id,
            policy_version=policy.version,
            node_name=policy.node_name,
            capability=invocation.capability,
            call_number=call_number,
            budget=policy.budget,
        )

    @staticmethod
    def enforce(
        token: CapabilityToken,
        usage: CapabilityUsage,
    ) -> None:
        if (
            usage.elapsed_ms < 0
            or usage.output_tokens < 0
            or usage.result_bytes < 0
            or usage.cost_microusd < 0
        ):
            raise InputValidationError("capability usage cannot be negative")
        if usage.elapsed_ms > token.budget.timeout_ms:
            raise BudgetExceededError("workflow timeout budget exceeded")
        if usage.output_tokens > token.budget.max_output_tokens:
            raise BudgetExceededError("workflow output token budget exceeded")
        if usage.result_bytes > token.budget.max_result_bytes:
            raise BudgetExceededError("workflow result-size budget exceeded")
        if usage.cost_microusd > token.budget.max_cost_microusd:
            raise BudgetExceededError("workflow cost budget exceeded")

    def complete(
        self,
        token: CapabilityToken,
        usage: CapabilityUsage,
    ) -> None:
        try:
            self.enforce(token, usage)
        except BudgetExceededError:
            self._records.append(
                CapabilityCallRecord(
                    capability=token.capability,
                    node_name=token.node_name,
                    call_number=token.call_number,
                    outcome=CapabilityCallOutcome.COMMITTED_BUDGET_EXCEEDED,
                    usage=usage,
                )
            )
            raise
        self._records.append(
            CapabilityCallRecord(
                capability=token.capability,
                node_name=token.node_name,
                call_number=token.call_number,
                outcome=CapabilityCallOutcome.COMPLETED,
                usage=usage,
            )
        )

    def fail(self, token: CapabilityToken, usage: CapabilityUsage) -> None:
        if any(
            record.node_name == token.node_name
            and record.capability is token.capability
            and record.call_number == token.call_number
            for record in self._records
        ):
            return
        self._records.append(
            CapabilityCallRecord(
                capability=token.capability,
                node_name=token.node_name,
                call_number=token.call_number,
                outcome=CapabilityCallOutcome.FAILED_BEFORE_COMMIT,
                usage=usage,
            )
        )
