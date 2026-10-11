"""The committed golden-v0-synthetic file (no database needed, so it runs in CI)."""

import json
from pathlib import Path

from refdesk.evals.golden import GoldenCase

GOLDEN = Path(__file__).resolve().parents[2] / "evals" / "golden" / "golden-v0-synthetic.jsonl"
CASES = [GoldenCase(**json.loads(line)) for line in GOLDEN.read_text("utf-8").splitlines() if line]


def test_every_case_is_synthetic_and_labelled_as_such():
    assert CASES and all(c.provenance == "synthetic" and c.labeller == "claude-code" for c in CASES)


def test_ids_are_unique_and_all_cases_share_one_corpus_version():
    assert len({c.id for c in CASES}) == len(CASES)
    assert len({c.corpus_version for c in CASES}) == 1


def test_every_retrieve_case_has_a_rule_and_decline_cases_have_none():
    for c in CASES:
        assert (c.rule is None) == (c.expected_decision == "decline"), c.id


def test_reproduction_cases_require_open_rights_in_their_rule():
    for c in CASES:
        if c.usage_mode == "reproduction":
            assert c.rule.get("rights") == "open", c.id
