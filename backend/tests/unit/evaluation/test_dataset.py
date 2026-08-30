from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from job_hunter.evaluation.dataset import EvaluationDataset, load_evaluation_dataset

REPOSITORY_ROOT = Path(__file__).parents[4]


def _dataset_payload() -> dict[str, object]:
    return {
        "manifest": {
            "dataset_version": "smoke-v1",
            "annotation_version": "annotation-v1",
            "split": "synthetic",
            "source": "synthetic fixtures",
            "generation_method": "hand-authored",
            "human_edits": True,
            "smoke_fixture": True,
        },
        "retrieval_cases": [
            {
                "case_id": "retrieval-1",
                "job_id": "job-1",
                "requirement_id": "requirement-1",
                "requirement_text": "Python evaluation pipeline",
                "source": "synthetic fixture",
                "generation_method": "hand-authored",
                "human_edits": True,
                "allowed_sensitivities": ["public"],
                "max_tokens": 100,
                "top_k": 5,
                "evidence": [
                    {
                        "evidence_id": "evidence-1",
                        "evidence_version_id": "evidence-version-1",
                        "evidence_type": "project",
                        "canonical_content": "Built a Python evaluation pipeline",
                        "source": "manual",
                        "provenance": "synthetic human-reviewed fixture",
                        "sensitivity": "public",
                        "validity": "valid",
                    }
                ],
                "judgments": [{"evidence_id": "evidence-1", "relevance": "direct"}],
                "no_relevant_evidence": False,
                "no_relevant_evidence_human_confirmed": False,
            }
        ],
        "parser_cases": [],
        "quick_screen_cases": [],
    }


def test_dataset_rejects_dangling_judgment() -> None:
    payload = _dataset_payload()
    retrieval_cases = cast(list[dict[str, object]], payload["retrieval_cases"])
    case = retrieval_cases[0]
    case["judgments"] = [{"evidence_id": "missing", "relevance": "direct"}]

    with pytest.raises(ValidationError, match="judgment must reference case evidence"):
        EvaluationDataset.model_validate(payload)


def test_dataset_rejects_unconfirmed_no_evidence_label() -> None:
    payload = _dataset_payload()
    retrieval_cases = cast(list[dict[str, object]], payload["retrieval_cases"])
    case = retrieval_cases[0]
    case["judgments"] = []
    case["no_relevant_evidence"] = True

    with pytest.raises(ValidationError, match="No-Evidence requires human confirmation"):
        EvaluationDataset.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    (
        ("validity", "expired"),
        ("validity", "revoked"),
        ("sensitivity", "sensitive"),
    ),
)
def test_dataset_rejects_judgment_for_ineligible_evidence(
    field_name: str,
    field_value: str,
) -> None:
    payload = _dataset_payload()
    retrieval_cases = cast(list[dict[str, object]], payload["retrieval_cases"])
    evidence = cast(list[dict[str, object]], retrieval_cases[0]["evidence"])
    evidence[0][field_name] = field_value

    with pytest.raises(ValidationError, match="judgment must reference eligible evidence"):
        EvaluationDataset.model_validate(payload)


def test_dataset_rejects_duplicate_case_ids_across_tracks() -> None:
    payload = _dataset_payload()
    payload["parser_cases"] = [
        {
            "case_id": "retrieval-1",
            "source": "synthetic fixture",
            "generation_method": "hand-authored",
            "human_edits": True,
            "description": "Must have Python experience",
            "expected_requirements": [
                {"text": "Must have Python experience", "priority": "required"}
            ],
        }
    ]

    with pytest.raises(ValidationError, match="case IDs must be unique"):
        EvaluationDataset.model_validate(payload)


def test_committed_smoke_dataset_is_valid_but_does_not_claim_dataset_gate() -> None:
    dataset = load_evaluation_dataset(REPOSITORY_ROOT / "evals" / "datasets" / "smoke-v1.json")

    assert dataset.manifest.dataset_version == "smoke-v1"
    assert dataset.manifest.smoke_fixture
    assert not dataset.satisfies_minimum_dataset_gate
    assert dataset.retrieval_cases
    assert dataset.parser_cases
    assert dataset.quick_screen_cases
