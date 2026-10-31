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
