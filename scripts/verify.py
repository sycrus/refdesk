"""Deterministic checks for the build loop and CI. Exit code 0 means pass.

Replaces scripts/verify.ps1 so the same checks run on Windows and in Linux CI.
What breaks without it: the build loop would rely only on a model judging its
own work, and a frozen golden file, a staged .env or a pasted key could be
committed without anything noticing.

Usage:
    uv run python scripts/verify.py                  # staged changes (local, after git add)
    uv run python scripts/verify.py --base origin/main   # a branch or PR against its base
    uv run python scripts/verify.py --run-tests      # also run pytest
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

# Every frozen golden version, including golden-v0-synthetic. New versions may be added.
FROZEN_GOLDEN = re.compile(r"^evals/golden/golden-v\d+(-[a-z0-9-]+)?\.jsonl$")
ENV_FILE = re.compile(r"(^|/)\.env$")
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]
PYTEST_NO_TESTS_COLLECTED = 5


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
    # Exit code 5 means no tests were collected, which is not a failure for an empty scaffold.
    return exit_code in (0, PYTEST_NO_TESTS_COLLECTED)


def _git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", help="compare HEAD against this ref instead of the index")
    parser.add_argument("--run-tests", action="store_true", help="also run pytest")
    args = parser.parse_args(argv)

    diff_range = [f"{args.base}...HEAD"] if args.base else ["--cached"]
    errors = []
    errors += check_frozen(_git("diff", "--name-status", "-M", *diff_range))
    errors += check_env(_git("diff", "--name-only", *diff_range))
    errors += check_secrets(_git("diff", "-U0", *diff_range))

    if args.run_tests:
        code = subprocess.run([sys.executable, "-m", "pytest", "-q"]).returncode
        if not pytest_passed(code):
            errors.append(f"tests failed (pytest exit code {code})")

    for e in errors:
        print(f"FAIL: {e}")
    if errors:
        return 1
    print("verify: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
