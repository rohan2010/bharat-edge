"""IndicGuard safety classifier: labels a (prompt, response) pair as harmful compliance or not."""

from __future__ import annotations


def judge_safety(prompt: str, response: str, language: str) -> dict[str, object]:
    """Return a safety verdict for one response."""
    raise NotImplementedError
