"""Narrow helpers for content-safe governed application execution."""

import json

type SerializedResultValue = str | int | float | bool | None | tuple["SerializedResultValue", ...]


def serialized_result_size(values: tuple[SerializedResultValue, ...]) -> int:
    """Measure a typed result projection without Candidate content or object reprs."""
    return len(json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode())
