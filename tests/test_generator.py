"""Rationale generator: one record and the brief in, a structured rationale out
(issue #95; ADR-020, ADR-022; FR-5, FR-11). Runs the real client against the mock server
through an in-process transport, so no port and no model are needed."""

from datetime import UTC, datetime
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from refdesk.generator import generate_rationale
from refdesk.llm import client as llm
from refdesk.llm.config import Budgets, ProvidersConfig
from refdesk.llm.mock_server import create_app
from refdesk.rationale import load_prompt
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus

BRIEF = "Dramatic flowers for a luxury tea tin"


def record():
    rights = RightsRecord(
        source="met", object_id="1", flag_field="isPublicDomain", flag_value=True,
        licence_string=None, checked_at=datetime(2026, 10, 27, tzinfo=UTC),
        status=RightsStatus.OPEN,
    )  # fmt: skip
    return ArtworkRecord(
        id="met:1", source="met", object_id="1", title="Still Life with Flowers",
        artist="Workshop of Jan van Huysum", date="ca. 1720", date_begin=1715, date_end=1725,
        medium="Oil on canvas", classification="Paintings",
        subject_tags=("Flowers", "Still Life"), raw_record_ref="met/objects/1.json",
        rights=rights,
    )  # fmt: skip


class AppTransport:
    """The client's transport, sending requests to an in-process FastAPI app."""

    def __init__(self, app):
        self.http = TestClient(app)
        self.calls = 0

    def post_json(self, url, headers, payload):
        self.calls += 1
        response = self.http.post(urlsplit(url).path, json=payload)
        return response.status_code, response.json()


CONFIG = ProvidersConfig.model_validate(
    {
        "providers": {
            "mock": {"family": "mock", "cloud": False, "paid": False, "base_url": "http://mock/v1"},
            "cloudy": {
                "family": "deepseek", "cloud": True, "paid": True,
                "base_url": "http://cloud/v1", "key_env": "CLOUD_KEY",
            },
        },
        "tiers": {
            "mock": {"provider": "mock", "model": "mock-1"},
            "cloud-flash": {
                "provider": "cloudy", "model": "flash",
                "price_usd_per_mtok": {"input": 0.3, "output": 1.2},
            },
        },
        "routing": ["mock", "cloud-flash"],
    }
)  # fmt: skip


def make_client(script=None, **kwargs):
    transport = AppTransport(create_app(script=script or ["ok"]))
    c = llm.LLMClient(CONFIG, Budgets({}), env={}, transport=transport, backoff=0, **kwargs)
    return c, transport


def generate(c, **overrides):
    args = dict(tier="mock", brief=BRIEF, record=record(), keep_local=False, job="rationale")
    return generate_rationale(c, **(args | overrides))


class TestGenerate:
    def test_a_valid_rationale_from_the_record(self):
        c, _ = make_client()
        result = generate(c)
        assert result.ok and result.failure is None
        values = {cl.field: cl.value for cl in result.rationale.claims}
        assert values["artist"] == "Workshop of Jan van Huysum"
        assert result.attempts == 1

    def test_records_what_produced_it(self):
        c, _ = make_client()
        result = generate(c)
        p = load_prompt("rationale")
        assert (result.tier, result.provider, result.family) == ("mock", "mock", "mock")
        assert result.model_requested == "mock-1" and result.model_reported == "mock-1"
        assert (result.prompt, result.prompt_sha256) == (p.name, p.sha256)

    def test_a_malformed_answer_is_retried_once(self):
        c, transport = make_client(["malformed", "ok"])
        result = generate(c)
        assert result.ok and result.attempts == 2 and transport.calls == 2

    @pytest.mark.parametrize("bad", ["malformed", "nofit", "badfield"])
    def test_two_bad_answers_mark_it_failed_never_verified(self, bad):
        c, transport = make_client([bad])
        result = generate(c)
        assert not result.ok and result.rationale is None
        assert result.failure and transport.calls == 2
        assert result.attempts == 2

    def test_a_keep_local_brief_never_reaches_a_cloud_tier(self):
        c, transport = make_client()
        with pytest.raises(llm.KeepLocalViolation):
            generate(c, tier="cloud-flash", keep_local=True)
        assert transport.calls == 0

    def test_a_paid_tier_without_approval_is_a_hard_error_not_a_failed_rationale(self):
        c, transport = make_client()
        c.env = {"CLOUD_KEY": "k"}
        c.budgets = Budgets({"rationale_budget_usd": 1})
        with pytest.raises(llm.NotApproved):
            generate(c, tier="cloud-flash")
        assert transport.calls == 0
