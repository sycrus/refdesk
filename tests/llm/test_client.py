"""LLM client guards (issue #38; CLAUDE.md hard rules; PRD 10, FR-11; ADR-020, ADR-021).

Every guard is a hard error raised before any network request. None of them falls back
to the mock or to another provider.
"""

import pytest

from refdesk.llm import client as llm
from refdesk.llm.config import Budgets, ProvidersConfig

CONFIG = {
    "providers": {
        "deepseek": {
            "family": "deepseek",
            "cloud": True,
            "paid": True,
            "base_url": "https://api.deepseek.com",
            "key_env": "DEEPSEEK_API_KEY",
        },
        "glm": {
            "family": "zhipu",
            "cloud": True,
            "paid": True,
            "base_url_env": "GLM_BASE_URL",
            "key_env": "GLM_API_KEY",
        },
        "ollama": {
            "family": "qwen-local",
            "cloud": False,
            "paid": False,
            "base_url": "http://127.0.0.1:11434/v1",
        },
        "mock": {
            "family": "mock",
            "cloud": False,
            "paid": False,
            "base_url": "http://127.0.0.1:8100/v1",
        },
    },
    "tiers": {
        "cloud-flash": {
            "provider": "deepseek",
            "model": "deepseek-flash",
            "price_usd_per_mtok": {"input": 1.0, "output": 2.0},
        },
        "unpriced": {
            "provider": "deepseek",
            "model": "deepseek-flash",
            "price_usd_per_mtok": {"input": None, "output": None},
        },
        "no-model": {
            "provider": "glm",
            "model": None,
            "price_usd_per_mtok": {"input": 1.0, "output": 1.0},
        },
        "glm-flash": {
            "provider": "glm",
            "model": "glm-x",
            "price_usd_per_mtok": {"input": 1.0, "output": 1.0},
        },
        "local-small": {"provider": "ollama", "model": "qwen-small"},
        "mock": {"provider": "mock", "model": "mock-1"},
    },
    "routing": ["local-small", "cloud-flash"],
}
BUDGETS = {"currency": "USD", "labelling_budget_usd": 20, "rationale_eval_budget_usd": 0}
ENV = {
    "DEEPSEEK_API_KEY": "test-key",
    "GLM_API_KEY": "test-key",
    "GLM_BASE_URL": "https://glm.test/v4",
}
MESSAGES = [{"role": "user", "content": "x" * 4000}]  # about 1,000 input tokens


