"""Trajectory evals: pass^k and the step failure taxonomy (issue #173; PRD 11.7).

The committed suite (tests/fixtures/trajectory/trajectory-v0-synthetic) holds k=3 recorded
runs per brief. Every test replays them through the current loop: no model, no network.

`TestPlantedBadChanges` is the regression suite PRD 11.7 asks for: each test makes a
deliberately bad change (the verifier ignores the judge, the stuck rule is switched off,
the board counts unverified items) and asserts the gate fails. The gate itself,
`test_the_current_code_passes_the_gate`, is what fails CI when such a change is real.
"""

from pathlib import Path

import pytest

import refdesk.loop
from refdesk.evals import trajectory as tj
from refdesk.loop import LoopResult
from refdesk.runlog import ReplayDiverged
from refdesk.wording import AttributionStatus, StopReason

ROOT = Path(__file__).resolve().parents[2]
SUITE_DIR = ROOT / "tests" / "fixtures" / "trajectory" / "trajectory-v0-synthetic"


@pytest.fixture(scope="module")
def suite():
    return tj.load_suite(SUITE_DIR)


def outcome_of(result, case_id, run):
    return next(r for r in result.runs if r.case_id == case_id and r.run == run)


class TestTheSuite:
    def test_is_synthetic_with_k_recorded_runs_per_brief(self, suite):
        assert suite.provenance == "synthetic" and suite.k == 3
        for case in suite.cases:
            assert len(case.runs) == 3
            for run in case.runs:
                assert suite.recording(case, run).exists()

    def test_records_say_synthetic_so_nobody_mistakes_them_for_museum_data(self, suite):
        for case in suite.cases:
            for record in case.pool:
                assert record.artist.startswith("Synthetic") and "Synthetic" in record.title

    def test_recordings_never_hold_a_brief(self, suite):
        for case in suite.cases:
            for run in case.runs:
                text = suite.recording(case, run).read_text(encoding="utf-8").casefold()
                assert case.brief.casefold() not in text

    def test_a_planted_wrong_rationale_really_reaches_the_judge(self, suite):
        # t02 run 2: met:900012's artist sentence is wrong but its value is right, so only
        # the judge can catch it; the loop needs a second round to reach K.
        case = next(c for c in suite.cases if c.id == "t02-recovers-from-a-wrong-rationale")
        assert case.runs[1].planted_bad == {"met:900012"}

        def round_1_judge_calls(run):
            events = tj.read_events(suite.recording(case, run))
            return sum(1 for e in events if e.round == 1 and e.tool == "llm:mock-judge")

        # Both round-1 items were judged, as in the clean run: code checks passed the fault.
        assert round_1_judge_calls(case.runs[1]) == round_1_judge_calls(case.runs[0]) > 0
        result = tj.run_trajectory_eval(suite)
        assert outcome_of(result, case.id, 2).rounds == 2


class TestPassK:
    def test_the_current_code_passes_the_gate(self, suite):
        """The CI gate: every replayed run gives the outcome the suite expects."""
        tj.check_gate(tj.run_trajectory_eval(suite))

    def test_pass_k_is_reported_next_to_single_run_success(self, suite):
        result = tj.run_trajectory_eval(suite)
        # 5 briefs: three succeed on all 3 runs, two succeed on 2 of 3.
        assert result.pass_k() == [1.0, 1.0, 0.0, 0.0, 1.0]
        assert result.single_run() == pytest.approx([1.0, 1.0, 2 / 3, 2 / 3, 1.0])
        assert sum(result.pass_k()) / 5 < sum(result.single_run()) / 5

    def test_failed_runs_are_classified_by_step(self, suite):
        result = tj.run_trajectory_eval(suite)
        assert result.taxonomy() == {"rationale_error": 1, "wrong_retrieval": 1}
        assert outcome_of(result, "t03-unusable-rationales", 2).stop == "no_progress"
        assert outcome_of(result, "t04-restricted-candidate", 2).outcome == "wrong_retrieval"

    def test_replay_is_deterministic(self, suite):
        a, b = tj.run_trajectory_eval(suite), tj.run_trajectory_eval(suite)
        assert [(r.outcome, r.detail) for r in a.runs] == [(r.outcome, r.detail) for r in b.runs]
        assert a.config_hash() == b.config_hash()


