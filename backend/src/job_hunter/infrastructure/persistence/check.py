"""Reproducible Alembic upgrade and metadata-drift verification."""

from pathlib import Path
from tempfile import TemporaryDirectory

from job_hunter.infrastructure.persistence.database import (
    check_database_metadata,
    upgrade_database,
)


def main() -> None:
    with TemporaryDirectory(prefix="job-hunter-db-check-") as directory:
        database_path = Path(directory) / "metadata-check.db"
        upgrade_database(database_path)
        check_database_metadata(database_path)


if __name__ == "__main__":
    main()
