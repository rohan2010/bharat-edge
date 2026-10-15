"""Run one cell of the grid: load a config, run one task, write JSONL.

Loads a GGUF build with llama-cpp-python (Metal), runs one task on its frozen item set in fixed
order with greedy decoding, and writes ``results/<run_id>.jsonl``: a provenance header line
(see ``bee.provenance``) followed by one record per item.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_config(grid: str, configs_dir: Path = Path("configs")) -> dict[str, Any]:
    """Resolve a named grid (e.g. "smoke", "full") from configs/*.yaml into run specs."""
    raise NotImplementedError


def run_cell(
    model: str, precision: str, task: str, language: str, seed: int, out_dir: Path
) -> Path:
    """Run one (model, precision, task, language) cell and return the JSONL path."""
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m bee.runner --grid smoke``."""
    raise NotImplementedError
