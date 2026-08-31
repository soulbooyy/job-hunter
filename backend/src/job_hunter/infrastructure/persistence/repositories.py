"""SQL repositories that hydrate validated Domain values from authoritative rows."""

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from job_hunter.application.ports import (
    CandidateKnowledgeRepository,
    JobRepository,
    RetrievalRepository,
    ScreeningRepository,
)
from job_hunter.domain.ids import (
    CandidateProfileId,
    EvidenceItemId,
    EvidenceVersionId,
    JobId,
    JobVersionId,
    QuickScreenResultId,
    RequirementId,
    RetrievalRunId,
    SourceSnapshotId,
)
from job_hunter.domain.jobs import Job, JobVersion, SourceReference, SourceSnapshot
from job_hunter.domain.knowledge import CandidateProfile, EvidenceItem, EvidenceItemVersion
from job_hunter.domain.retrieval import RetrievalRun
from job_hunter.domain.screening import JobTriageRecord, ParsedRequirement, QuickScreenResult
from job_hunter.errors import ConflictError, DependencyUnavailableError, EntityNotFoundError
from job_hunter.infrastructure.persistence.models import (
    CandidateProfileRow,
    CandidateProfileStateRow,
    EvidenceItemRow,
    EvidenceVersionRow,
    JobRow,
    JobTriageRecordRow,
    JobVersionRow,
    ParsedRequirementRow,
    QuickScreenRequirementRow,
    QuickScreenResultRow,
    RetrievalRunExclusionRow,
    RetrievalRunHitRow,
    RetrievalRunRow,
    SourceReferenceRow,
    SourceSnapshotRow,
)
from job_hunter.infrastructure.persistence.serialization import dump_payload, load_payload

_JOB = TypeAdapter(Job)
_JOB_VERSION = TypeAdapter(JobVersion)
_SOURCE_REFERENCE = TypeAdapter(SourceReference)
_SOURCE_SNAPSHOT = TypeAdapter(SourceSnapshot)
_PROFILE = TypeAdapter(CandidateProfile)
_EVIDENCE_ITEM = TypeAdapter(EvidenceItem)
_EVIDENCE_VERSION = TypeAdapter(EvidenceItemVersion)
_REQUIREMENT = TypeAdapter(ParsedRequirement)
_SCREEN_RESULT = TypeAdapter(QuickScreenResult)
_TRIAGE = TypeAdapter(JobTriageRecord)
_RETRIEVAL_RUN = TypeAdapter(RetrievalRun)


def _invalid_state() -> DependencyUnavailableError:
    return DependencyUnavailableError("persisted state is invalid")


