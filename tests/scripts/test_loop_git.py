"""Tests for scripts/loop_git.py: what the build loop may commit (issue #182)."""

import loop_git
import pytest

CLEAN = []


class TestStartClean:
    def test_a_clean_tree_may_start(self):
        assert loop_git.start_errors(CLEAN) == []

    @pytest.mark.parametrize(
        "line", [" M src/refdesk/boards.py", "?? evals/reports/x.md", "A  docs/new.md"]
    )
    def test_any_change_or_untracked_file_refuses(self, line):
        # Without a clean start, the runner cannot tell the agent's work from leftovers.
        assert loop_git.start_errors([line])


class TestPathsToStage:
    def test_reads_modified_added_and_untracked_paths(self):
        lines = [" M src/a.py", "?? tests/test_a.py", "A  docs/b.md"]
        assert loop_git.paths_to_stage(lines) == ["docs/b.md", "src/a.py", "tests/test_a.py"]

    def test_a_rename_stages_both_sides(self):
        assert loop_git.paths_to_stage(["R  old.py -> new.py"]) == ["new.py", "old.py"]

    def test_deleted_files_are_staged_as_deletions(self):
        assert loop_git.paths_to_stage([" D src/gone.py"]) == ["src/gone.py"]

    def test_quoted_paths_are_unquoted(self):
        assert loop_git.paths_to_stage(['?? "docs/a b.md"']) == ["docs/a b.md"]


class TestCommitErrors:
    @pytest.mark.parametrize(
        "path", ["data/refdesk.sqlite", "data/images/met/1.jpg", "runs/abc/manifest.json"]
    )
    def test_derived_paths_are_refused(self, path):
        assert loop_git.commit_errors([path])

    def test_ordinary_paths_pass(self):
        assert loop_git.commit_errors(["src/refdesk/boards.py", "docs/runs-explained.md"]) == []


class TestNothingToStage:
    """#204: an agent that only commented (needs-info) leaves no change. The runner must stop
    before it commits or pushes, not push an empty branch."""

    def test_stage_with_no_changes_exits_3(self, monkeypatch, capsys):
        monkeypatch.setattr(loop_git, "_porcelain", lambda: [])
        assert loop_git.main(["stage"]) == loop_git.EXIT_NO_CHANGES == 3
        assert "nothing to stage" in capsys.readouterr().err

    def test_refused_paths_still_exit_1(self, monkeypatch):
        monkeypatch.setattr(loop_git, "_porcelain", lambda: ["?? data/x.jpg"])
        assert loop_git.main(["stage"]) == 1


class TestRunnerQuoting:
    """#204: Windows PowerShell 5.1 strips `"` inside arguments passed to native programs, so
    `--jq '... join(",")'` reached jq as `join(,)` and the needs-info stop never fired."""

    def test_no_single_quoted_native_argument_contains_a_double_quote(self):
        import re
        from pathlib import Path

        runner = Path(__file__).resolve().parents[2] / "scripts" / "run-loop.ps1"
        native = re.compile(r"^\s*(?:\$\w+\s*=\s*)?(gh|git|uv|claude|npm)\b(.*)$")
        offenders = []
        for number, line in enumerate(runner.read_text(encoding="utf-8").splitlines(), 1):
            match = native.match(line)
            if match and any('"' in arg for arg in re.findall(r"'([^']*)'", match.group(2))):
                offenders.append(f"run-loop.ps1:{number}: {line.strip()}")
        assert offenders == []
