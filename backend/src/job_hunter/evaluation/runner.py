"""Offline replay runner for deterministic retrieval, parser, and screening baselines."""

from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from job_hunter.application.ports import EvidenceRetriever
from job_hunter.application.quick_screen_policy import (
    QUICK_SCREEN_POLICY_VERSION,
    recommend_quick_screen,
)
from job_hunter.application.requirement_parsing import DeterministicRequirementParser
from job_hunter.domain.context import (
    CONTEXT_BUILDER_VERSION,
    CONTEXT_PACKAGING_OVERHEAD_TOKENS,
    CONTEXT_REDACTION_POLICY_VERSION,
    assemble_context,
)
from job_hunter.domain.ids import (
    CandidateProfileId,
    CorrelationId,
    EvidenceItemId,
    EvidenceVersionId,
    RequirementId,
    RunId,
)
from job_hunter.domain.knowledge import CandidateProfile, EvidenceItemVersion
from job_hunter.domain.retrieval import (
    EvidenceEligibilityPolicy,
    RetrievalHit,
    RetrievalMatchReason,
    RetrievalPolicy,
    RetrievalQuery,
    RetrievalStatus,
    RetrievalStrategy,
    RetrievalTaskType,
    RetrieverResult,
    estimate_tokens,
)
from job_hunter.evaluation.dataset import (
    EvaluationDataset,
    EvidenceFixture,
    RetrievalEvaluationCase,
)
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
_EVALUATION_CONTEXT_PROJECTION_VERSION = "evaluation-context-projection-v1"


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
    eligible_estimated_tokens: int
    selected_estimated_tokens: int

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
            eligible_estimated_tokens=metrics.eligible_estimated_tokens,
            selected_estimated_tokens=metrics.selected_estimated_tokens,
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
    hybrid_promotion: "HybridPromotionReport | None"


class HybridPromotionReport(_ReportModel):
    policy_version: str
    dataset_eligible: bool
    thresholds_met: bool
    promoted: bool
    recall_at_5_target: float
    direct_mrr_target: float
    no_evidence_accuracy_target: float
    retrieval_selection_token_reduction: float
    final_context_token_reduction: float | None
    large_context_case_count: int
    large_context_relevant_case_count: int
    large_context_no_evidence_count: int
    full_context_final_tokens: int
    hybrid_final_tokens: int
    full_context_reference_version: str
    context_builder_version: str
    redaction_policy_version: str
    context_projection_version: str
    large_context_threshold_tokens: int
    packaging_overhead_tokens: int
    recall_degradation: float | None
    no_evidence_degradation: float | None
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _CaseEvaluation:
    case: RetrievalEvaluationCase
    eligible: tuple[EvidenceItemVersion, ...]
    result: RetrieverResult
    observation: RetrievalObservation


@dataclass(frozen=True, slots=True)
class _StrategyEvaluation:
    retriever: EvidenceRetriever
    metrics: RetrievalMetrics
    cases: tuple[_CaseEvaluation, ...]


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


def _strategy_evaluation(
    dataset: EvaluationDataset,
    retriever: EvidenceRetriever,
) -> _StrategyEvaluation:
    policy = EvidenceEligibilityPolicy()
    case_evaluations: list[_CaseEvaluation] = []
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
        eligible_tokens = sum(estimate_tokens(item.canonical_content) for item in eligible.eligible)
        selected_ids = {hit.evidence_id for hit in result.hits}
        selected_tokens = sum(
            estimate_tokens(item.canonical_content)
            for item in eligible.eligible
            if item.evidence_id in selected_ids
        )
        if (
            result.eligible_count != len(eligible.eligible)
            or result.eligible_estimated_tokens != eligible_tokens
            or result.selected_estimated_tokens != selected_tokens
        ):
            raise ValueError("evaluation retriever returned invalid token accounting")
        observation = RetrievalObservation(
            judgments=tuple(
                RetrievalJudgmentValue(
                    evidence_id=EvidenceItemId(item.evidence_id),
                    relevance=item.relevance,
                )
                for item in case.judgments
            ),
            retrieved_ids=tuple(hit.evidence_id for hit in result.hits),
            no_relevant_evidence=case.no_relevant_evidence,
            predicted_no_relevant_evidence=(result.status is RetrievalStatus.NO_RELEVANT_EVIDENCE),
            eligible_estimated_tokens=result.eligible_estimated_tokens,
            selected_estimated_tokens=result.selected_estimated_tokens,
        )
        case_evaluations.append(
            _CaseEvaluation(
                case=case,
                eligible=eligible.eligible,
                result=result,
                observation=observation,
            )
        )
    cases = tuple(case_evaluations)
    return _StrategyEvaluation(
        retriever=retriever,
        metrics=evaluate_retrieval(tuple(item.observation for item in cases)),
        cases=cases,
    )


def _evaluation_profile(case_id: str) -> CandidateProfile:
    return CandidateProfile(
        profile_id=CandidateProfileId(f"evaluation-profile-{case_id}"),
        target_role_keywords=("synthetic evaluation role",),
        skill_keywords=("synthetic evaluation skill",),
        preferred_cities=(),
        created_at=_FIXTURE_TIME,
        correlation_id=CorrelationId(f"evaluation-profile-{case_id}"),
        run_id=RunId(f"evaluation-profile-{case_id}"),
    )