class SqlAlchemyJobRepository(JobRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_jobs(self) -> tuple[Job, ...]:
        rows = self._session.scalars(select(JobRow).order_by(JobRow.job_id)).all()
        return tuple(self._hydrate(row) for row in rows)

    def get_job(self, job_id: JobId) -> Job:
        row = self._session.get(JobRow, str(job_id))
        if row is None:
            raise EntityNotFoundError(f"job not found: {job_id}")
        return self._hydrate(row)

    def _hydrate(self, row: JobRow) -> Job:
        job = load_payload(_JOB, row.payload)
        version_rows = self._session.scalars(
            select(JobVersionRow)
            .where(JobVersionRow.job_id == row.job_id)
            .order_by(JobVersionRow.version_number)
        ).all()
        reference_rows = self._session.scalars(
            select(SourceReferenceRow)
            .where(SourceReferenceRow.job_id == row.job_id)
            .order_by(SourceReferenceRow.ordinal)
        ).all()
        references = tuple(load_payload(_SOURCE_REFERENCE, item.payload) for item in reference_rows)
        if (
            str(job.job_id) != row.job_id
            or str(job.active_version_id) != row.active_version_id
            or (
                str(job.latest_quick_screen_result_id)
                if job.latest_quick_screen_result_id is not None
                else None
            )
            != row.latest_quick_screen_result_id
            or job.lifecycle_status.value != row.lifecycle_status
            or tuple(str(item) for item in job.version_ids)
            != tuple(item.version_id for item in version_rows)
            or job.source_references != references
            or tuple(item.reference_id for item in reference_rows)
            != tuple(str(item.reference_id) for item in references)
            or tuple(item.job_version_id for item in reference_rows)
            != tuple(str(item) for item in job.version_ids)
            or tuple(item.snapshot_id for item in reference_rows)
            != tuple(str(item.snapshot_id) for item in references)
        ):
            raise _invalid_state()
        if row.latest_quick_screen_result_id is not None:
            screen = self._session.scalars(
                select(QuickScreenResultRow).where(
                    QuickScreenResultRow.result_id == row.latest_quick_screen_result_id
                )
            ).one_or_none()
            if screen is None or screen.job_id != row.job_id:
                raise _invalid_state()
        return job

    def get_version(self, version_id: JobVersionId) -> JobVersion:
        row = self._session.get(JobVersionRow, str(version_id))
        if row is None:
            raise EntityNotFoundError(f"job version not found: {version_id}")
        version = load_payload(_JOB_VERSION, row.payload)
        if (
            str(version.version_id) != row.version_id
            or str(version.job_id) != row.job_id
            or version.version_number != row.version_number
            or str(version.source_snapshot_id) != row.source_snapshot_id
            or version.created_at.isoformat() != row.created_at
        ):
            raise _invalid_state()
        return version

    def get_snapshot(self, snapshot_id: SourceSnapshotId) -> SourceSnapshot:
        row = self._session.get(SourceSnapshotRow, str(snapshot_id))
        if row is None:
            raise EntityNotFoundError(f"source snapshot not found: {snapshot_id}")
        snapshot = load_payload(_SOURCE_SNAPSHOT, row.payload)
        if (
            str(snapshot.snapshot_id) != row.snapshot_id
            or snapshot.captured_at.isoformat() != row.captured_at
        ):
            raise _invalid_state()
        return snapshot

    def add_job(self, job: Job) -> None:
        self._session.add(
            JobRow(
                job_id=str(job.job_id),
                active_version_id=str(job.active_version_id),
                latest_quick_screen_result_id=(
                    str(job.latest_quick_screen_result_id)
                    if job.latest_quick_screen_result_id is not None
                    else None
                ),
                lifecycle_status=job.lifecycle_status.value,
                payload=dump_payload(_JOB, job),
                revision=1,
            )
        )
        self._add_missing_references(job, existing_ids=set())

    def save_job(self, job: Job) -> None:
        row = self._session.get(JobRow, str(job.job_id))
        if row is None:
            raise EntityNotFoundError(f"job not found: {job.job_id}")
        existing_ids = set(
            self._session.scalars(
                select(SourceReferenceRow.reference_id).where(
                    SourceReferenceRow.job_id == row.job_id
                )
            ).all()
        )
        row.active_version_id = str(job.active_version_id)
        row.latest_quick_screen_result_id = (
            str(job.latest_quick_screen_result_id)
            if job.latest_quick_screen_result_id is not None
            else None
        )
        row.lifecycle_status = job.lifecycle_status.value
        row.payload = dump_payload(_JOB, job)
        self._add_missing_references(job, existing_ids=existing_ids)

    def _add_missing_references(self, job: Job, *, existing_ids: set[str]) -> None:
        for ordinal, (version_id, reference) in enumerate(
            zip(job.version_ids, job.source_references, strict=True), start=1
        ):
            if str(reference.reference_id) in existing_ids:
                continue
            self._session.add(
                SourceReferenceRow(
                    reference_id=str(reference.reference_id),
                    job_id=str(job.job_id),
                    job_version_id=str(version_id),
                    snapshot_id=str(reference.snapshot_id),
                    ordinal=ordinal,
                    payload=dump_payload(_SOURCE_REFERENCE, reference),
                )
            )

    def add_version(self, version: JobVersion) -> None:
        self._session.add(
            JobVersionRow(
                version_id=str(version.version_id),
                job_id=str(version.job_id),
                version_number=version.version_number,
                source_snapshot_id=str(version.source_snapshot_id),
                created_at=version.created_at.isoformat(),
                payload=dump_payload(_JOB_VERSION, version),
            )
        )

    def add_snapshot(self, snapshot: SourceSnapshot) -> None:
        self._session.add(
            SourceSnapshotRow(
                snapshot_id=str(snapshot.snapshot_id),
                captured_at=snapshot.captured_at.isoformat(),
                payload=dump_payload(_SOURCE_SNAPSHOT, snapshot),
            )
        )


class SqlAlchemyCandidateKnowledgeRepository(CandidateKnowledgeRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_profiles(self) -> tuple[CandidateProfile, ...]:
        rows = self._session.scalars(
            select(CandidateProfileRow).order_by(CandidateProfileRow.sequence_id)
        ).all()
        return tuple(self._hydrate_profile(row) for row in rows)

    def _profile_state(self) -> CandidateProfileStateRow:
        state = self._session.get(CandidateProfileStateRow, 1)
        if state is None:
            raise _invalid_state()
        return state

    def get_active_profile_id(self) -> CandidateProfileId | None:
        value = self._profile_state().active_profile_id
        return CandidateProfileId(value) if value is not None else None

    def get_profile(self, profile_id: CandidateProfileId) -> CandidateProfile:
        row = self._session.scalars(
            select(CandidateProfileRow).where(CandidateProfileRow.profile_id == str(profile_id))
        ).one_or_none()
        if row is None:
            raise EntityNotFoundError(f"candidate profile not found: {profile_id}")
        return self._hydrate_profile(row)

    @staticmethod
    def _hydrate_profile(row: CandidateProfileRow) -> CandidateProfile:
        profile = load_payload(_PROFILE, row.payload)
        if (
            str(profile.profile_id) != row.profile_id
            or profile.created_at.isoformat() != row.created_at
        ):
            raise _invalid_state()
        return profile

    def get_active_profile(self) -> CandidateProfile:
        profile_id = self.get_active_profile_id()
        if profile_id is None:
            raise EntityNotFoundError("candidate profile not found")
        return self.get_profile(profile_id)

    def add_profile(self, profile: CandidateProfile) -> None:
        state = self._profile_state()
        self._session.add(
            CandidateProfileRow(
                profile_id=str(profile.profile_id),
                created_at=profile.created_at.isoformat(),
                payload=dump_payload(_PROFILE, profile),
            )
        )
        state.active_profile_id = str(profile.profile_id)

    def get_evidence(self, evidence_id: EvidenceItemId) -> EvidenceItem:
        row = self._session.scalars(
            select(EvidenceItemRow).where(EvidenceItemRow.evidence_id == str(evidence_id))
        ).one_or_none()
        if row is None:
            raise EntityNotFoundError(f"evidence not found: {evidence_id}")
        return self._hydrate_evidence(row)

    def list_evidence(self) -> tuple[EvidenceItem, ...]:
        rows = self._session.scalars(
            select(EvidenceItemRow).order_by(EvidenceItemRow.sequence_id)
        ).all()
        return tuple(self._hydrate_evidence(row) for row in rows)

    def _hydrate_evidence(self, row: EvidenceItemRow) -> EvidenceItem:
        item = load_payload(_EVIDENCE_ITEM, row.payload)
        version_ids = tuple(
            self._session.scalars(
                select(EvidenceVersionRow.version_id)
                .where(EvidenceVersionRow.evidence_id == row.evidence_id)
                .order_by(EvidenceVersionRow.version_number)
            ).all()
        )
        if (
            str(item.evidence_id) != row.evidence_id
            or str(item.active_version_id) != row.active_version_id
            or tuple(str(value) for value in item.version_ids) != version_ids
        ):
            raise _invalid_state()
        return item

    def get_evidence_version(self, version_id: EvidenceVersionId) -> EvidenceItemVersion:
        row = self._session.get(EvidenceVersionRow, str(version_id))
        if row is None:
            raise EntityNotFoundError(f"evidence version not found: {version_id}")
        version = load_payload(_EVIDENCE_VERSION, row.payload)
        if (
            str(version.version_id) != row.version_id
            or str(version.evidence_id) != row.evidence_id
            or version.version_number != row.version_number
            or version.created_at.isoformat() != row.created_at
        ):
            raise _invalid_state()
        return version

    def add_evidence(self, evidence: EvidenceItem) -> None:
        self._session.add(
            EvidenceItemRow(
                evidence_id=str(evidence.evidence_id),
                active_version_id=str(evidence.active_version_id),
                payload=dump_payload(_EVIDENCE_ITEM, evidence),
                revision=1,
            )
        )

    def save_evidence(self, evidence: EvidenceItem) -> None:
        row = self._session.scalars(
            select(EvidenceItemRow).where(EvidenceItemRow.evidence_id == str(evidence.evidence_id))
        ).one_or_none()
        if row is None:
            raise EntityNotFoundError(f"evidence not found: {evidence.evidence_id}")
        row.active_version_id = str(evidence.active_version_id)
        row.payload = dump_payload(_EVIDENCE_ITEM, evidence)

    def add_evidence_version(self, version: EvidenceItemVersion) -> None:
        self._session.add(
            EvidenceVersionRow(
                version_id=str(version.version_id),
                evidence_id=str(version.evidence_id),
                version_number=version.version_number,
                created_at=version.created_at.isoformat(),
                payload=dump_payload(_EVIDENCE_VERSION, version),
            )
        )


class SqlAlchemyScreeningRepository(ScreeningRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_requirement(self, requirement_id: RequirementId) -> ParsedRequirement:
        row = self._session.get(ParsedRequirementRow, str(requirement_id))
        if row is None:
            raise EntityNotFoundError(f"requirement not found: {requirement_id}")
        return self._hydrate_requirement(row)

    def list_requirements(self, job_version_id: JobVersionId) -> tuple[ParsedRequirement, ...]:
        rows = self._session.scalars(
            select(ParsedRequirementRow)
            .where(ParsedRequirementRow.job_version_id == str(job_version_id))
            .order_by(ParsedRequirementRow.ordinal)
        ).all()
        return tuple(self._hydrate_requirement(row) for row in rows)

    @staticmethod
    def _hydrate_requirement(row: ParsedRequirementRow) -> ParsedRequirement:
        requirement = load_payload(_REQUIREMENT, row.payload)
        if (
            str(requirement.requirement_id) != row.requirement_id
            or str(requirement.job_version_id) != row.job_version_id
            or requirement.created_at.isoformat() != row.created_at
        ):
            raise _invalid_state()
        return requirement

    def add_requirements(self, requirements: tuple[ParsedRequirement, ...]) -> None:
        if requirements and any(
            item.job_version_id != requirements[0].job_version_id for item in requirements
        ):
            raise ConflictError("requirements must belong to one JobVersion")
        for ordinal, requirement in enumerate(requirements, start=1):
            self._session.add(
                ParsedRequirementRow(
                    requirement_id=str(requirement.requirement_id),
                    job_version_id=str(requirement.job_version_id),
                    ordinal=ordinal,
                    created_at=requirement.created_at.isoformat(),
                    payload=dump_payload(_REQUIREMENT, requirement),
                )
            )

    def get_quick_screen_result(self, result_id: QuickScreenResultId) -> QuickScreenResult:
        row = self._session.scalars(
            select(QuickScreenResultRow).where(QuickScreenResultRow.result_id == str(result_id))
        ).one_or_none()
        if row is None:
            raise EntityNotFoundError(f"quick screen result not found: {result_id}")
        return self._hydrate_screen_result(row)

    def get_latest_quick_screen_result(self, job_id: JobId) -> QuickScreenResult:
        job_row = self._session.get(JobRow, str(job_id))
        if job_row is None or job_row.latest_quick_screen_result_id is None:
            raise EntityNotFoundError(f"quick screen result not found for job: {job_id}")
        row = self._session.scalars(
            select(QuickScreenResultRow).where(
                QuickScreenResultRow.result_id == job_row.latest_quick_screen_result_id
            )
        ).one_or_none()
        if row is None or row.job_id != job_row.job_id:
            raise _invalid_state()
        return self._hydrate_screen_result(row)

    def list_quick_screen_results(self, job_id: JobId) -> tuple[QuickScreenResult, ...]:
        rows = self._session.scalars(
            select(QuickScreenResultRow)
            .where(QuickScreenResultRow.job_id == str(job_id))
            .order_by(QuickScreenResultRow.sequence_id)
        ).all()
        return tuple(self._hydrate_screen_result(row) for row in rows)

    def _hydrate_screen_result(self, row: QuickScreenResultRow) -> QuickScreenResult:
        result = load_payload(_SCREEN_RESULT, row.payload)
        version_row = self._session.get(JobVersionRow, row.job_version_id)
        requirement_rows = self._session.scalars(
            select(QuickScreenRequirementRow)
            .where(QuickScreenRequirementRow.quick_screen_result_id == row.result_id)
            .order_by(QuickScreenRequirementRow.ordinal)
        ).all()
        if (
            str(result.result_id) != row.result_id
            or str(result.job_id) != row.job_id
            or str(result.job_version_id) != row.job_version_id
            or str(result.candidate_profile_id) != row.candidate_profile_id
            or result.created_at.isoformat() != row.created_at
            or version_row is None
            or version_row.job_id != row.job_id
            or tuple(item.requirement_id for item in requirement_rows)
            != tuple(str(item) for item in result.requirement_ids)
            or any(item.job_version_id != row.job_version_id for item in requirement_rows)
        ):
            raise _invalid_state()
        for association in requirement_rows:
            requirement = self._session.get(ParsedRequirementRow, association.requirement_id)
            if requirement is None or requirement.job_version_id != row.job_version_id:
                raise _invalid_state()
        return result

    def add_quick_screen_result(self, result: QuickScreenResult) -> None:
        self._session.add(
            QuickScreenResultRow(
                result_id=str(result.result_id),
                job_id=str(result.job_id),
                job_version_id=str(result.job_version_id),
                candidate_profile_id=str(result.candidate_profile_id),
                created_at=result.created_at.isoformat(),
                payload=dump_payload(_SCREEN_RESULT, result),
            )
        )
        for ordinal, requirement_id in enumerate(result.requirement_ids, start=1):
            self._session.add(
                QuickScreenRequirementRow(
                    quick_screen_result_id=str(result.result_id),
                    job_version_id=str(result.job_version_id),
                    requirement_id=str(requirement_id),
                    ordinal=ordinal,
                )
            )

    def add_triage_record(self, record: JobTriageRecord) -> None:
        self._session.add(
            JobTriageRecordRow(
                decision_id=str(record.decision_id),
                job_id=str(record.job_id),
                quick_screen_result_id=str(record.quick_screen_result_id),
                decided_at=record.decided_at.isoformat(),
                payload=dump_payload(_TRIAGE, record),
            )
        )

    def list_triage_records(self, job_id: JobId) -> tuple[JobTriageRecord, ...]:
        rows = self._session.scalars(
            select(JobTriageRecordRow)
            .where(JobTriageRecordRow.job_id == str(job_id))
            .order_by(JobTriageRecordRow.sequence_id)
        ).all()
        return tuple(self._hydrate_triage_record(row) for row in rows)

    def _hydrate_triage_record(self, row: JobTriageRecordRow) -> JobTriageRecord:
        record = load_payload(_TRIAGE, row.payload)
        screen = self._session.scalars(
            select(QuickScreenResultRow).where(
                QuickScreenResultRow.result_id == row.quick_screen_result_id
            )
        ).one_or_none()
        if (
            str(record.decision_id) != row.decision_id
            or str(record.job_id) != row.job_id
            or str(record.quick_screen_result_id) != row.quick_screen_result_id
            or record.decided_at.isoformat() != row.decided_at
            or screen is None
            or screen.job_id != row.job_id
        ):
            raise _invalid_state()
        return record


class SqlAlchemyRetrievalRepository(RetrievalRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_run(self, retrieval_run_id: RetrievalRunId) -> RetrievalRun:
        row = self._session.scalars(
            select(RetrievalRunRow).where(RetrievalRunRow.retrieval_run_id == str(retrieval_run_id))
        ).one_or_none()
        if row is None:
            raise EntityNotFoundError(f"retrieval run not found: {retrieval_run_id}")
        return self._hydrate_run(row)

    def list_runs(self, requirement_id: RequirementId) -> tuple[RetrievalRun, ...]:
        rows = self._session.scalars(
            select(RetrievalRunRow)
            .where(RetrievalRunRow.requirement_id == str(requirement_id))
            .order_by(RetrievalRunRow.sequence_id)
        ).all()
        return tuple(self._hydrate_run(row) for row in rows)

    def _hydrate_run(self, row: RetrievalRunRow) -> RetrievalRun:
        run = load_payload(_RETRIEVAL_RUN, row.payload)
        requirement = self._session.get(ParsedRequirementRow, row.requirement_id)
        hit_rows = self._session.scalars(
            select(RetrievalRunHitRow)
            .where(RetrievalRunHitRow.retrieval_run_id == row.retrieval_run_id)
            .order_by(RetrievalRunHitRow.ordinal)
        ).all()
        exclusion_rows = self._session.scalars(
            select(RetrievalRunExclusionRow)
            .where(RetrievalRunExclusionRow.retrieval_run_id == row.retrieval_run_id)
            .order_by(RetrievalRunExclusionRow.ordinal)
        ).all()
        if (
            str(run.retrieval_run_id) != row.retrieval_run_id
            or str(run.requirement_id) != row.requirement_id
            or str(run.job_version_id) != row.job_version_id
            or run.created_at.isoformat() != row.created_at
            or requirement is None
            or requirement.job_version_id != row.job_version_id
            or tuple((item.evidence_id, item.evidence_version_id) for item in hit_rows)
            != tuple((str(item.evidence_id), str(item.evidence_version_id)) for item in run.hits)
            or tuple((item.evidence_id, item.evidence_version_id) for item in exclusion_rows)
            != tuple(
                (str(item.evidence_id), str(item.evidence_version_id)) for item in run.exclusions
            )
        ):
            raise _invalid_state()
        for association in (*hit_rows, *exclusion_rows):
            version = self._session.get(EvidenceVersionRow, association.evidence_version_id)
            if version is None or version.evidence_id != association.evidence_id:
                raise _invalid_state()
        return run

    def add_run(self, run: RetrievalRun) -> None:
        self._session.add(
            RetrievalRunRow(
                retrieval_run_id=str(run.retrieval_run_id),
                requirement_id=str(run.requirement_id),
                job_version_id=str(run.job_version_id),
                created_at=run.created_at.isoformat(),
                payload=dump_payload(_RETRIEVAL_RUN, run),
            )
        )
        for ordinal, hit in enumerate(run.hits, start=1):
            self._session.add(
                RetrievalRunHitRow(
                    retrieval_run_id=str(run.retrieval_run_id),
                    evidence_id=str(hit.evidence_id),
                    evidence_version_id=str(hit.evidence_version_id),
                    ordinal=ordinal,
                )
            )
        for ordinal, exclusion in enumerate(run.exclusions, start=1):
            self._session.add(
                RetrievalRunExclusionRow(
                    retrieval_run_id=str(run.retrieval_run_id),
                    evidence_id=str(exclusion.evidence_id),
                    evidence_version_id=str(exclusion.evidence_version_id),
                    ordinal=ordinal,
                )
            )
