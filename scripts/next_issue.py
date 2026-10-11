"""Pick the next GitHub issue for the build loop (docs/build-loop.md).

Rules (docs/agents/issue-tracker.md): only open `ready-for-agent` issues, skipping any
whose `## Blocked by` section lists an issue that is still open; ordered by milestone
(M0 before M1), then issue number. Issues without a milestone come last.

Why this is separate from run-loop.ps1: the selection rules are the part most likely
to be wrong, so they live in plain, tested Python. The PowerShell runner only calls it.

Exit codes: 0 picked (JSON on stdout), 10 queue empty, 3 agent work is waiting on a
`ready-for-human` issue.

Usage: uv run python scripts/next_issue.py [--skip 2,6]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

REPO = "sycrus/refdesk"
AGENT = "ready-for-agent"
HUMAN = "ready-for-human"
EXIT_PICKED, EXIT_NEEDS_HUMAN, EXIT_EMPTY = 0, 3, 10

_SECTION = re.compile(r"^##\s+Blocked by\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
_REF = re.compile(r"#(\d+)")


def parse_blockers(body: str) -> list[int]:
    match = _SECTION.search(body or "")
    return [int(n) for n in _REF.findall(match.group(1))] if match else []


def _labels(issue: dict) -> set[str]:
    return {label["name"] for label in issue.get("labels", [])}


def _order(issue: dict) -> tuple:
    milestone = (issue.get("milestone") or {}).get("title")
    # "M0 ...", "M1 ..." sort naturally; no milestone sorts after every milestone.
    return (milestone is None, milestone or "", issue["number"])


def pick_next(open_issues: list[dict], skip: set[int]) -> tuple[dict | None, str]:
    """Return (issue, "picked") or (None, "needs-human" | "empty")."""
    open_numbers = {i["number"] for i in open_issues}
    human = {i["number"] for i in open_issues if HUMAN in _labels(i)}
    candidates = [i for i in open_issues if AGENT in _labels(i) and i["number"] not in skip]
    waiting_on_human = False
    for candidate in sorted(candidates, key=_order):
        open_blockers = [b for b in parse_blockers(candidate["body"]) if b in open_numbers]
        if not open_blockers:
            return candidate, "picked"
        if any(b in human for b in open_blockers):
            waiting_on_human = True
    return None, "needs-human" if waiting_on_human else "empty"


def _open_issues() -> list[dict]:
    out = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "-R",
            REPO,
            "--state",
            "open",
            "--limit",
            "500",
            "--json",
            "number,title,body,labels,milestone",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip", default="", help="comma-separated issue numbers to skip")
    args = parser.parse_args(argv)
    skip = {int(n) for n in args.skip.split(",") if n.strip()}

    picked, reason = pick_next(_open_issues(), skip)
    if picked is None:
        print(reason, file=sys.stderr)
        return EXIT_NEEDS_HUMAN if reason == "needs-human" else EXIT_EMPTY
    print(json.dumps({"number": picked["number"], "title": picked["title"]}))
    return EXIT_PICKED


if __name__ == "__main__":
    sys.exit(main())
