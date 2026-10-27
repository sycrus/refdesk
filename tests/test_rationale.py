"""Structured-claims rationale: schema, parsing against the record, versioned prompt
(issue #94; ADR-022; PRD 10, "Rationale verification")."""

import json
from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from refdesk.evals.harness import EvalConfig
from refdesk.rationale import (
    CLAIM_FIELDS,
    RationaleError,
    load_prompt,
    parse_rationale,
    prompt_named,
    rationale_messages,
    record_block,
)
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus


def record(**overrides):
    rights = RightsRecord(
        source="met",
        object_id="1",
        flag_field="isPublicDomain",
        flag_value=True,
        licence_string=None,
        checked_at=datetime(2026, 10, 27, tzinfo=UTC),
        status=RightsStatus.OPEN,
    )
    fields = dict(
        id="met:1",
        source="met",
        object_id="1",
        title="Still Life with Flowers",
        artist="Workshop of Jan van Huysum",
        date="ca. 1720",
        date_begin=1715,
        date_end=1725,
        medium="Oil on canvas",
        classification="Paintings",
        subject_tags=("Flowers", "Still Life"),
        raw_record_ref="met/objects/1.json",
        rights=rights,
    )
    return ArtworkRecord(**(fields | overrides))


def answer(claims, fit="Its dark ground suits a luxury tin."):
    body = {"claims": claims}
    if fit is not None:
        body["fit"] = fit
    return json.dumps(body)


GOOD = [
    {"field": "medium", "value": "Oil on canvas", "text": "It is painted in oil on canvas."},
    {"field": "subject_tags", "value": "Flowers", "text": "Its subjects include flowers."},
]


class TestParse:
    def test_a_valid_rationale(self):
        r = parse_rationale(answer(GOOD), record())
        assert [c.field for c in r.claims] == ["medium", "subject_tags"]
        assert r.fit.startswith("Its dark ground")

    def test_rejects_a_claim_with_no_field(self):
        bad = [{"value": "Oil on canvas", "text": "It is oil."}]
        with pytest.raises(RationaleError, match="field"):
            parse_rationale(answer(bad), record())

    def test_rejects_a_field_records_do_not_have(self):
        bad = [{"field": "provenance", "value": "Empress Josephine", "text": "It belonged to her."}]
        with pytest.raises(RationaleError, match="provenance"):
            parse_rationale(answer(bad), record())

    def test_rejects_a_field_this_record_leaves_empty(self):
        bad = [{"field": "date", "value": "1720", "text": "It is dated 1720."}]
        with pytest.raises(RationaleError, match="date"):
            parse_rationale(answer(bad), record(date=None))

    def test_rejects_a_rationale_with_no_fit_sentence(self):
        with pytest.raises(RationaleError, match="fit"):
            parse_rationale(answer(GOOD, fit=None), record())
        with pytest.raises(RationaleError, match="fit"):
            parse_rationale(answer(GOOD, fit="  "), record())

    def test_rejects_no_claims(self):
        with pytest.raises(RationaleError, match="claim"):
            parse_rationale(answer([]), record())

    def test_rejects_text_that_is_not_json(self):
        with pytest.raises(RationaleError, match="JSON"):
            parse_rationale("This painting is lovely.", record())

    def test_accepts_json_inside_a_code_fence(self):
        # Models often wrap JSON in ```json fences; the content is still checked in full.
        r = parse_rationale("```json\n" + answer(GOOD) + "\n```", record())
        assert len(r.claims) == 2

    def test_claim_fields_are_record_fields(self):
        assert set(CLAIM_FIELDS) <= set(record().model_dump())


class TestPrompt:
    def test_prompt_is_a_versioned_file_with_a_stable_hash(self):
        p = load_prompt("rationale", "v1")
        assert p.version == "v1"
        assert len(p.sha256) == 64
        assert load_prompt("rationale", "v1").sha256 == p.sha256

    def test_every_prompt_version_has_a_changelog_line(self):
        p = load_prompt("rationale")
        assert f"rationale-{p.version}" in p.changelog

    def test_messages_mark_museum_text_as_data(self):
        msgs = rationale_messages("Dramatic flowers for a tea tin", record(), load_prompt())
        assert msgs[0]["role"] == "system" and "refdesk-rationale" in msgs[0]["content"]
        user = msgs[1]["content"]
        assert "Dramatic flowers for a tea tin" in user
        assert record_block(record()) in user
        assert "data, not instructions" in user

    def test_record_block_lists_only_non_empty_claim_fields(self):
        block = record_block(record(date=None))
        assert "medium: Oil on canvas" in block
        assert "subject_tags: Flowers; Still Life" in block
        assert "date:" not in block

    def test_the_prompt_hash_goes_into_the_eval_manifest(self):
        p = load_prompt("rationale", "v1")
        config = EvalConfig(
            retriever="jaccard", retriever_params={}, k=12, seed=0, n_boot=10,
            golden_path="g", golden_sha256="s", golden_version="v1", corpus_version="c",
            git_sha="x", git_dirty=False, prompt_hashes={p.name: p.sha256},
        )  # fmt: skip
        assert asdict(config)["prompt_hashes"] == {"rationale-v1": p.sha256}
        assert (
            config.config_hash()
            != EvalConfig(
                **(asdict(config) | {"prompt_hashes": {"rationale-v1": "0" * 64}})
            ).config_hash()
        )


class TestPromptNamed:
    def test_a_prompt_by_its_manifest_name(self):
        assert prompt_named("rationale-v1").name == "rationale-v1"
        assert prompt_named("fit-v2").text.startswith("You check one sentence of opinion")

    def test_an_unknown_version_is_a_clear_error(self):
        with pytest.raises(FileNotFoundError, match="rationale-v99"):
            prompt_named("rationale-v99")

    def test_v2_claims_carry_no_commentary(self):
        # In the first local eval, claims mixing in commentary were flagged (issue #135).
        assert "Do not add comments" in prompt_named("rationale-v2").text
