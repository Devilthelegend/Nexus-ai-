"""Offline evaluation: retrieval metrics, a golden dataset and a runner."""

from app.eval.harness import (
    EvalReport,
    GoldenCase,
    GoldenDataset,
    GoldenDocument,
    run_evaluation,
    sample_dataset,
)

__all__ = [
    "EvalReport",
    "GoldenCase",
    "GoldenDataset",
    "GoldenDocument",
    "run_evaluation",
    "sample_dataset",
]
