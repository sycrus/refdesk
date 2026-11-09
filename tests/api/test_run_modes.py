"""Run-mode indicators (issue #251): how a board's brief was answered, and what a new
board here would use.

Five modes. `recorded` in the demo profile (ADR-025: the hosted demo replays runs baked
into the image, so nothing runs there); `mock` when a mock provider answered (test
answers, not real models); `local` when only non-cloud providers answered; `cloud` when
any cloud provider saw the brief; `retrieval_only` when no model was called at all. The
mode is derived once, in the API, from the run's own `sent_to` and the providers config
— the UI never infers it, because "where did this brief go" is a trust statement, and a
UI that guesses it can guess wrong.

`/healthz` names the configured generator and judge tiers (names only, never a base
URL, key or env var name), so the stage panel can say what a new board would use.
"""

import pytest
from fastapi.testclient import TestClient

from refdesk.api.app import app, get_service
from refdesk.api.models import BoardRequest, Cost, LoopState, RunView
from refdesk.boards import BoardService, RunStore, cloud_providers, run_mode
from refdesk.llm.config import ProvidersConfig
from refdesk.reasoning import Reasoner
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.wording import RunMode
from test_boards_reasoning import CONFIG, WITH_ARTISTS, Mocks

S = LoopState

# The test config's providers, with the mock flag #251 adds to providers.yaml. A deep
# copy: CONFIG is shared with every other reasoning test.
FLAGGED = CONFIG.model_copy(deep=True)
FLAGGED.providers["mock"].mock = True
FLAGGED.providers["mock-judge"].mock = True

# A standalone config with all four natures, for the pure derivation tests.
PROVIDERS = ProvidersConfig.model_validate(
    {
        "providers": {
            "local": {"family": "q", "cloud": False, "paid": False, "base_url": "http://l/v1"},
            "local-judge": {"family": "m", "cloud": False, "paid": False, "base_url": "http://lj/v1"},
            "mock": {"family": "mock", "cloud": False, "paid": False, "mock": True, "base_url": "http://m/v1"},
            "cloudy": {
                "family": "d", "cloud": True, "paid": True,
                "base_url": "http://c/v1", "key_env": "CLOUD_KEY",
            },
        },
        "tiers": {
            "local": {"provider": "local", "model": "l-1"},
            "local-judge": {"provider": "local-judge", "model": "lj-1"},
            "mock": {"provider": "mock", "model": "m-1"},
            "cloud-flash": {"provider": "cloudy", "model": "c-1"},
        },
        "routing": ["local"],
        "judges": ["local-judge"],
    }
)  # fmt: skip


def default_stamp(providers):
    """The stamp default_service wires (issue #251): the derived mode plus the cloud
    provider names, assigned in place — that is the store's annotate contract."""

    def annotate(view: RunView) -> None:
        view.mode = run_mode(view.sent_to, providers)
        view.cloud_providers = cloud_providers(view.sent_to, providers)

    return annotate


def recorded_stamp(view: RunView) -> None:
    """The demo profile's stamp: every run is a recording."""
    view.mode = RunMode.RECORDED


class TestDeriveMode:
    def test_nothing_sent_is_retrieval_only(self):
        assert run_mode([], PROVIDERS) is RunMode.RETRIEVAL_ONLY

    def test_local_providers_only_are_local(self):
        assert run_mode(["local", "local-judge"], PROVIDERS) is RunMode.LOCAL

    def test_one_cloud_provider_makes_the_whole_board_cloud(self):
        assert run_mode(["local", "cloudy"], PROVIDERS) is RunMode.CLOUD

    def test_mock_providers_are_mock_even_beside_a_local_one(self):
        assert run_mode(["mock"], PROVIDERS) is RunMode.MOCK
        assert run_mode(["mock", "local"], PROVIDERS) is RunMode.MOCK

    def test_cloud_wins_over_mock(self):
        # The strongest warning wins: a mock beside a cloud provider is not the fact to
        # state first.
        assert run_mode(["mock", "cloudy"], PROVIDERS) is RunMode.CLOUD

    def test_a_provider_no_longer_in_the_config_gives_no_mode(self):
        # Config edited after the run: no honest indicator beats a wrong one.
        assert run_mode(["gone"], PROVIDERS) is None

    def test_without_a_config_only_retrieval_only_is_known(self):
        # Services built without the providers config (most tests): an empty sent_to is
        # still derivable; anything else is not.
        assert run_mode([], None) is RunMode.RETRIEVAL_ONLY
        assert run_mode(["mock"], None) is None


