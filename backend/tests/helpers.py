from collections import defaultdict
from datetime import datetime

from job_hunter.api.lifespan import ApplicationUseCases
from job_hunter.application.candidate_knowledge import CreateCandidateProfile, SaveEvidence
from job_hunter.application.import_job import ImportJob
from job_hunter.application.ports import Clock, IdGenerator, UnitOfWorkFactory
from job_hunter.application.screening import RecordJobTriage, RunQuickScreen
from job_hunter.application.workspace_queries import WorkspaceQueries
from job_hunter.domain.ids import (
    CandidateProfileId,
    EvidenceItemId,
    EvidenceVersionId,
    JobId,
    JobVersionId,
    QuickScreenResultId,
    RequirementId,
    RetrievalRunId,
    SourceReferenceId,
    SourceSnapshotId,
    TriageDecisionId,
)
from job_hunter.infrastructure.memory import InMemoryStore, InMemoryUnitOfWorkFactory
from job_hunter.ingestion.manual import (
    JobSource,
    JobSourceRegistry,
    ManualJDSource,
    ManualURLSource,
)


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def now(self) -> datetime:
        return self._value


class DeterministicIdGenerator:
    def __init__(self) -> None:
        self._counts: defaultdict[str, int] = defaultdict(int)

    def _next(self, kind: str) -> str:
        self._counts[kind] += 1
        return f"{kind}-{self._counts[kind]:03d}"

    def new_job_id(self) -> JobId:
        return JobId(self._next("job"))

    def new_job_version_id(self) -> JobVersionId:
        return JobVersionId(self._next("job-version"))

    def new_source_snapshot_id(self) -> SourceSnapshotId:
        return SourceSnapshotId(self._next("source-snapshot"))

    def new_source_reference_id(self) -> SourceReferenceId:
        return SourceReferenceId(self._next("source-reference"))

    def new_candidate_profile_id(self) -> CandidateProfileId:
        return CandidateProfileId(self._next("candidate-profile"))

    def new_evidence_item_id(self) -> EvidenceItemId:
        return EvidenceItemId(self._next("evidence"))

    def new_evidence_version_id(self) -> EvidenceVersionId:
        return EvidenceVersionId(self._next("evidence-version"))

    def new_requirement_id(self) -> RequirementId:
        return RequirementId(self._next("requirement"))

    def new_quick_screen_result_id(self) -> QuickScreenResultId:
        return QuickScreenResultId(self._next("quick-screen"))

    def new_triage_decision_id(self) -> TriageDecisionId:
        return TriageDecisionId(self._next("triage"))

    def new_retrieval_run_id(self) -> RetrievalRunId:
        return RetrievalRunId(self._next("retrieval-run"))


def build_test_use_cases(
    *,
    clock: Clock,
    id_generator: IdGenerator,
    sources: tuple[JobSource, ...] | None = None,
    import_job: ImportJob | None = None,
    unit_of_work_factory: UnitOfWorkFactory | None = None,
) -> ApplicationUseCases:
    """Build one explicit, internally shared application graph for API tests."""
    factory = (
        unit_of_work_factory
        if unit_of_work_factory is not None
        else InMemoryUnitOfWorkFactory(InMemoryStore())
    )
    importer = (
        import_job
        if import_job is not None
        else ImportJob(
            source_registry=JobSourceRegistry(
                sources if sources is not None else (ManualJDSource(), ManualURLSource())
            ),
            unit_of_work_factory=factory,
            clock=clock,
            id_generator=id_generator,
        )
    )
    return ApplicationUseCases(
        import_job=importer,
        create_candidate_profile=CreateCandidateProfile(
            unit_of_work_factory=factory,
            clock=clock,
            id_generator=id_generator,
        ),
        save_evidence=SaveEvidence(
            unit_of_work_factory=factory,
            clock=clock,
            id_generator=id_generator,
        ),
        run_quick_screen=RunQuickScreen(
            unit_of_work_factory=factory,
            clock=clock,
            id_generator=id_generator,
        ),
        record_job_triage=RecordJobTriage(
            unit_of_work_factory=factory,
            clock=clock,
            id_generator=id_generator,
        ),
        workspace_queries=WorkspaceQueries(unit_of_work_factory=factory),
    )
