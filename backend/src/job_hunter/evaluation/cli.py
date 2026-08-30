"""Command-line entry point for deterministic replay evaluation."""

import argparse
from pathlib import Path

from job_hunter.evaluation.dataset import load_evaluation_dataset
from job_hunter.evaluation.runner import run_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic Job Hunter replay evaluation")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    report = run_evaluation(load_evaluation_dataset(arguments.dataset))
    payload = report.model_dump_json(indent=2)
    if arguments.output is not None:
        try:
            arguments.output.write_text(f"{payload}\n", encoding="utf-8")
        except OSError as error:
            parser.error(f"cannot write evaluation report: {error}")
    print(payload)


if __name__ == "__main__":
    main()
