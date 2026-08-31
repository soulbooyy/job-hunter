"""Deterministic synthetic benchmark and admission result for Spike 5.5."""

from __future__ import annotations

import importlib.metadata
import platform
import statistics
import subprocess
import sys
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict

from job_hunter.domain.ids import EvidenceItemId, EvidenceVersionId
from job_hunter.domain.knowledge import EvidenceSensitivity, EvidenceType, EvidenceValidity
from spikes.chroma_feasibility.contracts import IndexManifest, IndexRecord, deterministic_embedding
from spikes.chroma_feasibility.index import ChromaFeasibilityIndex
from spikes.chroma_feasibility.network import NetworkGuard
from spikes.chroma_feasibility.rebuild import identity_metadata_match, reconcile_records

BENCHMARK_SCHEMA_VERSION = "chroma-feasibility-benchmark-v1"


class BenchmarkThresholds(BaseModel):
    model_config = ConfigDict(frozen=True)

    cold_index_ms: float = 15_000
    query_p95_ms: float = 250
    reopen_first_query_ms: float = 3_000
    reconcile_ms: float = 5_000
    full_rebuild_ms: float = 15_000

    @classmethod
    def permissive_for_contract_test(cls) -> BenchmarkThresholds:
        return cls(
            cold_index_ms=60_000,
            query_p95_ms=60_000,
            reopen_first_query_ms=60_000,
            reconcile_ms=60_000,
            full_rebuild_ms=60_000,
        )


