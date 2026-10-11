"""Tests for scripts/next_issue.py: how the build loop picks its next GitHub issue."""

import next_issue


def issue(number, label, milestone="M1 Ingest and baselines", blocked_by=()):
    body = "## What to build\nx\n\n## Acceptance criteria\n- [ ] y"
    if blocked_by:
        body += "\n\n## Blocked by\n" + "\n".join(f"- #{n}" for n in blocked_by)
    return {
        "number": number,
        "title": f"issue {number}",
        "body": body,
        "labels": [{"name": label}],
        "milestone": {"title": milestone} if milestone else None,
    }


class TestParseBlockers:
    def test_reads_the_blocked_by_section(self):
        assert next_issue.parse_blockers(issue(9, "x", blocked_by=[3, 7])["body"]) == [3, 7]

    def test_no_section_means_no_blockers(self):
        assert next_issue.parse_blockers(issue(9, "x")["body"]) == []

    def test_ignores_issue_refs_outside_the_section(self):
        body = "## What to build\nSee #4.\n\n## Blocked by\n- #5\n\n## Notes\nAlso #6."
        assert next_issue.parse_blockers(body) == [5]


class TestPickNext:
    def test_first_unblocked_agent_issue_by_milestone_then_number(self):
        issues = [
            issue(8, "ready-for-agent", "M1 Ingest and baselines"),
            issue(2, "ready-for-agent", "M0 Scope and sources"),
            issue(6, "ready-for-agent", "M1 Ingest and baselines"),
        ]
        assert next_issue.pick_next(issues, skip=set())[0]["number"] == 2

    def test_skips_issues_with_an_open_blocker(self):
        issues = [issue(7, "ready-for-agent", blocked_by=[6]), issue(6, "needs-triage")]
        picked, reason = next_issue.pick_next(issues, skip=set())
        assert picked is None and reason == "empty"

    def test_closed_blocker_does_not_block(self):
        # Blocker #1 is not in the open list, so it is closed.
        picked, _ = next_issue.pick_next([issue(6, "ready-for-agent", blocked_by=[1])], skip=set())
        assert picked["number"] == 6

    def test_ignores_non_agent_labels(self):
        issues = [issue(3, "ready-for-human"), issue(4, "needs-triage")]
        assert next_issue.pick_next(issues, skip=set()) == (None, "empty")

    def test_skip_list_excludes_issues_done_this_run(self):
        issues = [issue(2, "ready-for-agent"), issue(6, "ready-for-agent")]
        assert next_issue.pick_next(issues, skip={2})[0]["number"] == 6

    def test_needs_human_when_agent_work_waits_on_a_human_issue(self):
        issues = [issue(12, "ready-for-human"), issue(13, "ready-for-agent", blocked_by=[12])]
        assert next_issue.pick_next(issues, skip=set()) == (None, "needs-human")

    def test_issues_without_milestone_come_last(self):
        issues = [issue(30, "ready-for-agent", milestone=None), issue(31, "ready-for-agent")]
        assert next_issue.pick_next(issues, skip=set())[0]["number"] == 31
