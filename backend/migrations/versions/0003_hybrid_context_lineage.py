"""Persist policy-driven retrieval and immutable ContextPackage lineage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_hybrid_context_lineage"
down_revision: str | None = "0002_persistence_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "retrieval_runs",
        sa.Column("strategy", sa.Text(), nullable=False, server_default="legacy"),
    )
    for name in (
        "policy_version",
        "initial_strategy",
        "decision_reason",
        "fallback_reason",
        "promotion_dataset_version",
        "index_version",
        "embedding_provider_version",
        "chunk_policy_version",
    ):
        op.add_column("retrieval_runs", sa.Column(name, sa.Text(), nullable=True))
    op.add_column(
        "retrieval_runs",
        sa.Column("semantic_ready", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "retrieval_runs",
        sa.Column("query_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.execute(sa.text("UPDATE retrieval_runs SET strategy = json_extract(payload, '$.strategy')"))

    op.create_table(
        "context_packages",
        sa.Column("sequence_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("context_package_id", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "job_version_id",
            sa.Text(),
            sa.ForeignKey("job_versions.version_id"),
            nullable=False,
        ),
        sa.Column(
            "retrieval_run_id",
            sa.Text(),
            sa.ForeignKey("retrieval_runs.retrieval_run_id"),
            nullable=False,
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
    op.create_index(
        "ix_context_packages_retrieval_run_id",
        "context_packages",
        ["retrieval_run_id"],
    )
    op.create_index(
        "ux_context_packages_package_version",
        "context_packages",
        ["context_package_id", "job_version_id"],
        unique=True,
    )
    op.create_table(
        "context_package_entries",
        sa.Column("association_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "context_package_id",
            sa.Text(),
            sa.ForeignKey("context_packages.context_package_id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("estimated_tokens", sa.Integer(), nullable=False),
        sa.Column("protected", sa.Integer(), nullable=False),
        sa.Column("redaction", sa.Text(), nullable=False),
        sa.Column("inclusion_reason", sa.Text(), nullable=False),
        sa.Column("requirement_id", sa.Text(), nullable=True),
        sa.Column("evidence_id", sa.Text(), nullable=True),
        sa.Column("evidence_version_id", sa.Text(), nullable=True),
        sa.Column("evidence_chunk_id", sa.Text(), nullable=True),
        sa.UniqueConstraint("context_package_id", "ordinal"),
    )
    op.create_index(
        "ix_context_package_entries_context_package_id",
        "context_package_entries",
        ["context_package_id"],
    )
    op.create_index(
        "ux_context_packages_package_retrieval",
        "context_packages",
        ["context_package_id", "retrieval_run_id"],
        unique=True,
    )
    op.create_table(
        "retrieval_run_hit_chunks",
        sa.Column("association_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("retrieval_run_id", sa.Text(), nullable=False),
        sa.Column("evidence_version_id", sa.Text(), nullable=False),
        sa.Column("evidence_chunk_id", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["retrieval_run_id", "evidence_version_id"],
            ["retrieval_run_hits.retrieval_run_id", "retrieval_run_hits.evidence_version_id"],
        ),
        sa.UniqueConstraint("retrieval_run_id", "evidence_chunk_id"),
        sa.UniqueConstraint("retrieval_run_id", "ordinal"),
    )
    op.create_index(
        "ix_retrieval_run_hit_chunks_retrieval_run_id",
        "retrieval_run_hit_chunks",
        ["retrieval_run_id"],
    )
    op.create_table(
        "context_package_requirements",
        sa.Column("association_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("context_package_id", sa.Text(), nullable=False),
        sa.Column("job_version_id", sa.Text(), nullable=False),
        sa.Column("requirement_id", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["context_package_id", "job_version_id"],
            ["context_packages.context_package_id", "context_packages.job_version_id"],
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id", "job_version_id"],
            ["parsed_requirements.requirement_id", "parsed_requirements.job_version_id"],
        ),
        sa.UniqueConstraint("context_package_id", "ordinal"),
        sa.UniqueConstraint("context_package_id", "requirement_id"),
    )
    op.create_index(
        "ix_context_package_requirements_context_package_id",
        "context_package_requirements",
        ["context_package_id"],
    )
    op.create_table(
        "context_package_evidence",
        sa.Column("association_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("context_package_id", sa.Text(), nullable=False),
        sa.Column("retrieval_run_id", sa.Text(), nullable=False),
        sa.Column("requirement_id", sa.Text(), nullable=False),
        sa.Column("evidence_id", sa.Text(), nullable=False),
        sa.Column("evidence_version_id", sa.Text(), nullable=False),
        sa.Column("evidence_chunk_id", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["context_package_id", "retrieval_run_id"],
            ["context_packages.context_package_id", "context_packages.retrieval_run_id"],
        ),
        sa.ForeignKeyConstraint(
            ["context_package_id", "requirement_id"],
            [
                "context_package_requirements.context_package_id",
                "context_package_requirements.requirement_id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_run_id", "evidence_version_id"],
            ["retrieval_run_hits.retrieval_run_id", "retrieval_run_hits.evidence_version_id"],
        ),
        sa.ForeignKeyConstraint(
            ["evidence_version_id", "evidence_id"],
            ["evidence_versions.version_id", "evidence_versions.evidence_id"],
        ),
        sa.UniqueConstraint("context_package_id", "ordinal"),
        sa.UniqueConstraint("context_package_id", "evidence_chunk_id"),
    )
    op.create_index(
        "ix_context_package_evidence_context_package_id",
        "context_package_evidence",
        ["context_package_id"],
    )
    op.create_table(
        "context_package_exclusions",
        sa.Column("association_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("context_package_id", sa.Text(), nullable=False),
        sa.Column("retrieval_run_id", sa.Text(), nullable=False),
        sa.Column("requirement_id", sa.Text(), nullable=False),
        sa.Column("evidence_id", sa.Text(), nullable=False),
        sa.Column("evidence_version_id", sa.Text(), nullable=False),
        sa.Column("evidence_chunk_id", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["context_package_id", "retrieval_run_id"],
            ["context_packages.context_package_id", "context_packages.retrieval_run_id"],
        ),
        sa.ForeignKeyConstraint(
            ["context_package_id", "requirement_id"],
            [
                "context_package_requirements.context_package_id",
                "context_package_requirements.requirement_id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_run_id", "evidence_version_id"],
            ["retrieval_run_hits.retrieval_run_id", "retrieval_run_hits.evidence_version_id"],
        ),
        sa.ForeignKeyConstraint(
            ["evidence_version_id", "evidence_id"],
            ["evidence_versions.version_id", "evidence_versions.evidence_id"],
        ),
        sa.UniqueConstraint("context_package_id", "ordinal"),
        sa.UniqueConstraint("context_package_id", "evidence_chunk_id"),
    )
    op.create_index(
        "ix_context_package_exclusions_context_package_id",
        "context_package_exclusions",
        ["context_package_id"],
    )


def downgrade() -> None:
    op.drop_table("context_package_exclusions")
    op.drop_table("context_package_evidence")
    op.drop_table("context_package_requirements")
    op.drop_table("context_package_entries")
    op.drop_table("retrieval_run_hit_chunks")
    op.drop_index("ux_context_packages_package_retrieval", table_name="context_packages")
    op.drop_index("ux_context_packages_package_version", table_name="context_packages")
    op.drop_index("ix_context_packages_retrieval_run_id", table_name="context_packages")
    op.drop_table("context_packages")
    for name in (
        "query_count",
        "semantic_ready",
        "chunk_policy_version",
        "embedding_provider_version",
        "index_version",
        "promotion_dataset_version",
        "fallback_reason",
        "decision_reason",
        "initial_strategy",
        "policy_version",
        "strategy",
    ):
        op.drop_column("retrieval_runs", name)
