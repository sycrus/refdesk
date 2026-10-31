"""Deterministic checks for the build loop and CI. Exit code 0 means pass.

Replaces scripts/verify.ps1 so the same checks run on Windows and in Linux CI.
What breaks without it: the build loop would rely only on a model judging its
own work, and a frozen golden file, a staged .env or a pasted key could be
committed without anything noticing.

Usage:
    uv run python scripts/verify.py                  # staged changes (local, after git add)
    uv run python scripts/verify.py --base origin/main   # a branch or PR against its base
    uv run python scripts/verify.py --run-tests      # also run CI's check steps (CHECKS)

--run-tests runs the same check steps as CI (ruff, pytest, UI typecheck, tests and
build), so the build loop sees a CI failure before it commits. What breaks without it:
on #158 the loop's draft passed pytest, then failed ruff and tsc in CI (PR #190).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Every frozen golden version, including golden-v0-synthetic, and every corpus snapshot a
# golden set is pinned to (ADR-023). New versions and snapshots may be added.
FROZEN_GOLDEN = re.compile(
    r"^evals/golden/(golden-v\d+(-[a-z0-9-]+)?\.jsonl|corpus/[a-z0-9+]+-\d+-[0-9a-f]{12}\.tsv)$"
)
ENV_FILE = re.compile(r"(^|/)\.env$")
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]
PYTEST_NO_TESTS_COLLECTED = 5
ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Check:
    name: str
    command: str  # exactly as written in .github/workflows/ci.yml
    cwd: str = "."
    ok_codes: tuple[int, ...] = (0,)


# CI's check steps, in CI's order. tests/scripts/test_verify.py fails if ci.yml gains a
# step that is neither here nor in NOT_RUN_LOCALLY.
CHECKS = [
    Check("ruff check", "uv run ruff check ."),
    # Exit code 5 means no tests were collected, which is not a failure for an empty scaffold.
    Check("pytest", "uv run pytest -q", ok_codes=(0, PYTEST_NO_TESTS_COLLECTED)),
    Check("ui typecheck", "npm run typecheck", cwd="ui"),
    Check("ui tests", "npm test", cwd="ui"),
    Check("ui build", "npm run build", cwd="ui"),
]

NOT_RUN_LOCALLY = {
    "uv sync --locked": "setup, not a check",
    "npm ci": "setup; a missing ui/node_modules is reported instead",
    "npx playwright install --with-deps chromium": "setup for the browser tests",
    "npm run test:e2e": "needs a browser and the live API; CI only",
    "uv run python scripts/verify.py --base origin/${{ github.base_ref }}": "this script",
}


def check_frozen(name_status: list[str]) -> list[str]:
    """Fail on any modification, deletion or rename of a frozen golden file."""
    errors = []
    for line in name_status:
        parts = line.split("\t")
        status, paths = parts[0], parts[1:]
        if status.startswith("A") or status.startswith("C"):
            continue
        # For a rename (R100<TAB>old<TAB>new) the original path is the frozen one.
        if paths and FROZEN_GOLDEN.match(paths[0]):
            errors.append(f"frozen golden file changed ({status}): {paths[0]}")
    return errors


def check_env(names: list[str]) -> list[str]:
    return [f".env file in the change: {n}" for n in names if ENV_FILE.search(n)]


def check_secrets(diff_lines: list[str]) -> list[str]:
    errors = []
    for line in diff_lines:
        if not line.startswith("+") or line.startswith("+++"):
            continue
        if any(p.search(line) for p in SECRET_PATTERNS):
            errors.append(f"possible secret in an added line: {line[:60]}...")
    return errors


def pytest_passed(exit_code: int) -> bool:
    return exit_code in (0, PYTEST_NO_TESTS_COLLECTED)


def _run(argv: list[str], cwd: Path) -> int:
    return subprocess.run(argv, cwd=cwd).returncode


def run_checks(checks, run=_run, which=shutil.which, root: Path = ROOT) -> list[str]:
    """Run every check, even after one fails, so one pass reports every failure.

    A missing tool or ui/node_modules is a failure with a hint, never a silent skip:
    a skipped check would let the loop commit work CI then rejects.
    """
    errors = []
    ui_ready = (root / "ui" / "node_modules").is_dir()
    if not ui_ready and any(c.cwd == "ui" for c in checks):
        errors.append("ui/node_modules missing: run `npm ci` in ui/ (UI checks not run)")
    for check in checks:
        if check.cwd == "ui" and not ui_ready:
            continue
        tool, *rest = check.command.split()
        exe = which(tool)  # resolves npm.cmd on Windows
        if exe is None:
            errors.append(f"{check.name}: {tool} not found on PATH (check not run)")
            continue
        code = run([exe, *rest], root / check.cwd)
        if code not in check.ok_codes:
            errors.append(f"{check.name} failed ({check.command} exit code {code})")
    return errors


def _git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", help="compare HEAD against this ref instead of the index")
    parser.add_argument("--run-tests", action="store_true", help="also run CI's check steps")
    args = parser.parse_args(argv)

    diff_range = [f"{args.base}...HEAD"] if args.base else ["--cached"]
    errors = []
    errors += check_frozen(_git("diff", "--name-status", "-M", *diff_range))
    errors += check_env(_git("diff", "--name-only", *diff_range))
    errors += check_secrets(_git("diff", "-U0", *diff_range))

    if args.run_tests:
        errors += run_checks(CHECKS)

    for e in errors:
        print(f"FAIL: {e}")
    if errors:
        return 1
    print("verify: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