def _full_context_reference(case: _CaseEvaluation) -> RetrieverResult:
    ordered = tuple(
        sorted(
            case.eligible,
            key=lambda item: (str(item.evidence_id), str(item.version_id)),
        )
    )
    hits = tuple(
        RetrievalHit(
            evidence_id=item.evidence_id,
            evidence_version_id=item.version_id,
            rank=rank,
            score=1.0,
            reasons=(RetrievalMatchReason.FULL_CONTEXT,),
        )
        for rank, item in enumerate(ordered, start=1)
    )
    return RetrieverResult(
        status=(RetrievalStatus.COMPLETED if hits else RetrievalStatus.NO_RELEVANT_EVIDENCE),
        hits=hits,
        eligible_count=len(ordered),
        eligible_estimated_tokens=case.result.eligible_estimated_tokens,
        selected_estimated_tokens=case.result.eligible_estimated_tokens,
    )


def _context_tokens(
    case: _CaseEvaluation,
    result: RetrieverResult,
    *,
    max_tokens: int,
) -> int:
    assembly = assemble_context(
        requirement_id=RequirementId(case.case.requirement_id),
        requirement_text=case.case.requirement_text,
        profile=_evaluation_profile(case.case.case_id),
        task_instruction="Assess only evidence-grounded fit.",
        workflow_identity="deep-fit-analysis",
        hits=result.hits,
        evidence=case.eligible,
        max_tokens=max_tokens,
        packaging_overhead_tokens=CONTEXT_PACKAGING_OVERHEAD_TOKENS,
    )
    return assembly.total_estimated_tokens


def _paired_large_context_metrics(
    full: _StrategyEvaluation,
    hybrid: _StrategyEvaluation,
) -> tuple[RetrievalMetrics, RetrievalMetrics, int, int, int, int, int]:
    full_by_case = {item.case.case_id: item for item in full.cases}
    hybrid_by_case = {item.case.case_id: item for item in hybrid.cases}
    if full_by_case.keys() != hybrid_by_case.keys():
        raise ValueError("promotion strategies evaluated different case sets")
    full_observations: list[RetrievalObservation] = []
    hybrid_observations: list[RetrievalObservation] = []
    full_tokens = 0
    hybrid_tokens = 0
    relevant_cases = 0
    no_evidence_cases = 0
    for case_id, full_case in full_by_case.items():
        hybrid_case = hybrid_by_case[case_id]
        full_identity = tuple((item.evidence_id, item.version_id) for item in full_case.eligible)
        hybrid_identity = tuple(
            (item.evidence_id, item.version_id) for item in hybrid_case.eligible
        )
        if full_identity != hybrid_identity:
            raise ValueError("promotion strategies evaluated different eligibility universes")
        if full_case.result.eligible_estimated_tokens <= RetrievalPolicy.small_context_threshold:
            continue
        full_result = _full_context_reference(full_case)
        full_observations.append(
            RetrievalObservation(
                judgments=full_case.observation.judgments,
                retrieved_ids=tuple(hit.evidence_id for hit in full_result.hits),
                no_relevant_evidence=full_case.observation.no_relevant_evidence,
                predicted_no_relevant_evidence=(
                    full_result.status is RetrievalStatus.NO_RELEVANT_EVIDENCE
                ),
                eligible_estimated_tokens=full_result.eligible_estimated_tokens,
                selected_estimated_tokens=full_result.selected_estimated_tokens,
            )
        )
        hybrid_observations.append(hybrid_case.observation)
        relevant_cases += bool(full_case.observation.judgments)
        no_evidence_cases += full_case.observation.no_relevant_evidence
        # The reference budget is intentionally unbounded: this measures the
        # exact final package reduction against all eligible authoritative context.
        full_tokens += _context_tokens(full_case, full_result, max_tokens=1_000_000_000)
        hybrid_tokens += _context_tokens(
            hybrid_case,
            hybrid_case.result,
            max_tokens=hybrid_case.case.max_tokens,
        )
    return (
        evaluate_retrieval(tuple(full_observations)),
        evaluate_retrieval(tuple(hybrid_observations)),
        len(full_observations),
        relevant_cases,
        no_evidence_cases,
        full_tokens,
        hybrid_tokens,
    )


