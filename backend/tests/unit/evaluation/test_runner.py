from pathlib import Path

from job_hunter.application.quick_screen_policy import QUICK_SCREEN_POLICY_VERSION
from job_hunter.evaluation.dataset import load_evaluation_dataset
from job_hunter.evaluation.runner import run_evaluation

REPOSITORY_ROOT = Path(__file__).parents[4]


def test_smoke_runner_is_reproducible_versioned_and_content_safe() -> None:
    dataset = load_evaluation_dataset(REPOSITORY_ROOT / "evals" / "datasets" / "smoke-v1.json")

    first = run_evaluation(dataset)
    second = run_evaluation(dataset)

    assert first == second
    assert first.dataset_version == "smoke-v1"
    assert first.annotation_version == "annotation-v1"
    assert not first.satisfies_minimum_dataset_gate
    assert {item.strategy for item in first.retrieval} == {
        "full_context",
        "lexical_metadata",
    }
    assert first.quick_screen.policy_version == QUICK_SCREEN_POLICY_VERSION
    assert set(first.parser.priority_per_class) == {
        "required",
        "preferred",
        "unspecified",
    }
    assert first.parser.priority_per_class["required"].support >= 0
    serialized = first.model_dump_json()
    assert "Built a Python evaluation pipeline" not in serialized
    assert "AC-DATA-001" in first.limitation
