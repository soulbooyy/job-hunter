"""Explicit local-model Hybrid evaluation; separate from offline seed replay."""

import argparse
from pathlib import Path

from job_hunter.evaluation.dataset import load_evaluation_dataset
from job_hunter.evaluation.runner import run_evaluation
from job_hunter.evaluation.semantic import LocalModelEvaluationRetriever
from job_hunter.infrastructure.chroma import LocalOnnxMiniLmEmbeddingProvider
from job_hunter.infrastructure.retrieval import (
    FullContextRetriever,
    HybridRetriever,
    LexicalMetadataRetriever,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run explicit local Hybrid evaluation")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    lexical = LexicalMetadataRetriever()
    semantic = LocalModelEvaluationRetriever(LocalOnnxMiniLmEmbeddingProvider())
    hybrid = HybridRetriever(lexical=lexical, semantic=semantic)
    report = run_evaluation(
        load_evaluation_dataset(arguments.dataset),
        retrievers=(FullContextRetriever(), lexical, hybrid),
    )
    payload = report.model_dump_json(indent=2)
    arguments.output.write_text(f"{payload}\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