class TestStoreStampsMode:
    """The store stamps `mode` (and `created_at`, for the recorded date) on every view it
    returns, so demo runs baked into an image are `recorded` without a rewrite."""

    REQUEST = BoardRequest(brief="boats")

    def view(self, sent_to):
        return RunView(
            run_id="run-modes1",
            state=S.DONE,
            gates=[],
            items=[],
            cost=Cost(spent_usd=0.0, cap_usd=0.05),
            keep_local=True,
            sent_to=sent_to,
        )

    def test_a_stored_run_is_stamped_on_save_and_on_read(self, tmp_path):
        store = RunStore(tmp_path / "runs.sqlite", annotate=default_stamp(PROVIDERS))
        store.save(self.view(["mock"]), self.REQUEST)
        read = store.get("run-modes1")
        assert read.mode is RunMode.MOCK
        assert read.created_at is not None
        assert read.cloud_providers == []

    def test_the_demo_override_marks_every_run_recorded(self, tmp_path):
        store = RunStore(tmp_path / "runs.sqlite", annotate=recorded_stamp)
        store.save(self.view(["ollama", "ollama-microsoft"]), self.REQUEST)
        assert store.get("run-modes1").mode is RunMode.RECORDED

    def test_a_cloud_run_names_its_cloud_providers(self, tmp_path):
        store = RunStore(tmp_path / "runs.sqlite", annotate=default_stamp(PROVIDERS))
        store.save(self.view(["local", "cloudy"]), self.REQUEST)
        read = store.get("run-modes1")
        assert read.mode is RunMode.CLOUD and read.cloud_providers == ["cloudy"]

    def test_without_an_annotate_the_mode_stays_unset(self, tmp_path):
        store = RunStore(tmp_path / "runs.sqlite")
        store.save(self.view(["mock"]), self.REQUEST)
        assert store.get("run-modes1").mode is None


class TestBoardMode:
    """A board run end to end carries its mode on the view and in the history list."""

    def service(self, tmp_path, annotate, reasoner=True):
        return BoardService(
            RunStore(tmp_path / "runs.sqlite", annotate=annotate),
            lambda: WITH_ARTISTS,
            JaccardRetriever,
            "jaccard",
            reasoner=Reasoner(CONFIG, generator_tier="mock", transport=Mocks()) if reasoner else None,
        )  # fmt: skip

    def test_a_finished_mock_board_is_mock_here_and_in_history(self, tmp_path):
        svc = self.service(tmp_path, default_stamp(FLAGGED))
        request = BoardRequest(brief="boats", target_items=1)
        run_id = svc.create(request).run_id
        view = svc.execute(run_id, request)
        assert view.state is S.DONE
        assert view.mode is RunMode.MOCK
        assert view.created_at is not None
        row = svc.history()[-1]
        assert row.run_id == run_id and row.mode is RunMode.MOCK

    def test_a_retrieval_only_board_is_retrieval_only(self, tmp_path):
        svc = self.service(tmp_path, default_stamp(FLAGGED), reasoner=False)
        request = BoardRequest(brief="boats", target_items=1)
        run_id = svc.create(request).run_id
        view = svc.execute(run_id, request)
        assert view.state is S.DONE and view.mode is RunMode.RETRIEVAL_ONLY

    def test_the_demo_profile_marks_a_run_recorded(self, tmp_path):
        svc = self.service(tmp_path, recorded_stamp)
        request = BoardRequest(brief="boats", target_items=1)
        run_id = svc.create(request).run_id
        assert svc.execute(run_id, request).mode is RunMode.RECORDED
        assert svc.history()[-1].mode is RunMode.RECORDED


