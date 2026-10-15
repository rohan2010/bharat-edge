"""Over-refusal (150 items per language).

XSTest, translated and native-checked. Judge decides: refused or answered."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

TASK_VERSION = "0"


def load_items(language: str, limit: int | None = None) -> Iterator[dict[str, Any]]:
    """Yield frozen items for ``language`` in fixed order (first ``limit`` for the smoke grid)."""
    raise NotImplementedError


def build_prompt(item: dict[str, Any]) -> str:
    """Render the versioned prompt template for one item."""
    raise NotImplementedError


def score(item: dict[str, Any], output: Any) -> dict[str, Any]:
    """Score one model output for one item."""
    raise NotImplementedError
