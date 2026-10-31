"""Routing-label pipeline (issue #161; PRD 10.3; ADR-021). Runs the real client against
the mock server through an in-process transport, so no port and no model are needed."""

import json
from datetime import UTC, datetime
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from refdesk import routing_labels as rl
from refdesk.llm import client as llm
from refdesk.llm.config import Budgets, ProvidersConfig
from refdesk.llm.mock_server import create_app
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus


def record(n: int, tags=("Flowers", "Still Life")) -> ArtworkRecord:
    rights = RightsRecord(
        source="met", object_id=str(n), flag_field="isPublicDomain", flag_value=True,
        licence_string=None, checked_at=datetime(2026, 10, 27, tzinfo=UTC),
        status=RightsStatus.OPEN,
    )  # fmt: skip
    return ArtworkRecord(
        id=f"met:{n}", source="met", object_id=str(n), title=f"Work {n}",
        artist="Workshop of Jan van Huysum", date="ca. 1720", date_begin=1715, date_end=1725,
        medium="Oil on canvas", classification="Paintings", subject_tags=tags,
        raw_record_ref=f"met/objects/{n}.json", rights=rights,
    )  # fmt: skip


class AppTransport:
    def __init__(self, app):
        self.http = TestClient(app)
        self.calls = 0

    def post_json(self, url, headers, payload):
        self.calls += 1
        response = self.http.post(urlsplit(url).path, json=payload)
        return response.status_code, response.json()


def mock_provider(family):
    return {"family": family, "cloud": False, "paid": False, "base_url": "http://mock/v1"}


CONFIG = ProvidersConfig.model_validate(
    {
        "providers": {
            "mock": mock_provider("mock"),
            "mock-judge": mock_provider("mock-judge"),
            "cloudy": {
                "family": "deepseek", "cloud": True, "paid": True,
                "base_url": "http://cloud/v1", "key_env": "CLOUD_KEY",
            },
        },
        "tiers": {
            "mock": {"provider": "mock", "model": "mock-1"},
            "mock-strong": {"provider": "mock", "model": "mock-2"},
            "mock-judge": {"provider": "mock-judge", "model": "mock-1"},
            "cloud-flash": {
                "provider": "cloudy", "model": "flash",
                "price_usd_per_mtok": {"input": 0.3, "output": 1.2},
            },
        },
        "routing": ["mock", "mock-strong"],
        "judges": ["mock-judge"],
    }
)  # fmt: skip

SETTINGS = rl.LabellingSettings(
    n_briefs=4, seed=0, items_per_brief=2, retriever="jaccard",
    quality_bar=rl.QualityBar(min_verified_share=1.0, placeholder=True),
)  # fmt: skip


class FixedRetriever:
    """Every brief gets the same two records, so tier results are comparable."""

    def __init__(self, records):
        self.records = records

    def records_for(self, brief, k):
        return self.records[:k]


def pipeline(script=None, *, tiers=("mock", "mock-strong"), judges=("mock-judge",),
             env=None, approved=False, budget=None):  # fmt: skip
    transport = AppTransport(create_app(script=script or ["ok"]))
    budgets = Budgets({} if budget is None else {"labelling_budget_usd": budget})
    p = rl.LabellingPipeline(
        CONFIG, budgets, SETTINGS, tiers=list(tiers), judges=list(judges),
        env=env or {}, approved=approved, transport=transport,
    )  # fmt: skip
    return p, transport


def run(p, n=4):
    briefs = rl.synthetic_briefs(n, seed=0)
    return p.run(briefs, FixedRetriever([record(1), record(2)]))


# --- the judge is never from the generator's family -------------------------------------


def test_judge_family_always_differs_from_the_generators():
    p, _ = pipeline()
    result = run(p)
    assert result.labels
    for label in result.labels:
        for attempt in label["tiers"].values():
            assert attempt["generator_family"] == "mock"
            assert attempt["judge_family"] == "mock-judge"
            assert attempt["judge_family"] != attempt["generator_family"]


def test_a_same_family_judge_is_skipped_for_one_from_another_family():
    p, _ = pipeline(judges=("mock-strong", "mock-judge"))  # mock-strong is family mock
    assert p.judge_for == {"mock": "mock-judge", "mock-strong": "mock-judge"}


def test_both_families_are_written_to_each_label():
    p, _ = pipeline()
    label = run(p).labels[0]
    assert label["label"] == "mock"
    assert label["generator_family"] == "mock"
    assert label["judge_family"] == "mock-judge"


# --- startup fails with no valid judge ---------------------------------------------------


@pytest.mark.parametrize("judges", [(), ("mock-strong",), ("mock",)])
def test_startup_fails_with_no_valid_judge_before_any_request(judges):
    transport = AppTransport(create_app())
    with pytest.raises(llm.NoValidJudge):
        rl.LabellingPipeline(
            CONFIG, Budgets({}), SETTINGS, tiers=["mock", "mock-strong"],
            judges=list(judges), env={}, transport=transport,
        )  # fmt: skip
    assert transport.calls == 0


# --- a blocked paid call is a hard error -------------------------------------------------


def test_paid_tier_without_approve_fails_at_startup_and_never_falls_back():
    transport = AppTransport(create_app())
    with pytest.raises(llm.NotApproved):
        rl.LabellingPipeline(
            CONFIG, Budgets({"labelling_budget_usd": 20}), SETTINGS,
            tiers=["mock", "cloud-flash"], judges=["mock-judge"],
            env={"CLOUD_KEY": "k"}, approved=False, transport=transport,
        )  # fmt: skip
    assert transport.calls == 0


