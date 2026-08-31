"""Add snapshot-safe screening and normalized retrieval lineage."""

import json
from collections.abc import Sequence
from typing import cast

import sqlalchemy as sa
from alembic import op

revision: str = "0002_persistence_integrity"
down_revision: str | None = "0001_current_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_owner_trigger(
    *,
    name: str,
    operation: str,
    table: str,
    predicate: str,
    message: str,
) -> None:
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {name}
            BEFORE {operation} ON {table}
            WHEN NOT EXISTS ({predicate})
            BEGIN
                SELECT RAISE(ABORT, '{message}');
            END
            """
        )
    )


def _backfill_latest_screen_pointer() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT job_id, active_version_id, lifecycle_status, payload FROM jobs")
    ).mappings()
    for row in rows:
        if row["lifecycle_status"] == "imported":
            continue
        job_id = cast(str, row["job_id"])
        latest = connection.execute(
            sa.text(
                """
                SELECT result_id
                FROM quick_screen_results
                WHERE job_id = :job_id AND job_version_id = :active_version_id
                ORDER BY sequence_id DESC
                LIMIT 1
                """
            ),
            {"job_id": job_id, "active_version_id": row["active_version_id"]},
        ).scalar_one_or_none()
        if latest is None:
            raise ValueError("screened persisted Job has no active-version QuickScreen")
        latest_id = cast(str, latest)
        payload = cast(dict[str, object], json.loads(cast(str, row["payload"])))
        payload["latest_quick_screen_result_id"] = {"value": latest_id}
        connection.execute(
            sa.text(
                """
                UPDATE jobs
                SET latest_quick_screen_result_id = :latest_id, payload = :payload
                WHERE job_id = :job_id
                """
            ),
            {"latest_id": latest_id, "payload": json.dumps(payload), "job_id": job_id},
        )


def _id_value(value: object) -> str:
    if not isinstance(value, dict) or not isinstance(value.get("value"), str):
        raise ValueError("invalid persisted identifier during migration")
    return value["value"]


def _backfill_lineage_associations() -> None:
    connection = op.get_bind()
    screens = connection.execute(
        sa.text("SELECT result_id, job_version_id, payload FROM quick_screen_results")
    ).mappings()
    for screen in screens:
        payload = cast(dict[str, object], json.loads(cast(str, screen["payload"])))
        requirement_ids = cast(list[object], payload.get("requirement_ids", []))
        for ordinal, requirement_id in enumerate(requirement_ids, start=1):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO quick_screen_requirements (
                        quick_screen_result_id, job_version_id, requirement_id, ordinal
                    ) VALUES (:result_id, :job_version_id, :requirement_id, :ordinal)
                    """
                ),
                {
                    "result_id": screen["result_id"],
                    "job_version_id": screen["job_version_id"],
                    "requirement_id": _id_value(requirement_id),
                    "ordinal": ordinal,
                },
            )

    runs = connection.execute(
        sa.text("SELECT retrieval_run_id, payload FROM retrieval_runs")
    ).mappings()
    for run in runs:
        payload = cast(dict[str, object], json.loads(cast(str, run["payload"])))
        for table, field in (
            ("retrieval_run_hits", "hits"),
            ("retrieval_run_exclusions", "exclusions"),
        ):
            entries = cast(list[dict[str, object]], payload.get(field, []))
            for ordinal, entry in enumerate(entries, start=1):
                connection.execute(
                    sa.text(
                        f"""
                        INSERT INTO {table} (
                            retrieval_run_id, evidence_id, evidence_version_id, ordinal
                        ) VALUES (:run_id, :evidence_id, :version_id, :ordinal)
                        """
                    ),
                    {
                        "run_id": run["retrieval_run_id"],
                        "evidence_id": _id_value(entry["evidence_id"]),
                        "version_id": _id_value(entry["evidence_version_id"]),
                        "ordinal": ordinal,
                    },
                )


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("latest_quick_screen_result_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "ux_job_versions_version_job",
        "job_versions",
        ["version_id", "job_id"],
        unique=True,
    )
    op.create_index(
        "ux_evidence_versions_version_evidence",
        "evidence_versions",
        ["version_id", "evidence_id"],
        unique=True,
    )
    op.create_index(
        "ux_parsed_requirements_requirement_version",
        "parsed_requirements",
        ["requirement_id", "job_version_id"],
        unique=True,
    )
    op.create_index(
        "ux_quick_screen_result_job",
        "quick_screen_results",
        ["result_id", "job_id"],
        unique=True,
    )
    op.create_index(
        "ux_quick_screen_result_version",
        "quick_screen_results",
        ["result_id", "job_version_id"],
        unique=True,
    )
    op.create_table(
        "quick_screen_requirements",
        sa.Column("association_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("quick_screen_result_id", sa.Text(), nullable=False),
        sa.Column("job_version_id", sa.Text(), nullable=False),
        sa.Column("requirement_id", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["quick_screen_result_id", "job_version_id"],
            ["quick_screen_results.result_id", "quick_screen_results.job_version_id"],
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id", "job_version_id"],
            ["parsed_requirements.requirement_id", "parsed_requirements.job_version_id"],
        ),
        sa.UniqueConstraint("quick_screen_result_id", "ordinal"),
        sa.UniqueConstraint("quick_screen_result_id", "requirement_id"),
    )
    op.create_index(
        "ix_quick_screen_requirements_quick_screen_result_id",
        "quick_screen_requirements",
        ["quick_screen_result_id"],
    )
    op.create_table(
        "retrieval_run_hits",
        sa.Column("association_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "retrieval_run_id",
            sa.Text(),
            sa.ForeignKey("retrieval_runs.retrieval_run_id"),
            nullable=False,
        ),
        sa.Column("evidence_id", sa.Text(), nullable=False),
        sa.Column("evidence_version_id", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_version_id", "evidence_id"],
            ["evidence_versions.version_id", "evidence_versions.evidence_id"],
        ),
        sa.UniqueConstraint("retrieval_run_id", "ordinal"),
        sa.UniqueConstraint("retrieval_run_id", "evidence_version_id"),
    )
    op.create_index(
        "ix_retrieval_run_hits_retrieval_run_id",
        "retrieval_run_hits",
        ["retrieval_run_id"],
    )
    op.create_table(
        "retrieval_run_exclusions",
        sa.Column("association_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "retrieval_run_id",
            sa.Text(),
            sa.ForeignKey("retrieval_runs.retrieval_run_id"),
            nullable=False,
        ),
        sa.Column("evidence_id", sa.Text(), nullable=False),
        sa.Column("evidence_version_id", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_version_id", "evidence_id"],
            ["evidence_versions.version_id", "evidence_versions.evidence_id"],
        ),
        sa.UniqueConstraint("retrieval_run_id", "ordinal"),
        sa.UniqueConstraint("retrieval_run_id", "evidence_version_id"),
    )
    op.create_index(
        "ix_retrieval_run_exclusions_retrieval_run_id",
        "retrieval_run_exclusions",
        ["retrieval_run_id"],
    )

    _create_owner_trigger(
        name="trg_quick_screen_owner_insert",
        operation="INSERT",
        table="quick_screen_results",
        predicate=(
            "SELECT 1 FROM job_versions "
            "WHERE version_id = NEW.job_version_id AND job_id = NEW.job_id"
        ),
        message="quick screen ownership conflict",
    )
    _create_owner_trigger(
        name="trg_quick_screen_owner_update",
        operation="UPDATE OF job_id, job_version_id",
        table="quick_screen_results",
        predicate=(
            "SELECT 1 FROM job_versions "
            "WHERE version_id = NEW.job_version_id AND job_id = NEW.job_id"
        ),
        message="quick screen ownership conflict",
    )
    _create_owner_trigger(
        name="trg_triage_owner_insert",
        operation="INSERT",
        table="job_triage_records",
        predicate=(
            "SELECT 1 FROM quick_screen_results "
            "WHERE result_id = NEW.quick_screen_result_id AND job_id = NEW.job_id"
        ),
        message="triage ownership conflict",
    )
    _create_owner_trigger(
        name="trg_triage_owner_update",
        operation="UPDATE OF job_id, quick_screen_result_id",
        table="job_triage_records",
        predicate=(
            "SELECT 1 FROM quick_screen_results "
            "WHERE result_id = NEW.quick_screen_result_id AND job_id = NEW.job_id"
        ),
        message="triage ownership conflict",
    )
    _create_owner_trigger(
        name="trg_retrieval_owner_insert",
        operation="INSERT",
        table="retrieval_runs",
        predicate=(
            "SELECT 1 FROM parsed_requirements "
            "WHERE requirement_id = NEW.requirement_id "
            "AND job_version_id = NEW.job_version_id"
        ),
        message="retrieval ownership conflict",
    )
    _create_owner_trigger(
        name="trg_retrieval_owner_update",
        operation="UPDATE OF requirement_id, job_version_id",
        table="retrieval_runs",
        predicate=(
            "SELECT 1 FROM parsed_requirements "
            "WHERE requirement_id = NEW.requirement_id "
            "AND job_version_id = NEW.job_version_id"
        ),
        message="retrieval ownership conflict",
    )
    _backfill_lineage_associations()
    _backfill_latest_screen_pointer()


def downgrade() -> None:
    for trigger in (
        "trg_retrieval_owner_update",
        "trg_retrieval_owner_insert",
        "trg_triage_owner_update",
        "trg_triage_owner_insert",
        "trg_quick_screen_owner_update",
        "trg_quick_screen_owner_insert",
    ):
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger}"))
    op.drop_table("retrieval_run_exclusions")
    op.drop_table("retrieval_run_hits")
    op.drop_table("quick_screen_requirements")
    op.drop_index("ux_quick_screen_result_version", table_name="quick_screen_results")
    op.drop_index("ux_quick_screen_result_job", table_name="quick_screen_results")
    op.drop_index("ux_parsed_requirements_requirement_version", table_name="parsed_requirements")
    op.drop_index("ux_evidence_versions_version_evidence", table_name="evidence_versions")
    op.drop_index("ux_job_versions_version_job", table_name="job_versions")
    op.drop_column("jobs", "latest_quick_screen_result_id")
