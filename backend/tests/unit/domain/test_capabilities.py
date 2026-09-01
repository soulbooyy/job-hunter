import pytest

from job_hunter.domain.capabilities import (
    CapabilityBudget,
    CapabilityId,
    CapabilityInvocation,
    CapabilityLedger,
    CapabilityUsage,
    NodeToolPolicy,
    ResourceScope,
    SideEffectClass,
)
from job_hunter.domain.ids import JobVersionId, RequirementId, WorkflowRunId
from job_hunter.errors import BudgetExceededError, CapabilityDeniedError


def _policy() -> NodeToolPolicy:
    return NodeToolPolicy(
        version="node-tool-policy-v1",
        node_name="retrieve",
        allowed_capabilities=(CapabilityId.RETRIEVE_EVIDENCE,),
        resource_scope=ResourceScope(
            job_version_id=JobVersionId("job-version-1"),
            requirement_id=RequirementId("requirement-1"),
        ),
        side_effect_ceiling=SideEffectClass.LOCAL_PERSISTENT_WRITE,
        budget=CapabilityBudget(
            max_calls=1,
            max_iterations=1,
            timeout_ms=100,
            max_input_tokens=20,
            max_output_tokens=10,
            max_result_bytes=100,
            max_cost_microusd=0,
        ),
    )


def test_capability_policy_rejects_unknown_scope_and_external_side_effects() -> None:
    ledger = CapabilityLedger(WorkflowRunId("workflow-run-1"))

    with pytest.raises(CapabilityDeniedError):
        ledger.start(
            _policy(),
            CapabilityInvocation(
                capability=CapabilityId.BUILD_CONTEXT_PACKAGE,
                resource_scope=ResourceScope(
                    job_version_id=JobVersionId("job-version-1"),
                    requirement_id=RequirementId("requirement-1"),
                ),
                side_effect_class=SideEffectClass.LOCAL_PERSISTENT_WRITE,
                iteration=1,
                input_tokens=1,
            ),
        )

    assert ledger.attempted_calls == 1
    assert ledger.completed_calls == 0

    with pytest.raises(CapabilityDeniedError):
        ledger.start(
            _policy(),
            CapabilityInvocation(
                capability=CapabilityId.RETRIEVE_EVIDENCE,
                resource_scope=ResourceScope(
                    job_version_id=JobVersionId("job-version-other"),
                    requirement_id=RequirementId("requirement-1"),
                ),
                side_effect_class=SideEffectClass.EXTERNAL_SIDE_EFFECT,
                iteration=1,
                input_tokens=1,
            ),
        )


def test_capability_ledger_distinguishes_attempted_completed_and_failed_usage() -> None:
    ledger = CapabilityLedger(WorkflowRunId("workflow-run-usage"))
    invocation = CapabilityInvocation(
        capability=CapabilityId.RETRIEVE_EVIDENCE,
        resource_scope=_policy().resource_scope,
        side_effect_class=SideEffectClass.LOCAL_PERSISTENT_WRITE,
        iteration=1,
        input_tokens=1,
    )
    token = ledger.start(_policy(), invocation)
    usage = CapabilityUsage(elapsed_ms=5, output_tokens=0, result_bytes=20, cost_microusd=0)
    ledger.fail(token, usage)

    assert ledger.attempted_calls == 1
    assert ledger.completed_calls == 0
    assert ledger.committed_calls == 0
    assert ledger.records[0].usage == usage


def test_capability_policy_enforces_every_budget_dimension() -> None:
    invocation = CapabilityInvocation(
        capability=CapabilityId.RETRIEVE_EVIDENCE,
        resource_scope=_policy().resource_scope,
        side_effect_class=SideEffectClass.LOCAL_PERSISTENT_WRITE,
        iteration=1,
        input_tokens=10,
    )

    for usage in (
        CapabilityUsage(elapsed_ms=101, output_tokens=1, result_bytes=1, cost_microusd=0),
        CapabilityUsage(elapsed_ms=1, output_tokens=11, result_bytes=1, cost_microusd=0),
        CapabilityUsage(elapsed_ms=1, output_tokens=1, result_bytes=101, cost_microusd=0),
        CapabilityUsage(elapsed_ms=1, output_tokens=1, result_bytes=1, cost_microusd=1),
    ):
        ledger = CapabilityLedger(WorkflowRunId("workflow-run-1"))
        token = ledger.start(_policy(), invocation)
        with pytest.raises(BudgetExceededError):
            ledger.complete(token, usage)

    ledger = CapabilityLedger(WorkflowRunId("workflow-run-1"))
    token = ledger.start(_policy(), invocation)
    ledger.complete(
        token,
        CapabilityUsage(elapsed_ms=1, output_tokens=1, result_bytes=1, cost_microusd=0),
    )
    with pytest.raises(BudgetExceededError):
        ledger.start(_policy(), invocation)
