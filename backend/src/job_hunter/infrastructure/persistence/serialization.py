"""Runtime-validated serialization at the SQL adapter boundary."""

from pydantic import TypeAdapter, ValidationError

from job_hunter.errors import DependencyUnavailableError, JobHunterError


def dump_payload[T](adapter: TypeAdapter[T], value: T) -> str:
    return adapter.dump_json(value).decode("utf-8")


def load_payload[T](adapter: TypeAdapter[T], payload: str) -> T:
    try:
        return adapter.validate_json(payload)
    except (JobHunterError, ValidationError, ValueError, TypeError):
        # Persisted bytes are an adapter input just like an external response. A
        # corrupt row cannot bypass Domain constructors or leak raw payload details.
        raise DependencyUnavailableError("persisted state is invalid") from None
