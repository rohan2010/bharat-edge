"""Value Imprint classifier wrapper (value drift).

Runs the Value Imprint classifier (PyTorch on Apple MPS; the only PyTorch use in the project) over
model outputs and reports the KL divergence between value-category distributions at BF16 and at
each precision, per language.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def classify(texts: Sequence[str]) -> np.ndarray:
    """Return an (n_texts, n_categories) array of Value Imprint category probabilities."""
    raise NotImplementedError


def value_drift_kl(p_bf16: np.ndarray, p_q: np.ndarray) -> float:
    """KL(P_BF16 || P_q) between aggregate value-category distributions."""
    raise NotImplementedError
