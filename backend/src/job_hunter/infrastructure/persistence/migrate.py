"""Explicit local database migration command."""

from job_hunter.config import RuntimeSettings
from job_hunter.infrastructure.persistence.database import upgrade_database


def main() -> None:
    upgrade_database(RuntimeSettings().database_path)


if __name__ == "__main__":
    main()
