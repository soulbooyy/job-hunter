from __future__ import annotations

from pathlib import Path

from spikes.chroma_feasibility.benchmark import (
    BENCHMARK_SCHEMA_VERSION,
    BenchmarkThresholds,
    run_benchmark,
)


def test_benchmark_is_deterministic_and_contains_no_candidate_content(
    tmp_path: Path,
) -> None:
    report = run_benchmark(
        tmp_path,
        record_count=32,
        query_count=10,
        replacement_count=4,
        deletion_count=4,
        thresholds=BenchmarkThresholds.permissive_for_contract_test(),
    )
    payload = report.model_dump_json()

    assert report.schema_version == BENCHMARK_SCHEMA_VERSION
    assert report.workload.record_count == 32
    assert report.workload.query_count == 10
    assert report.correctness.identity_metadata_match is True
    assert report.correctness.process_reopen_succeeded is True
    assert report.correctness.documents_absent is True
    assert report.correctness.hidden_network_used is False
    assert report.admission in {"admitted", "admitted_with_constraints"}
    assert "Synthetic capability" not in payload
    assert str(tmp_path) not in payload
