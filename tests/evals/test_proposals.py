"""phi4 checks Claude's golden-v1 proposals one at a time (ADR-018 step 4, issue #15).
A fake transport answers per proposal, so no model runs."""

from datetime import UTC, datetime

import pytest

from refdesk.evals.proposals import judge_proposals, load_proposal_prompt, proposal_messages
from refdesk.llm import client as llm
from refdesk.llm.config import Budgets, ProvidersConfig
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus


def record(object_id, title):
    rights = RightsRecord(
        source="met", object_id=object_id, flag_field="isPublicDomain", flag_value=True,
        licence_string=None, checked_at=datetime(2026, 10, 27, tzinfo=UTC),
        status=RightsStatus.OPEN,
    )  # fmt: skip
    return ArtworkRecord(
        id=f"met:{object_id}", source="met", object_id=object_id, title=title,
        date="1865", subject_tags=("Boats",), raw_record_ref="x", rights=rights,
    )  # fmt: skip


RECORDS = {"met:1": record("1", "Calm Sea"), "met:2": record("2", "Boats on a River")}
CASE = {
    "draft_id": "d02",
    "proposals": [
        {"record_id": "met:1", "grade": 2, "fields": ["title"], "reason": "boats on open sea"},
        {"record_id": "met:2", "grade": 1, "fields": ["title"], "reason": "boats, but a river"},
    ],
}
CONFIG = ProvidersConfig.model_validate(
    {
        "providers": {
            "phi": {"family": "microsoft", "cloud": False, "paid": False, "base_url": "http://p/v1"},
            "claude": {"family": "anthropic", "cloud": False, "paid": False, "base_url": "http://c/v1"},
        },
        "tiers": {
            "judge-phi4": {"provider": "phi", "model": "phi4"},
            "claude-tier": {"provider": "claude", "model": "claude"},
        },
        "routing": ["judge-phi4"],
        "judges": ["judge-phi4"],
    }
)  # fmt: skip


class FakeTransport:
    def __init__(self, answer):
        self.answer = answer
        self.users = []

    def post_json(self, url, headers, payload):
        self.users.append(payload["messages"][-1]["content"])
        text = self.answer(self.users[-1], len(self.users))
        return 200, {"model": "phi4", "choices": [{"message": {"content": text}}], "usage": {}}


def run(answer, tier="judge-phi4"):
    transport = FakeTransport(answer)
    client = llm.LLMClient(CONFIG, Budgets({}), env={}, transport=transport, backoff=0)
    return judge_proposals(client, CASE, "Boats at sea", RECORDS, judge_tier=tier), transport


def test_each_proposal_is_judged_on_its_own_with_the_brief():
    judged, transport = run(lambda u, n: "SUPPORTED" if "open sea" in u else "UNSUPPORTED")
    assert [p["judge_verdict"] for p in judged] == ["supported", "unsupported"]
    assert all(u.startswith("Brief: Boats at sea\n\nRecord:") for u in transport.users)
    assert judged[0]["judge_model"] == "phi4" and judged[0]["judge_family"] == "microsoft"
    assert judged[1]["reason"] == "boats, but a river"  # the proposal itself is kept


def test_a_malformed_answer_gets_one_retry_then_is_invalid():
    judged, transport = run(lambda u, n: "Hmm" if "river" in u else "SUPPORTED")
    assert [p["judge_verdict"] for p in judged] == ["supported", "invalid"]
    assert len(transport.users) == 3


def test_a_judge_from_claudes_family_is_refused_before_any_request():
    with pytest.raises(llm.NoValidJudge):
        run(lambda u, n: "SUPPORTED", tier="claude-tier")


def test_the_message_carries_the_grade_meaning_and_reason():
    msgs = proposal_messages("Boats at sea", RECORDS["met:2"], CASE["proposals"][1],
                             load_proposal_prompt())  # fmt: skip
    assert msgs[1]["content"].endswith(
        "Proposal:\nGrade 1 (fits part of the brief). Reason: boats, but a river"
    )
    assert "You cannot see the image" in msgs[0]["content"]
