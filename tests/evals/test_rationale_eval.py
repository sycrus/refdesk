"""Rationale eval: verifier pass rates over a golden set's top-k items (issue #102; ADR-018,
ADR-022). Runs the real Reasoner against the mock server in-process; hand-computed rates."""

from datetime import UTC, datetime
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from refdesk.evals.golden import GoldenCase
from refdesk.evals.harness import EvalConfig
from refdesk.evals.rationale_eval import (
    RATIONALE_METRICS,
    run_rationale_eval,
    write_rationale_outputs,
)
from refdesk.llm.config import ProvidersConfig
from refdesk.llm.mock_server import create_app
from refdesk.reasoning import Reasoner
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus

CHECKED = datetime(2026, 10, 27, tzinfo=UTC)


def rec(i, tags):
    rights = RightsRecord(
        source="met", object_id=str(i), flag_field="isPublicDomain", flag_value=True,
        licence_string=None, checked_at=CHECKED, status=RightsStatus.OPEN,
    )  # fmt: skip
    return ArtworkRecord(
        id=f"met:{i}", source="met", object_id=str(i), title=f"Painting {i}",
        artist=f"Painter {i}", date="1650", date_begin=1650, date_end=1650,
        medium="Oil on canvas", classification="Paintings", subject_tags=tags,
        raw_record_ref=f"met/objects/{i}.json", rights=rights,
    )  # fmt: skip


RECORDS = [rec(1, ("Boats",)), rec(2, ("Boats", "Harbors")), rec(3, ("Flowers",))]


def case(id_, brief, decision="retrieve", difficulty="easy"):
    return GoldenCase(
        id=id_, brief=brief, expected_decision=decision,
        expected=[{"record_id": "met:1", "grade": 2}] if decision == "retrieve" else [],
        source="synthetic:claude-code", labeller="claude-code", difficulty=difficulty,
        version="v0-synthetic", provenance="synthetic", corpus_version="met:3:test",
    )  # fmt: skip


CASES = [
    case("g0-001", "boats"),
    case("g0-002", "flowers", difficulty="hard"),
    case("g0-003", "paint like a living artist", decision="decline"),
]

CONFIG = ProvidersConfig.model_validate(
    {
        "providers": {
            "mock": {"family": "mock", "cloud": False, "paid": False, "base_url": "http://m/v1"},
            "mock-judge": {
                "family": "mock-judge", "cloud": False, "paid": False, "base_url": "http://j/v1",
            },
        },
        "tiers": {
            "mock": {"provider": "mock", "model": "mock-1"},
            "mock-judge": {"provider": "mock-judge", "model": "mock-1"},
        },
        "routing": ["mock"],
        "judges": ["mock-judge"],
    }
)  # fmt: skip


class Mocks:
    def __init__(self, generator=("ok",), judge=("ok",)):
        self.gen = TestClient(create_app(script=list(generator)))
        self.judge = TestClient(create_app(script=list(judge)))

    def post_json(self, url, headers, payload):
        http = self.judge if urlsplit(url).hostname == "j" else self.gen
        response = http.post(urlsplit(url).path, json=payload)
        return response.status_code, response.json()


def config(**overrides):
    fields = dict(
        retriever="jaccard",
        retriever_params={"generator_tier": "mock", "judge_tier": "mock-judge"},
        k=2, seed=0, n_boot=200, golden_path="evals/golden/test.jsonl", golden_sha256="s",
        golden_version="v0-synthetic", corpus_version="met:3:test", git_sha="abc", git_dirty=False,
        model="mock-1",
    )  # fmt: skip
    return EvalConfig(**(fields | overrides))


def run(mocks):
    reasoner = Reasoner(CONFIG, generator_tier="mock", transport=mocks, env={})
    return run_rationale_eval(JaccardRetriever(RECORDS), reasoner, CASES, RECORDS, config())


class TestRates:
    def test_every_item_verified_when_both_stages_pass(self):
        result = run(Mocks())
        assert set(result.summary) == set(RATIONALE_METRICS)
        for metric in RATIONALE_METRICS:
            assert result.summary[metric]["mean"] == pytest.approx(1.0)
            assert result.summary[metric]["n"] == 2  # two retrieve cases; the decline is skipped

    def test_judge_failures_lower_judge_pass_and_verified_but_not_code_pass(self):
        result = run(Mocks(judge=("unsupported",)))
        assert result.summary["usable"]["mean"] == pytest.approx(1.0)
        assert result.summary["code_pass"]["mean"] == pytest.approx(1.0)
        assert result.summary["judge_pass"]["mean"] == pytest.approx(0.0)
        assert result.summary["verified"]["mean"] == pytest.approx(0.0)

    def test_unusable_rationales_count_against_usable(self):
        result = run(Mocks(generator=("malformed",)))
        assert result.summary["usable"]["mean"] == pytest.approx(0.0)
        assert result.summary["verified"]["mean"] == pytest.approx(0.0)
        assert result.failures  # reasons are counted

    def test_decline_cases_are_not_applicable(self):
        rows = {r["id"]: r for r in run(Mocks()).rows}
        assert rows["g0-003"]["status"] == "not applicable: decline case"


class TestOutputs:
    def test_report_says_synthetic_is_plumbing_and_name_has_the_config_hash(self, tmp_path):
        result = run(Mocks())
        paths = write_rationale_outputs(result, root=tmp_path, date="2026-10-27")
        h = result.config.config_hash()
        assert paths["report"].name == f"rationale-eval-2026-10-27-mock-{h}.md"
        text = paths["report"].read_text(encoding="utf-8")
        assert "plumbing only" in text and "not a claim" in text
        assert "verifier" in text and "not human-rated" in text
        assert (tmp_path / "runs" / h / "manifest.json").exists()

    def test_a_second_run_never_overwrites_a_report(self, tmp_path):
        result = run(Mocks())
        write_rationale_outputs(result, root=tmp_path, date="2026-10-27")
        with pytest.raises(FileExistsError):
            write_rationale_outputs(result, root=tmp_path, date="2026-10-27")
