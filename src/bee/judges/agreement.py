"""Judge-judge and judge-human agreement (Gate 2: judge-human agreement must reach 80%)."""

from __future__ import annotations

from collections.abc import Sequence

GATE2_THRESHOLD = 0.80


def percent_agreement(a: Sequence[object], b: Sequence[object]) -> float:
    """Share of items on which two raters give the same label."""
    raise NotImplementedError


def cohens_kappa(a: Sequence[object], b: Sequence[object]) -> float:
    """Cohen's kappa between two raters."""
    raise NotImplementedError