class TestEndpoint:
    def test_get_run_and_history_carry_the_mode(self, tmp_path):
        svc = BoardService(
            RunStore(tmp_path / "runs.sqlite", annotate=default_stamp(FLAGGED)),
            lambda: WITH_ARTISTS,
            JaccardRetriever,
            "jaccard",
            reasoner=Reasoner(CONFIG, generator_tier="mock", transport=Mocks()),
        )  # fmt: skip
        run_id = svc.create(BoardRequest(brief="boats", target_items=1)).run_id
        svc.execute(run_id, BoardRequest(brief="boats", target_items=1))
        app.dependency_overrides[get_service] = lambda: svc
        try:
            client = TestClient(app)
            assert client.get(f"/runs/{run_id}").json()["mode"] == "mock"
            row = next(r for r in client.get("/runs").json() if r["run_id"] == run_id)
            assert row["mode"] == "mock"
        finally:
            app.dependency_overrides.clear()


class TestHealthz:
    """/healthz stays liveness (it reads config files only, never the store or a model
    backend) and now says how a new board would run here."""

    @pytest.fixture(autouse=True)
    def no_env_overrides(self, monkeypatch):
        monkeypatch.delenv("REFDESK_GENERATOR_TIER", raising=False)
        monkeypatch.delenv("REFDESK_JUDGE_TIER", raising=False)

    def client(self):
        return TestClient(app)

    def test_the_committed_default_is_the_mock_server(self):
        body = self.client().get("/healthz").json()
        assert body["mode"] == "mock"
        assert body["generator"] == {
            "tier": "mock", "provider": "mock", "model": "mock-1",
            "cloud": False, "mock": True,
        }  # fmt: skip
        assert body["judge"] == {
            "tier": "mock-judge", "provider": "mock-judge", "model": "mock-1",
            "cloud": False, "mock": True,
        }  # fmt: skip

    def test_retrieval_only_names_no_tiers(self, monkeypatch):
        monkeypatch.setenv("REFDESK_GENERATOR_TIER", "none")
        body = self.client().get("/healthz").json()
        assert body == {
            "status": "ok", "profile": "full", "mode": "retrieval_only",
            "generator": None, "judge": None,
        }  # fmt: skip

    def test_a_cloud_generator_is_reported_as_cloud(self, monkeypatch):
        # `auto` resolves the judge by family (ADR-021), as the run itself would.
        monkeypatch.setenv("REFDESK_GENERATOR_TIER", "cloud-flash")
        monkeypatch.setenv("REFDESK_JUDGE_TIER", "auto")
        body = self.client().get("/healthz").json()
        assert body["mode"] == "cloud"
        assert body["generator"]["cloud"] is True and body["generator"]["mock"] is False
        assert body["judge"]["tier"] == "judge-phi4" and body["judge"]["cloud"] is False

    def test_a_local_generator_reports_local(self, monkeypatch):
        monkeypatch.setenv("REFDESK_GENERATOR_TIER", "local-small")
        monkeypatch.setenv("REFDESK_JUDGE_TIER", "auto")
        body = self.client().get("/healthz").json()
        assert body["mode"] == "local"
        assert body["generator"] == {
            "tier": "local-small", "provider": "ollama", "model": "qwen3.5:9b",
            "cloud": False, "mock": False,
        }  # fmt: skip
        assert body["judge"]["model"] == "phi4"

    def test_the_committed_judge_is_named_as_configured(self, monkeypatch):
        # config/retrieval.yaml pins judge_tier: mock-judge; "auto" is not the only way.
        monkeypatch.setenv("REFDESK_GENERATOR_TIER", "local-small")
        body = self.client().get("/healthz").json()
        assert body["judge"]["tier"] == "mock-judge" and body["judge"]["mock"] is True

    def test_no_secrets_ever_leave_in_this_response(self):
        text = self.client().get("/healthz").text
        for secret in ("key_env", "base_url", "DEEPSEEK", "GLM_API", "CLOUD_KEY", "api.z.ai"):
            assert secret not in text

    def test_the_demo_profile_is_recorded_whatever_is_configured(self, monkeypatch):
        monkeypatch.setenv("REFDESK_PROFILE", "demo")
        monkeypatch.setenv("REFDESK_GENERATOR_TIER", "cloud-flash")
        body = self.client().get("/healthz").json()
        assert body == {
            "status": "ok", "profile": "demo", "mode": "recorded",
            "generator": None, "judge": None,
        }  # fmt: skip
