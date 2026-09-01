"""Ports required by the current application slice."""

from datetime import datetime
from typing import Protocol

from job_hunter.domain.context import ContextPackage
from job_hunter.domain.ids import (
    ArtifactId,
    CandidateProfileId,
    ContextPackageId,
    ContextReferenceId,
    EvidenceItemId,
    EvidenceVersionId,
    JobId,
    JobVersionId,
    QuickScreenResultId,
    RequirementId,
    RetrievalRunId,
    RuntimeContextId,
    SourceReferenceId,
    SourceSnapshotId,
    TriageDecisionId,
)
from job_hunter.domain.jobs import Job, JobVersion, SourceSnapshot
from job_hunter.domain.knowledge import (
    CandidateProfile,
    EvidenceItem,
    EvidenceItemVersion,
    EvidenceSensitivity,
)
from job_hunter.domain.retrieval import (
    RetrievalQuery,
    RetrievalRun,
    RetrievalStrategy,
    RetrieverResult,
    SemanticChunkMatch,
    SemanticIndexRecord,
)
from job_hunter.domain.runtime_context import (
    ArtifactRecord,
    ArtifactReference,
    RuntimeContextPlan,
    RuntimeContextSnapshot,
)
from job_hunter.domain.screening import JobTriageRecord, ParsedRequirement, QuickScreenResult


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdGenerator(Protocol):
    def new_job_id(self) -> JobId: ...

    def new_job_version_id(self) -> JobVersionId: ...

    def new_source_snapshot_id(self) -> SourceSnapshotId: ...

    def new_source_reference_id(self) -> SourceReferenceId: ...

    def new_candidate_profile_id(self) -> CandidateProfileId: ...

    def new_evidence_item_id(self) -> EvidenceItemId: ...

    def new_evidence_version_id(self) -> EvidenceVersionId: ...

    def new_requirement_id(self) -> RequirementId: ...

    def new_quick_screen_result_id(self) -> QuickScreenResultId: ...

    def new_triage_decision_id(self) -> TriageDecisionId: ...

    def new_retrieval_run_id(self) -> RetrievalRunId: ...

    def new_context_package_id(self) -> ContextPackageId: ...

    def new_runtime_context_id(self) -> RuntimeContextId: ...


class ArtifactStore(Protocol):
    def write(self, record: ArtifactRecord, content: str) -> None: ...

    def read(self, record: ArtifactRecord) -> str: ...


class CapabilityExecutionGuard(Protocol):
    """Cooperative pre-commit checks supplied by a governed workflow."""

    def check(self) -> None: ...

    def check_before_commit(self, *, result_bytes: int) -> None: ...


class EvidenceRetriever(Protocol):
    @property
    def strategy(self) -> RetrievalStrategy: ...

    @property
    def version(self) -> str: ...

    @property
    def token_estimator_version(self) -> str: ...

    def retrieve(
        self,
        query: RetrievalQuery,
        evidence: tuple[EvidenceItemVersion, ...],
    ) -> RetrieverResult: ...