class TestPlantedBadChanges:
    """Each deliberately bad change must fail the gate (PRD 11.7)."""

    def test_a_verifier_that_ignores_the_judge_fails(self, suite, monkeypatch):
        def code_only(code, judged):
            ok = code is not None and code.passed
            return AttributionStatus.VERIFIED if ok else AttributionStatus.NEEDS_HUMAN_CHECK

        monkeypatch.setattr(refdesk.loop, "item_status", code_only)
        result = tj.run_trajectory_eval(suite)
        with pytest.raises(tj.TrajectoryRegression, match="verification_miss"):
            tj.check_gate(result)
        bad = outcome_of(result, "t02-recovers-from-a-wrong-rationale", 2)
        assert bad.outcome == "verification_miss" and "met:900012" in bad.detail

    def test_a_loop_without_the_stuck_rule_fails(self, suite):
        result = tj.run_trajectory_eval(suite, loop_overrides={"stuck_rounds": 99})
        with pytest.raises(tj.TrajectoryRegression, match="bad_stop"):
            tj.check_gate(result)
        assert outcome_of(result, "t03-unusable-rationales", 2).outcome == "bad_stop"

    def test_a_board_that_counts_unverified_items_fails(self, suite, monkeypatch):
        monkeypatch.setattr(LoopResult, "accepted", property(lambda self: len(self.items)))
        with pytest.raises(tj.TrajectoryRegression):
            tj.check_gate(tj.run_trajectory_eval(suite))

    def test_a_changed_prompt_is_reported_as_diverged(self, suite):
        changed = tj.Suite(**{**suite.__dict__, "prompts": {**suite.prompts, "fit": "fit-v2"}})
        result = tj.run_trajectory_eval(changed)
        assert result.taxonomy()["diverged"] > 0
        with pytest.raises(tj.TrajectoryRegression, match="diverged"):
            tj.check_gate(result)


class TestClassify:
    """The order of the checks, on hand-built results."""

    @pytest.fixture
    def case(self, suite):
        return next(c for c in suite.cases if c.id == "t02-recovers-from-a-wrong-rationale")

    def test_a_call_past_the_recording_is_a_bad_stop(self, case):
        error = tj.WentPastRecording("x")
        assert tj.classify(case, case.runs[0], None, error=error)[0] == "bad_stop"

    def test_a_changed_call_is_diverged(self, case):
        error = ReplayDiverged("step 4 differs")
        assert tj.classify(case, case.runs[0], None, error=error)[0] == "diverged"

    def test_a_wrong_tier_is_a_bad_decision(self, case):
        result = LoopResult(tiers=["cloud-flash"], stop=None)
        assert tj.classify(case, case.runs[0], result)[0] == "bad_decision"

    def test_a_keep_local_brief_sent_to_the_cloud_is_a_bad_decision(self, suite):
        case = next(c for c in suite.cases if c.keep_local)
        result = LoopResult(tiers=["mock"], sent_to=["mock", "cloudy"])
        got = tj.classify(case, case.runs[0], result, cloud_providers=frozenset({"cloudy"}))
        assert got[0] == "bad_decision"

    def test_the_wrong_stop_reason_is_a_bad_stop(self, case):
        result = LoopResult(tiers=["mock"], stop=StopReason.STEP_CAP)
        assert tj.classify(case, case.runs[0], result)[0] == "bad_stop"

    def test_recorded_calls_left_over_are_a_bad_stop(self, case):
        result = LoopResult(tiers=["mock"])
        assert tj.classify(case, case.runs[0], result, left_over=3)[0] == "bad_stop"

    def test_a_correct_stop_short_of_k_is_a_rationale_error(self, case):
        result = LoopResult(tiers=["mock"])
        assert tj.classify(case, case.runs[0], result)[0] == "rationale_error"


class TestReport:
    def test_the_report_gives_pass_k_single_run_and_every_category(self, suite):
        text = tj.report(tj.run_trajectory_eval(suite), date="2026-10-31", dirty=False)
        assert "pass^3" in text and "Single-run success" in text
        for category in tj.CATEGORIES:
            assert f"| {category} |" in text
        assert "synthetic" in text and "Plumbing only" in text and "Gate: **PASS**" in text

    def test_a_report_is_never_overwritten(self, suite, tmp_path):
        result = tj.run_trajectory_eval(suite)
        path = tj.write_report(result, root=tmp_path, date="2026-10-31", dirty=False)
        assert path.name == f"trajectory-eval-2026-10-31-{result.config_hash()}.md"
        with pytest.raises(FileExistsError):
            tj.write_report(result, root=tmp_path, date="2026-10-31", dirty=False)

    def test_the_hash_changes_with_the_code_and_the_overrides(self, suite):
        a = tj.run_trajectory_eval(suite, git_sha="a")
        assert a.config_hash() != tj.run_trajectory_eval(suite, git_sha="b").config_hash()
        b = tj.run_trajectory_eval(suite, git_sha="a", loop_overrides={"stuck_rounds": 3})
        assert a.config_hash() != b.config_hash()
