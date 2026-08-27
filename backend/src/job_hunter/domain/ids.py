"""Stable identifiers used across workflow and trace boundaries."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _StableId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or any(character.isspace() for character in self.value):
            raise ValueError("IDs must be non-empty and contain no whitespace")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class RunId(_StableId):
    """Stable identity for one application or workflow run."""


@dataclass(frozen=True, slots=True)
class CorrelationId(_StableId):
    """Stable identity connecting work across local boundaries."""
