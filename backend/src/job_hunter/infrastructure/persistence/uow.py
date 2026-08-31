"""One-session SQLAlchemy UnitOfWork with stable failure translation."""

import sqlite3

from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from job_hunter.application.ports import (
    CandidateKnowledgeRepository,
    JobRepository,
    RetrievalRepository,
    ScreeningRepository,
    UnitOfWork,
)
from job_hunter.errors import ConflictError, DependencyUnavailableError, StaleWriteError
from job_hunter.infrastructure.persistence.repositories import (
    SqlAlchemyCandidateKnowledgeRepository,
    SqlAlchemyJobRepository,
    SqlAlchemyRetrievalRepository,
    SqlAlchemyScreeningRepository,
)


def _is_stale_sqlite_snapshot(error: OperationalError) -> bool:
    original = error.orig
    return isinstance(original, sqlite3.OperationalError) and getattr(
        original, "sqlite_errorcode", None
    ) in {sqlite3.SQLITE_BUSY_SNAPSHOT, sqlite3.SQLITE_LOCKED}


class SqlAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session: Session) -> None:
        self._session = session
        self._jobs = SqlAlchemyJobRepository(session)
        self._knowledge = SqlAlchemyCandidateKnowledgeRepository(session)
        self._screening = SqlAlchemyScreeningRepository(session)
        self._retrieval = SqlAlchemyRetrievalRepository(session)
        self._closed = False

    @property
    def jobs(self) -> JobRepository:
        return self._jobs

    @property
    def knowledge(self) -> CandidateKnowledgeRepository:
        return self._knowledge

    @property
    def screening(self) -> ScreeningRepository:
        return self._screening

    @property
    def retrieval(self) -> RetrievalRepository:
        return self._retrieval

    def commit(self) -> None:
        try:
            self._session.commit()
        except StaleDataError:
            self._session.rollback()
            raise StaleWriteError("state changed before this transaction could commit") from None
        except OperationalError as error:
            self._session.rollback()
            if _is_stale_sqlite_snapshot(error):
                raise StaleWriteError(
                    "state changed before this transaction could commit"
                ) from None
            raise DependencyUnavailableError("database transaction is unavailable") from None
        except IntegrityError:
            self._session.rollback()
            raise ConflictError("database state conflicts with this operation") from None
        except SQLAlchemyError:
            self._session.rollback()
            raise DependencyUnavailableError("database transaction is unavailable") from None

    def rollback(self) -> None:
        if self._closed:
            return
        try:
            self._session.rollback()
        except SQLAlchemyError:
            raise DependencyUnavailableError("database transaction is unavailable") from None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._session.close()
        except SQLAlchemyError:
            raise DependencyUnavailableError("database session is unavailable") from None


class SqlAlchemyUnitOfWorkFactory:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> UnitOfWork:
        return SqlAlchemyUnitOfWork(self._session_factory())
