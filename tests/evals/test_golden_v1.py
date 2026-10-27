"""Assembling golden-v1 from the labelling files, and its trust report (ADR-018, issue #15).

All data here is made up: a few cases, pools of four works, hand-computed results.
"""

from datetime import UTC, datetime

from refdesk.evals.golden_v1 import assemble, decision, report

WHEN = datetime(2026, 10, 28, tzinfo=UTC)
DRAFTS = [
    {"draft_id": "d01", "brief": "Boats at sea", "detail": "sparse", "difficulty": "easy",
     "usage_mode": "reference_only", "expected_decision": "retrieve", "tags": ["sea"]},
    {"draft_id": "d02", "brief": "Winter scenes", "detail": "rich", "difficulty": "medium",
     "usage_mode": "reproduction", "expected_decision": "retrieve", "tags": []},
    {"draft_id": "d03", "brief": "Gardens", "detail": "moderate", "difficulty": "easy",
     "usage_mode": "reference_only", "expected_decision": "retrieve", "tags": []},
    {"draft_id": "d04", "brief": "Price this Old Master", "detail": "moderate",
     "difficulty": "hard", "usage_mode": "reference_only", "expected_decision": "decline"},
]  # fmt: skip


def rows(draft_id, labels):
    """labels: {"met:1": "y2", "met:2": "n", "met:3": ""}"""
    return [
        {"draft_id": draft_id, "candidate": rid, "relevant": v[:1], "grade": v[1:], "note": ""}
        for rid, v in labels.items()
    ]


def prop(record_id, grade, verdict="supported"):
    judge = {"judge_model": "phi4", "judge_family": "microsoft", "judge_verdict": verdict}
    return {"record_id": record_id, "grade": grade, "fields": ["title"], "reason": "r"} | judge


PASS1 = rows("d01", {"met:1": "y2", "met:2": "y1", "met:3": "n", "met:4": "n"}) + rows(
    "d02", {"met:5": "y2", "met:6": "n", "met:7": "n", "met:8": "n"}
)
PASS2 = rows("d01", {"met:1": "y2", "met:2": "n", "met:3": "n", "met:4": "n"}) + rows(
    "d02", {"met:5": "y1", "met:6": "n", "met:7": "n", "met:8": "n"}
)
REVIEW = rows("d03", {"met:9": "y2", "met:10": "y2", "met:11": "n", "met:12": "y1"})
PROPOSALS = {
    "d01": {"proposals": [prop("met:1", 2), prop("met:3", 1, "unsupported")]},
    "d02": {"proposals": [prop("met:5", 2)]},
    # Joe: met:9 same grade (accepted), met:10 other grade (regraded), met:11 rejected;
    # met:12 he added.
    "d03": {"proposals": [prop("met:9", 2), prop("met:10", 1), prop("met:11", 2, "unsupported")]},
}


def build(**overrides):
    args = dict(
        drafts=DRAFTS, blind_ids={"d01", "d02"}, corpus_version="met:4:x", pass1=PASS1,
        pass2=PASS2, proposals=PROPOSALS, review=REVIEW, reviewed_at=WHEN,
    )  # fmt: skip
    return assemble(**(args | overrides))


class TestAssemble:
    def test_every_case_is_built_with_joes_labels_as_expected(self):
        a = build()
        assert a.problems == [] and [c.id for c in a.cases] == [
            "g1-001",
            "g1-002",
            "g1-003",
            "g1-004",
        ]
        first = a.cases[0]
        assert [(e.record_id, e.grade) for e in first.expected] == [("met:1", 2), ("met:2", 1)]
        assert first.provenance == "human" and first.labeller == "joe" and first.version == "v1"

    def test_blind_cases_keep_the_pool_proposals_undecided_and_pass_2(self):
        review = build().cases[0].review
        assert review.blind and review.pool == ["met:1", "met:2", "met:3", "met:4"]
        assert review.relabel == ["met:1"]
        assert [p.decision for p in review.proposals] == [None, None]
        assert review.proposals[1].judge_verdict == "unsupported"

    def test_review_decisions_come_from_joes_own_labels(self):
        a = build()
        review = a.cases[2].review
        assert [p.decision for p in review.proposals] == ["accepted", "regraded", "rejected"]
        assert {e.record_id for e in a.cases[2].expected} == {"met:9", "met:10", "met:12"}
        assert a.added["d03"] == 1 and review.reviewed_by == "joe"

    def test_a_decline_case_has_no_references(self):
        case = build().cases[3]
        assert case.expected_decision == "decline" and case.expected == []

    def test_unfinished_sheets_are_reported_not_guessed(self):
        partial = REVIEW[:-1] + rows("d03", {"met:12": ""})
        a = build(review=partial)
        assert a.problems == ["d03: review is not complete"]
        assert "g1-003" not in [c.id for c in a.cases]

    def test_no_pass_2_leaves_relabel_empty(self):
        a = build(pass2=None)
        assert not a.pass2_complete and a.cases[0].review.relabel is None

    def test_a_case_with_nothing_relevant_is_left_for_joe(self):
        nothing = rows("d01", {"met:1": "n", "met:2": "n", "met:3": "n", "met:4": "n"})
        a = build(pass1=nothing + PASS1[4:])
        assert a.problems[0].startswith("d01: Joe marked no work relevant")

    def test_decision_reads_the_grade(self):
        assert decision({"grade": 2}, {"relevant": "y", "grade": "1"}) == "regraded"


class TestReport:
    def test_numbers_are_hand_checkable(self):
        text, result = report(build(), title="t", caveats=["pass 2 on the same day"])
        # d01: Claude {1,3} vs Joe {1,2} over 4 -> 2/4 agree; d02: {5} vs {5} -> 4/4. Mean 0.75.
        assert result.claude_agreement == 0.75
        # Self: d01 {1,2} vs {1} -> 3/4; d02 {5} vs {5} -> 4/4. Mean 0.875.
        assert result.self_agreement == 0.875
        # Blind proposals: met:1 g2 (Joe g2, agree), met:3 (not picked), met:5 g2 (Joe g2).
        assert round(result.blind_disagreement, 3) == round(1 / 3, 3)
        # Review: 2 of 3 proposals corrected.
        assert round(result.correction_rate, 3) == round(2 / 3, 3)
        assert "| sparse | 1 | 50.0% | 75.0% |" in text
        assert "Works Joe added that Claude did not propose: 1" in text
        assert "| unsupported | 0 | 0 | 1 |" in text
        assert "- pass 2 on the same day" in text

    def test_without_pass_2_the_trust_rules_are_pending(self):
        text, result = report(build(pass2=None), title="t", caveats=[])
        assert result is None and "Pending: Joe's second blind pass" in text

    def test_without_reviews_anchoring_is_pending(self):
        text, _ = report(build(review=[]), title="t", caveats=[])
        assert "pending (no reviewed cases yet)" in text
