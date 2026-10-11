"""Eval harness: run, manifest and config hash, report, history (issue #11)."""

import csv
import json
from datetime import UTC, datetime

import pytest

from refdesk.evals.golden import GoldenCase
from refdesk.evals.harness import EvalConfig, run_eval, write_outputs
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus

CHECKED = datetime(2026, 10, 11, tzinfo=UTC)


def rec(object_id, tags, status=RightsStatus.OPEN):
    open_ = status is RightsStatus.OPEN
    rights = RightsRecord(
        source="met",
        object_id=object_id,
        flag_field="isPublicDomain",
        flag_value=open_,
        licence_string=None,
        checked_at=CHECKED,
        status=status,
    )
    return ArtworkRecord(
        id=f"met:{object_id}",
        source="met",
        object_id=object_id,
        title=f"Work {object_id}",
        classification="Paintings",
        subject_tags=tuple(tags),
        raw_record_ref=f"met/objects/{object_id}.json",
        rights=rights,
    )


RECORDS = [
    rec("1", ["Flowers", "Still Life"]),
    rec("2", ["Flowers"]),
    rec("3", ["Boats"], RightsStatus.PERMISSION_REQUIRED),
    rec("4", ["Boats", "Night"]),
]


def case(id_, brief, expected, **extra):
    fields = dict(
        id=id_,
        brief=brief,
        expected=[{"record_id": r, "grade": 2} for r in expected],
        source="synthetic:claude-code",
        labeller="claude-code",
        difficulty="easy",
        version="v0-synthetic",
        provenance="synthetic",
        corpus_version="met:4:test",
        rule={"tags_any": ["x"]},
    )
    return GoldenCase(**(fields | extra))


CASES = [
    case("g0-001", "flowers still life", ["met:1", "met:2"]),
    case("g0-002", "boats", ["met:3", "met:4"], usage_mode="reproduction", difficulty="medium"),
    case("g0-003", "zeppelin", ["met:1"], difficulty="hard"),
    case("g0-004", "paint like a living artist", [], expected_decision="decline", rule=None),
]


def config(**overrides):
    fields = dict(
        retriever="jaccard",
        retriever_params={},
        k=2,
        seed=0,
        n_boot=500,
        golden_path="evals/golden/test.jsonl",
        golden_sha256="abc",
        golden_version="v0-synthetic",
        corpus_version="met:4:test",
        git_sha="deadbeef",
        git_dirty=False,
    )
    return EvalConfig(**(fields | overrides))


@pytest.fixture
def result():
    return run_eval(JaccardRetriever(RECORDS), CASES, RECORDS, config())


class TestRun:
    def test_per_case_scores(self, result):
        rows = {r["id"]: r for r in result.rows}
        assert rows["g0-001"]["recall"] == 1.0
        assert rows["g0-003"]["recall"] == 0.0
        assert rows["g0-003"]["failure"] == "no_results"

    def test_decline_cases_are_not_scored_by_a_retriever(self, result):
        rows = {r["id"]: r for r in result.rows}
        assert rows["g0-004"]["status"] == "not applicable: decline case"
        assert result.summary["recall"]["n"] == 3

    def test_reproduction_cases_report_the_open_rights_share(self, result):
        rows = {r["id"]: r for r in result.rows}
        # met:3 is permission required, so reproduction mode filters it out (#35).
        assert rows["g0-002"]["open_share"] == 1.0
        assert rows["g0-001"]["open_share"] is None  # reference-only case

    def test_every_metric_has_an_interval(self, result):
        for metric in ("recall", "precision", "mrr"):
            s = result.summary[metric]
            assert s["low"] <= s["mean"] <= s["high"]

    def test_slices_by_difficulty_and_usage_mode(self, result):
        assert set(result.slices["difficulty"]) == {"easy", "medium", "hard"}
        assert set(result.slices["usage_mode"]) == {"reference_only", "reproduction"}

    def test_determinism_is_checked(self, result):
        assert result.deterministic is True


class TestConfigHash:
    def test_same_config_same_hash(self):
        assert config().config_hash() == config().config_hash()

    def test_any_change_changes_the_hash(self):
        assert config(k=3).config_hash() != config().config_hash()
        assert config(golden_sha256="other").config_hash() != config().config_hash()


class TestOutputs:
    def test_writes_manifest_report_and_history(self, result, tmp_path):
        paths = write_outputs(result, root=tmp_path, date="2026-10-11")
        manifest = json.loads(paths["manifest"].read_text("utf-8"))
        assert manifest["config_hash"] == result.config.config_hash()
        assert manifest["config"]["golden_version"] == "v0-synthetic"

        report = paths["report"].read_text("utf-8")
        assert result.config.config_hash() in report
        assert "v0-synthetic" in report
        assert "95% CI" in report
        assert "Never use for claims" in report  # synthetic golden set warning
        assert "No gate policy" in report

        with paths["history"].open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows[-1]["config_hash"] == result.config.config_hash()
        assert rows[-1]["golden_version"] == "v0-synthetic"

    def test_history_appends_one_row_per_metric_per_run(self, result, tmp_path):
        def count(path):
            with path.open(encoding="utf-8") as f:
                return len(list(csv.DictReader(f)))

        first = count(write_outputs(result, root=tmp_path, date="2026-10-11")["history"])
        second = count(write_outputs(result, root=tmp_path, date="2026-10-11")["history"])
        assert first == len(result.summary)
        assert second == 2 * first  # appended, not overwritten

    def test_report_quotes_the_gate_policy_status(self, result, tmp_path):
        policy = tmp_path / "docs" / "eval-gate-policy.md"
        policy.parent.mkdir(parents=True)
        policy.write_text("# Eval gate policy\n\n- **Status:** draft. Tripwire only.\n")
        report = write_outputs(result, root=tmp_path, date="2026-10-11")["report"]
        assert "Gates: draft. Tripwire only." in report.read_text("utf-8")


def test_case_query_carries_the_usage_mode():
    from refdesk.evals.harness import case_query

    assert case_query(CASES[1], k=12).usage_mode == "reproduction"


def test_a_second_run_with_a_different_config_never_overwrites_a_report(tmp_path):
    first = run_eval(JaccardRetriever(RECORDS), CASES, RECORDS, config(k=2))
    second = run_eval(JaccardRetriever(RECORDS), CASES, RECORDS, config(k=3))
    a = write_outputs(first, root=tmp_path, date="2026-10-11")["report"]
    b = write_outputs(second, root=tmp_path, date="2026-10-11")["report"]
    assert a != b and a.exists() and b.exists()
