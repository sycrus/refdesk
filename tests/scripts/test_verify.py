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