@pytest.mark.parametrize(
    ("env", "budget", "error"),
    [({}, 20, llm.MissingKey), ({"CLOUD_KEY": "k"}, None, llm.MissingBudget)],
)
def test_paid_tier_without_key_or_budget_fails_at_startup(env, budget, error):
    transport = AppTransport(create_app())
    budgets = Budgets({} if budget is None else {"labelling_budget_usd": budget})
    with pytest.raises(error):
        rl.LabellingPipeline(
            CONFIG, budgets, SETTINGS, tiers=["mock", "cloud-flash"], judges=["mock-judge"],
            env=env, approved=True, transport=transport,
        )  # fmt: skip
    assert transport.calls == 0


def test_a_paid_call_blocked_mid_run_is_a_hard_error_not_a_label():
    # Approved, key and budget present, but the budget is too small for the first call.
    p, transport = pipeline(
        tiers=("mock", "cloud-flash"), env={"CLOUD_KEY": "k"}, approved=True, budget=1e-9
    )
    with pytest.raises(llm.BudgetExceeded):
        run(p)
    # Only the free tier's calls were made; nothing was sent in place of the paid call.
    assert all(c.tier != "cloud-flash" for c in p.calls)


def test_a_provider_error_is_a_hard_error():
    p, _ = pipeline(script=["500"])
    with pytest.raises(llm.ProviderError):
        run(p)


# --- labels -----------------------------------------------------------------------------


def test_label_is_the_cheapest_tier_that_met_the_bar():
    p, _ = pipeline()
    for label in run(p).labels:
        assert label["label"] == "mock"  # first in routing order, and it passed
        assert label["tiers"]["mock"]["met_bar"] is True


def test_no_label_when_no_tier_met_the_bar():
    p, _ = pipeline(script=["unsupported"])  # the judge rejects every claim
    for label in run(p).labels:
        assert label["label"] is None
        assert label["label_reason"] == "no tier met the quality bar"
        assert all(not t["met_bar"] for t in label["tiers"].values())


def test_every_label_says_where_the_brief_was_sent_and_is_synthetic():
    p, _ = pipeline()
    label = run(p).labels[0]
    assert label["sent_to"] == ["mock", "mock-judge"]
    assert label["provenance"] == "synthetic"
    assert label["quality_bar_placeholder"] is True


def test_models_load_once_per_phase():
    loads = []
    transport = AppTransport(create_app())
    p = rl.LabellingPipeline(
        CONFIG, Budgets({}), SETTINGS, tiers=["mock", "mock-strong"], judges=["mock-judge"],
        env={}, transport=transport, ensure_model=loads.append,
    )  # fmt: skip
    run(p)
    assert loads == ["mock-1", "mock-1", "mock-2", "mock-1"]  # gen, judge, gen, judge


# --- synthetic briefs -------------------------------------------------------------------


def test_synthetic_briefs_are_deterministic_unique_and_marked_synthetic():
    a, b = rl.synthetic_briefs(1500, seed=0), rl.synthetic_briefs(1500, seed=0)
    assert a == b
    assert len(a) == 1500
    assert len({x.brief for x in a}) == 1500
    assert all(x.provenance == "synthetic" for x in a)
    assert {x.brief_type for x in a} == set(rl.TEMPLATES)
    assert rl.synthetic_briefs(10, seed=1) != rl.synthetic_briefs(10, seed=0)


# --- dry run ----------------------------------------------------------------------------


def test_dry_run_estimates_calls_tokens_and_cost_without_any_request():
    transport = AppTransport(create_app())
    p = rl.LabellingPipeline(
        CONFIG, Budgets({"labelling_budget_usd": 20}), SETTINGS,
        tiers=["mock", "cloud-flash"], judges=["mock-judge"], env={}, transport=transport,
        dry_run=True,
    )  # fmt: skip
    estimate = p.estimate(rl.synthetic_briefs(4, seed=0), FixedRetriever([record(1), record(2)]))
    assert transport.calls == 0
    by_tier = {t.tier: t for t in estimate.tiers}
    assert by_tier["mock"].generation_calls == 8  # 4 briefs x 2 items
    assert by_tier["mock"].cost_usd == 0
    assert by_tier["cloud-flash"].cost_usd > 0
    assert by_tier["cloud-flash"].worst_case_cost_usd == pytest.approx(
        2 * by_tier["cloud-flash"].cost_usd
    )
    assert estimate.budget_usd == 20
    assert estimate.fits_budget
    assert "cloud-flash" in rl.format_estimate(estimate)


# --- outputs ----------------------------------------------------------------------------


def test_outputs_write_labels_and_manifest_and_never_overwrite(tmp_path):
    p, _ = pipeline()
    result = run(p)
    paths = rl.write_outputs(result, root=tmp_path, date="2026-10-31")
    rows = [json.loads(x) for x in paths["labels"].read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 4
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["tiers"] == ["mock", "mock-strong"]
    assert manifest["judge_for"] == {"mock": "mock-judge", "mock-strong": "mock-judge"}
    assert manifest["quality_bar"]["placeholder"] is True
    assert manifest["counts"]["labelled"]["mock"] == 4
    assert manifest["provenance"] == "synthetic"
    assert manifest["approved"] is False
    assert manifest["models_reported"]["mock"] == ["mock-1"]
    with pytest.raises(FileExistsError):
        rl.write_outputs(result, root=tmp_path, date="2026-10-31")
