"""Runtime-validated versioned evaluation dataset contracts."""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from job_hunter.domain.knowledge import EvidenceSensitivity, EvidenceType, EvidenceValidity
from job_hunter.domain.retrieval import EvidenceEligibilityPolicy
from job_hunter.domain.screening import QuickScreenRecommendation, RequirementPriority
from job_hunter.errors import InputValidationError


class DatasetSplit(StrEnum):
    DEVELOPMENT = "development"
    REPLAY = "replay"
    FROZEN_HOLDOUT = "frozen_holdout"
    SYNTHETIC = "synthetic"
    LIVE = "live"


class RelevanceGrade(StrEnum):
    DIRECT = "direct"
    PARTIAL = "partial"
    BACKGROUND = "background"


class _DatasetModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class DatasetManifest(_DatasetModel):
    dataset_version: str = Field(min_length=1)
    annotation_version: str = Field(min_length=1)
    split: DatasetSplit
    source: str = Field(min_length=1)
    generation_method: str = Field(min_length=1)
    human_edits: bool
    smoke_fixture: bool


class EvaluationCase(_DatasetModel):
    case_id: str = Field(min_length=1, pattern=r"^\S+$")
    source: str = Field(min_length=1)
    generation_method: str = Field(min_length=1)
    human_edits: bool


class EvidenceFixture(_DatasetModel):
    evidence_id: str = Field(min_length=1, pattern=r"^\S+$")
    evidence_version_id: str = Field(min_length=1, pattern=r"^\S+$")
    evidence_type: EvidenceType
    canonical_content: str = Field(min_length=1)
    source: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    sensitivity: EvidenceSensitivity
    validity: EvidenceValidity


class RetrievalJudgment(_DatasetModel):
    evidence_id: str = Field(min_length=1, pattern=r"^\S+$")
    relevance: RelevanceGrade


class RetrievalEvaluationCase(EvaluationCase):
    job_id: str = Field(min_length=1, pattern=r"^\S+$")
    requirement_id: str = Field(min_length=1, pattern=r"^\S+$")
    requirement_text: str = Field(min_length=1)
    allowed_sensitivities: tuple[EvidenceSensitivity, ...] = Field(min_length=1)
    max_tokens: int = Field(gt=0)
    top_k: int = Field(gt=0)
    evidence: tuple[EvidenceFixture, ...]
    judgments: tuple[RetrievalJudgment, ...]
    no_relevant_evidence: bool
    no_relevant_evidence_human_confirmed: bool

    @model_validator(mode="after")
    def validate_ground_truth(self) -> "RetrievalEvaluationCase":
        evidence_ids = tuple(item.evidence_id for item in self.evidence)
        version_ids = tuple(item.evidence_version_id for item in self.evidence)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("case EvidenceItem IDs must be unique")
        if len(set(version_ids)) != len(version_ids):
            raise ValueError("case EvidenceVersion IDs must be unique")
        judgment_ids = tuple(item.evidence_id for item in self.judgments)
        if len(set(judgment_ids)) != len(judgment_ids):
            raise ValueError("judgment EvidenceItem IDs must be unique")
        if any(item_id not in evidence_ids for item_id in judgment_ids):
            raise ValueError("judgment must reference case evidence")
        evidence_by_id = {item.evidence_id: item for item in self.evidence}
        if any(
            EvidenceEligibilityPolicy.exclusion_reason(
                validity=evidence_by_id[judgment.evidence_id].validity,
                sensitivity=evidence_by_id[judgment.evidence_id].sensitivity,
                allowed_sensitivities=self.allowed_sensitivities,
            )
            is not None
            for judgment in self.judgments
        ):
            # Ground truth is defined only over the exact eligible candidate
            # universe; otherwise a correct exclusion would be scored as a miss.
            raise ValueError("judgment must reference eligible evidence")
        if self.no_relevant_evidence:
            if not self.no_relevant_evidence_human_confirmed:
                raise ValueError("No-Evidence requires human confirmation")
            if self.judgments:
                raise ValueError("No-Evidence case cannot contain relevance judgments")
        elif not self.judgments:
            raise ValueError("relevant-evidence case requires at least one judgment")
        if len(set(self.allowed_sensitivities)) != len(self.allowed_sensitivities):
            raise ValueError("allowed sensitivities must be unique")
        return self


class ExpectedRequirement(_DatasetModel):
    text: str = Field(min_length=1)
    priority: RequirementPriority


class ParserEvaluationCase(EvaluationCase):
    description: str = Field(min_length=1)
    expected_requirements: tuple[ExpectedRequirement, ...] = Field(min_length=1)


class QuickScreenEvaluationCase(EvaluationCase):
    title: str = Field(min_length=1)
    city: str = Field(min_length=1)
    requirement_texts: tuple[str, ...] = Field(min_length=1)
    target_role_keywords: tuple[str, ...] = Field(min_length=1)
    skill_keywords: tuple[str, ...] = Field(min_length=1)
    preferred_cities: tuple[str, ...] = ()
    expected_recommendation: QuickScreenRecommendation


class EvaluationDataset(_DatasetModel):
    manifest: DatasetManifest
    retrieval_cases: tuple[RetrievalEvaluationCase, ...]
    parser_cases: tuple[ParserEvaluationCase, ...]
    quick_screen_cases: tuple[QuickScreenEvaluationCase, ...]

    @model_validator(mode="after")
    def validate_case_ids(self) -> "EvaluationDataset":
        case_ids = tuple(
            item.case_id
            for track in (
                self.retrieval_cases,
                self.parser_cases,
                self.quick_screen_cases,
            )
            for item in track
        )
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("case IDs must be unique across evaluation tracks")
        return self

    @property
    def satisfies_minimum_dataset_gate(self) -> bool:
        if self.manifest.smoke_fixture:
            return False
        split = self.manifest.split
        if split in (DatasetSplit.DEVELOPMENT, DatasetSplit.REPLAY):
            job_count = len({item.job_id for item in self.retrieval_cases})
            return job_count >= 20 and len(self.retrieval_cases) >= 100
        if split is DatasetSplit.FROZEN_HOLDOUT:
            job_count = len({item.job_id for item in self.retrieval_cases})
            total = len(self.retrieval_cases)
            no_evidence = sum(item.no_relevant_evidence for item in self.retrieval_cases)
            ratio = no_evidence / total if total else 0.0
            return job_count >= 10 and total >= 50 and 0.2 <= ratio <= 0.3
        if split is DatasetSplit.SYNTHETIC:
            return (
                len(self.retrieval_cases) + len(self.parser_cases) + len(self.quick_screen_cases)
                >= 20
            )
        return False


def load_evaluation_dataset(path: Path) -> EvaluationDataset:
    try:
        payload = path.read_text(encoding="utf-8")
    except OSError:
        raise InputValidationError(f"evaluation dataset is unavailable: {path.name}") from None
    try:
        return EvaluationDataset.model_validate_json(payload)
    except ValidationError:
        raise InputValidationError(f"evaluation dataset is invalid: {path.name}") from None
