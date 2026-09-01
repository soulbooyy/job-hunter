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


class StaleWriteError(ConflictError):
    """Optimistic write lost because authoritative state changed first."""

    code = "stale_write"


class DependencyUnavailableError(JobHunterError):
    """A boundary dependency failed without exposing its raw exception."""

    code = "dependency_unavailable"


class SemanticUnavailableError(DependencyUnavailableError):
    """The optional semantic runtime is unavailable and policy may fall back."""


class SemanticIndexIntegrityError(DependencyUnavailableError):
    """The derivative semantic index violates frozen identity or metadata contracts."""


class ContextBudgetExceededError(JobHunterError):
    """Protected context plus packaging overhead exceeds the hard final budget."""

    code = "context_budget_exceeded"


class CapabilityDeniedError(JobHunterError):
    """A workflow capability invocation is outside its static policy."""

    code = "capability_denied"


class BudgetExceededError(JobHunterError):
    """A versioned workflow or capability budget was exceeded."""

    code = "budget_exceeded"
