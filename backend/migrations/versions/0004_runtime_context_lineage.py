"""Persist immutable runtime-context and redacted artifact lineage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_runtime_context_lineage"
down_revision: str | None = "0003_hybrid_context_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_contexts",
        sa.Column("sequence_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("runtime_context_id", sa.Text(), nullable=False, unique=True),
        sa.Column("context_package_id", sa.Text(), nullable=False),
        sa.Column("job_version_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["context_package_id", "job_version_id"],
            ["context_packages.context_package_id", "context_packages.job_version_id"],
        ),
    )
    op.create_index(
        "ix_runtime_contexts_context_package_id",
        "runtime_contexts",
        ["context_package_id"],
    )
    op.create_index(
        "ux_runtime_contexts_context_package",
        "runtime_contexts",
        ["runtime_context_id", "context_package_id"],
        unique=True,
    )
    op.create_table(
        "runtime_artifacts",
        sa.Column("artifact_id", sa.Text(), primary_key=True),
        sa.Column("content_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("estimated_tokens", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
    )
    op.create_table(
        "runtime_context_references",
        sa.Column("reference_id", sa.Text(), primary_key=True),
        sa.Column(
            "artifact_id",
            sa.Text(),
            sa.ForeignKey("runtime_artifacts.artifact_id"),
            nullable=False,
        ),
        sa.Column(
            "context_package_id",
            sa.Text(),
            sa.ForeignKey("context_packages.context_package_id"),
            nullable=False,
        ),
        sa.Column("source_ordinals", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("source_estimated_tokens", sa.Integer(), nullable=False),
        sa.Column("reference_estimated_tokens", sa.Integer(), nullable=False),
    )
    op.create_table(
        "runtime_context_entries",
        sa.Column("association_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "runtime_context_id",
            sa.Text(),
            sa.ForeignKey("runtime_contexts.runtime_context_id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("source_ordinals", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "reference_id",
            sa.Text(),
            sa.ForeignKey("runtime_context_references.reference_id"),
            nullable=True,
        ),
        sa.Column("estimated_tokens", sa.Integer(), nullable=False),
        sa.Column("protected", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Text(), nullable=False),
        sa.Column("retention_class", sa.Text(), nullable=False),
        sa.UniqueConstraint("runtime_context_id", "ordinal"),
    )
    op.create_index(
        "ix_runtime_context_entries_runtime_context_id",
        "runtime_context_entries",
        ["runtime_context_id"],
    )
    op.create_table(
        "runtime_context_decisions",
        sa.Column("association_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "runtime_context_id",
            sa.Text(),
            sa.ForeignKey("runtime_contexts.runtime_context_id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("source_ordinals", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("retained_source_ordinals", sa.Text(), nullable=False),
        sa.UniqueConstraint("runtime_context_id", "ordinal"),
    )
    op.create_index(
        "ix_runtime_context_decisions_runtime_context_id",
        "runtime_context_decisions",
        ["runtime_context_id"],
    )


def downgrade() -> None:
    op.drop_table("runtime_context_decisions")
    op.drop_table("runtime_context_entries")
    op.drop_table("runtime_context_references")
    op.drop_table("runtime_artifacts")
    op.drop_index("ux_runtime_contexts_context_package", table_name="runtime_contexts")
    op.drop_index("ix_runtime_contexts_context_package_id", table_name="runtime_contexts")
    op.drop_table("runtime_contexts")
