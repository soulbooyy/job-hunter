from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from job_hunter.infrastructure.persistence.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
if not config.get_main_option("sqlalchemy.url"):
    # Programmatic entry points replace this with the selected workspace path.
    # The fallback keeps direct Alembic diagnostics well-defined.
    config.set_main_option("sqlalchemy.url", "sqlite:///job-hunter.db")

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        # SQLite treats DDL around the seeded singleton row as partially
        # transactional; explicitly commit both schema and Alembic head metadata.
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
