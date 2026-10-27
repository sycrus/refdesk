"""Boards that generate and verify (issue #98; ADR-022; PRD 8B gates G1 and G2; acceptance
scenarios 1, 4 and 6).

The real LLM client talks to the mock server in-process. The mock generator answers with
claims built from each record; a mock judge (its own family, so the cross-family rule
holds) answers SUPPORTED unless scripted otherwise.
"""

from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from test_boards import RECORDS, conforms, rec

from refdesk.api.app import app, get_service
from refdesk.boards import BoardService, RunStore
from refdesk.llm.config import ProvidersConfig
from refdesk.llm.mock_server import create_app
from refdesk.reasoning import Reasoner
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.schema import RightsStatus
from refdesk.wording import AttributionStatus, StopReason

# Records with an artist, so attribution can be verified.
ARTISTS = {"1": "Workshop of Jan Porcellis", "2": "Willem van de Velde", "3": "Rachel Ruysch"}
WITH_ARTISTS = [r.model_copy(update={"artist": ARTISTS[r.object_id]}) for r in RECORDS]

CONFIG = ProvidersConfig.model_validate(
    {
        "providers": {
            "mock": {"family": "mock", "cloud": False, "paid": False, "base_url": "http://m/v1"},
            "mock-judge": {
                "family": "mock-judge", "cloud": False, "paid": False, "base_url": "http://j/v1",
            },
            "cloudy": {
                "family": "deepseek", "cloud": True, "paid": True,
                "base_url": "http://c/v1", "key_env": "CLOUD_KEY",
            },
        },
        "tiers": {
            "mock": {"provider": "mock", "model": "mock-1"},
            "mock-judge": {"provider": "mock-judge", "model": "mock-1"},
            "cloud-flash": {
                "provider": "cloudy", "model": "flash",
                # Output priced high: one call's worst case (600 tokens = USD 0.60) fits
                # a 0.65 cap, but a second one cannot fit after the first one's cost.
                "price_usd_per_mtok": {"input": 0.0, "output": 1000.0},
            },
        },
        "routing": ["mock"],
        "judges": ["mock-judge"],
    }
)  # fmt: skip


class Mocks:
    """Generator and judge: two mock apps behind one transport, routed by host."""

    def __init__(self, generator_script=None, judge_script=None):
        self.apps = {
            "j": TestClient(create_app(script=judge_script or ["ok"])),
            "default": TestClient(create_app(script=generator_script or ["ok"])),
        }
        self.calls = []

    def post_json(self, url, headers, payload):
        host = urlsplit(url).hostname
        self.calls.append(host)
        http = self.apps["j"] if host == "j" else self.apps["default"]
        response = http.post(urlsplit(url).path, json=payload)
        return response.status_code, response.json()


def service(tmp_path, mocks, generator_tier="mock", records=WITH_ARTISTS, **reasoner_args):
    reasoner = Reasoner(
        CONFIG, generator_tier=generator_tier, transport=mocks,
        env={"CLOUD_KEY": "k"}, **reasoner_args,
    )  # fmt: skip
    return BoardService(
        RunStore(tmp_path / "runs.sqlite"), lambda: records, JaccardRetriever, "jaccard",
        reasoner=reasoner,
    )  # fmt: skip


def run(tmp_path, mocks, body=None, **kwargs):
    app.dependency_overrides[get_service] = lambda: service(tmp_path, mocks, **kwargs)
    try:
        client = TestClient(app)
        created = client.post("/boards", json={"brief": "boats", **(body or {})})
        assert created.status_code == 202, created.text
        view = client.get(f"/runs/{created.json()['run_id']}").json()
    finally:
        app.dependency_overrides.clear()
    conforms(view, "RunView")
    return view


def gate(view, gate_id):
    return next(g for g in view["gates"] if g["id"] == gate_id)


class TestExplainedItems:
    def test_every_card_has_a_rationale_and_is_verified_when_both_stages_pass(self, tmp_path):
        view = run(tmp_path, Mocks())
        assert view["state"] == "done" and view["items"]
        for item in view["items"]:
            assert item["rationale"], item
            assert item["attribution_status"] == AttributionStatus.VERIFIED
            assert item["flag_reasons"] == []
            assert item["tier_used"] == "mock"

    def test_claims_become_evidence_chips_with_the_records_own_values(self, tmp_path):
        view = run(tmp_path, Mocks())
        item = next(i for i in view["items"] if i["record"]["object_id"] == "1")
        chips = {(e["field"], e["value"]) for e in item["evidence"]}
        assert ("artist", "Workshop of Jan Porcellis") in chips
        assert ("medium", "Oil on canvas") in chips

    def test_records_where_the_brief_went_and_which_models_answered(self, tmp_path):
        view = run(tmp_path, Mocks())
        assert view["sent_to"] == ["mock", "mock-judge"]
        assert view["models_used"] == {"generator": "mock-1", "judge": "mock-1"}
        assert view["cost"]["spent_usd"] == 0.0

    def test_g2_passes_only_when_every_item_is_verified(self, tmp_path):
        view = run(tmp_path, Mocks())
        assert gate(view, "G2")["state"] == "passed"
        assert gate(view, "G3")["state"] == "skipped"


