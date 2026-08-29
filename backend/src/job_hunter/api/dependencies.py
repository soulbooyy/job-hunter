"""Request-time access to lifespan-managed application dependencies."""

from typing import Annotated, cast

from fastapi import Depends, Request

from job_hunter.application.candidate_knowledge import CreateCandidateProfile, SaveEvidence
from job_hunter.application.import_job import ImportJob
from job_hunter.application.screening import RecordJobTriage, RunQuickScreen


def _state_dependency[T](request: Request, name: str, expected_type: type[T]) -> T:
    try:
        candidate = cast(object, getattr(request.app.state, name))
    except AttributeError:
        raise RuntimeError(
            f"{expected_type.__name__} is unavailable outside the lifespan"
        ) from None
    # app.state is dynamic framework storage. Static casts cannot replace this guard
    # against lifecycle mistakes or incorrectly composed dependencies.
    if not isinstance(candidate, expected_type):
        raise RuntimeError(f"Application state contains an invalid {expected_type.__name__}")
    return candidate


def get_import_job(request: Request) -> ImportJob:
    return _state_dependency(request, "import_job", ImportJob)


def get_create_candidate_profile(request: Request) -> CreateCandidateProfile:
    return _state_dependency(request, "create_candidate_profile", CreateCandidateProfile)


def get_save_evidence(request: Request) -> SaveEvidence:
    return _state_dependency(request, "save_evidence", SaveEvidence)


def get_run_quick_screen(request: Request) -> RunQuickScreen:
    return _state_dependency(request, "run_quick_screen", RunQuickScreen)


def get_record_job_triage(request: Request) -> RecordJobTriage:
    return _state_dependency(request, "record_job_triage", RecordJobTriage)


ImportJobDep = Annotated[ImportJob, Depends(get_import_job)]
CreateCandidateProfileDep = Annotated[
    CreateCandidateProfile,
    Depends(get_create_candidate_profile),
]
SaveEvidenceDep = Annotated[SaveEvidence, Depends(get_save_evidence)]
RunQuickScreenDep = Annotated[RunQuickScreen, Depends(get_run_quick_screen)]
RecordJobTriageDep = Annotated[RecordJobTriage, Depends(get_record_job_triage)]
