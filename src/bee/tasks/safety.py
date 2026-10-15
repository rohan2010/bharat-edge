"""Harmful requests (300 items per language).

IndicSafeEval (Hindi), MultiJail (Bengali), translated and native-checked for Hinglish. Scored by
IndicGuard plus a second judge; harmful-compliance rate is reported on items the model understood
(see probe.py). Model outputs are never printed or committed."""

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
