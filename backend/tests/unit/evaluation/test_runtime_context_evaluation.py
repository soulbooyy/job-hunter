from pathlib import Path

from pydantic import TypeAdapter

from job_hunter.evaluation.runtime_context import (
    RuntimeContextDataset,
    run_runtime_context_evaluation,
)

REPOSITORY_ROOT = Path(__file__).parents[4]


def test_runtime_context_synthetic_evaluation_is_reproducible_and_narrow() -> None:
    dataset_path = REPOSITORY_ROOT / "evals" / "datasets" / "context-runtime-synthetic-v1.json"
    dataset = TypeAdapter(RuntimeContextDataset).validate_json(
        dataset_path.read_text(encoding="utf-8")
    )

    first = run_runtime_context_evaluation(dataset)
    second = run_runtime_context_evaluation(dataset)

    assert first == second
    assert first.mechanics_gate_passed
    assert first.protected_loss_count == 0
    assert first.reference_rehydration_accuracy == 1.0
    assert first.provenance_accuracy == 1.0
    assert first.unsupported_fact_count == 0
    assert first.silent_truncation_count == 0
    assert first.token_reduction >= 0.25
    assert first.evidence_lineage_coverage == 1.0
    assert first.effective_evidence_recall_degradation is None
    assert first.workflow_completion_degradation is None
    assert not first.product_quality_claim
    assert "downstream model" in first.limitation
