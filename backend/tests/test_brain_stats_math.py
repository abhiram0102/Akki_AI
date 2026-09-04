"""Tests for the G² (log-likelihood ratio) association-strength formula
(Dunning, 1993) — a pure function, no I/O."""
import math

from backend.services.brain_stats_math import log_likelihood_ratio


def test_returns_zero_for_any_zero_count():
    assert log_likelihood_ratio(0, 10, 10, 1000) == 0.0
    assert log_likelihood_ratio(5, 0, 10, 1000) == 0.0
    assert log_likelihood_ratio(5, 10, 0, 1000) == 0.0
    assert log_likelihood_ratio(5, 10, 10, 0) == 0.0


def test_perfectly_independent_pair_scores_near_zero():
    # a and b occur exactly as often together as chance alone predicts
    total = 10_000
    count_a = 100
    count_b = 100
    expected_ab = (count_a * count_b) / total  # = 1
    g2 = log_likelihood_ratio(round(expected_ab), count_a, count_b, total)
    assert g2 < 1.0


def test_strongly_associated_pair_scores_high():
    # a and b co-occur almost every time either appears — strong association
    total = 10_000
    count_a = 50
    count_b = 50
    count_ab = 48
    g2 = log_likelihood_ratio(count_ab, count_a, count_b, total)
    assert g2 > 50.0


def test_rare_pair_does_not_get_inflated_like_raw_pmi_would():
    # This is the exact failure mode raw PMI had in the original prototype:
    # two words that each appear only twice, and happen to co-occur once,
    # produce a huge raw-PMI score despite being statistically meaningless.
    # G² must NOT rank this above the strongly-associated pair above.
    total = 10_000
    g2_rare = log_likelihood_ratio(1, 2, 2, total)
    g2_strong = log_likelihood_ratio(48, 50, 50, total)
    assert g2_rare < g2_strong


def test_symmetric_in_a_and_b():
    total = 5000
    g2_ab = log_likelihood_ratio(20, 60, 40, total)
    g2_ba = log_likelihood_ratio(20, 40, 60, total)
    assert math.isclose(g2_ab, g2_ba, rel_tol=1e-6)
