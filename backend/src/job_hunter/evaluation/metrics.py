"""Exact deterministic metrics with raw counts for reproducible reports."""

from dataclasses import dataclass

from job_hunter.domain.ids import EvidenceItemId
from job_hunter.domain.screening import QuickScreenRecommendation, RequirementPriority
from job_hunter.evaluation.dataset import RelevanceGrade


@dataclass(frozen=True, slots=True)
class RetrievalJudgmentValue:
    evidence_id: EvidenceItemId
    relevance: RelevanceGrade


@dataclass(frozen=True, slots=True)
class RetrievalObservation:
    judgments: tuple[RetrievalJudgmentValue, ...]
    retrieved_ids: tuple[EvidenceItemId, ...]
    no_relevant_evidence: bool
    predicted_no_relevant_evidence: bool
    eligible_estimated_tokens: int = 0
    selected_estimated_tokens: int = 0


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    recall_at_5: float
    recall_case_count: int
    direct_mrr: float
    direct_case_count: int
    no_evidence_accuracy: float
    no_evidence_correct: int
    no_evidence_total: int
    eligible_estimated_tokens: int
    selected_estimated_tokens: int


def evaluate_retrieval(
    observations: tuple[RetrievalObservation, ...],
) -> RetrievalMetrics:
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    no_evidence_correct = 0
    no_evidence_total = 0
    for observation in observations:
        relevant_ids = {item.evidence_id for item in observation.judgments}
        if relevant_ids:
            retrieved_at_5 = set(observation.retrieved_ids[:5])
            recalls.append(len(relevant_ids & retrieved_at_5) / len(relevant_ids))
        direct_ids = {
            item.evidence_id
            for item in observation.judgments
            if item.relevance is RelevanceGrade.DIRECT
        }
        if direct_ids:
            reciprocal_rank = next(
                (
                    1.0 / rank
                    for rank, evidence_id in enumerate(observation.retrieved_ids, start=1)
                    if evidence_id in direct_ids
                ),
                0.0,
            )
            reciprocal_ranks.append(reciprocal_rank)
        if observation.no_relevant_evidence:
            no_evidence_total += 1
            if observation.predicted_no_relevant_evidence:
                no_evidence_correct += 1
    return RetrievalMetrics(
        recall_at_5=sum(recalls) / len(recalls) if recalls else 0.0,
        recall_case_count=len(recalls),
        direct_mrr=(sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0.0),
        direct_case_count=len(reciprocal_ranks),
        no_evidence_accuracy=(
            no_evidence_correct / no_evidence_total if no_evidence_total else 0.0
        ),
        no_evidence_correct=no_evidence_correct,
        no_evidence_total=no_evidence_total,
        eligible_estimated_tokens=sum(item.eligible_estimated_tokens for item in observations),
        selected_estimated_tokens=sum(item.selected_estimated_tokens for item in observations),
    )


@dataclass(frozen=True, slots=True)
class ParserObservation:
    expected: tuple[tuple[str, RequirementPriority], ...]
    predicted: tuple[tuple[str, RequirementPriority], ...]


@dataclass(frozen=True, slots=True)
class PriorityClassMetrics:
    precision: float
    recall: float
    f1: float
    support: int


@dataclass(frozen=True, slots=True)
class ParserMetrics:
    atomic_precision: float
    atomic_recall: float
    true_positive: int
    false_positive: int
    false_negative: int
    priority_macro_f1: float
    priority_confusion: dict[str, dict[str, int]]
    priority_per_class: dict[str, PriorityClassMetrics]


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def evaluate_parser(observations: tuple[ParserObservation, ...]) -> ParserMetrics:
    true_positive = 0
    false_positive = 0
    false_negative = 0
    classes = tuple(RequirementPriority)
    confusion = {
        expected.value: {predicted.value: 0 for predicted in classes} for expected in classes
    }
    for observation in observations:
        expected = {_normalized(text): priority for text, priority in observation.expected}
        predicted = {_normalized(text): priority for text, priority in observation.predicted}
        matched = expected.keys() & predicted.keys()
        true_positive += len(matched)
        false_positive += len(predicted.keys() - expected.keys())
        false_negative += len(expected.keys() - predicted.keys())
        for text in matched:
            confusion[expected[text].value][predicted[text].value] += 1
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    priority_per_class: dict[str, PriorityClassMetrics] = {}
    for current in classes:
        true_class = confusion[current.value][current.value]
        false_class_positive = sum(
            confusion[other.value][current.value] for other in classes if other is not current
        )
        false_class_negative = sum(
            confusion[current.value][other.value] for other in classes if other is not current
        )
        predicted = true_class + false_class_positive
        support = true_class + false_class_negative
        precision = true_class / predicted if predicted else 0.0
        recall = true_class / support if support else 0.0
        f1_denominator = precision + recall
        priority_per_class[current.value] = PriorityClassMetrics(
            precision=precision,
            recall=recall,
            f1=(2 * precision * recall / f1_denominator if f1_denominator else 0.0),
            support=support,
        )
    return ParserMetrics(
        atomic_precision=(true_positive / precision_denominator if precision_denominator else 0.0),
        atomic_recall=true_positive / recall_denominator if recall_denominator else 0.0,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        priority_macro_f1=(
            sum(item.f1 for item in priority_per_class.values()) / len(priority_per_class)
        ),
        priority_confusion=confusion,
        priority_per_class=priority_per_class,
    )


@dataclass(frozen=True, slots=True)
class QuickScreenObservation:
    expected: QuickScreenRecommendation
    predicted: QuickScreenRecommendation


@dataclass(frozen=True, slots=True)
class QuickScreenMetrics:
    accuracy: float
    correct: int
    total: int
    confusion: dict[str, dict[str, int]]


def evaluate_quick_screen(
    observations: tuple[QuickScreenObservation, ...],
) -> QuickScreenMetrics:
    classes = tuple(QuickScreenRecommendation)
    confusion = {
        expected.value: {predicted.value: 0 for predicted in classes} for expected in classes
    }
    correct = 0
    for observation in observations:
        confusion[observation.expected.value][observation.predicted.value] += 1
        if observation.expected is observation.predicted:
            correct += 1
    total = len(observations)
    return QuickScreenMetrics(
        accuracy=correct / total if total else 0.0,
        correct=correct,
        total=total,
        confusion=confusion,
    )
