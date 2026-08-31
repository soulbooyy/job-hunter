"""Create the authoritative current Workspace schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_current_workspace"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("job_id", sa.Text(), primary_key=True),
        sa.Column("active_version_id", sa.Text(), nullable=False),
        sa.Column("lifecycle_status", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "source_snapshots",
        sa.Column("snapshot_id", sa.Text(), primary_key=True),
        sa.Column("captured_at", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index("ix_source_snapshots_captured_at", "source_snapshots", ["captured_at"])
    op.create_table(
        "job_versions",
        sa.Column("version_id", sa.Text(), primary_key=True),
        sa.Column("job_id", sa.Text(), sa.ForeignKey("jobs.job_id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "source_snapshot_id",
            sa.Text(),
            sa.ForeignKey("source_snapshots.snapshot_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.UniqueConstraint("job_id", "version_number"),
    )
    op.create_index("ix_job_versions_job_id", "job_versions", ["job_id"])
    op.create_table(
        "source_references",
        sa.Column("reference_id", sa.Text(), primary_key=True),
        sa.Column("job_id", sa.Text(), sa.ForeignKey("jobs.job_id"), nullable=False),
        sa.Column(
            "job_version_id", sa.Text(), sa.ForeignKey("job_versions.version_id"), nullable=False
        ),
        sa.Column(
            "snapshot_id", sa.Text(), sa.ForeignKey("source_snapshots.snapshot_id"), nullable=False
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.UniqueConstraint("job_id", "ordinal"),
        sa.UniqueConstraint("job_id", "job_version_id"),
    )
    op.create_index("ix_source_references_job_id", "source_references", ["job_id"])
    op.create_table(
        "candidate_profiles",
        sa.Column("sequence_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index("ix_candidate_profiles_created_at", "candidate_profiles", ["created_at"])
    op.create_table(
        "candidate_profile_state",
        sa.Column("state_id", sa.Integer(), primary_key=True),
        sa.Column(
            "active_profile_id",
            sa.Text(),
            sa.ForeignKey("candidate_profiles.profile_id"),
            nullable=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.bulk_insert(
        sa.table(
            "candidate_profile_state",
            sa.column("state_id", sa.Integer()),
            sa.column("active_profile_id", sa.Text()),
            sa.column("revision", sa.Integer()),
        ),
        [{"state_id": 1, "active_profile_id": None, "revision": 1}],
    )
    op.create_table(
        "evidence_items",
        sa.Column("sequence_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("evidence_id", sa.Text(), nullable=False, unique=True),
        sa.Column("active_version_id", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "evidence_versions",
        sa.Column("version_id", sa.Text(), primary_key=True),
        sa.Column(
            "evidence_id", sa.Text(), sa.ForeignKey("evidence_items.evidence_id"), nullable=False
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.UniqueConstraint("evidence_id", "version_number"),
    )
    op.create_index("ix_evidence_versions_evidence_id", "evidence_versions", ["evidence_id"])
    op.create_table(
        "parsed_requirements",
        sa.Column("requirement_id", sa.Text(), primary_key=True),
        sa.Column(
            "job_version_id", sa.Text(), sa.ForeignKey("job_versions.version_id"), nullable=False
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.UniqueConstraint("job_version_id", "ordinal"),
    )
    op.create_index(
        "ix_parsed_requirements_job_version_id", "parsed_requirements", ["job_version_id"]
    )
    op.create_table(
        "quick_screen_results",
        sa.Column("sequence_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("result_id", sa.Text(), nullable=False, unique=True),
        sa.Column("job_id", sa.Text(), sa.ForeignKey("jobs.job_id"), nullable=False),
        sa.Column(
            "job_version_id", sa.Text(), sa.ForeignKey("job_versions.version_id"), nullable=False
        ),
        sa.Column(
            "candidate_profile_id",
            sa.Text(),
            sa.ForeignKey("candidate_profiles.profile_id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index("ix_quick_screen_results_job_id", "quick_screen_results", ["job_id"])
    op.create_table(
        "job_triage_records",
        sa.Column("sequence_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_id", sa.Text(), nullable=False, unique=True),
        sa.Column("job_id", sa.Text(), sa.ForeignKey("jobs.job_id"), nullable=False),
        sa.Column(
            "quick_screen_result_id",
            sa.Text(),
            sa.ForeignKey("quick_screen_results.result_id"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index("ix_job_triage_records_job_id", "job_triage_records", ["job_id"])
    op.create_table(
        "retrieval_runs",
        sa.Column("sequence_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("retrieval_run_id", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "requirement_id",
            sa.Text(),
            sa.ForeignKey("parsed_requirements.requirement_id"),
            nullable=False,
        ),
        sa.Column(
            "job_version_id", sa.Text(), sa.ForeignKey("job_versions.version_id"), nullable=False
        ),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index("ix_retrieval_runs_requirement_id", "retrieval_runs", ["requirement_id"])


def downgrade() -> None:
    for table_name in (
        "retrieval_runs",
        "job_triage_records",
        "quick_screen_results",
        "parsed_requirements",
        "evidence_versions",
        "evidence_items",
        "candidate_profile_state",
        "candidate_profiles",
        "source_references",
        "job_versions",
        "source_snapshots",
        "jobs",
    ):
        op.drop_table(table_name)
