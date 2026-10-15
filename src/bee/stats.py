"""Statistics for BharatEdge-Eval: bootstrap CIs, paired permutation tests, Holm correction.

Also defines the two primary metrics from the experimental protocol:

* relative loss   Delta_{L,q} = (S_{L,BF16} - S_{L,q}) / S_{L,BF16}
* gap             G_{L,q}     = Delta_{L,q} - Delta_{en,q}

and the gap amplification ratio Delta_{L,q} / Delta_{en,q}, which is reported only when
the English loss exceeds 1 point (the ratio is unstable when the English loss is near zero).

Scores ``S`` may be on any scale (fractions or percentages); the relative loss is scale-free.
Losses are fractions, so "1 point" of English loss is ``0.01``.

Pure NumPy/SciPy; no model code lives here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

N_BOOTSTRAP = 1000
CONFIDENCE = 0.95
MIN_EN_LOSS_FOR_RATIO = 0.01  # 1 point, on the fractional Delta scale


@dataclass(frozen=True)
class CI:
    """A point estimate with a percentile-bootstrap confidence interval."""

    estimate: float
    low: float
    high: float
    confidence: float = CONFIDENCE
    n_resamples: int = N_BOOTSTRAP


# --------------------------------------------------------------------------- metrics


def relative_loss(s_bf16: float, s_q: float) -> float:
    """Delta_{L,q} = (S_BF16 - S_q) / S_BF16. Positive means the quantized build is worse."""
    if s_bf16 == 0:
        raise ValueError("BF16 reference score is 0; relative loss is undefined")
    return (s_bf16 - s_q) / s_bf16


def gap(delta_lang: float, delta_en: float) -> float:
    """G_{L,q} = Delta_{L,q} - Delta_{en,q}. Positive means language L loses more than English."""
    return delta_lang - delta_en


def amplification_ratio(
    delta_lang: float, delta_en: float, min_en_loss: float = MIN_EN_LOSS_FOR_RATIO
) -> float | None:
    """Delta_{L,q} / Delta_{en,q}, or ``None`` unless the English loss exceeds ``min_en_loss``."""
    if delta_en <= min_en_loss:
        return None
    return delta_lang / delta_en


# --------------------------------------------------------------------------- bootstrap


def _as_1d(x: ArrayLike, name: str) -> np.ndarray:
    arr = np.asarray(x, dtype=float)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError(f"{name} must be a non-empty 1-D array")
    return arr


def _percentile_ci(estimate: float, samples: np.ndarray, confidence: float, n: int) -> CI:
    alpha = 1.0 - confidence
    lo, hi = np.nanpercentile(samples, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return CI(float(estimate), float(lo), float(hi), confidence, n)


def bootstrap_ci(
    values: ArrayLike,
    statistic: Callable[[np.ndarray], float] = np.mean,
    n_resamples: int = N_BOOTSTRAP,
    confidence: float = CONFIDENCE,
    seed: int = 0,
) -> CI:
    """Percentile bootstrap CI for ``statistic`` over per-item ``values`` (e.g. 0/1 correctness)."""
    x = _as_1d(values, "values")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, x.size, size=(n_resamples, x.size))
    samples = np.array([statistic(x[row]) for row in idx])
    return _percentile_ci(statistic(x), samples, confidence, n_resamples)


def _rel_loss_vec(ref: np.ndarray, q: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(ref != 0, (ref - q) / ref, np.nan)


def bootstrap_relative_loss(
    ref_scores: ArrayLike,
    q_scores: ArrayLike,
    n_resamples: int = N_BOOTSTRAP,
    confidence: float = CONFIDENCE,
    seed: int = 0,
) -> CI:
    """CI for Delta_{L,q}, resampling items jointly (BF16 and q are scored on identical items)."""
    ref = _as_1d(ref_scores, "ref_scores")
    q = _as_1d(q_scores, "q_scores")
    if ref.shape != q.shape:
        raise ValueError("ref_scores and q_scores must be paired (same items, same length)")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, ref.size, size=(n_resamples, ref.size))
    samples = _rel_loss_vec(ref[idx].mean(axis=1), q[idx].mean(axis=1))
    return _percentile_ci(relative_loss(ref.mean(), q.mean()), samples, confidence, n_resamples)


def bootstrap_gap(
    ref_lang: ArrayLike,
    q_lang: ArrayLike,
    ref_en: ArrayLike,
    q_en: ArrayLike,
    aligned: bool = False,
    n_resamples: int = N_BOOTSTRAP,
    confidence: float = CONFIDENCE,
    seed: int = 0,
) -> CI:
    """CI for G_{L,q} = Delta_{L,q} - Delta_{en,q}.

    Within a language, BF16 and q are resampled jointly. If ``aligned`` (parallel item sets such
    as Belebele, where item i is the same passage in every language), the same item indices are
    used for L and English; otherwise the two languages are resampled independently.
    """
    rl, ql = _as_1d(ref_lang, "ref_lang"), _as_1d(q_lang, "q_lang")
    re, qe = _as_1d(ref_en, "ref_en"), _as_1d(q_en, "q_en")
    if rl.shape != ql.shape or re.shape != qe.shape:
        raise ValueError("BF16 and q scores must be paired within each language")
    if aligned and rl.shape != re.shape:
        raise ValueError("aligned=True requires equal item counts across languages")
    rng = np.random.default_rng(seed)
    idx_l = rng.integers(0, rl.size, size=(n_resamples, rl.size))
    idx_e = idx_l if aligned else rng.integers(0, re.size, size=(n_resamples, re.size))
    d_l = _rel_loss_vec(rl[idx_l].mean(axis=1), ql[idx_l].mean(axis=1))
    d_e = _rel_loss_vec(re[idx_e].mean(axis=1), qe[idx_e].mean(axis=1))
    est = gap(relative_loss(rl.mean(), ql.mean()), relative_loss(re.mean(), qe.mean()))
    return _percentile_ci(est, d_l - d_e, confidence, n_resamples)


# --------------------------------------------------------------------------- tests


def paired_permutation_test(
    a: ArrayLike,
    b: ArrayLike,
    n_permutations: int = 10_000,
    alternative: str = "two-sided",
    seed: int = 0,
) -> float:
    """Paired (sign-flip) permutation test on mean(a - b) for scores on identical items.

    ``alternative``: "two-sided", "greater" (mean(a) > mean(b)) or "less".
    Returns a p-value with the +1 correction, so it is never exactly 0.
    """
    x, y = _as_1d(a, "a"), _as_1d(b, "b")
    if x.shape != y.shape:
        raise ValueError("a and b must be paired (same length)")
    if alternative not in ("two-sided", "greater", "less"):
        raise ValueError(f"unknown alternative: {alternative!r}")
    d = x - y
    observed = d.mean()
    rng = np.random.default_rng(seed)
    signs = rng.choice(np.array([-1.0, 1.0]), size=(n_permutations, d.size))
    null = (signs * d).mean(axis=1)
    tol = 1e-12
    if alternative == "two-sided":
        hits = np.sum(np.abs(null) >= abs(observed) - tol)
    elif alternative == "greater":
        hits = np.sum(null >= observed - tol)
    else:
        hits = np.sum(null <= observed + tol)
    return float((hits + 1) / (n_permutations + 1))


def holm_correction(
    pvalues: Sequence[float] | ArrayLike, alpha: float = 0.05
) -> tuple[np.ndarray, np.ndarray]:
    """Holm-Bonferroni step-down correction.

    Returns ``(adjusted_pvalues, reject)`` in the original order.
    """
    p = np.asarray(pvalues, dtype=float)
    if p.ndim != 1:
        raise ValueError("pvalues must be 1-D")
    m = p.size
    if m == 0:
        return p.copy(), np.zeros(0, dtype=bool)
    order = np.argsort(p, kind="stable")
    scaled = (m - np.arange(m)) * p[order]
    adj_sorted = np.minimum(np.maximum.accumulate(scaled), 1.0)
    adjusted = np.empty(m)
    adjusted[order] = adj_sorted
    return adjusted, adjusted <= alpha
