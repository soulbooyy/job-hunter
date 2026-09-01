"""CLI for the deterministic synthetic runtime-context evaluation."""

import argparse
from pathlib import Path

from pydantic import TypeAdapter

from job_hunter.evaluation.runtime_context import (
    RuntimeContextDataset,
    run_runtime_context_evaluation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run runtime-context mechanics evaluation")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    dataset = TypeAdapter(RuntimeContextDataset).validate_json(
        arguments.dataset.read_text(encoding="utf-8")
    )
    report = run_runtime_context_evaluation(dataset)
    payload = report.model_dump_json(indent=2)
    arguments.output.write_text(f"{payload}\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
