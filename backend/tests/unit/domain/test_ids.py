import pytest

from job_hunter.domain.ids import CorrelationId, RunId


def test_ids_preserve_their_canonical_value() -> None:
    run_id = RunId("run-01")

    assert run_id.value == "run-01"
    assert str(run_id) == "run-01"


def test_different_id_types_do_not_compare_equal() -> None:
    run_id = RunId("shared-value")
    correlation_id = CorrelationId("shared-value")

    assert run_id != correlation_id
    assert len({run_id, correlation_id}) == 2


@pytest.mark.parametrize("value", ["", " ", "run id", "run\nid"])
def test_ids_reject_empty_or_whitespace_values(value: str) -> None:
    with pytest.raises(ValueError, match="non-empty and contain no whitespace"):
        RunId(value)
