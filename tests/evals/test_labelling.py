"""golden-v1 labelling: review records and the ADR-018 trust rules (issue #15).

Hand-computed expectations. The rules: Claude's agreement with Joe's blind labels may be
at most 5 points below Joe's self-agreement (judged on a paired interval), and Joe's
correction rate in review may be at most 5 points below his blind disagreement rate.
"""

import pytest
from pydantic import ValidationError

from refdesk.evals.golden import GoldenCase
from refdesk.evals.labelling import (
    blind_disagreement,
    build_pool,
    claude_agreement,
    correction_rate,
    select_blind,
    self_agreement,
    trust_check,
)

POOL = [f"met:{i}" for i in range(1, 11)]  # 10 unranked candidates


def proposal(record_id, grade=2, decision=None, verdict="supported"):
    return {
        "record_id": record_id,
        "grade": grade,
        "fields": ["subject_tags"],
        "judge_model": "phi4",
        "judge_family": "microsoft",
        "judge_verdict": verdict,
        "decision": decision,
    }


def v1(n=1, *, expected, review, **overrides):
    fields = {
        "id": f"g1-{n:03d}",
        "brief": f"Brief number {n} about dramatic still lifes",
        "expected": [{"record_id": r, "grade": 2} for r in expected],
        "source": "draft:claude-code, edited:joe",
        "labeller": "joe",
        "difficulty": "medium",
        "version": "v1",
        "provenance": "human",
        "corpus_version": "met:2588:d188937d8a53",
        "detail": "rich",
        "review": review,
    }
    return GoldenCase(**(fields | overrides))


def blind(n, *, joe, claude, relabel):
    return v1(
        n,
        expected=joe,
        review={
            "blind": True,
            "pool": POOL,
            "proposals": [proposal(r) for r in claude],
            "relabel": relabel,
        },
    )


def reviewed(n, decisions):
    props = [proposal(f"met:{i + 1}", decision=d) for i, d in enumerate(decisions)]
    kept = [p["record_id"] for p in props if p["decision"] != "rejected"] or ["met:1"]
    return v1(
        n,
        expected=kept,
        review={"blind": False, "proposals": props, "reviewed_by": "joe"},
    )


class TestReviewSchema:
    def test_a_human_case_needs_a_review_record(self):
        with pytest.raises(ValidationError, match="review"):
            v1(expected=["met:1"], review=None)

    def test_blind_cases_need_the_pool_and_their_labels_come_from_it(self):
        with pytest.raises(ValidationError, match="pool"):
            v1(expected=["met:1"], review={"blind": True, "pool": [], "proposals": []})
        with pytest.raises(ValidationError, match="pool"):
            v1(expected=["met:99"], review={"blind": True, "pool": POOL})

    def test_blind_proposals_are_never_decided(self):
        # Joe never saw them, so there is nothing to accept or reject.
        decided = [proposal("met:1", decision="accepted")]
        with pytest.raises(ValidationError, match="blind"):
            v1(expected=["met:1"], review={"blind": True, "pool": POOL, "proposals": decided})

    def test_a_reviewed_case_has_a_decision_on_every_proposal(self):
        with pytest.raises(ValidationError, match="decision"):
            v1(
                expected=["met:1"],
                review={"blind": False, "proposals": [proposal("met:1")], "reviewed_by": "joe"},
            )

    def test_the_judge_is_never_from_claudes_family(self):
        bad = proposal("met:1") | {"judge_family": "anthropic"}
        with pytest.raises(ValidationError, match="family"):
            v1(expected=["met:1"], review={"blind": False, "proposals": [bad]})

    def test_a_proposal_cites_at_least_one_record_field(self):
        bad = proposal("met:1") | {"fields": []}
        with pytest.raises(ValidationError):
            v1(expected=["met:1"], review={"blind": False, "proposals": [bad]})

    def test_v0_cases_need_no_review(self):
        case = GoldenCase(
            id="g0-001", brief="x", expected=[{"record_id": "met:1", "grade": 2}],
            source="synthetic:claude-code", labeller="claude-code", difficulty="easy",
            version="v0-synthetic", provenance="synthetic", corpus_version="c",
        )  # fmt: skip
        assert case.review is None


class TestAgreement:
    def test_claude_agreement_is_over_the_whole_pool(self):
        # Joe: 1-3 relevant. Claude: 1, 2, 4. Pool of 10: they differ on 3 and 4 -> 8/10.
        case = blind(
            1, joe=["met:1", "met:2", "met:3"], claude=["met:1", "met:2", "met:4"], relabel=[]
        )
        assert claude_agreement([case]) == pytest.approx(0.8)

    def test_self_agreement_compares_joes_two_blind_passes(self):
        # Second pass drops met:3 -> differs on one of ten.
        case = blind(1, joe=["met:1", "met:2", "met:3"], claude=[], relabel=["met:1", "met:2"])
        assert self_agreement([case]) == pytest.approx(0.9)

    def test_blind_disagreement_is_the_share_of_claudes_proposals_joe_did_not_pick(self):
        case = blind(
            1, joe=["met:1", "met:2"], claude=["met:1", "met:2", "met:3", "met:4"], relabel=[]
        )
        assert blind_disagreement([case]) == pytest.approx(0.5)

    def test_correction_rate_counts_rejected_and_regraded_proposals(self):
        case = reviewed(1, ["accepted", "accepted", "rejected", "regraded"])
        assert correction_rate([case]) == pytest.approx(0.5)


