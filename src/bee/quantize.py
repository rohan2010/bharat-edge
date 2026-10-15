"""GGUF conversion, quantization and importance-matrix (imatrix) calibration.

Wraps llama.cpp's ``convert_hf_to_gguf.py``, ``llama-quantize`` and ``llama-imatrix`` from the
pinned checkout in ``third_party/llama.cpp``. Produces the BF16 reference GGUF, the Q8_0, Q6_K,
Q4_K_M and Q3_K_M builds, and (Milestone 7, H4) multilingual/safety-calibrated Q4_K_M and Q3_K_M
builds. Every output file's SHA-256 is recorded.
"""

from __future__ import annotations

from pathlib import Path


def convert_to_bf16_gguf(hf_model_dir: Path, out_path: Path) -> Path:
    """Convert a Hugging Face checkpoint to a BF16 GGUF file."""
    raise NotImplementedError


def quantize(bf16_gguf: Path, precision: str, out_path: Path, imatrix: Path | None = None) -> Path:
    """Quantize a BF16 GGUF to ``precision`` (e.g. "Q4_K_M"), optionally with an imatrix."""
    raise NotImplementedError


def build_imatrix(bf16_gguf: Path, calibration_text: Path, out_path: Path) -> Path:
    """Compute an importance matrix from a calibration corpus with ``llama-imatrix``."""
    raise NotImplementedError
