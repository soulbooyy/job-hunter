"""Offline replay runner for deterministic retrieval, parser, and screening baselines."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from job_hunter.application.ports import EvidenceRetriever
from job_hunter.application.quick_screen_policy import (
    QUICK_SCREEN_POLICY_VERSION,
    recommend_quick_screen,
)
from job_hunter.application.requirement_parsing import DeterministicRequirementParser
from job_hunter.domain.ids import (
    CorrelationId,
    EvidenceItemId,
    EvidenceVersionId,
    RequirementId,
    RunId,
)
from job_hunter.domain.knowledge import EvidenceItemVersion
from job_hunter.domain.retrieval import (
    EvidenceEligibilityPolicy,
    RetrievalQuery,
    RetrievalStatus,
    RetrievalTaskType,
)
from job_hunter.evaluation.dataset import EvaluationDataset, EvidenceFixture
from job_hunter.evaluation.metrics import (
    ParserMetrics,
    ParserObservation,
    QuickScreenMetrics,
    QuickScreenObservation,
    RetrievalJudgmentValue,
    RetrievalMetrics,
    RetrievalObservation,
    evaluate_parser,
    evaluate_quick_screen,
    evaluate_retrieval,
)
from job_hunter.infrastructure.retrieval import FullContextRetriever, LexicalMetadataRetriever

_FIXTURE_TIME = datetime(2000, 1, 1, tzinfo=UTC)


class _ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RetrievalMetricReport(_ReportModel):
    strategy: str
    retriever_version: str
    token_estimator_version: str
    recall_at_5: float
    recall_case_count: int
    direct_mrr: float
    direct_case_count: int
    no_evidence_accuracy: float
    no_evidence_correct: int
    no_evidence_total: int

    @classmethod
    def from_metrics(
        cls,
        retriever: EvidenceRetriever,
        metrics: RetrievalMetrics,
    ) -> "RetrievalMetricReport":
        return cls(
            strategy=retriever.strategy.value,
            retriever_version=retriever.version,
            token_estimator_version=retriever.token_estimator_version,
            recall_at_5=metrics.recall_at_5,
            recall_case_count=metrics.recall_case_count,
            direct_mrr=metrics.direct_mrr,
            direct_case_count=metrics.direct_case_count,
            no_evidence_accuracy=metrics.no_evidence_accuracy,
            no_evidence_correct=metrics.no_evidence_correct,
            no_evidence_total=metrics.no_evidence_total,
        )


class PriorityClassMetricReport(_ReportModel):
    precision: float
    recall: float
    f1: float
    support: int


class ParserMetricReport(_ReportModel):
    parser_name: str
    parser_version: str
    atomic_precision: float
    atomic_recall: float
    true_positive: int
    false_positive: int
    false_negative: int
    priority_macro_f1: float
    priority_confusion: dict[str, dict[str, int]]
    priority_per_class: dict[str, PriorityClassMetricReport]

    @classmethod
    def from_metrics(
        cls,
        parser: DeterministicRequirementParser,
        metrics: ParserMetrics,
    ) -> "ParserMetricReport":
        return cls(
            parser_name=parser.name,
            parser_version=parser.version,
            atomic_precision=metrics.atomic_precision,
            atomic_recall=metrics.atomic_recall,
            true_positive=metrics.true_positive,
            false_positive=metrics.false_positive,
            false_negative=metrics.false_negative,
            priority_macro_f1=metrics.priority_macro_f1,
            priority_confusion=metrics.priority_confusion,
            priority_per_class={
                name: PriorityClassMetricReport(
                    precision=item.precision,
                    recall=item.recall,
                    f1=item.f1,
                    support=item.support,
                )
                for name, item in metrics.priority_per_class.items()
            },
        )


class QuickScreenMetricReport(_ReportModel):
    policy_version: str
    accuracy: float
    correct: int
    total: int
    confusion: dict[str, dict[str, int]]

    @classmethod
    def from_metrics(cls, metrics: QuickScreenMetrics) -> "QuickScreenMetricReport":
        return cls(
            policy_version=QUICK_SCREEN_POLICY_VERSION,
            accuracy=metrics.accuracy,
            correct=metrics.correct,
            total=metrics.total,
            confusion=metrics.confusion,
        )


class EvaluationReport(_ReportModel):
    dataset_version: str
    annotation_version: str
    split: str
    smoke_fixture: bool
    satisfies_minimum_dataset_gate: bool
    retrieval_case_count: int
    parser_case_count: int
    quick_screen_case_count: int
    eligibility_policy_version: str
    retrieval: tuple[RetrievalMetricReport, ...]
    parser: ParserMetricReport
    quick_screen: QuickScreenMetricReport
    limitation: str


def _evidence(
    case_id: str,
    item_index: int,
    fixture: EvidenceFixture,
) -> EvidenceItemVersion:
    return EvidenceItemVersion(
        version_id=EvidenceVersionId(fixture.evidence_version_id),
        evidence_id=EvidenceItemId(fixture.evidence_id),
        version_number=1,
        evidence_type=fixture.evidence_type,
        canonical_content=fixture.canonical_content,
        occurred_on=None,
        source=fixture.source,
        provenance=fixture.provenance,
        sensitivity=fixture.sensitivity,
        validity=fixture.validity,
        created_at=_FIXTURE_TIME,
        correlation_id=CorrelationId(f"eval-{case_id}-{item_index}"),
        run_id=RunId(f"eval-{case_id}-{item_index}"),
    )


def _retrieval_metrics(
    dataset: EvaluationDataset,
    retriever: EvidenceRetriever,
) -> RetrievalMetrics:
    policy = EvidenceEligibilityPolicy()
    observations: list[RetrievalObservation] = []
    for case in dataset.retrieval_cases:
        candidates = tuple(
            _evidence(case.case_id, index, item)
            for index, item in enumerate(case.evidence, start=1)
        )
        eligible = policy.evaluate(
            candidates,
            allowed_sensitivities=case.allowed_sensitivities,
        )
        result = retriever.retrieve(
            RetrievalQuery(
                requirement_id=RequirementId(case.requirement_id),
                text=case.requirement_text,
                task_type=RetrievalTaskType.DEEP_FIT,
                max_tokens=case.max_tokens,
                top_k=case.top_k,
            ),
            eligible.eligible,
        )
        observations.append(
            RetrievalObservation(
                judgments=tuple(
                    RetrievalJudgmentValue(
                        evidence_id=EvidenceItemId(item.evidence_id),
                        relevance=item.relevance,
                    )
                    for item in case.judgments
                ),
                retrieved_ids=tuple(hit.evidence_id for hit in result.hits),
                no_relevant_evidence=case.no_relevant_evidence,
                predicted_no_relevant_evidence=(
                    result.status is RetrievalStatus.NO_RELEVANT_EVIDENCE
                ),
            )
        )
    return evaluate_retrieval(tuple(observations))


def run_evaluation(dataset: EvaluationDataset) -> EvaluationReport:
    parser = DeterministicRequirementParser()
    parser_observations = tuple(
        ParserObservation(
            expected=tuple((item.text, item.priority) for item in case.expected_requirements),
            predicted=tuple((item.text, item.priority) for item in parser.parse(case.description)),
        )
        for case in dataset.parser_cases
    )
    quick_screen_observations = tuple(
        QuickScreenObservation(
            expected=case.expected_recommendation,
            predicted=recommend_quick_screen(
                title=case.title,
                city=case.city,
                requirement_texts=case.requirement_texts,
                target_role_keywords=case.target_role_keywords,
                skill_keywords=case.skill_keywords,
                preferred_cities=case.preferred_cities,
            )[0],
        )
        for case in dataset.quick_screen_cases
    )
    retrievers: tuple[EvidenceRetriever, ...] = (
        FullContextRetriever(),
        LexicalMetadataRetriever(),
    )
    return EvaluationReport(
        dataset_version=dataset.manifest.dataset_version,
        annotation_version=dataset.manifest.annotation_version,
        split=dataset.manifest.split.value,
        smoke_fixture=dataset.manifest.smoke_fixture,
        satisfies_minimum_dataset_gate=dataset.satisfies_minimum_dataset_gate,
        retrieval_case_count=len(dataset.retrieval_cases),
        parser_case_count=len(dataset.parser_cases),
        quick_screen_case_count=len(dataset.quick_screen_cases),
        eligibility_policy_version=EvidenceEligibilityPolicy.version,
        retrieval=tuple(
            RetrievalMetricReport.from_metrics(
                retriever,
                _retrieval_metrics(dataset, retriever),
            )
            for retriever in retrievers
        ),
        parser=ParserMetricReport.from_metrics(
            parser,
            evaluate_parser(parser_observations),
        ),
        quick_screen=QuickScreenMetricReport.from_metrics(
            evaluate_quick_screen(quick_screen_observations)
        ),
        limitation=(
            "Synthetic smoke fixtures verify runner mechanics only and do not satisfy "
            "AC-DATA-001 or support product-quality claims."
        ),
    )
