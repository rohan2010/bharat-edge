"""Free-tier API model used as a second-opinion judge (spot checks, not the primary judge)."""

from __future__ import annotations


def judge(prompt: str, response: str, rubric: str, language: str) -> dict[str, object]:
    """Return the second judge's verdict for one response."""
    raise NotImplementedError
