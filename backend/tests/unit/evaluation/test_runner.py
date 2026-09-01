from pathlib import Path

from job_hunter.application.quick_screen_policy import QUICK_SCREEN_POLICY_VERSION
from job_hunter.domain.ids import RequirementId
from job_hunter.domain.knowledge import EvidenceItemVersion
from job_hunter.domain.retrieval import (
    TOKEN_ESTIMATOR_VERSION,
    RetrievalHit,
    RetrievalMatchReason,
    RetrievalQuery,
    RetrievalStatus,
    RetrievalStrategy,
    RetrieverResult,
    estimate_tokens,
)
from job_hunter.evaluation.dataset import EvaluationDataset, load_evaluation_dataset
from job_hunter.evaluation.runner import run_evaluation
from job_hunter.infrastructure.retrieval import FullContextRetriever

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


class _PairedHybridRetriever:
    @property
    def strategy(self) -> RetrievalStrategy:
        return RetrievalStrategy.HYBRID

    @property
    def version(self) -> str:
        return "paired-hybrid-test-v1"

    @property
    def token_estimator_version(self) -> str:
        return TOKEN_ESTIMATOR_VERSION

    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> RetrieverResult:
        eligible_tokens = sum(estimate_tokens(item.canonical_content) for item in evidence)
        if query.requirement_id == RequirementId("requirement-relevant"):
            selected = evidence[0]
            selected_tokens = estimate_tokens(selected.canonical_content)
            return RetrieverResult(
                status=RetrievalStatus.COMPLETED,
                hits=(
                    RetrievalHit(
                        evidence_id=selected.evidence_id,
                        evidence_version_id=selected.version_id,
                        rank=1,
                        score=1.0,
                        reasons=(RetrievalMatchReason.HYBRID_FUSION,),
                    ),
                ),
                eligible_count=len(evidence),
                eligible_estimated_tokens=eligible_tokens,
                selected_estimated_tokens=selected_tokens,
            )
        return RetrieverResult(
            status=RetrievalStatus.NO_RELEVANT_EVIDENCE,
            hits=(),
            eligible_count=len(evidence),
            eligible_estimated_tokens=eligible_tokens,
            selected_estimated_tokens=0,
        )


def _large_context_dataset() -> EvaluationDataset:
    def evidence_for(case: str) -> list[dict[str, object]]:
        return [
            {
                "evidence_id": f"evidence-{case}-{index}",
                "evidence_version_id": f"evidence-version-{case}-{index}",
                "evidence_type": "experience",
                "canonical_content": " ".join(
                    ("direct" if index == 0 else "background",)
                    + tuple(f"token{case}{index}{token}" for token in range(199))
                ),
                "source": "synthetic",
                "provenance": "human-confirmed synthetic fixture",
                "sensitivity": "public",
                "validity": "valid",
            }
            for index in range(7)
        ]

    cases: list[dict[str, object]] = []
    for case in ("relevant", "empty"):
        cases.append(
            {
                "case_id": f"large-{case}",
                "source": "synthetic",
                "generation_method": "deterministic unit fixture",
                "human_edits": True,
                "job_id": f"job-{case}",
                "requirement_id": f"requirement-{case}",
                "requirement_text": f"Synthetic {case} requirement",
                "allowed_sensitivities": ["public"],
                "max_tokens": 400,
                "top_k": 2,
                "evidence": evidence_for(case),
                "judgments": (
                    [
                        {
                            "evidence_id": f"evidence-{case}-0",
                            "relevance": "direct",
                        }
                    ]
                    if case == "relevant"
                    else []
                ),
                "no_relevant_evidence": case == "empty",
                "no_relevant_evidence_human_confirmed": case == "empty",
            }
        )
    return EvaluationDataset.model_validate(
        {
            "manifest": {
                "dataset_version": "paired-large-test-v1",
                "annotation_version": "annotation-v1",
                "split": "frozen_holdout",
                "source": "synthetic",
                "generation_method": "deterministic unit fixture",
                "human_edits": True,
                "smoke_fixture": False,
            },
            "retrieval_cases": cases,
            "parser_cases": [],
            "quick_screen_cases": [],
        }
    )


def test_hybrid_promotion_uses_paired_large_final_context_packages() -> None:
    report = run_evaluation(
        _large_context_dataset(),
        retrievers=(FullContextRetriever(), _PairedHybridRetriever()),
    )

    promotion = report.hybrid_promotion
    assert promotion is not None
    assert promotion.large_context_case_count == 2
    assert promotion.large_context_relevant_case_count == 1
    assert promotion.large_context_no_evidence_count == 1
    assert promotion.recall_degradation == 0.0
    assert promotion.no_evidence_degradation == 0.0
    assert promotion.final_context_token_reduction is not None
    assert promotion.final_context_token_reduction >= 0.30
    assert promotion.full_context_final_tokens > promotion.hybrid_final_tokens
    assert promotion.thresholds_met
    assert not promotion.promoted