class TestFlaggedItems:
    def test_a_judge_failure_flags_the_item_and_names_the_claim(self, tmp_path):
        view = run(tmp_path, Mocks(judge_script=["unsupported"]))
        for item in view["items"]:
            assert item["attribution_status"] == AttributionStatus.NEEDS_HUMAN_CHECK
            assert any("claim 1" in r for r in item["flag_reasons"])
        assert gate(view, "G2")["state"] == "blocked"
        assert gate(view, "G3")["state"] == "active"

    def test_an_unusable_rationale_says_why_there_is_none(self, tmp_path):
        view = run(tmp_path, Mocks(generator_script=["malformed"]))
        for item in view["items"]:
            assert item["rationale"] is None
            assert item["attribution_status"] == AttributionStatus.NEEDS_HUMAN_CHECK
            assert any("rationale unusable" in r for r in item["flag_reasons"])

    def test_a_code_check_failure_is_never_verified_even_if_the_judge_passes(self, tmp_path):
        no_rights_field = rec("9", ("Boats",), medium="Oil on canvas", artist="Jan Porcellis")
        no_rights_field = no_rights_field.model_copy(
            update={
                "rights": no_rights_field.rights.model_copy(
                    update={
                        "flag_field": None,
                        "flag_value": None,
                        "status": RightsStatus.UNVERIFIED,
                    }
                )
            }
        )
        view = run(tmp_path, Mocks(), records=[no_rights_field])
        (item,) = view["items"]
        assert item["attribution_status"] == AttributionStatus.NEEDS_HUMAN_CHECK
        assert any("structured source field" in r for r in item["flag_reasons"])


class TestBudget:
    """Scenario 1: the run stops before a model call that would exceed the cap."""

    def test_stops_before_the_call_that_would_exceed_the_cap(self, tmp_path):
        mocks = Mocks()
        view = run(
            tmp_path, mocks, body={"budget_cap_usd": 0.65}, generator_tier="cloud-flash",
            approved=True,
        )  # fmt: skip
        assert view["state"] == "stopped"
        assert view["stop_reason"] == StopReason.BUDGET_CAP
        assert view["cost"]["spent_usd"] <= 0.65
        explained = [i for i in view["items"] if i["rationale"]]
        assert len(explained) == len([h for h in mocks.calls if h == "c"]) == 1
        for item in view["items"]:
            if not item["rationale"]:
                assert any("budget cap" in r for r in item["flag_reasons"])
        assert gate(view, "G1")["state"] == "blocked"

    def test_a_paid_tier_without_approval_stops_loudly_with_no_call(self, tmp_path):
        mocks = Mocks()
        view = run(tmp_path, mocks, generator_tier="cloud-flash")
        assert view["stop_reason"] == StopReason.SOURCE_UNAVAILABLE
        assert "approve" in view["stop_detail"]
        assert mocks.calls == []


class TestKeepLocal:
    """Scenario 4: a keep-local brief never reaches a cloud tier."""

    def test_keep_local_with_a_cloud_generator_is_declined_with_no_call(self, tmp_path):
        mocks = Mocks()
        view = run(tmp_path, mocks, body={"keep_local": True}, generator_tier="cloud-flash")
        assert view["stop_reason"] == StopReason.DECLINED
        assert "keep-local" in view["stop_detail"]
        assert mocks.calls == [] and view["sent_to"] == []


class TestNoJudge:
    def test_without_a_judge_outside_the_generators_family_nothing_is_verified(self, tmp_path):
        view = run(tmp_path, Mocks(), judge_tier=None, judges=[])
        for item in view["items"]:
            assert item["rationale"]
            assert item["attribution_status"] == AttributionStatus.NEEDS_HUMAN_CHECK
            assert any("no judge" in r.lower() for r in item["flag_reasons"])
        assert view["sent_to"] == ["mock"]


@pytest.mark.parametrize("brief", ["zeppelins"])
def test_no_results_still_stops_with_pool_exhausted_and_no_model_call(tmp_path, brief):
    mocks = Mocks()
    view = run(tmp_path, mocks, body={"brief": brief})
    assert view["stop_reason"] == StopReason.POOL_EXHAUSTED and mocks.calls == []


def test_a_model_that_cannot_load_stops_the_run_loudly(tmp_path):
    def no_gpu(model):
        raise RuntimeError("only 2000 MiB free")

    mocks = Mocks()
    view = run(tmp_path, mocks, ensure_model=no_gpu)
    assert view["state"] == "stopped"
    assert view["stop_reason"] == StopReason.SOURCE_UNAVAILABLE
    assert "only 2000 MiB free" in view["stop_detail"]
    assert mocks.calls == []


class TestPinnedPrompts:
    """Prompt versions are pinned in config, so adding v2 never changes boards silently."""

    def test_the_reasoner_uses_the_pinned_versions(self):
        r = Reasoner(CONFIG, generator_tier="mock", prompts={"fit": "fit-v1"})
        assert r.prompts["fit"].name == "fit-v1"
        assert set(r.prompts) == {"rationale", "judge", "fit"}

    def test_the_repository_config_pins_every_prompt(self):
        import yaml

        config = yaml.safe_load(open("config/retrieval.yaml", encoding="utf-8"))
        assert set(config["api"]["reasoning"]["prompts"]) == {"rationale", "judge", "fit"}
