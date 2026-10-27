"""Mock LLM server, exercised through the real client over real HTTP (issue #39, PRD 10)."""

import socket
import threading
import time

import pytest
import uvicorn

from refdesk.llm import client as llm
from refdesk.llm.config import Budgets, ProvidersConfig
from refdesk.llm.mock_server import create_app

MESSAGES = [{"role": "user", "content": "Explain why this painting fits the brief."}]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def mock(request):
    """Start the mock server on a free port; `request.param` is the server's settings."""
    settings = getattr(request, "param", {})
    app = create_app(**settings)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    yield port
    server.should_exit = True
    thread.join(timeout=5)


def client(port, *, timeout=2.0, max_retries=2):
    config = ProvidersConfig.model_validate(
        {
            "providers": {
                "mock": {
                    "family": "mock",
                    "cloud": False,
                    "paid": False,
                    "base_url": f"http://127.0.0.1:{port}/v1",
                }
            },
            "tiers": {"mock": {"provider": "mock", "model": "mock-1"}},
            "routing": ["mock"],
        }
    )
    return llm.LLMClient(
        config,
        Budgets({}),
        env={},
        transport=llm.UrllibTransport(timeout=timeout),
        max_retries=max_retries,
        backoff=0.01,
    )


def call(c):
    return c.complete("mock", MESSAGES, job="test", keep_local=True)


def test_ok_returns_a_deterministic_answer(mock):
    first, second = call(client(mock)), call(client(mock))
    assert first.text == second.text and first.text.startswith("MOCK:")
    assert first.model_reported == "mock-1" and first.cost_usd == 0.0


@pytest.mark.parametrize("mock", [{"latency_s": 0.3}], indirect=True)
def test_configurable_latency(mock):
    assert call(client(mock)).latency_s >= 0.3


@pytest.mark.parametrize("mock", [{"script": ["429", "ok"]}], indirect=True)
def test_429_is_retried_then_succeeds(mock):
    result = call(client(mock))
    assert result.attempts == 2


@pytest.mark.parametrize("mock", [{"script": ["429"]}], indirect=True)
def test_429_beyond_the_retry_limit_is_a_provider_error(mock):
    with pytest.raises(llm.ProviderError, match="429"):
        call(client(mock, max_retries=2))


@pytest.mark.parametrize("mock", [{"script": ["timeout"], "timeout_s": 1.5}], indirect=True)
def test_timeout_is_a_provider_error_not_a_raw_socket_error(mock):
    with pytest.raises(llm.ProviderError, match="timeout"):
        call(client(mock, timeout=0.3, max_retries=0))


@pytest.mark.parametrize("mock", [{"script": ["500", "500", "ok"]}], indirect=True)
def test_server_errors_are_retried(mock):
    assert call(client(mock, max_retries=2)).attempts == 3


def test_script_can_be_changed_at_runtime(mock):
    import json
    import urllib.request

    request = urllib.request.Request(
        f"http://127.0.0.1:{mock}/_mock/script",
        method="POST",
        data=json.dumps({"script": ["429"]}).encode(),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(request).close()
    with pytest.raises(llm.ProviderError, match="429"):
        call(client(mock, max_retries=0))


def test_unreachable_server_is_a_provider_error():
    with pytest.raises(llm.ProviderError):
        call(client(free_port(), max_retries=0))


class TestRationaleAnswers:
    """The mock answers rationale prompts with structured claims built from the record
    block, and can be scripted to return malformed ones (issue #94)."""

    @staticmethod
    def ask(app, record):
        from fastapi.testclient import TestClient

        from refdesk.rationale import load_prompt, rationale_messages

        messages = rationale_messages("Flowers for a tea tin", record, load_prompt())
        with TestClient(app) as http:
            body = http.post("/v1/chat/completions", json={"messages": messages}).json()
        return body["choices"][0]["message"]["content"]

    @staticmethod
    def record():
        from datetime import UTC, datetime

        from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus

        rights = RightsRecord(
            source="met", object_id="1", flag_field="isPublicDomain", flag_value=True,
            licence_string=None, checked_at=datetime(2026, 10, 27, tzinfo=UTC),
            status=RightsStatus.OPEN,
        )  # fmt: skip
        return ArtworkRecord(
            id="met:1", source="met", object_id="1", title="Still Life with Flowers",
            artist="Workshop of Jan van Huysum", date="ca. 1720", date_begin=1715,
            date_end=1725, medium="Oil on canvas", classification="Paintings",
            subject_tags=("Flowers", "Still Life"), raw_record_ref="met/objects/1.json",
            rights=rights,
        )  # fmt: skip

    def test_valid_claims_from_the_record(self):
        from refdesk.rationale import parse_rationale

        rec = self.record()
        r = parse_rationale(self.ask(create_app(), rec), rec)
        values = {c.field: c.value for c in r.claims}
        assert values["medium"] == "Oil on canvas"
        assert values["artist"] == "Workshop of Jan van Huysum"
        assert r.fit

    @pytest.mark.parametrize(
        ("behaviour", "error"),
        [("malformed", "JSON"), ("nofit", "fit"), ("badfield", "provenance")],
    )
    def test_scripted_malformed_answers(self, behaviour, error):
        from refdesk.rationale import RationaleError, parse_rationale

        rec = self.record()
        text = self.ask(create_app(script=[behaviour]), rec)
        with pytest.raises(RationaleError, match=error):
            parse_rationale(text, rec)

    def test_other_prompts_keep_the_plain_answer(self):
        from fastapi.testclient import TestClient

        with TestClient(create_app()) as http:
            body = http.post("/v1/chat/completions", json={"messages": MESSAGES}).json()
        assert body["choices"][0]["message"]["content"].startswith("MOCK:")


@pytest.mark.parametrize(
    ("script", "answer"),
    [(["ok"], "SUPPORTED"), (["unsupported"], "UNSUPPORTED"), (["malformed"], "Maybe.")],
)
def test_judge_prompts_get_a_verdict(script, answer):
    from fastapi.testclient import TestClient

    from refdesk.judge import judge_messages, load_judge_prompt

    rec = TestRationaleAnswers.record()
    messages = judge_messages(rec, "It is oil on canvas.", load_judge_prompt())
    with TestClient(create_app(script=script)) as http:
        body = http.post("/v1/chat/completions", json={"messages": messages}).json()
    assert body["choices"][0]["message"]["content"] == answer


def test_fit_prompts_get_a_verdict_too():
    from fastapi.testclient import TestClient

    from refdesk.judge import judge_messages, load_fit_prompt

    rec = TestRationaleAnswers.record()
    messages = judge_messages(rec, "Its quiet mood suits the brief.", load_fit_prompt())
    with TestClient(create_app()) as http:
        body = http.post("/v1/chat/completions", json={"messages": messages}).json()
    assert body["choices"][0]["message"]["content"] == "SUPPORTED"
