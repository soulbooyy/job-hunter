"""SQLite engine lifecycle and explicit Alembic migration entry points."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import URL, Connection, Engine, create_engine, event, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from job_hunter.errors import DependencyUnavailableError

_BACKEND_ROOT = Path(__file__).resolve().parents[4]


def _database_url(database_path: Path) -> URL:
    return URL.create("sqlite", database=str(database_path.resolve()))


def _alembic_config(database_path: Path) -> Config:
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "migrations"))
    config.set_main_option(
        "sqlalchemy.url",
        _database_url(database_path).render_as_string(hide_password=False),
    )
    return config


def upgrade_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(_alembic_config(database_path), "head")


def get_migration_head() -> str:
    heads = ScriptDirectory.from_config(_alembic_config(Path("job-hunter.db"))).get_heads()
    if len(heads) != 1:
        raise DependencyUnavailableError("database migration graph is invalid")
    return heads[0]


def check_database_metadata(database_path: Path) -> None:
    """Fail when ORM metadata would require an uncommitted migration."""
    command.check(_alembic_config(database_path))


def get_database_revision(database_path: Path) -> str | None:
    if not database_path.exists():
        return None
    engine = create_engine(_database_url(database_path), future=True)
    try:
        with engine.connect() as connection:
            if "alembic_version" not in inspect(connection).get_table_names():
                return None
            return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()


@dataclass(frozen=True, slots=True)
class DatabaseRuntime:
    engine: Engine
    session_factory: sessionmaker[Session]

    def table_names(self) -> set[str]:
        return set(inspect(self.engine).get_table_names())

    def dispose(self) -> None:
        self.engine.dispose()


def _configure_sqlite(connection: sqlite3.Connection, _record: object) -> None:
    # sqlite3's legacy mode does not BEGIN for SELECT. SQLAlchemy owns transaction
    # control so read-only UoWs receive the same real snapshot semantics as writes.
    connection.isolation_level = None
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


def _defer_foreign_keys(connection: Connection) -> None:
    connection.exec_driver_sql("BEGIN")
    # Repositories stage an aggregate and its immutable children in one UoW.
    # Deferral validates the complete graph at commit regardless of mapper flush
    # order; it does not weaken the final foreign-key check.
    connection.exec_driver_sql("PRAGMA defer_foreign_keys=ON")


def create_database_runtime(database_path: Path) -> DatabaseRuntime:
    engine: Engine | None = None
    try:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            _database_url(database_path),
            connect_args={"check_same_thread": False, "timeout": 5.0},
            future=True,
            hide_parameters=True,
        )
        event.listen(engine, "connect", _configure_sqlite)
        event.listen(engine, "begin", _defer_foreign_keys)
        # Establish the lifespan-owned resource now, not on the first request, so
        # an unusable database fails startup through the stable adapter taxonomy.
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except (OSError, sqlite3.Error, SQLAlchemyError):
        if engine is not None:
            engine.dispose()
        raise DependencyUnavailableError("database runtime is unavailable") from None
    return DatabaseRuntime(
        engine=engine,
        session_factory=sessionmaker(bind=engine, expire_on_commit=False),
    )


def require_current_schema(database_path: Path) -> None:
    try:
        revision = get_database_revision(database_path)
    except Exception:
        raise DependencyUnavailableError("database schema is unavailable") from None
    if revision != get_migration_head():
        raise DependencyUnavailableError("database schema upgrade is required")
