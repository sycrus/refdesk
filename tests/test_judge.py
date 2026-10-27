"""Verifier stage 2: phi4 judges each claim's text and the fit sentence, one at a time
(issue #97; ADR-021, ADR-022). A fake transport answers per statement, so no model runs.

Pass rule (Joe, 2026-10-27): SUPPORTED passes; UNSUPPORTED fails; a malformed answer gets
one retry, then counts as a fail.
"""

from datetime import UTC, datetime

import pytest

from refdesk.judge import (
    judge_messages,
    judge_rationale,
    load_fit_prompt,
    load_judge_prompt,
)
from refdesk.llm import client as llm
from refdesk.llm.config import Budgets, ProvidersConfig
from refdesk.rationale import Claim, Rationale
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus


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


RATIONALE = Rationale(
    claims=(
        Claim(field="medium", value="Oil on canvas", text="It is oil on canvas."),
        Claim(field="date", value="ca. 1720", text="It was painted around 1720 for a duke."),
    ),
    fit="Its dark ground suits a luxury tin.",
)


class FakeTransport:
    """Answers a judge request by looking at the statement it carries."""

    def __init__(self, answer):
        self.answer = answer
        self.statements = []

    def post_json(self, url, headers, payload):
        statement = payload["messages"][-1]["content"].rsplit("Rationale:\n", 1)[1]
        self.statements.append(statement)
        text = self.answer(statement, len(self.statements))
        return 200, {"model": "phi4", "choices": [{"message": {"content": text}}], "usage": {}}


CONFIG = ProvidersConfig.model_validate(
    {
        "providers": {
            "gen": {"family": "qwen-local", "cloud": False, "paid": False, "base_url": "http://g/v1"},
            "phi": {"family": "microsoft", "cloud": False, "paid": False, "base_url": "http://p/v1"},
        },
        "tiers": {
            "local-small": {"provider": "gen", "model": "qwen3.5:9b"},
            "judge-phi4": {"provider": "phi", "model": "phi4"},
        },
        "routing": ["local-small"],
        "judges": ["judge-phi4"],
    }
)  # fmt: skip


def judge(answer, **overrides):
    transport = FakeTransport(answer)
    client = llm.LLMClient(CONFIG, Budgets({}), env={}, transport=transport, backoff=0)
    args = dict(
        judge_tier="judge-phi4", generator_tier="local-small", record=record(),
        rationale=RATIONALE, keep_local=False, job="rationale",
    )  # fmt: skip
    return judge_rationale(client, **(args | overrides)), transport


class TestJudge:
    def test_every_claim_and_the_fit_sentence_are_judged_one_at_a_time(self):
        result, transport = judge(lambda s, n: "SUPPORTED")
        assert result.verdict.passed and result.verdict.failures == ()
        assert transport.statements == [
            "It is oil on canvas.",
            "It was painted around 1720 for a duke.",
            "Its dark ground suits a luxury tin.",
        ]

    def test_one_unsupported_claim_fails_the_item_and_is_named(self):
        result, _ = judge(lambda s, n: "UNSUPPORTED" if "duke" in s else "SUPPORTED")
        assert not result.verdict.passed
        assert result.verdict.failures == ("claim 2 (date): the judge found it unsupported",)

    def test_an_unsupported_fit_sentence_fails(self):
        result, _ = judge(lambda s, n: "UNSUPPORTED" if "tin" in s else "SUPPORTED")
        assert result.verdict.failures == ("fit sentence: the judge found it unsupported",)

    def test_a_malformed_answer_gets_one_retry(self):
        answers = iter(["Maybe?", "SUPPORTED", "SUPPORTED", "SUPPORTED"])
        result, transport = judge(lambda s, n: next(answers))
        assert result.verdict.passed and len(transport.statements) == 4

    def test_two_malformed_answers_count_as_a_fail(self):
        result, _ = judge(lambda s, n: "I think so" if "oil" in s else "SUPPORTED")
        assert not result.verdict.passed
        assert result.verdict.failures[0].startswith("claim 1 (medium): judge answer unusable")

    def test_the_same_family_judge_is_refused_before_any_request(self):
        with pytest.raises(llm.NoValidJudge):
            judge(lambda s, n: "SUPPORTED", generator_tier="judge-phi4")

    def test_records_the_judge_model_and_prompt(self):
        result, _ = judge(lambda s, n: "SUPPORTED")
        assert result.model_reported == "phi4" and result.family == "microsoft"
        assert result.prompt == load_judge_prompt().name
        assert result.fit_prompt == load_fit_prompt().name

    def test_the_fit_sentence_uses_its_own_prompt(self):
        seen = []

        class Spy(FakeTransport):
            def post_json(self, url, headers, payload):
                seen.append(payload["messages"][0]["content"])
                return super().post_json(url, headers, payload)

        client = llm.LLMClient(
            CONFIG, Budgets({}), env={}, transport=Spy(lambda s, n: "SUPPORTED"), backoff=0
        )
        judge_rationale(
            client, judge_tier="judge-phi4", generator_tier="local-small", record=record(),
            rationale=RATIONALE, keep_local=False, job="rationale",
        )  # fmt: skip
        assert seen[:2] == [load_judge_prompt().text] * 2
        assert "sentence of opinion" in seen[2]


class TestPrompt:
    def test_the_judge_prompt_is_the_probed_wording(self):
        # The hard probe (#122) measured this exact instruction; changing it means re-probing.
        p = load_judge_prompt()
        assert p.name == "judge-v1"
        assert "Reply with exactly one word: SUPPORTED" in p.text

    def test_messages_carry_the_record_and_one_statement(self):
        msgs = judge_messages(record(), "It is oil on canvas.", load_judge_prompt())
        assert msgs[0]["role"] == "system"
        assert msgs[1]["content"].endswith("Rationale:\nIt is oil on canvas.")
        assert "medium: Oil on canvas" in msgs[1]["content"]


class TestBrief:
    """From fit-v2 the fit judge sees the brief; claims never do (issue #135)."""

    def messages(self, fit_prompt):
        seen = []

        class Spy(FakeTransport):
            def post_json(self, url, headers, payload):
                seen.append(payload["messages"][-1]["content"])
                return super().post_json(url, headers, payload)

        client = llm.LLMClient(
            CONFIG, Budgets({}), env={}, transport=Spy(lambda s, n: "SUPPORTED"), backoff=0
        )
        judge_rationale(
            client, judge_tier="judge-phi4", generator_tier="local-small", record=record(),
            rationale=RATIONALE, keep_local=False, job="rationale",
            fit_prompt=load_fit_prompt(fit_prompt), brief="Flowers for a luxury tea tin",
        )  # fmt: skip
        return seen

    def test_fit_v2_sees_the_brief_and_claims_do_not(self):
        *claims, fit = self.messages("v2")
        assert all("Brief:" not in m for m in claims)
        assert fit.startswith("Brief: Flowers for a luxury tea tin\n\nRecord:")

    def test_fit_v1_is_still_sent_as_it_was_measured(self):
        assert all("Brief:" not in m for m in self.messages("v1"))

    def test_messages_without_a_brief_are_unchanged(self):
        msgs = judge_messages(record(), "x", load_judge_prompt())
        assert msgs[1]["content"].startswith("Record:")
