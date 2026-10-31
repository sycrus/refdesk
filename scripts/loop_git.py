"""What the build loop may commit (docs/build-loop.md, issue #182).

The runner used to stage with `git add -A`, which CLAUDE.md forbids: on its first M4 run
it swept leftover eval reports and an unrelated trust report into the agent's commit. Now:

- `start`: the runner refuses to begin unless the tree is clean, so everything changed
  after the agent runs is the agent's own work.
- `stage`: stages exactly those paths, by name, and refuses any path under `data/` or
  `runs/` (derived and gitignored; cached images were once committed by mistake).

Why this is separate from run-loop.ps1: like the picker, the rules are the part most
likely to be wrong, so they live in plain, tested Python. The PowerShell runner only calls it.

Exit codes: 0 ok, 1 refused (reasons on stderr).

Usage: uv run python scripts/loop_git.py start | stage
"""

from __future__ import annotations

import argparse
import subprocess
import sys

DERIVED = ("data/", "runs/")


def _unquote(path: str) -> str:
    return path[1:-1] if len(path) > 1 and path[0] == path[-1] == '"' else path


def start_errors(porcelain: list[str]) -> list[str]:
    return [f"working tree not clean: {line}" for line in porcelain]


def paths_to_stage(porcelain: list[str]) -> list[str]:
    """Every path in `git status --porcelain` output; both sides of a rename."""
    paths = set()
    for line in porcelain:
        rest = line[3:]
        for part in rest.split(" -> ") if line[0] in "RC" else [rest]:
            paths.add(_unquote(part))
    return sorted(paths)


def commit_errors(paths: list[str]) -> list[str]:
    return [f"derived path must never be committed: {p}" for p in paths if p.startswith(DERIVED)]


def _porcelain() -> list[str]:
    out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return [line for line in out.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["start", "stage"])
    args = parser.parse_args(argv)

    porcelain = _porcelain()
    if args.action == "start":
        errors = start_errors(porcelain)
    else:
        paths = paths_to_stage(porcelain)
        errors = commit_errors(paths)
        if not errors and paths:
            subprocess.run(["git", "add", "--", *paths], check=True)
            print("\n".join(paths))
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
