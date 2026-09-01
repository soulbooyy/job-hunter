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
    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    initial_strategy: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    promotion_dataset_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    semantic_ready: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    index_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_provider_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_policy_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class ContextPackageRow(Base):
    __tablename__ = "context_packages"
    __table_args__ = (
        Index(
            "ux_context_packages_package_version",
            "context_package_id",
            "job_version_id",
            unique=True,
        ),
        Index(
            "ux_context_packages_package_retrieval",
            "context_package_id",
            "retrieval_run_id",
            unique=True,
        ),
    )

    sequence_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    context_package_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    job_version_id: Mapped[str] = mapped_column(
        ForeignKey("job_versions.version_id"), nullable=False
    )
    retrieval_run_id: Mapped[str] = mapped_column(
        ForeignKey("retrieval_runs.retrieval_run_id"), nullable=False, index=True
    )
    candidate_profile_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.profile_id"), nullable=False
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class ContextPackageEntryRow(Base):
    __tablename__ = "context_package_entries"
    __table_args__ = (UniqueConstraint("context_package_id", "ordinal"),)

    association_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    context_package_id: Mapped[str] = mapped_column(
        ForeignKey("context_packages.context_package_id"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    protected: Mapped[int] = mapped_column(Integer, nullable=False)
    redaction: Mapped[str] = mapped_column(Text, nullable=False)
    inclusion_reason: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_version_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_chunk_id: Mapped[str | None] = mapped_column(Text, nullable=True)


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


class RetrievalRunHitChunkRow(Base):
    __tablename__ = "retrieval_run_hit_chunks"
    __table_args__ = (
        UniqueConstraint("retrieval_run_id", "evidence_chunk_id"),
        UniqueConstraint("retrieval_run_id", "ordinal"),
        ForeignKeyConstraint(
            ("retrieval_run_id", "evidence_version_id"),
            ("retrieval_run_hits.retrieval_run_id", "retrieval_run_hits.evidence_version_id"),
        ),
    )

    association_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    retrieval_run_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    evidence_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_chunk_id: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class ContextPackageRequirementRow(Base):
    __tablename__ = "context_package_requirements"
    __table_args__ = (
        UniqueConstraint("context_package_id", "ordinal"),
        UniqueConstraint("context_package_id", "requirement_id"),
        ForeignKeyConstraint(
            ("context_package_id", "job_version_id"),
            ("context_packages.context_package_id", "context_packages.job_version_id"),
        ),
        ForeignKeyConstraint(
            ("requirement_id", "job_version_id"),
            ("parsed_requirements.requirement_id", "parsed_requirements.job_version_id"),
        ),
    )

    association_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    context_package_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    job_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_id: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class ContextPackageEvidenceRow(Base):
    __tablename__ = "context_package_evidence"
    __table_args__ = (
        UniqueConstraint("context_package_id", "ordinal"),
        UniqueConstraint("context_package_id", "evidence_chunk_id"),
        ForeignKeyConstraint(
            ("context_package_id", "retrieval_run_id"),
            ("context_packages.context_package_id", "context_packages.retrieval_run_id"),
        ),
        ForeignKeyConstraint(
            ("context_package_id", "requirement_id"),
            (
                "context_package_requirements.context_package_id",
                "context_package_requirements.requirement_id",
            ),
        ),
        ForeignKeyConstraint(
            ("retrieval_run_id", "evidence_version_id"),
            ("retrieval_run_hits.retrieval_run_id", "retrieval_run_hits.evidence_version_id"),
        ),
        ForeignKeyConstraint(
            ("evidence_version_id", "evidence_id"),
            ("evidence_versions.version_id", "evidence_versions.evidence_id"),
        ),
    )

    association_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    context_package_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    retrieval_run_id: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_id: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_id: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_chunk_id: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class ContextPackageExclusionRow(Base):
    __tablename__ = "context_package_exclusions"
    __table_args__ = (
        UniqueConstraint("context_package_id", "ordinal"),
        UniqueConstraint("context_package_id", "evidence_chunk_id"),
        ForeignKeyConstraint(
            ("context_package_id", "retrieval_run_id"),
            ("context_packages.context_package_id", "context_packages.retrieval_run_id"),
        ),
        ForeignKeyConstraint(
            ("context_package_id", "requirement_id"),
            (
                "context_package_requirements.context_package_id",
                "context_package_requirements.requirement_id",
            ),
        ),
        ForeignKeyConstraint(
            ("retrieval_run_id", "evidence_version_id"),
            ("retrieval_run_hits.retrieval_run_id", "retrieval_run_hits.evidence_version_id"),
        ),
        ForeignKeyConstraint(
            ("evidence_version_id", "evidence_id"),
            ("evidence_versions.version_id", "evidence_versions.evidence_id"),
        ),
    )

    association_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    context_package_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    retrieval_run_id: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_id: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_id: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_chunk_id: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class RuntimeContextRow(Base):
    __tablename__ = "runtime_contexts"
    __table_args__ = (
        Index(
            "ux_runtime_contexts_context_package",
            "runtime_context_id",
            "context_package_id",
            unique=True,
        ),
        ForeignKeyConstraint(
            ("context_package_id", "job_version_id"),
            ("context_packages.context_package_id", "context_packages.job_version_id"),
        ),
    )

    sequence_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    runtime_context_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    context_package_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    job_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class RuntimeContextEntryRow(Base):
    __tablename__ = "runtime_context_entries"
    __table_args__ = (UniqueConstraint("runtime_context_id", "ordinal"),)

    association_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    runtime_context_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_contexts.runtime_context_id"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_ordinals: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_context_references.reference_id"), nullable=True
    )
    estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    protected: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[str] = mapped_column(Text, nullable=False)
    retention_class: Mapped[str] = mapped_column(Text, nullable=False)


class RuntimeArtifactRow(Base):
    __tablename__ = "runtime_artifacts"

    artifact_id: Mapped[str] = mapped_column(Text, primary_key=True)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)


class RuntimeContextReferenceRow(Base):
    __tablename__ = "runtime_context_references"

    reference_id: Mapped[str] = mapped_column(Text, primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_artifacts.artifact_id"), nullable=False
    )
    context_package_id: Mapped[str] = mapped_column(
        ForeignKey("context_packages.context_package_id"), nullable=False
    )
    source_ordinals: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False)


class RuntimeContextDecisionRow(Base):
    __tablename__ = "runtime_context_decisions"
    __table_args__ = (UniqueConstraint("runtime_context_id", "ordinal"),)

    association_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    runtime_context_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_contexts.runtime_context_id"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    source_ordinals: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    retained_source_ordinals: Mapped[str] = mapped_column(Text, nullable=False)
