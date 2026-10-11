"""Scorers and bootstrap intervals (run-evals skill). Hand-computed expectations."""

import pytest

from refdesk.evals.scorers import (
    bootstrap_ci,
    mrr,
    open_rights_share,
    precision_at_k,
    recall_at_k,
)

RELEVANT = {"a", "b", "c", "d"}


class TestRecallAtK:
    def test_counts_relevant_items_in_the_top_k_over_min_of_relevant_and_k(self):
        # 2 relevant in the top 3; at most min(4, 3) = 3 could fit.
        assert recall_at_k(["a", "x", "b", "y"], RELEVANT, k=3) == pytest.approx(2 / 3)

    def test_equals_ordinary_recall_when_k_exceeds_the_relevant_count(self):
        assert recall_at_k(["a", "x", "b", "y"], RELEVANT, k=10) == pytest.approx(2 / 4)

    def test_only_the_top_k_count(self):
        assert recall_at_k(["x", "y", "a"], RELEVANT, k=2) == 0.0

    def test_capped_by_k_when_there_are_more_relevant_than_k(self):
        # 2 of 4 relevant can fit in k=2, and both are there: recall is min-normalised.
        assert recall_at_k(["a", "b"], RELEVANT, k=2) == 1.0

    def test_empty_relevant_set_is_an_error(self):
        with pytest.raises(ValueError):
            recall_at_k(["a"], set(), k=10)


class TestPrecisionAtK:
    def test_relevant_share_of_k(self):
        assert precision_at_k(["a", "x", "b", "y"], RELEVANT, k=4) == 0.5

    def test_fewer_results_than_k_still_divides_by_k(self):
        assert precision_at_k(["a"], RELEVANT, k=4) == 0.25


class TestMRR:
    def test_reciprocal_rank_of_the_first_relevant(self):
        assert mrr(["x", "y", "b"], RELEVANT) == pytest.approx(1 / 3)

    def test_zero_when_nothing_relevant(self):
        assert mrr(["x", "y"], RELEVANT) == 0.0

    def test_first_position(self):
        assert mrr(["a", "x"], RELEVANT) == 1.0


class TestOpenRightsShare:
    def test_share_of_top_k_that_is_open(self):
        statuses = {"a": "open", "b": "permission required", "c": "open"}
        assert open_rights_share(["a", "b", "c"], statuses, k=3) == pytest.approx(2 / 3)

    def test_no_results_is_none(self):
        assert open_rights_share([], {}, k=3) is None


class TestBootstrap:
    def test_interval_contains_the_mean(self):
        values = [0.1, 0.4, 0.5, 0.9, 0.3, 0.6]
        mean, low, high = bootstrap_ci(values, seed=7)
        assert mean == pytest.approx(sum(values) / len(values))
        assert low <= mean <= high

    def test_is_reproducible_with_a_seed(self):
        values = [0.2, 0.8, 0.5, 0.1]
        assert bootstrap_ci(values, seed=1) == bootstrap_ci(values, seed=1)

    def test_identical_values_give_a_zero_width_interval(self):
        assert bootstrap_ci([0.5] * 10, seed=0) == (0.5, 0.5, 0.5)

    def test_more_spread_gives_a_wider_interval(self):
        _, lo1, hi1 = bootstrap_ci([0.4, 0.5, 0.6] * 5, seed=0)
        _, lo2, hi2 = bootstrap_ci([0.0, 0.5, 1.0] * 5, seed=0)
        assert hi2 - lo2 > hi1 - lo1

    def test_empty_values_is_an_error(self):
        with pytest.raises(ValueError):
            bootstrap_ci([], seed=0)
