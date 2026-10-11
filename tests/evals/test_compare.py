"""Paired comparison of two eval runs (issue #36, docs/eval-gate-policy.md)."""

import json

import pytest

from refdesk.evals.compare import NotComparable, compare_runs

BASE = {
    "golden_version": "v0-synthetic",
    "golden_sha256": "g",
    "corpus_version": "c",
    "scorers_version": "scorers-v1",
    "retriever": "jaccard",
    "k": 12,
}


def write_run(root, run_hash, rows, **config):
    run = root / "runs" / run_hash
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(
        json.dumps({"config_hash": run_hash, "config": BASE | config}), encoding="utf-8"
    )
    (run / "cases.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def row(case_id, recall, mrr=0.5):
    return {
        "id": case_id,
        "status": "scored",
        "recall": recall,
        "precision": recall,
        "mrr": mrr,
        "open_share": None,
    }


class TestPairedDifferences:
    def test_mean_difference_is_hand_computed(self, tmp_path):
        write_run(tmp_path, "a", [row("g1", 0.5), row("g2", 0.5), row("g3", 1.0)])
        write_run(tmp_path, "b", [row("g1", 0.75), row("g2", 0.5), row("g3", 0.75)])
        result = compare_runs(tmp_path, "a", "b", seed=0)
        recall = result.metrics["recall"]
        # differences b - a: +0.25, 0, -0.25 -> mean 0
        assert recall.mean_diff == pytest.approx(0.0)
        assert (recall.better, recall.same, recall.worse) == (1, 1, 1)
        assert recall.low <= 0.0 <= recall.high

    def test_a_consistent_improvement_has_an_interval_above_zero(self, tmp_path):
        write_run(tmp_path, "a", [row(f"g{i}", 0.4) for i in range(10)])
        write_run(tmp_path, "b", [row(f"g{i}", 0.6) for i in range(10)])
        recall = compare_runs(tmp_path, "a", "b", seed=0).metrics["recall"]
        assert recall.mean_diff == pytest.approx(0.2)
        assert recall.low > 0

    def test_only_cases_scored_in_both_runs_are_paired(self, tmp_path):
        write_run(tmp_path, "a", [row("g1", 0.5), row("g2", 0.5)])
        write_run(tmp_path, "b", [row("g1", 1.0), {"id": "g2", "status": "not applicable"}])
        recall = compare_runs(tmp_path, "a", "b", seed=0).metrics["recall"]
        assert recall.n == 1 and recall.mean_diff == pytest.approx(0.5)

    def test_metrics_missing_on_every_case_are_left_out(self, tmp_path):
        write_run(tmp_path, "a", [row("g1", 0.5)])
        write_run(tmp_path, "b", [row("g1", 0.5)])
        assert "open_share" not in compare_runs(tmp_path, "a", "b", seed=0).metrics


class TestRefusal:
    @pytest.mark.parametrize(
        "field", ["golden_version", "golden_sha256", "corpus_version", "scorers_version"]
    )
    def test_refuses_runs_that_are_not_comparable(self, tmp_path, field):
        write_run(tmp_path, "a", [row("g1", 0.5)])
        write_run(tmp_path, "b", [row("g1", 0.5)], **{field: "different"})
        with pytest.raises(NotComparable, match=field):
            compare_runs(tmp_path, "a", "b", seed=0)

    def test_a_different_retriever_or_k_is_what_we_compare(self, tmp_path):
        write_run(tmp_path, "a", [row("g1", 0.5)])
        write_run(tmp_path, "b", [row("g1", 0.7)], retriever="clip", k=20)
        assert compare_runs(tmp_path, "a", "b", seed=0).metrics["recall"].n == 1

    def test_unknown_run(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            compare_runs(tmp_path, "nope", "nope2", seed=0)
