import pytest
from pydantic import BaseModel, ConfigDict

from job_hunter.domain.ids import EvidenceItemId
from job_hunter.domain.screening import QuickScreenRecommendation, RequirementPriority
from job_hunter.errors import InputValidationError
from job_hunter.evaluation.dataset import RelevanceGrade
from job_hunter.evaluation.metrics import (
    ParserObservation,
    QuickScreenObservation,
    RetrievalJudgmentValue,
    RetrievalObservation,
    evaluate_parser,
    evaluate_quick_screen,
    evaluate_retrieval,
)
from job_hunter.evaluation.replay import StructuredReplayModel


class _ReplayAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    answer: str


def test_retrieval_metrics_match_hand_calculated_macro_fixture() -> None:
    metrics = evaluate_retrieval(
        (
            RetrievalObservation(
                judgments=(
                    RetrievalJudgmentValue(EvidenceItemId("evidence-1"), RelevanceGrade.DIRECT),
                    RetrievalJudgmentValue(EvidenceItemId("evidence-2"), RelevanceGrade.PARTIAL),
                ),
                retrieved_ids=(EvidenceItemId("evidence-1"),),
                no_relevant_evidence=False,
                predicted_no_relevant_evidence=False,
            ),
            RetrievalObservation(
                judgments=(
                    RetrievalJudgmentValue(EvidenceItemId("evidence-3"), RelevanceGrade.DIRECT),
                ),
                retrieved_ids=(EvidenceItemId("evidence-4"), EvidenceItemId("evidence-3")),
                no_relevant_evidence=False,
                predicted_no_relevant_evidence=False,
            ),
            RetrievalObservation(
                judgments=(),
                retrieved_ids=(),
                no_relevant_evidence=True,
                predicted_no_relevant_evidence=True,
            ),
            RetrievalObservation(
                judgments=(),
                retrieved_ids=(EvidenceItemId("evidence-5"),),
                no_relevant_evidence=True,
                predicted_no_relevant_evidence=False,
            ),
        )
    )

    assert metrics.recall_at_5 == pytest.approx(0.75)
    assert metrics.recall_case_count == 2
    assert metrics.direct_mrr == pytest.approx(0.75)
    assert metrics.direct_case_count == 2
    assert metrics.no_evidence_accuracy == pytest.approx(0.5)
    assert metrics.no_evidence_correct == 1
    assert metrics.no_evidence_total == 2


def test_parser_metrics_use_normalized_exact_matching_and_raw_counts() -> None:
    metrics = evaluate_parser(
        (
            ParserObservation(
                expected=(
                    ("Must have Python", RequirementPriority.REQUIRED),
                    ("LLM experience preferred", RequirementPriority.PREFERRED),
                    ("Build APIs", RequirementPriority.UNSPECIFIED),
                ),
                predicted=(
                    ("  Must   have Python ", RequirementPriority.REQUIRED),
                    ("LLM experience preferred", RequirementPriority.REQUIRED),
                    ("Unrelated requirement", RequirementPriority.UNSPECIFIED),
                ),
            ),
        )
    )

    assert metrics.true_positive == 2
    assert metrics.false_positive == 1
    assert metrics.false_negative == 1
    assert metrics.atomic_precision == pytest.approx(2 / 3)
    assert metrics.atomic_recall == pytest.approx(2 / 3)
    assert metrics.priority_confusion["required"]["required"] == 1
    assert metrics.priority_confusion["preferred"]["required"] == 1
    assert metrics.priority_per_class["required"].precision == pytest.approx(0.5)
    assert metrics.priority_per_class["required"].recall == pytest.approx(1.0)
    assert metrics.priority_per_class["required"].f1 == pytest.approx(2 / 3)
    assert metrics.priority_per_class["required"].support == 1
    assert metrics.priority_per_class["preferred"].precision == pytest.approx(0.0)
    assert metrics.priority_per_class["preferred"].recall == pytest.approx(0.0)
    assert metrics.priority_per_class["preferred"].f1 == pytest.approx(0.0)
    assert metrics.priority_per_class["preferred"].support == 1
    assert metrics.priority_per_class["unspecified"].support == 0
    assert metrics.priority_macro_f1 == pytest.approx(2 / 9)


def test_quick_screen_metrics_are_separate_exact_label_counts() -> None:
    metrics = evaluate_quick_screen(
        (
            QuickScreenObservation(
                expected=QuickScreenRecommendation.SCREEN_IN,
                predicted=QuickScreenRecommendation.SCREEN_IN,
            ),
            QuickScreenObservation(
                expected=QuickScreenRecommendation.SCREEN_OUT,
                predicted=QuickScreenRecommendation.UNCERTAIN,
            ),
            QuickScreenObservation(
                expected=QuickScreenRecommendation.UNCERTAIN,
                predicted=QuickScreenRecommendation.UNCERTAIN,
            ),
        )
    )

    assert metrics.accuracy == pytest.approx(2 / 3)
    assert metrics.correct == 2
    assert metrics.total == 3
    assert metrics.confusion["screen_out"]["uncertain"] == 1


def test_structured_replay_model_validates_frozen_responses() -> None:
    model = StructuredReplayModel({"case-1": '{"answer":"validated"}'})

    assert model.invoke("case-1", _ReplayAnswer).answer == "validated"

    with pytest.raises(InputValidationError, match="replay response not found"):
        model.invoke("missing", _ReplayAnswer)

    invalid = StructuredReplayModel({"case-1": '{"unexpected":"value"}'})
    with pytest.raises(InputValidationError, match="replay response is invalid"):
        invalid.invoke("case-1", _ReplayAnswer)
