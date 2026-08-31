"""Infrastructure-only SQLAlchemy rows for the current authoritative graph."""

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# Payloads preserve complete typed immutable values; explicit columns carry the
# database-owned identity, ownership, ordering, and revision constraints. Repository
# hydration must cross-check both representations before returning Domain State.
class JobRow(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(Text, primary_key=True)
    active_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    latest_quick_screen_result_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": revision}


class SourceSnapshotRow(Base):
    __tablename__ = "source_snapshots"

    snapshot_id: Mapped[str] = mapped_column(Text, primary_key=True)
    captured_at: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class JobVersionRow(Base):
    __tablename__ = "job_versions"
    __table_args__ = (
        UniqueConstraint("job_id", "version_number"),
        Index("ux_job_versions_version_job", "version_id", "job_id", unique=True),
    )

    version_id: Mapped[str] = mapped_column(Text, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("source_snapshots.snapshot_id"), nullable=False, unique=True
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class SourceReferenceRow(Base):
    __tablename__ = "source_references"
    __table_args__ = (
        UniqueConstraint("job_id", "ordinal"),
        UniqueConstraint("job_id", "job_version_id"),
    )

    reference_id: Mapped[str] = mapped_column(Text, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"), nullable=False, index=True)
    job_version_id: Mapped[str] = mapped_column(
        ForeignKey("job_versions.version_id"), nullable=False
    )
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("source_snapshots.snapshot_id"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class CandidateProfileRow(Base):
    __tablename__ = "candidate_profiles"

    # UUIDs and deterministic clocks are not a safe proxy for write order.
    sequence_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class CandidateProfileStateRow(Base):
    __tablename__ = "candidate_profile_state"

    state_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidate_profiles.profile_id"), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": revision}


class EvidenceItemRow(Base):
    __tablename__ = "evidence_items"

    sequence_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evidence_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    active_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": revision}


class EvidenceVersionRow(Base):
    __tablename__ = "evidence_versions"
    __table_args__ = (
        UniqueConstraint("evidence_id", "version_number"),
        Index("ux_evidence_versions_version_evidence", "version_id", "evidence_id", unique=True),
    )

    version_id: Mapped[str] = mapped_column(Text, primary_key=True)
    evidence_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_items.evidence_id"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class ParsedRequirementRow(Base):
    __tablename__ = "parsed_requirements"
    __table_args__ = (
        UniqueConstraint("job_version_id", "ordinal"),
        Index(
            "ux_parsed_requirements_requirement_version",
            "requirement_id",
            "job_version_id",
            unique=True,
        ),
    )

    requirement_id: Mapped[str] = mapped_column(Text, primary_key=True)
    job_version_id: Mapped[str] = mapped_column(
        ForeignKey("job_versions.version_id"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class QuickScreenResultRow(Base):
    __tablename__ = "quick_screen_results"
    __table_args__ = (
        Index("ux_quick_screen_result_job", "result_id", "job_id", unique=True),
        Index("ux_quick_screen_result_version", "result_id", "job_version_id", unique=True),
    )

    sequence_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    result_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"), nullable=False, index=True)
    job_version_id: Mapped[str] = mapped_column(
        ForeignKey("job_versions.version_id"), nullable=False
    )
    candidate_profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.profile_id"), nullable=False
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class JobTriageRecordRow(Base):
    __tablename__ = "job_triage_records"

    sequence_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"), nullable=False, index=True)
    quick_screen_result_id: Mapped[str] = mapped_column(
        ForeignKey("quick_screen_results.result_id"), nullable=False
    )
    decided_at: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class RetrievalRunRow(Base):
    __tablename__ = "retrieval_runs"

    sequence_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    retrieval_run_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    requirement_id: Mapped[str] = mapped_column(
        ForeignKey("parsed_requirements.requirement_id"), nullable=False, index=True
    )
    job_version_id: Mapped[str] = mapped_column(
        ForeignKey("job_versions.version_id"), nullable=False
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class QuickScreenRequirementRow(Base):
    __tablename__ = "quick_screen_requirements"
    __table_args__ = (
        UniqueConstraint("quick_screen_result_id", "ordinal"),
        UniqueConstraint("quick_screen_result_id", "requirement_id"),
        ForeignKeyConstraint(
            ("quick_screen_result_id", "job_version_id"),
            ("quick_screen_results.result_id", "quick_screen_results.job_version_id"),
        ),
        ForeignKeyConstraint(
            ("requirement_id", "job_version_id"),
            ("parsed_requirements.requirement_id", "parsed_requirements.job_version_id"),
        ),
    )

    association_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quick_screen_result_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    job_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_id: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class RetrievalRunHitRow(Base):
    __tablename__ = "retrieval_run_hits"
    __table_args__ = (
        UniqueConstraint("retrieval_run_id", "ordinal"),
        UniqueConstraint("retrieval_run_id", "evidence_version_id"),
        ForeignKeyConstraint(
            ("evidence_version_id", "evidence_id"),
            ("evidence_versions.version_id", "evidence_versions.evidence_id"),
        ),
    )

    association_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    retrieval_run_id: Mapped[str] = mapped_column(
        ForeignKey("retrieval_runs.retrieval_run_id"), nullable=False, index=True
    )
    evidence_id: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class RetrievalRunExclusionRow(Base):
    __tablename__ = "retrieval_run_exclusions"
    __table_args__ = (
        UniqueConstraint("retrieval_run_id", "ordinal"),
        UniqueConstraint("retrieval_run_id", "evidence_version_id"),
        ForeignKeyConstraint(
            ("evidence_version_id", "evidence_id"),
            ("evidence_versions.version_id", "evidence_versions.evidence_id"),
        ),
    )

    association_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    retrieval_run_id: Mapped[str] = mapped_column(
        ForeignKey("retrieval_runs.retrieval_run_id"), nullable=False, index=True
    )
    evidence_id: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
