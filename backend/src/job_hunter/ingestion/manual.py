"""First-class manual job sources and their static registry."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qsl, urlsplit

from job_hunter.domain.jobs import SourceKind
from job_hunter.errors import ConflictError, EntityNotFoundError, InputValidationError


@dataclass(frozen=True, slots=True)
class ManualJDInput:
    title: str
    company: str
    city: str
    content: str


@dataclass(frozen=True, slots=True)
class ManualURLInput:
    url: str
    title: str
    company: str
    city: str
    content: str


type ManualSourceInput = ManualJDInput | ManualURLInput


@dataclass(frozen=True, slots=True)
class ValidatedSourceData:
    source_kind: SourceKind
    source_locator: str | None
    raw_title: str
    raw_company: str
    raw_city: str
    raw_description: str


class JobSource(Protocol):
    @property
    def kind(self) -> SourceKind: ...

    def capture(self, source_input: ManualSourceInput) -> ValidatedSourceData: ...


def _required(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise InputValidationError(f"{field_name} is required")
    return stripped


def _validated_common(
    *, title: str, company: str, city: str, content: str
) -> tuple[str, str, str, str]:
    return (
        _required(title, "title"),
        _required(company, "company"),
        _required(city, "city"),
        _required(content, "content"),
    )


def _is_sensitive_parameter_name(name: str) -> bool:
    normalized = "".join(character for character in name.casefold() if character.isalnum())
    sensitive_families = (
        "token",
        "secret",
        "password",
        "passwd",
        "credential",
        "authorization",
        "apikey",
        "signature",
    )
    return normalized in {"auth", "key", "sig"} or any(
        family in normalized for family in sensitive_families
    )


def _contains_sensitive_locator_parameter(query: str, fragment: str) -> bool:
    # SPA URLs commonly put a second query after a fragment route. Inspect both that
    # form and a fragment that is itself a query without retaining parameter values.
    fragment_parameters = fragment.partition("?")[2] if "?" in fragment else fragment
    return any(
        _is_sensitive_parameter_name(name)
        for parameters in (query, fragment_parameters)
        for name, _ in parse_qsl(parameters, keep_blank_values=True)
    )


class ManualJDSource:
    @property
    def kind(self) -> SourceKind:
        return SourceKind.MANUAL_JD

    def capture(self, source_input: ManualSourceInput) -> ValidatedSourceData:
        if not isinstance(source_input, ManualJDInput):
            raise InputValidationError("manual JD source received incompatible input")
        title, company, city, content = _validated_common(
            title=source_input.title,
            company=source_input.company,
            city=source_input.city,
            content=source_input.content,
        )
        return ValidatedSourceData(
            source_kind=self.kind,
            source_locator=None,
            raw_title=title,
            raw_company=company,
            raw_city=city,
            raw_description=content,
        )


class ManualURLSource:
    @property
    def kind(self) -> SourceKind:
        return SourceKind.MANUAL_URL

    def capture(self, source_input: ManualSourceInput) -> ValidatedSourceData:
        if not isinstance(source_input, ManualURLInput):
            raise InputValidationError("manual URL source received incompatible input")
        url = _required(source_input.url, "url")
        try:
            parsed = urlsplit(url)
        except ValueError:
            raise InputValidationError("url must be a valid HTTP(S) URL") from None
        # Credentials are excluded even for syntactically valid HTTP URLs: source
        # provenance must never become an accidental credential container.
        is_valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
        )
        if not is_valid:
            raise InputValidationError("url must be a valid HTTP(S) URL")
        if _contains_sensitive_locator_parameter(parsed.query, parsed.fragment):
            raise InputValidationError("url contains a sensitive credential parameter")
        title, company, city, content = _validated_common(
            title=source_input.title,
            company=source_input.company,
            city=source_input.city,
            content=source_input.content,
        )
        return ValidatedSourceData(
            source_kind=self.kind,
            source_locator=url,
            raw_title=title,
            raw_company=company,
            raw_city=city,
            raw_description=content,
        )


class JobSourceRegistry:
    """Minimal static registry; it performs no discovery or installation.

    Static registration is intentional for the current architecture: "source plugin"
    means an owned adapter seam, not a dynamic plugin or capability runtime.
    """

    def __init__(self, sources: Iterable[JobSource]) -> None:
        registered: dict[SourceKind, JobSource] = {}
        for source in sources:
            if source.kind in registered:
                raise ConflictError(f"duplicate job source: {source.kind}")
            registered[source.kind] = source
        self._sources = registered

    def get(self, kind: SourceKind) -> JobSource:
        try:
            return self._sources[kind]
        except KeyError:
            raise EntityNotFoundError(f"job source is not registered: {kind}") from None