class EmbeddingProvider(Protocol):
    @property
    def version(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class SemanticIndex(Protocol):
    @property
    def version(self) -> str: ...

    @property
    def chunk_policy_version(self) -> str: ...

    @property
    def embedding_provider_version(self) -> str: ...

    @property
    def embedding_dimension(self) -> int: ...

    def is_ready(self) -> bool: ...

    def reconcile(
        self,
        records: tuple[SemanticIndexRecord, ...],
        embeddings: tuple[tuple[float, ...], ...],
    ) -> None: ...

    def query(
        self,
        embedding: tuple[float, ...],
        *,
        allowed_sensitivities: tuple[EvidenceSensitivity, ...],
        limit: int,
    ) -> tuple[SemanticChunkMatch, ...]: ...


class JobRepository(Protocol):
    def list_jobs(self) -> tuple[Job, ...]: ...

    def get_job(self, job_id: JobId) -> Job: ...

    def get_version(self, version_id: JobVersionId) -> JobVersion: ...

    def get_snapshot(self, snapshot_id: SourceSnapshotId) -> SourceSnapshot: ...

    def add_job(self, job: Job) -> None: ...

    def save_job(self, job: Job) -> None: ...

    def add_version(self, version: JobVersion) -> None: ...

    def add_snapshot(self, snapshot: SourceSnapshot) -> None: ...


class CandidateKnowledgeRepository(Protocol):
    def list_profiles(self) -> tuple[CandidateProfile, ...]: ...

    def get_active_profile_id(self) -> CandidateProfileId | None: ...

    def get_profile(self, profile_id: CandidateProfileId) -> CandidateProfile: ...

    def get_active_profile(self) -> CandidateProfile: ...

    def add_profile(self, profile: CandidateProfile) -> None: ...

    def get_evidence(self, evidence_id: EvidenceItemId) -> EvidenceItem: ...

    def list_evidence(self) -> tuple[EvidenceItem, ...]: ...

    def get_evidence_version(self, version_id: EvidenceVersionId) -> EvidenceItemVersion: ...

    def add_evidence(self, evidence: EvidenceItem) -> None: ...

    def save_evidence(self, evidence: EvidenceItem) -> None: ...

    def add_evidence_version(self, version: EvidenceItemVersion) -> None: ...


class ScreeningRepository(Protocol):
    def get_requirement(self, requirement_id: RequirementId) -> ParsedRequirement: ...

    def list_requirements(self, job_version_id: JobVersionId) -> tuple[ParsedRequirement, ...]: ...

    def add_requirements(self, requirements: tuple[ParsedRequirement, ...]) -> None: ...

    def get_quick_screen_result(self, result_id: QuickScreenResultId) -> QuickScreenResult: ...

    def get_latest_quick_screen_result(self, job_id: JobId) -> QuickScreenResult: ...

    def list_quick_screen_results(self, job_id: JobId) -> tuple[QuickScreenResult, ...]: ...

    def add_quick_screen_result(self, result: QuickScreenResult) -> None: ...

    def add_triage_record(self, record: JobTriageRecord) -> None: ...

    def list_triage_records(self, job_id: JobId) -> tuple[JobTriageRecord, ...]: ...


class RetrievalRepository(Protocol):
    def get_run(self, retrieval_run_id: RetrievalRunId) -> RetrievalRun: ...

    def list_runs(self, requirement_id: RequirementId) -> tuple[RetrievalRun, ...]: ...

    def add_run(self, run: RetrievalRun) -> None: ...


class ContextRepository(Protocol):
    def get_package(self, context_package_id: ContextPackageId) -> ContextPackage: ...

    def list_packages(self, retrieval_run_id: RetrievalRunId) -> tuple[ContextPackage, ...]: ...

    def add_package(self, package: ContextPackage) -> None: ...


class RuntimeContextRepository(Protocol):
    def get_snapshot(self, runtime_context_id: RuntimeContextId) -> RuntimeContextSnapshot: ...

    def list_snapshots(
        self, context_package_id: ContextPackageId
    ) -> tuple[RuntimeContextSnapshot, ...]: ...

    def get_artifact(self, artifact_id: ArtifactId) -> ArtifactRecord: ...

    def get_reference(self, reference_id: ContextReferenceId) -> ArtifactReference: ...

    def add_plan(self, plan: RuntimeContextPlan) -> None: ...


class UnitOfWork(Protocol):
    @property
    def jobs(self) -> JobRepository: ...

    @property
    def knowledge(self) -> CandidateKnowledgeRepository: ...

    @property
    def screening(self) -> ScreeningRepository: ...

    @property
    def retrieval(self) -> RetrievalRepository: ...

    @property
    def context(self) -> ContextRepository: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


class RuntimeContextUnitOfWork(UnitOfWork, Protocol):
    @property
    def runtime_context(self) -> RuntimeContextRepository: ...


class RuntimeContextUnitOfWorkFactory(Protocol):
    def __call__(self) -> RuntimeContextUnitOfWork: ...