class BenchmarkWorkload(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_count: int
    query_count: int
    replacement_count: int
    deletion_count: int
    embedding_dimension: int


class BenchmarkTimings(BaseModel):
    model_config = ConfigDict(frozen=True)

    cold_index_ms: float
    query_p95_ms: float
    reopen_first_query_ms: float
    reconcile_ms: float
    full_rebuild_ms: float


class BenchmarkCorrectness(BaseModel):
    model_config = ConfigDict(frozen=True)

    identity_metadata_match: bool
    process_reopen_succeeded: bool
    documents_absent: bool
    hidden_network_used: bool


class PackageRuntime(BaseModel):
    model_config = ConfigDict(frozen=True)

    chromadb_version: str
    python_version: str
    platform_system: str
    platform_machine: str
    chromadb_distribution_bytes: int


class _ProcessProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int
    hit_count: int
    elapsed_ms: float
    hidden_network_used: bool


class BenchmarkReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str
    manifest: IndexManifest
    workload: BenchmarkWorkload
    thresholds: BenchmarkThresholds
    timings: BenchmarkTimings
    correctness: BenchmarkCorrectness
    runtime: PackageRuntime
    admission: Literal["admitted", "admitted_with_constraints", "rejected"]
    constraints: tuple[str, ...]


def _record(number: int, *, replacement: bool = False) -> IndexRecord:
    suffix = "replacement" if replacement else "original"
    version_id = f"evidence-version-{number:04d}-{suffix}"
    content = f"Synthetic capability evidence {number} {suffix} deterministic fixture."
    return IndexRecord(
        evidence_id=EvidenceItemId(f"evidence-{number:04d}"),
        evidence_version_id=EvidenceVersionId(version_id),
        evidence_type=EvidenceType.SKILL,
        sensitivity=EvidenceSensitivity.PUBLIC,
        validity=EvidenceValidity.VALID,
        embedding=deterministic_embedding(content),
    )


def _distribution_size(distribution_name: str) -> int:
    distribution = importlib.metadata.distribution(distribution_name)
    total = 0
    for package_path in distribution.files or ():
        located = Path(package_path.locate())
        if located.is_file():
            total += located.stat().st_size
    return total


def _p95(values: list[float]) -> float:
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[94]


def _process_reopen(probe_path: Path) -> tuple[bool, float]:
    backend_root = Path(__file__).resolve().parents[2]
    module = "spikes.chroma_feasibility.process_probe"
    write = subprocess.run(
        [sys.executable, "-m", module, "write", str(probe_path)],
        cwd=backend_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if write.returncode != 0:
        return False, float("inf")
    query = subprocess.run(
        [sys.executable, "-m", module, "query", str(probe_path)],
        cwd=backend_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if query.returncode != 0:
        return False, float("inf")
    try:
        payload = _ProcessProbeResult.model_validate_json(query.stdout)
        return (
            payload.count == 1 and payload.hit_count == 1 and not payload.hidden_network_used,
            payload.elapsed_ms,
        )
    except ValueError:
        return False, float("inf")


def run_benchmark(
    root: Path,
    *,
    record_count: int = 256,
    query_count: int = 50,
    replacement_count: int = 32,
    deletion_count: int = 32,
    thresholds: BenchmarkThresholds | None = None,
) -> BenchmarkReport:
    if min(record_count, query_count) < 1:
        raise ValueError("benchmark requires records and queries")
    if replacement_count + deletion_count > record_count:
        raise ValueError("benchmark mutations exceed record count")
    applied_thresholds = thresholds or BenchmarkThresholds()
    root.mkdir(parents=True, exist_ok=True)
    records = tuple(_record(index) for index in range(record_count))

    with NetworkGuard() as network:
        cold_started = perf_counter()
        index = ChromaFeasibilityIndex(root / "cold")
        index.upsert(records)
        cold_ms = (perf_counter() - cold_started) * 1000

        query_latencies: list[float] = []
        for query_index in range(query_count):
            started = perf_counter()
            index.query(
                records[query_index % record_count].embedding,
                allowed_sensitivities=(EvidenceSensitivity.PUBLIC,),
                limit=10,
            )
            query_latencies.append((perf_counter() - started) * 1000)

        replacements = tuple(
            _record(index_number, replacement=True) for index_number in range(replacement_count)
        )
        retained = records[replacement_count + deletion_count :]
        desired = (*replacements, *retained)
        reconcile_started = perf_counter()
        reconcile_records(index, desired)
        reconcile_ms = (perf_counter() - reconcile_started) * 1000

        rebuild_started = perf_counter()
        rebuilt = ChromaFeasibilityIndex(root / "rebuilt")
        reconcile_records(rebuilt, desired)
        full_rebuild_ms = (perf_counter() - rebuild_started) * 1000

        process_reopen_succeeded, reopen_ms = _process_reopen(root / "process-reopen")

    persisted = index.list_records()
    rebuilt_records = rebuilt.list_records()
    metadata_matches = identity_metadata_match(persisted, desired) and identity_metadata_match(
        rebuilt_records, desired
    )
    documents_absent = index.documents_absent() and rebuilt.documents_absent()
    correctness = BenchmarkCorrectness(
        identity_metadata_match=metadata_matches,
        process_reopen_succeeded=process_reopen_succeeded,
        documents_absent=documents_absent,
        hidden_network_used=network.used,
    )
    timings = BenchmarkTimings(
        cold_index_ms=round(cold_ms, 3),
        query_p95_ms=round(_p95(query_latencies), 3),
        reopen_first_query_ms=round(reopen_ms, 3),
        reconcile_ms=round(reconcile_ms, 3),
        full_rebuild_ms=round(full_rebuild_ms, 3),
    )
    correctness_passed = (
        correctness.identity_metadata_match
        and correctness.process_reopen_succeeded
        and correctness.documents_absent
        and not correctness.hidden_network_used
    )
    performance_passed = (
        timings.cold_index_ms <= applied_thresholds.cold_index_ms
        and timings.query_p95_ms <= applied_thresholds.query_p95_ms
        and timings.reopen_first_query_ms <= applied_thresholds.reopen_first_query_ms
        and timings.reconcile_ms <= applied_thresholds.reconcile_ms
        and timings.full_rebuild_ms <= applied_thresholds.full_rebuild_ms
    )
    constraint_values = [
        "Chroma remains an opt-in derivative index; SQLite remains authoritative.",
        "The benchmark uses deterministic synthetic vectors, not semantic embeddings.",
        "The locked Chroma distribution has a materially larger transitive package surface.",
        "The embedded PersistentClient path is admitted only for this local-first scope.",
    ]
    if not performance_passed:
        constraint_values.append("One or more bounded benchmark ceilings were exceeded.")
    constraints = tuple(constraint_values)
    if not correctness_passed:
        admission: Literal["admitted", "admitted_with_constraints", "rejected"] = "rejected"
    elif constraints:
        admission = "admitted_with_constraints"
    else:
        admission = "admitted"
    return BenchmarkReport(
        schema_version=BENCHMARK_SCHEMA_VERSION,
        manifest=IndexManifest.default(),
        workload=BenchmarkWorkload(
            record_count=record_count,
            query_count=query_count,
            replacement_count=replacement_count,
            deletion_count=deletion_count,
            embedding_dimension=len(records[0].embedding),
        ),
        thresholds=applied_thresholds,
        timings=timings,
        correctness=correctness,
        runtime=PackageRuntime(
            chromadb_version=importlib.metadata.version("chromadb"),
            python_version=platform.python_version(),
            platform_system=platform.system(),
            platform_machine=platform.machine(),
            chromadb_distribution_bytes=_distribution_size("chromadb"),
        ),
        admission=admission,
        constraints=constraints,
    )
