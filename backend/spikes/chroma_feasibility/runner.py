"""CLI for the bounded Chroma feasibility benchmark."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from spikes.chroma_feasibility.benchmark import run_benchmark


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="job-hunter-chroma-spike-") as directory:
        report = run_benchmark(Path(directory))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Chroma feasibility: {report.admission}; "
        f"{report.workload.record_count} records, "
        f"query p95 {report.timings.query_p95_ms:.3f} ms"
    )


if __name__ == "__main__":
    main()
