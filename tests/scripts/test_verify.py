"""Tests for scripts/verify.py: the deterministic build-loop checks (docs/build-loop.md)."""

import verify

# Fake secrets are assembled at runtime so this file never contains a literal
# that the verifier itself would flag when the file is committed.
FAKE_SK = "sk-" + "a" * 24
FAKE_QUOTED = "api_key = " + '"' + "b" * 20 + '"'


class TestFrozenGolden:
    def test_modified_frozen_file_fails(self):
        assert verify.check_frozen(["M\tevals/golden/golden-v1.jsonl"])

    def test_deleted_frozen_file_fails(self):
        assert verify.check_frozen(["D\tevals/golden/golden-v1.jsonl"])

    def test_renamed_frozen_file_fails(self):
        assert verify.check_frozen(["R100\tevals/golden/golden-v1.jsonl\tevals/golden/old.jsonl"])

    def test_synthetic_version_is_frozen_too(self):
        assert verify.check_frozen(["M\tevals/golden/golden-v0-synthetic.jsonl"])

    def test_corpus_snapshots_are_frozen_too(self):
        # ADR-023: a golden set's scores only mean something against its snapshot.
        assert verify.check_frozen(["M	evals/golden/corpus/met-2588-d188937d8a53.tsv"])

    def test_adding_a_new_snapshot_passes(self):
        assert verify.check_frozen(["A	evals/golden/corpus/met-2600-abcdef123456.tsv"]) == []

    def test_adding_a_new_version_passes(self):
        assert verify.check_frozen(["A\tevals/golden/golden-v2.jsonl"]) == []

    def test_other_files_pass(self):
        assert verify.check_frozen(["M\tsrc/refdesk/__init__.py", "D\tevals/reports/old.md"]) == []


class TestEnvFile:
    def test_staged_env_fails(self):
        assert verify.check_env([".env"])

    def test_nested_env_fails(self):
        assert verify.check_env(["config/.env"])

    def test_env_example_passes(self):
        assert verify.check_env([".env.example"]) == []


class TestSecrets:
    def test_deepseek_style_key_fails(self):
        assert verify.check_secrets(["+DEEPSEEK_API_KEY=" + FAKE_SK])

    def test_quoted_assignment_fails(self):
        assert verify.check_secrets(["+" + FAKE_QUOTED])

    def test_empty_placeholder_passes(self):
        assert verify.check_secrets(["+DEEPSEEK_API_KEY=", "+GLM_API_KEY="]) == []

    def test_removed_lines_are_ignored(self):
        assert verify.check_secrets(["-" + FAKE_QUOTED]) == []

    def test_diff_header_is_ignored(self):
        assert verify.check_secrets(["+++ b/" + FAKE_SK + ".py"]) == []


class TestPytestExitCode:
    def test_no_tests_collected_is_not_a_failure(self):
        assert verify.pytest_passed(5)

    def test_success(self):
        assert verify.pytest_passed(0)

    def test_failures(self):
        assert not verify.pytest_passed(1)


class TestCiChecks:
    """--run-tests runs CI's check steps (#191): #158 passed pytest but failed ruff and tsc."""

    def ci_run_steps(self):
        import re
        from pathlib import Path

        ci = (Path(verify.ROOT) / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        return {m.strip() for m in re.findall(r"^\s*-? *run: (.+)$", ci, re.MULTILINE)}

    def test_every_ci_step_is_a_check_or_listed_as_not_run(self):
        # Adding a step to ci.yml forces a choice: run it locally, or say why not.
        local = {c.command for c in verify.CHECKS} | set(verify.NOT_RUN_LOCALLY)
        assert self.ci_run_steps() == local

    def test_ruff_and_ui_checks_are_included(self):
        commands = {c.command for c in verify.CHECKS}
        assert {"uv run ruff check .", "npm run typecheck", "npm test", "npm run build"} <= commands

    def run_with(self, codes, tmp_path, missing_tools=()):
        (tmp_path / "ui" / "node_modules").mkdir(parents=True)
        calls = []

        def run(argv, cwd):
            calls.append((argv, cwd))
            return codes.get(" ".join(argv), 0)

        def which(tool):
            return None if tool in missing_tools else tool

        errors = verify.run_checks(verify.CHECKS, run=run, which=which, root=tmp_path)
        return errors, calls

    def test_all_pass(self, tmp_path):
        errors, calls = self.run_with({}, tmp_path)
        assert errors == []
        assert len(calls) == len(verify.CHECKS)

    def test_a_failure_is_named_and_later_checks_still_run(self, tmp_path):
        errors, calls = self.run_with({"uv run ruff check .": 1}, tmp_path)
        assert errors == ["ruff check failed (uv run ruff check . exit code 1)"]
        assert len(calls) == len(verify.CHECKS)

    def test_pytest_no_tests_collected_still_passes(self, tmp_path):
        errors, _ = self.run_with({"uv run pytest -q": 5}, tmp_path)
        assert errors == []

    def test_exit_code_5_fails_other_checks(self, tmp_path):
        errors, _ = self.run_with({"npm run typecheck": 5}, tmp_path)
        assert errors == ["ui typecheck failed (npm run typecheck exit code 5)"]

    def test_ui_checks_run_in_ui(self, tmp_path):
        _, calls = self.run_with({}, tmp_path)
        cwds = {" ".join(argv): cwd for argv, cwd in calls}
        assert cwds["npm test"] == tmp_path / "ui"
        assert cwds["uv run ruff check ."] == tmp_path

    def test_missing_tool_fails_not_skips(self, tmp_path):
        errors, calls = self.run_with({}, tmp_path, missing_tools={"npm"})
        assert sum("npm not found" in e for e in errors) == 3
        assert all(argv[0] != "npm" for argv, _ in calls)

    def test_missing_node_modules_fails_with_a_hint(self, tmp_path):
        (tmp_path / "ui").mkdir()

        def run(argv, cwd):
            return 0

        errors = verify.run_checks(verify.CHECKS, run=run, which=lambda t: t, root=tmp_path)
        assert errors == ["ui/node_modules missing: run `npm ci` in ui/ (UI checks not run)"]
