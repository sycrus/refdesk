"""Which generator and judge tiers the API's reasoner uses (issue #147).

config/retrieval.yaml defaults both to the mock. A session with real models (the
usability test) sets REFDESK_GENERATOR_TIER and REFDESK_JUDGE_TIER instead of editing the
committed config, so a real generator is never paired with the mock judge by accident.
"""

from refdesk.boards import default_reasoner

SETTINGS = {"generator_tier": "mock", "judge_tier": "mock-judge"}


def test_the_config_tiers_are_used_by_default(monkeypatch):
    monkeypatch.delenv("REFDESK_GENERATOR_TIER", raising=False)
    monkeypatch.delenv("REFDESK_JUDGE_TIER", raising=False)
    reasoner = default_reasoner(SETTINGS)
    assert reasoner.generator_tier == "mock"
    assert reasoner._judge_tier == "mock-judge"


def test_each_tier_can_be_overridden_from_the_environment(monkeypatch):
    monkeypatch.setenv("REFDESK_GENERATOR_TIER", "local-small")
    monkeypatch.setenv("REFDESK_JUDGE_TIER", "auto")
    reasoner = default_reasoner(SETTINGS)
    assert reasoner.generator_tier == "local-small"
    assert reasoner._judge_tier == "auto"


def test_no_generator_gives_retrieval_only_boards(monkeypatch):
    monkeypatch.setenv("REFDESK_GENERATOR_TIER", "none")
    assert default_reasoner(SETTINGS) is None
