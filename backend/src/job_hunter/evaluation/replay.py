"""Evaluation-only structured response replay with runtime validation."""

from collections.abc import Mapping

from pydantic import BaseModel, ValidationError

from job_hunter.errors import InputValidationError


class StructuredReplayModel:
    def __init__(self, responses: Mapping[str, str]) -> None:
        self._responses = dict(responses)

    def invoke[T: BaseModel](self, case_id: str, response_type: type[T]) -> T:
        try:
            payload = self._responses[case_id]
        except KeyError:
            raise InputValidationError(f"replay response not found: {case_id}") from None
        try:
            return response_type.model_validate_json(payload)
        except (ValidationError, ValueError):
            # Replay data is an IO boundary just like a live model response. Invalid
            # structured output never becomes a typed evaluation observation.
            raise InputValidationError(f"replay response is invalid: {case_id}") from None
