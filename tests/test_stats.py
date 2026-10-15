import numpy as np
import pytest
from scipy import stats as sps

from bee import stats


def test_relative_loss_and_gap():
    assert stats.relative_loss(0.80, 0.60) == pytest.approx(0.25)
    assert stats.relative_loss(80.0, 60.0) == pytest.approx(0.25)  # scale-free
    assert stats.relative_loss(0.5, 0.6) == pytest.approx(-0.2)  # quantized build better
    assert stats.gap(0.25, 0.05) == pytest.approx(0.20)
    with pytest.raises(ValueError):
        stats.relative_loss(0.0, 0.1)


def test_amplification_ratio_only_above_one_point():
    assert stats.amplification_ratio(0.10, 0.02) == pytest.approx(5.0)
    assert stats.amplification_ratio(0.10, 0.01) is None  # exactly 1 point: not reported
    assert stats.amplification_ratio(0.10, 0.005) is None
    assert stats.amplification_ratio(0.10, -0.03) is None
    assert stats.amplification_ratio(0.10, 0.03, min_en_loss=0.05) is None


def test_bootstrap_ci_mean_covers_and_is_deterministic():
    rng = np.random.default_rng(1)
    x = rng.binomial(1, 0.7, size=900).astype(float)
    ci = stats.bootstrap_ci(x, seed=3)
    assert ci.n_resamples == 1000 and ci.confidence == 0.95
    assert ci.estimate == pytest.approx(x.mean())
    assert ci.low < ci.estimate < ci.high
    # roughly the normal-approximation width for a proportion
    se = np.sqrt(x.mean() * (1 - x.mean()) / x.size)
    assert (ci.high - ci.low) == pytest.approx(2 * 1.96 * se, rel=0.2)
    assert stats.bootstrap_ci(x, seed=3) == ci


def test_bootstrap_ci_rejects_empty():
    with pytest.raises(ValueError):
        stats.bootstrap_ci([])


def test_bootstrap_relative_loss():
    rng = np.random.default_rng(0)
    ref = rng.binomial(1, 0.8, size=900).astype(float)
    q = ref.copy()
    flip = rng.choice(np.flatnonzero(ref == 1), size=90, replace=False)
    q[flip] = 0.0
    ci = stats.bootstrap_relative_loss(ref, q)
    assert ci.estimate == pytest.approx(stats.relative_loss(ref.mean(), q.mean()))
    assert 0 < ci.low < ci.estimate < ci.high
    with pytest.raises(ValueError):
        stats.bootstrap_relative_loss(ref, q[:-1])


def test_bootstrap_gap_detects_amplified_loss():
    rng = np.random.default_rng(2)
    n = 900
    ref_en = rng.binomial(1, 0.85, n).astype(float)
    q_en = ref_en * rng.binomial(1, 0.98, n)  # ~2% relative loss
    ref_hi = rng.binomial(1, 0.70, n).astype(float)
    q_hi = ref_hi * rng.binomial(1, 0.80, n)  # ~20% relative loss
    for aligned in (False, True):
        ci = stats.bootstrap_gap(ref_hi, q_hi, ref_en, q_en, aligned=aligned)
        assert ci.low > 0.1
        assert ci.estimate == pytest.approx(
            stats.relative_loss(ref_hi.mean(), q_hi.mean())
            - stats.relative_loss(ref_en.mean(), q_en.mean())
        )
    with pytest.raises(ValueError):
        stats.bootstrap_gap(ref_hi, q_hi, ref_en[:10], q_en[:10], aligned=True)


def test_paired_permutation_identical_is_not_significant():
    x = np.random.default_rng(0).normal(size=50)
    assert stats.paired_permutation_test(x, x) == 1.0


def test_paired_permutation_detects_shift_and_matches_exact():
    rng = np.random.default_rng(0)
    a = rng.normal(size=40)
    b = a - 0.8 + rng.normal(scale=0.3, size=40)
    p = stats.paired_permutation_test(a, b, n_permutations=5000)
    assert p < 0.001
    assert stats.paired_permutation_test(a, b, alternative="greater") < 0.001
    assert stats.paired_permutation_test(a, b, alternative="less") > 0.99

    # agrees with SciPy's paired permutation test on a weak effect
    a2 = rng.normal(size=30)
    b2 = a2 - 0.15 + rng.normal(scale=0.5, size=30)
    ours = stats.paired_permutation_test(a2, b2, n_permutations=20_000, seed=1)
    ref = sps.permutation_test(
        (a2 - b2,),
        np.mean,
        permutation_type="samples",
        n_resamples=20_000,
        random_state=1,
    ).pvalue
    assert ours == pytest.approx(ref, abs=0.02)


def test_paired_permutation_validates():
    with pytest.raises(ValueError):
        stats.paired_permutation_test([1, 2], [1, 2, 3])
    with pytest.raises(ValueError):
        stats.paired_permutation_test([1, 2], [1, 2], alternative="bigger")


def test_holm_matches_known_values():
    p = [0.01, 0.04, 0.03, 0.005]
    adj, reject = stats.holm_correction(p, alpha=0.05)
    # sorted: 0.005*4=0.02, 0.01*3=0.03, 0.03*2=0.06, 0.04*1=0.04 -> monotone 0.06
    np.testing.assert_allclose(adj, [0.03, 0.06, 0.06, 0.02])
    np.testing.assert_array_equal(reject, [True, False, False, True])


def test_holm_matches_statsmodels_style_reference_and_caps_at_one():
    p = np.array([0.2, 0.5, 0.9])
    adj, reject = stats.holm_correction(p)
    np.testing.assert_allclose(adj, [0.6, 1.0, 1.0])
    assert not reject.any()
    adj, reject = stats.holm_correction([])
    assert adj.size == 0 and reject.size == 0