def _blinds(claude_hits, self_hits, n=20, start=1):
    """n blind cases; Claude and Joe's second pass each match Joe on that many of 10."""
    joe = POOL[:5]
    claude = POOL[: 5 - (10 - claude_hits)]
    relabel = POOL[: 5 - (10 - self_hits)]
    return [blind(start + i, joe=joe, claude=claude, relabel=relabel) for i in range(n)]


class TestTrustRules:
    def test_passes_when_claude_is_as_consistent_as_joe_and_review_is_not_anchored(self):
        cases = _blinds(claude_hits=9, self_hits=9) + [
            reviewed(30, ["accepted"] * 9 + ["rejected"])
        ]
        result = trust_check(cases, seed=0)
        assert result.gap_verdict == "pass"
        assert result.anchoring_verdict == "pass"
        assert result.passed

    def test_gap_fails_when_the_whole_interval_is_above_five_points(self):
        cases = _blinds(claude_hits=7, self_hits=10) + [reviewed(30, ["rejected"] * 5)]
        result = trust_check(cases, seed=0)
        assert result.gap_points == pytest.approx(30.0)
        assert result.gap_verdict == "fail" and not result.passed

    def test_gap_straddling_five_points_asks_for_more_blind_cases(self):
        # Half the cases have a 10-point gap, half none: mean 5, interval straddles 5.
        cases = _blinds(9, 10, n=10) + _blinds(10, 10, n=10, start=40)
        cases.append(reviewed(30, ["accepted"] * 20))
        result = trust_check(cases, seed=0)
        assert result.gap_verdict == "add blind cases"
        assert not result.passed

    def test_anchoring_fails_when_review_corrects_far_less_than_blind_disagreement(self):
        # Blind: Claude proposes 5, Joe picks 4 -> 20% disagreement. Review: 2 of 100 corrected.
        cases = [blind(i + 1, joe=POOL[:4], claude=POOL[:5], relabel=POOL[:4]) for i in range(20)]
        cases.append(reviewed(30, ["accepted"] * 98 + ["rejected"] * 2))
        result = trust_check(cases, seed=0)
        assert result.blind_disagreement == pytest.approx(0.2)
        assert result.correction_rate == pytest.approx(0.02)
        assert result.anchoring_verdict == "fail" and not result.passed

    def test_refuses_without_joes_second_blind_pass(self):
        case = blind(1, joe=["met:1"], claude=["met:1"], relabel=None)
        with pytest.raises(ValueError, match="self-agreement"):
            trust_check([case, reviewed(2, ["accepted"])], seed=0)


class TestBlindSelection:
    DRAFTS = [
        {"draft_id": f"d{i:02d}", "detail": d, "expected_decision": dec}
        for i, (d, dec) in enumerate(
            [("sparse", "retrieve")] * 15
            + [("moderate", "retrieve")] * 14
            + [("rich", "retrieve")] * 12
            + [("rich", "decline")] * 4,
            start=1,
        )
    ]

    def test_picks_n_retrieve_cases_only(self):
        chosen = select_blind(self.DRAFTS, n=20, seed=0)
        assert len(chosen) == 20
        decisions = {d["draft_id"]: d["expected_decision"] for d in self.DRAFTS}
        assert all(decisions[c] == "retrieve" for c in chosen)

    def test_spread_across_detail_levels_in_proportion(self):
        chosen = set(select_blind(self.DRAFTS, n=20, seed=0))
        by_level = {}
        for d in self.DRAFTS:
            if d["draft_id"] in chosen:
                by_level[d["detail"]] = by_level.get(d["detail"], 0) + 1
        assert by_level == {"sparse": 7, "moderate": 7, "rich": 6}

    def test_deterministic(self):
        assert select_blind(self.DRAFTS, n=20, seed=0) == select_blind(self.DRAFTS, n=20, seed=0)


class TestPool:
    def test_union_of_retrievers_plus_random_records_deduplicated(self):
        hits = {"jaccard": ["a", "b", "c"], "clip": ["c", "d"], "combined": ["a", "e"]}
        pool, sources = build_pool(hits, random_ids=["x", "y"], seed=0)
        assert sorted(pool) == ["a", "b", "c", "d", "e", "x", "y"]
        assert sources["c"] == ["clip", "jaccard"]
        assert sources["x"] == ["random"]

    def test_the_pool_is_shuffled_so_rank_is_hidden(self):
        hits = {"jaccard": [f"r{i}" for i in range(12)]}
        pool, _ = build_pool(hits, random_ids=[], seed=0)
        assert pool != hits["jaccard"] and sorted(pool) == sorted(hits["jaccard"])

    def test_deterministic(self):
        hits = {"jaccard": ["a", "b", "c"], "clip": ["d"]}
        assert build_pool(hits, random_ids=["x"], seed=3) == build_pool(
            hits, random_ids=["x"], seed=3
        )
