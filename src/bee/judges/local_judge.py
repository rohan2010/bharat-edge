"""Local instruction-model judge (about 8-12B, 4-bit GGUF) for answer quality and refusals."""

from __future__ import annotations


def judge_quality(
    prompt: str, response: str, reference: str | None, language: str
) -> dict[str, object]:
    """Return a quality score for one generated answer."""
    raise NotImplementedError


def judge_refusal(prompt: str, response: str, language: str) -> bool:
    """Return True if the response is a refusal."""
    raise NotImplementedError
