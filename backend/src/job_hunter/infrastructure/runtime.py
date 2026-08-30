"""Local runtime implementations of deterministic control-plane ports."""

from datetime import UTC, datetime
from uuid import uuid4

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


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class UuidIdGenerator:
    def new_job_id(self) -> JobId:
        return JobId(f"job-{uuid4().hex}")

    def new_job_version_id(self) -> JobVersionId:
        return JobVersionId(f"job-version-{uuid4().hex}")

    def new_source_snapshot_id(self) -> SourceSnapshotId:
        return SourceSnapshotId(f"source-snapshot-{uuid4().hex}")

    def new_source_reference_id(self) -> SourceReferenceId:
        return SourceReferenceId(f"source-reference-{uuid4().hex}")

    def new_candidate_profile_id(self) -> CandidateProfileId:
        return CandidateProfileId(f"candidate-profile-{uuid4().hex}")

    def new_evidence_item_id(self) -> EvidenceItemId:
        return EvidenceItemId(f"evidence-{uuid4().hex}")

    def new_evidence_version_id(self) -> EvidenceVersionId:
        return EvidenceVersionId(f"evidence-version-{uuid4().hex}")

    def new_requirement_id(self) -> RequirementId:
        return RequirementId(f"requirement-{uuid4().hex}")

    def new_quick_screen_result_id(self) -> QuickScreenResultId:
        return QuickScreenResultId(f"quick-screen-{uuid4().hex}")

    def new_triage_decision_id(self) -> TriageDecisionId:
        return TriageDecisionId(f"triage-{uuid4().hex}")

    def new_retrieval_run_id(self) -> RetrievalRunId:
        return RetrievalRunId(f"retrieval-run-{uuid4().hex}")
