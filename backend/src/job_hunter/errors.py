"""Stable Job Hunter errors that may cross internal layer boundaries."""


class JobHunterError(Exception):
    """Base class carrying a safe, stable error code and message."""

    code = "job_hunter_error"


class InputValidationError(JobHunterError):
    """Validated input or a domain invariant is invalid."""

    code = "input_validation"


class EntityNotFoundError(JobHunterError):
    """A referenced domain entity does not exist."""

    code = "not_found"


class ConflictError(JobHunterError):
    """Requested state conflicts with existing domain state."""

    code = "conflict"


class DependencyUnavailableError(JobHunterError):
    """A boundary dependency failed without exposing its raw exception."""

    code = "dependency_unavailable"