def _promotion_report(
    dataset: EvaluationDataset,
    evaluations: tuple[_StrategyEvaluation, ...],
) -> HybridPromotionReport | None:
    hybrid_evaluation = next(
        (item for item in evaluations if item.retriever.strategy is RetrievalStrategy.HYBRID),
        None,
    )
    if hybrid_evaluation is None:
        return None
    full_evaluation = next(
        (item for item in evaluations if item.retriever.strategy is RetrievalStrategy.FULL_CONTEXT),
        None,
    )
    if full_evaluation is None:
        raise ValueError("Hybrid promotion evaluation requires Full Context baseline")
    hybrid = RetrievalMetricReport.from_metrics(
        hybrid_evaluation.retriever,
        hybrid_evaluation.metrics,
    )
    dataset_eligible = (
        dataset.manifest.split.value == "frozen_holdout"
        and dataset.satisfies_minimum_dataset_gate
        and dataset.manifest.human_edits
    )
    retrieval_selection_reduction = (
        1.0 - hybrid.selected_estimated_tokens / hybrid.eligible_estimated_tokens
        if hybrid.eligible_estimated_tokens
        else 0.0
    )
    (
        full_large,
        hybrid_large,
        large_case_count,
        large_relevant_case_count,
        large_no_evidence_count,
        full_context_tokens,
        hybrid_context_tokens,
    ) = _paired_large_context_metrics(full_evaluation, hybrid_evaluation)
    final_context_reduction = (
        1.0 - hybrid_context_tokens / full_context_tokens
        if large_case_count and full_context_tokens
        else None
    )
    recall_degradation = (
        max(0.0, full_large.recall_at_5 - hybrid_large.recall_at_5)
        if large_relevant_case_count
        else None
    )
    no_evidence_degradation = (
        max(
            0.0,
            full_large.no_evidence_accuracy - hybrid_large.no_evidence_accuracy,
        )
        if large_no_evidence_count
        else None
    )
    thresholds_met = (
        hybrid.recall_at_5 >= 0.85
        and hybrid.direct_mrr >= 0.70
        and hybrid.no_evidence_total > 0
        and hybrid.no_evidence_accuracy >= 0.90
        and large_case_count > 0
        and large_relevant_case_count > 0
        and large_no_evidence_count > 0
        and final_context_reduction is not None
        and final_context_reduction >= 0.30
        and recall_degradation is not None
        and recall_degradation <= 0.05
        and no_evidence_degradation is not None
        and no_evidence_degradation <= 0.02
    )
    reasons: list[str] = []
    if not dataset_eligible:
        reasons.append("dataset_is_not_an_eligible_human-reviewed_frozen_holdout")
    if large_case_count == 0:
        reasons.append("no_large_eligible_context_cases")
    elif large_relevant_case_count == 0:
        reasons.append("no_large_eligible_context_relevance_cases")
    if large_no_evidence_count == 0:
        reasons.append("no_large_eligible_context_no-evidence_cases")
    if not thresholds_met:
        reasons.append("one_or_more_AC-RAG_promotion_thresholds_are_unmet")
    return HybridPromotionReport(
        policy_version="retrieval-policy-v1",
        dataset_eligible=dataset_eligible,
        thresholds_met=thresholds_met,
        promoted=dataset_eligible and thresholds_met,
        recall_at_5_target=0.85,
        direct_mrr_target=0.70,
        no_evidence_accuracy_target=0.90,
        retrieval_selection_token_reduction=retrieval_selection_reduction,
        final_context_token_reduction=final_context_reduction,
        large_context_case_count=large_case_count,
        large_context_relevant_case_count=large_relevant_case_count,
        large_context_no_evidence_count=large_no_evidence_count,
        full_context_final_tokens=full_context_tokens,
        hybrid_final_tokens=hybrid_context_tokens,
        full_context_reference_version="paired-full-context-package-v1",
        context_builder_version=CONTEXT_BUILDER_VERSION,
        redaction_policy_version=CONTEXT_REDACTION_POLICY_VERSION,
        context_projection_version=_EVALUATION_CONTEXT_PROJECTION_VERSION,
        large_context_threshold_tokens=RetrievalPolicy.small_context_threshold,
        packaging_overhead_tokens=CONTEXT_PACKAGING_OVERHEAD_TOKENS,
        recall_degradation=recall_degradation,
        no_evidence_degradation=no_evidence_degradation,
        reasons=tuple(reasons),
    )


def run_evaluation(
    dataset: EvaluationDataset,
    *,
    retrievers: tuple[EvidenceRetriever, ...] | None = None,
) -> EvaluationReport:
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
    selected_retrievers = retrievers or (
        FullContextRetriever(),
        LexicalMetadataRetriever(),
    )
    retrieval_evaluations = tuple(
        _strategy_evaluation(dataset, retriever) for retriever in selected_retrievers
    )
    retrieval_reports = tuple(
        RetrievalMetricReport.from_metrics(item.retriever, item.metrics)
        for item in retrieval_evaluations
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
        retrieval=retrieval_reports,
        parser=ParserMetricReport.from_metrics(
            parser,
            evaluate_parser(parser_observations),
        ),
        quick_screen=QuickScreenMetricReport.from_metrics(
            evaluate_quick_screen(quick_screen_observations)
        ),
        limitation=(
            "Synthetic fixtures verify retrieval mechanics only; they are not a "
            "human-reviewed Frozen Holdout, do not complete AC-DATA-001, and do not "
            "support product-quality claims."
            if dataset.manifest.split.value == "synthetic"
            else "This versioned dataset report is limited to its recorded split and sample."
        ),
        hybrid_promotion=_promotion_report(dataset, retrieval_evaluations),
    )