class FakeTransport:
    def __init__(self, status=200, model="deepseek-flash-2026-10-01"):
        self.calls = []
        self.status, self.model = status, model

    def post_json(self, url, headers, payload):
        self.calls.append((url, headers, payload))
        if self.status != 200:
            return self.status, {"error": "boom"}
        return 200, {
            "model": self.model,
            "choices": [{"message": {"content": "a rationale"}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 100},
        }


def client(*, env=ENV, approved=True, transport=None, budgets=BUDGETS):
    return llm.LLMClient(
        ProvidersConfig.model_validate(CONFIG),
        Budgets(budgets),
        env=env,
        approved=approved,
        transport=transport or FakeTransport(),
        sleep=lambda seconds: None,
    )


def call(c, tier="cloud-flash", *, job="labelling", keep_local=False, max_tokens=500):
    return c.complete(tier, MESSAGES, job=job, keep_local=keep_local, max_tokens=max_tokens)


class TestKeepLocal:
    @pytest.mark.parametrize("tier", ["cloud-flash", "glm-flash"])
    def test_keep_local_blocks_every_cloud_provider(self, tier):
        t = FakeTransport()
        with pytest.raises(llm.KeepLocalViolation):
            call(client(transport=t), tier, keep_local=True)
        assert t.calls == []

    def test_keep_local_allows_local_providers(self):
        t = FakeTransport(model="qwen-small")
        assert call(client(transport=t), "local-small", keep_local=True).text == "a rationale"


class TestPaidCallGuards:
    def test_missing_key(self):
        with pytest.raises(llm.MissingKey, match="DEEPSEEK_API_KEY"):
            call(client(env={}))

    def test_missing_budget(self):
        with pytest.raises(llm.MissingBudget, match="nonexistent"):
            call(client(), job="nonexistent")

    def test_zero_budget_blocks_any_paid_call(self):
        with pytest.raises(llm.BudgetExceeded):
            call(client(), job="rationale_eval")

    def test_not_approved(self):
        t = FakeTransport()
        with pytest.raises(llm.NotApproved):
            call(client(approved=False, transport=t))
        assert t.calls == []

    def test_unpriced_model_cannot_be_called(self):
        with pytest.raises(llm.MissingPrice):
            call(client(), "unpriced")

    def test_tier_without_a_model_cannot_be_called(self):
        with pytest.raises(llm.MissingModel):
            call(client(), "no-model")

    def test_stops_before_the_call_that_would_exceed_the_budget(self):
        tight = BUDGETS | {"labelling_budget_usd": 0.0025}
        t = FakeTransport()
        c = client(budgets=tight, transport=t)
        call(c)  # estimate: 1,000 in x $1/M + 500 out x $2/M = $0.002
        with pytest.raises(llm.BudgetExceeded):
            call(c)  # $0.0012 spent + $0.002 estimate > $0.0025
        assert len(t.calls) == 1

    def test_free_providers_need_no_key_budget_or_approval(self):
        t = FakeTransport(model="mock-1")
        c = client(env={}, approved=False, transport=t, budgets={"currency": "USD"})
        assert call(c, "mock", job="anything").cost_usd == 0.0


class TestNoSilentFallback:
    def test_provider_error_is_raised_after_retrying_the_same_provider_only(self):
        t = FakeTransport(status=503)
        with pytest.raises(llm.ProviderError, match="503"):
            call(client(transport=t))
        urls = {url for url, _, _ in t.calls}
        assert urls == {"https://api.deepseek.com/chat/completions"}  # never another provider
        assert len(t.calls) == 3  # 1 attempt + 2 retries

    def test_non_retryable_status_is_not_retried(self):
        t = FakeTransport(status=400)
        with pytest.raises(llm.ProviderError, match="400"):
            call(client(transport=t))
        assert len(t.calls) == 1


class TestCompletion:
    def test_records_the_model_the_provider_reports(self):
        result = call(client())
        assert result.model_requested == "deepseek-flash"
        assert result.model_reported == "deepseek-flash-2026-10-01"
        assert result.family == "deepseek" and result.tier == "cloud-flash"

    def test_cost_uses_reported_usage_and_configured_prices(self):
        # 1,000 in x $1/M + 100 out x $2/M = $0.0012
        assert call(client()).cost_usd == pytest.approx(0.0012)

    def test_request_shape(self):
        t = FakeTransport()
        call(client(transport=t))
        url, headers, payload = t.calls[0]
        assert url == "https://api.deepseek.com/chat/completions"
        assert headers["Authorization"] == "Bearer test-key"
        assert payload == {"model": "deepseek-flash", "messages": MESSAGES, "max_tokens": 500}

    def test_a_tier_can_turn_reasoning_off(self):
        # Ollama's OpenAI-style endpoint thinks by default for qwen3 models, spending every
        # output token on reasoning; "none" asks for no thinking (issue #102).
        config = CONFIG | {
            "tiers": CONFIG["tiers"]
            | {"local-small": {"provider": "ollama", "model": "qwen", "reasoning_effort": "none"}}
        }
        t = FakeTransport(model="qwen")
        c = llm.LLMClient(
            ProvidersConfig.model_validate(config), Budgets(BUDGETS), env=ENV, transport=t
        )
        call(c, "local-small", keep_local=True)
        assert t.calls[0][2]["reasoning_effort"] == "none"

    def test_no_reasoning_field_unless_the_tier_sets_one(self):
        t = FakeTransport()
        call(client(transport=t))
        assert "reasoning_effort" not in t.calls[0][2]

    def test_base_url_from_environment(self):
        t = FakeTransport(model="glm-x")
        call(client(transport=t), "glm-flash")
        assert t.calls[0][0] == "https://glm.test/v4/chat/completions"


class TestEstimate:
    def test_dry_run_estimate_makes_no_call(self):
        t = FakeTransport()
        estimate = client(transport=t).estimate("cloud-flash", MESSAGES, max_tokens=500)
        assert estimate.tokens_in == 1000 and estimate.tokens_out_max == 500
        assert estimate.cost_usd == pytest.approx(0.002)
        assert t.calls == []


class TestJudgeFamily:
    def test_picks_a_judge_from_a_different_family(self):
        cfg = ProvidersConfig.model_validate(CONFIG)
        assert (
            llm.pick_judge(
                cfg, generator_tier="cloud-flash", candidates=["cloud-flash", "glm-flash"]
            )
            == "glm-flash"
        )

    def test_no_valid_judge_is_an_error(self):
        cfg = ProvidersConfig.model_validate(CONFIG)
        with pytest.raises(llm.NoValidJudge):
            llm.pick_judge(
                cfg, generator_tier="cloud-flash", candidates=["cloud-flash", "unpriced"]
            )


def test_the_repository_config_loads():
    cfg = ProvidersConfig.load("config/providers.yaml")
    assert set(cfg.routing) <= set(cfg.tiers)


class EmptyAnswerTransport(FakeTransport):
    def post_json(self, url, headers, payload):
        self.calls.append((url, headers, payload))
        return 200, {
            "model": "qwen3:4b",
            "choices": [{"message": {"content": "", "reasoning": "Okay, the user..."}}],
            "usage": {"prompt_tokens": 32, "completion_tokens": 600},
        }


def test_an_empty_answer_is_an_error_not_an_empty_rationale():
    # Seen in the #40 smoke run: a thinking model spent every output token on reasoning.
    t = EmptyAnswerTransport()
    with pytest.raises(llm.EmptyCompletion, match="reasoning"):
        call(client(transport=t))
